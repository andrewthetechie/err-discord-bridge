from pydantic import BaseModel, model_validator
from pydantic import ConfigDict, Field, AliasPath
from enum import Enum
from functools import cached_property
from pydantic import dataclasses


class MessageSource(str, Enum):
    err = "err"
    discord = "discord"


class MessageDestination(str, Enum):
    err = "err"
    discord = "discord"


class SrcDestAbstract(BaseModel):
    identifier: str
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class SourceConfig(SrcDestAbstract):
    src: MessageSource = MessageSource.err

    @cached_property
    def routing_key(self) -> str:
        return f"{str(self.src.value)}-{self.identifier}"


class DestinationConfig(SrcDestAbstract):
    dest: MessageDestination = MessageSource.discord
    images: bool = True
    links: bool = True
    threads: bool = True
    msg_template: str = Field(default="{sender}: {message}")

    @cached_property
    def routing_key(self) -> str:
        return f"{str(self.dest.value)}-{self.identifier}"


class ConfigAbstract(BaseModel):
    source: SourceConfig
    destination: DestinationConfig


class OneWayConfig(ConfigAbstract):
    pass


class TwoWayConfig(ConfigAbstract):
    pass


class ReplyMode(str, Enum):
    thread = "thread"
    direct = "direct"


class ReplyConfig(ConfigAbstract):
    reply_mode: ReplyMode = Field(ReplyMode.direct)


class GeneralConfig(BaseModel):
    ignore_messages_from_self: bool = Field(True)
    ignore_all_bots: bool = Field(False)

    @classmethod
    def new(cls) -> "GeneralConfig":
        return cls()


class BridgeConfig(BaseModel):
    one_way: list[OneWayConfig] = Field(default_factory=lambda: list(), validation_alias=AliasPath("OneWay"))
    two_way: list[TwoWayConfig] = Field(default_factory=lambda: list(), validation_alias=AliasPath("TwoWay"))
    reply: list[ReplyConfig] = Field(default_factory=lambda: list(), validation_alias=AliasPath("Reply"))
    config: GeneralConfig = Field(default_factory=GeneralConfig.new, validation_alias=AliasPath("Config"))

    model_config = ConfigDict(extra="forbid", frozen=False, str_strip_whitespace=True, populate_by_name=True)

    class ConfigType(str, Enum):
        one_way = "one_way"
        two_way = "two_way"
        reply = "reply"

    @dataclasses.dataclass
    class Destination:
        config_type: "BridgeConfig.ConfigType"
        destination: DestinationConfig

    @model_validator(mode="after")
    def check_for_config(self) -> "BridgeConfig":
        one_way_len = len(self.one_way) if self.one_way is not None else 0
        two_way_len = len(self.two_way) if self.two_way is not None else 0
        reply_len = len(self.reply) if self.reply is not None else 0
        if one_way_len + two_way_len + reply_len == 0:
            raise ValueError("No bridge configurations specified")
        return self

    @cached_property
    def destinations(self: "BridgeConfig") -> dict[str, Destination]:
        dest_dict = {}
        if self.one_way is not None:
            for config in self.one_way:
                dest_dict[config.source.routing_key] = self.__class__.Destination(
                    config_type="one_way", destination=config.destination
                )
        if self.two_way is not None:
            for config in self.two_way:
                dest_dict[config.source.routing_key] = self.__class__.Destination(
                    config_type="two_way", destination=config.destination
                )
                dest_dict[config.destination.routing_key] = self.__class__.Destination(
                    config_type="two_way",
                    destination=DestinationConfig(
                        identifier=config.source.identifier,
                        dest=config.source.src,
                        images=config.destination.images,
                        links=config.destination.images,
                        threads=config.destination.threads,
                        msg_template=config.destination.msg_template,
                    ),
                )
        if self.reply is not None:
            for config in self.reply:
                dest_dict[config.source.routing_key] = self.__class__.Destination(
                    config_type="reply", destination=config.destination
                )
                dest_dict[config.destination.routing_key] = self.__class__.Destination(
                    config_type="reply",
                    destination=DestinationConfig(
                        identifier=config.source.identifier,
                        dest=config.source.src,
                        images=config.destination.images,
                        links=config.destination.images,
                        threads=config.destination.threads,
                        msg_template=config.destination.msg_template,
                    ),
                )
        return dest_dict
