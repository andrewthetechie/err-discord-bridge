from errbot.backends.base import Room

from functools import cached_property
import discord


class DiscordRoom(Room):
    def __init__(self, discord_channel: discord.channel.TextChannel):
        self.discord_channel = discord_channel

    def __str__(self):
        return f"<#{self.id}>"

    def __eq__(self, other: "DiscordRoom"):
        if not isinstance(other, DiscordRoom):
            return False

        return None not in [other.id, self.id] and other.id == self.id

    def __hash__(self):
        return hash(str(self))

    @cached_property
    def created_at(self):
        return discord.utils.snowflake_time(self.id)

    @property
    def topic(self) -> str:
        return "" if self.discord_channel.topic is None else self.discord_channel.topic

    @property
    def guild(self) -> int:
        return self.discord_channel.guild.id

    @property
    def name(self) -> str:
        return self.discord_channel.name

    @property
    def id(self):
        return self.discord_channel.id
