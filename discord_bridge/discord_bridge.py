from errbot import BotPlugin
import discord
import os

import asyncio
import logging

def find_reverse_discord_destinations(bridge_config: dict, dest: int) -> list[dict]:
    dict(filter(lambda item: item[1]['dest'] == dest, bridge_config.items()))


class DiscordBridge(BotPlugin):
    def __init__(self, bot, name: str | None = None):
        super().__init__(bot=bot, name=name)
        intents = discord.Intents(messages=True, guilds=True)
        intents.message_content = True
        self._client = discord.Client(intents=intents)
        setattr(self._client, "on_message", self.discord_message_callback)
        self._bot_token = os.environ.get("BOT_TOKEN")
        # keys are errbot identifiers (message sources), values are dictionary config values
        self._errbot_bridge_config = {
            self.build_identifier("@KG5JNC-10"):
                {
                    "dest": 1220921511364264029,
                    "mode": "bi-directional",
                    "template": "{frm}: {body}",
                }
        }
        # keys are discord channel or message ids
        self._discord_bridge_config = {
            1220921511364264029:
                {
                    "dest": self.build_identifier("@KG5JNC-10"),
                    "mode": "bi-directional",
                    "template": "{author_name}: {content}"
                }
        }

        self._discord_send_queue = asyncio.Queue()

    def activate(self):
        super().activate()
        self.start_poller(1, self.start_discord_listener, times=1)

    def start_discord_listener(self):
        self._client.run(self._bot_token, log_level=logging.INFO)

    def send_discord_message(self, destination_id: int, message: str):
        self.log.debug("send_discord_message, calling asyncio.run_coroutine_threadsafe")
        return asyncio.run_coroutine_threadsafe(self.__async_send_discord_message(destination_id, message), self._client.loop)

    async def __async_send_discord_message(self, destination_id: int, message: str):
        self.log.debug("__async_send_discord_message, calling asyncio.run_coroutine_threadsafe")
        channel = await self.get_discord_channel(destination_id)
        return await channel.send(message)

    async def discord_message_callback(self, message):
        self.log.debug("Got message from discord %s", message)
        if message.author == self._client.user:
            self.log.debug("Discord message from the bot, nothing to do")
            return
        bridge_config = self._discord_bridge_config.get(message.channel.id, None)
        if bridge_config is None:
            self.log.debug("No configs found for %s", message.channel.id)
            return

        match bridge_config["mode"]:
            case "bi-directional":
                message_template = bridge_config.get("template", "{content}")
                self.log.debug(message)
                self.log.debug(message.content)
                message_text = message_template.format(content=message.content, author_name=message.author.name)
                self.send(bridge_config["dest"], message_text)
            case _:
                self.log.error("Unimplemented mode in config %s - %s", bridge_config["dest"], bridge_config)

    async def discord_on_ready_callback(self) -> None:
        self.log.debug("Logged in as %s", self._client.user)

    async def get_discord_channel(self, channel_id: int):
        return self._client.get_channel(channel_id)

    def callback_message(self, message):
        self.log.debug("Got message from backend %s", message)
        if message.body == "":
            self.log.debug("Empty message, ignoring")
            return

        this_bridge_config = self._errbot_bridge_config.get(message.frm, {})
        self.log.debug("Bridge config %s", this_bridge_config)
        if "dest" in this_bridge_config:
            match this_bridge_config.get('mode', 'bi-directional'):
                case 'bi-directional':
                    self.log.debug("Sending message to discord: %s", message)
                    message_template = this_bridge_config.get('template', '{body}')
                    message_text = message_template.format(frm=message.frm, body=message.body, to=message.to)
                    self.send_discord_message(this_bridge_config['dest'], message_text)
                case _:
                    self.log.error("Unsupported mode for %s - %s", message.frm, this_bridge_config)
