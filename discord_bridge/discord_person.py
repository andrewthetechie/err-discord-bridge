import logging
import re
from functools import cached_property
import discord


from errbot.backends.base import Person

log = logging.getLogger(__name__)

# Discord uses 18 or more digits for user, channel and server (guild) ids.
RE_DISCORD_ID = re.compile(r"^[0-9]{18}")


class DiscordPerson(Person):
    """Converts a discord.py user.User into a Person that Errbot understands"""

    def __init__(self, discord_user: discord.user.User, client: discord.Client) -> None:
        self.discord_user = discord_user
        self._user_id = discord_user.id
        self._client = client

    def __eq__(self, other):
        return isinstance(other, DiscordPerson) and other.aclattr == self.aclattr

    def __str__(self):
        return f"{self.fullname}"

    def __hash__(self):
        return hash(f"{self._user_id}-{self.fullname}")

    @cached_property
    def created_at(self):
        return discord.utils.snowflake_time(self.id)

    @property
    def client(self):
        return self._client

    @property
    def nick(self) -> str:
        return self.aclattr

    @property
    def person(self) -> str:
        return self.aclattr

    @property
    def email(self) -> str:
        return "Unavailable"

    @property
    def id(self) -> str:
        return self._user_id

    @property
    def username(self) -> str:
        return self.discord_user.name

    @property
    def discriminator(self) -> str:
        return self.discord_user.discriminator

    @property
    def is_bot_user(self) -> bool:
        return self.discord_user.both

    @property
    def fullname(self) -> str:
        return f"{self.username}#{self.discriminator}"

    @property
    def aclattr(self) -> str:
        return self._user_id

    async def send(
        self,
        content: str = None,
        tts: bool = False,
        embed: discord.Embed = None,
        file: discord.File = None,
        files: list[discord.File] = None,
        delete_after: float = None,
        nonce: int = None,
        allowed_mentions: discord.AllowedMentions = None,
        reference: discord.Message | discord.MessageReference = None,
        mention_author: bool | None = None,
    ):
        await self.discord_user.send(
            content=content,
            tts=tts,
            embed=embed,
            file=file,
            files=files,
            delete_after=delete_after,
            nonce=nonce,
            allowed_mentions=allowed_mentions,
            reference=reference,
            mention_author=mention_author,
        )
