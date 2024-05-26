from errbot import BotPlugin
import discord
from pathlib import Path
from pydantic import ValidationError

from discord_bridge.schemas import BridgeConfig, MessageDestination
from discord_bridge.discord_person import DiscordPerson
from discord_bridge.discord_room import DiscordRoom
from errbot.backends.base import Message

import asyncio
import logging

import yaml


def find_reverse_discord_destinations(bridge_config: dict, dest: int) -> list[dict]:
    dict(filter(lambda item: item[1]["dest"] == dest, bridge_config.items()))


class DiscordBridge(BotPlugin):
    def __init__(self, bot, name: str | None = None):
        super().__init__(bot=bot, name=name)
        intents = discord.Intents(messages=True, guilds=True)
        intents.message_content = True
        self._client = discord.Client(intents=intents)
        setattr(self._client, "on_message", self.discord_message_callback)
        self._bot_token: str | None = None
        self._bridge_config_file: str | Path | None = None
        self.bridge_config: BridgeConfig | None = None
        self._discord_send_queue = asyncio.Queue()

    def activate(self):
        """Discord Bridge checks its configuration in activate
        It will log errors and deactivate if it does not have valid
        config.

        """
        super().activate()
        self._bot_token = getattr(self._bot.bot_config, "DISCORD_BOT_TOKEN", None)
        if self._bot_token is None:
            self.log.error("No DISCORD_BOT_TOKEN set in bot config, DiscordBridge cannot activate")
            self.deactivate()
            return
        self._bridge_config_file = getattr(self._bot.bot_config, "DISCORD_BRIDGE_CONFIG_FILE", None)
        if self._bridge_config_file is None:
            self._bridge_config_file = Path(self._bot.bot_config.BOT_DATA_DIR) / Path("../discord_bridge_config.yaml")

        # load the bridge config yaml file from disk
        try:
            with open(self._bridge_config_file) as fh:
                data = yaml.safe_load(fh)
        except FileNotFoundError:
            self.log.error("The bridge config file does not exist at %s", self._bridge_config_file)
            self.is_activated = False
            self.deactivate()
            return
        except yaml.YAMLError as exc:
            self.log.error("Yaml error while loading bridge config %s", str(exc))
            self.deactivate()
            return

        # validate the config with Pydantic
        try:
            self.bridge_config = BridgeConfig.model_validate(data)
        except ValidationError as exc:
            self.log.error("Bridge Config is invalid, Discord Bridge cannot start. Error: %s", str(exc))
            self.deactivate()
            return

        # if we've made it this far, the plugin is activated and we can start the discord listener
        self.log.debug("Starting discord listener poller")
        self.start_poller(1, self.start_discord_listener, times=1)

    def start_discord_listener(self):
        """Calls client.run on the discord.py client.
        Called via a Poller to not block the main plugin thread
        """
        self._client.run(self._bot_token, log_level=logging.INFO)

    def send_discord_message(self, destination_id: int, message: str):
        """Sends a message to discord"""
        self.log.debug("send_discord_message, calling asyncio.run_coroutine_threadsafe")
        return asyncio.run_coroutine_threadsafe(
            self.__async_send_discord_message(destination_id, message), self._client.loop
        )

    async def __async_send_discord_message(self, destination_id: str, message: str):
        self.log.debug("__async_send_discord_message: %s - %s", destination_id, message)
        channel = await self.get_discord_channel(destination_id)
        self.log.debug("Channel %s", channel)
        return await channel.send(message)

    def is_message_a_reply(self, message: discord.Message) -> bool:
        return False

    async def discord_on_ready_callback(self) -> None:
        """Callback when discord logs in"""
        self.log.debug("Logged in as %s", self._client.user)

    async def get_discord_channel(self, channel_id: int):
        """Get a discord channel from its ID"""
        return await self._client.fetch_channel(channel_id)

    async def discord_message_callback(self, message):
        """Callback run on every discord message"""
        self.log.debug("Got message from discord %s - %s", message, message.content)
        if self.bridge_config.config.ignore_messages_from_self and message.author == self._client.user:
            self.log.debug("Discord message from the bot, discarding")
            return

        err_msg_obj = Message(message.content, extras=message.embeds)
        if isinstance(message.channel, discord.abc.PrivateChannel):
            err_msg_obj.frm = DiscordPerson(discord_user=message.author, client=self._client)
            err_msg_obj.to = self.bot_identifier
            routing_key = f"discord-{err_msg_obj.frm.person}"
        else:
            err_msg_obj.to = DiscordRoom(message.channel)
            err_msg_obj.frm = DiscordPerson(discord_user=message.author, client=self._client)
            routing_key = f"discord-{err_msg_obj.to.id}"
        self.log.debug(err_msg_obj)
        self.log.debug(routing_key)
        if (destination := self.bridge_config.destinations.get(routing_key, None)) is None:
            self.log.debug("No destination for %s for message %s", routing_key, message.content)
            return
        self.log.debug(destination)
        match destination.config_type:
            case BridgeConfig.ConfigType.one_way:
                self.log.debug("OneWay Bridge found")
                self.one_way_bridge(err_msg_obj, destination)
            case BridgeConfig.ConfigType.two_way:
                self.log.debug("TwoWay Bridge found")
                # a two way bridge is just two one way bridges, so use the same method
                self.one_way_bridge(err_msg_obj, destination)
            case BridgeConfig.ConfigType.reply:
                self.log.debug("Reply Bridge found")

    def callback_message(self, message):
        """Callback on every errbot message"""
        self.log.debug("Got message from backend %s", message)
        if message.body == "":
            self.log.debug("Empty message, ignoring")
            return

        self.log.debug("trying to find bridge config for %s in %s", message, self.bridge_config.destinations.keys())
        try:
            direct_message = message.is_direct
        except KeyError:
            self.log.error("Backend message %s doesn't support is_direct, assuming no direct messaging")
            direct_message = False

        if direct_message:
            routing_key = f"err-{message.frm.person}"
        else:
            routing_key = f"err-{message.to.aclattr}"

        self.log.debug("Routing key %s", routing_key)
        destination = self.bridge_config.destinations.get(routing_key, None)
        self.log.debug("Destination %s", destination)
        if destination is None:
            self.log.debug("No Destination for this message")
            return

        match destination.config_type:
            case BridgeConfig.ConfigType.one_way:
                self.log.debug("OneWay Bridge found")
                self.one_way_bridge(message, destination)
            case BridgeConfig.ConfigType.two_way:
                self.log.debug("TwoWay Bridge found")
                # a two way bridge is just two one way bridges, so use the same method
                self.one_way_bridge(message, destination)
            case BridgeConfig.ConfigType.reply:
                self.log.debug("Reply Bridge found")

    def one_way_bridge(self, message: Message, destination: BridgeConfig.Destination) -> None:
        if isinstance(message.frm, DiscordPerson):
            sender = message.frm.username
        else:
            sender = message.frm.aclattr
        message_content = destination.destination.msg_template.format(sender=sender, message=message.body)
        self.log.debug("Sending %s to %s", message_content, destination.destination.identifier)
        match destination.destination.dest:
            case MessageDestination.err:
                self.send(self.build_identifier(destination.destination.identifier), message_content)
            case MessageDestination.discord:
                self.send_discord_message(destination_id=destination.destination.identifier, message=message_content)
            case _:
                self.log.error("Invalid message destination for %s message %s dest", message, destination)
