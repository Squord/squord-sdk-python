"""Enumerações e flags da API do Squord.

Espelham o contrato publicado em https://docs.squord.com.br (OpenAPI).
Valores em ``SCREAMING_SNAKE`` trafegam como strings; permissões e intents
como bits somados (``IntFlag`` — Python já tem precisão arbitrária).
"""

from __future__ import annotations

from enum import IntFlag


class StrEnum(str):
    """Membro de enumeração que trafega como string da API (comparável a ``str``)."""


# ---------------------------------------------------------------------
# Canais
# ---------------------------------------------------------------------


class ChannelType(StrEnum):
    TEXT = "TEXT"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    CATEGORY = "CATEGORY"
    FORUM = "FORUM"
    VOICE = "VOICE"
    STAGE = "STAGE"
    THREAD = "THREAD"


class ThreadAutoArchiveMinutes(IntFlag):
    MINUTES_60 = 60
    HOURS_24 = 1440
    DAYS_3 = 4320
    DAYS_7 = 10080


# ---------------------------------------------------------------------
# Mensagens
# ---------------------------------------------------------------------


class MessageType(StrEnum):
    DEFAULT = "DEFAULT"
    REPLY = "REPLY"
    POLL = "POLL"
    SYSTEM_MEMBER_JOIN = "SYSTEM_MEMBER_JOIN"
    SYSTEM_MEMBER_LEAVE = "SYSTEM_MEMBER_LEAVE"
    SYSTEM_CHANNEL_PINNED = "SYSTEM_CHANNEL_PINNED"
    SYSTEM_CALL_STARTED = "SYSTEM_CALL_STARTED"
    SYSTEM_GROUP_CREATED = "SYSTEM_GROUP_CREATED"
    SYSTEM_MEMBER_ADDED = "SYSTEM_MEMBER_ADDED"
    SYSTEM_MEMBER_REMOVED = "SYSTEM_MEMBER_REMOVED"
    SYSTEM_GROUP_LEFT = "SYSTEM_GROUP_LEFT"
    SYSTEM_CHANNEL_FOLLOWED = "SYSTEM_CHANNEL_FOLLOWED"
    SYSTEM_GUILD_BOOST = "SYSTEM_GUILD_BOOST"
    SYSTEM_THREAD_CREATED = "SYSTEM_THREAD_CREATED"
    SYSTEM_AUTOMOD_ALERT = "SYSTEM_AUTOMOD_ALERT"


class AttachmentScanStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"
    FAILED = "FAILED"
    EXPLICIT = "EXPLICIT"


class ButtonStyle(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DANGER = "danger"
    LINK = "link"


class UploadStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    ATTACHED = "ATTACHED"


# ---------------------------------------------------------------------
# Membros e cargos
# ---------------------------------------------------------------------


class MemberType(StrEnum):
    INTERNAL = "INTERNAL"
    BOT = "BOT"
    WEBHOOK = "WEBHOOK"


class RoleManagedKind(StrEnum):
    BOOSTER = "BOOSTER"
    BOT = "BOT"


# ---------------------------------------------------------------------
# Comandos e interações
# ---------------------------------------------------------------------


class CommandOptionType(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    USER = "USER"
    CHANNEL = "CHANNEL"
    ROLE = "ROLE"


class InteractionType(StrEnum):
    COMMAND = "COMMAND"
    COMPONENT = "COMPONENT"


class InteractionCallbackType(StrEnum):
    MESSAGE = "MESSAGE"
    DEFERRED = "DEFERRED"
    UPDATE = "UPDATE"
    DEFERRED_UPDATE = "DEFERRED_UPDATE"


# ---------------------------------------------------------------------
# Flags de conta e Space
# ---------------------------------------------------------------------


class UserFlags(IntFlag):
    """Flags de uma conta, somadas no campo ``flags``."""

    STAFF = 1 << 0
    EARLY_SUPPORTER = 1 << 1
    VERIFIED_BOT = 1 << 2
    SYSTEM = 1 << 3
    VERIFIED = 1 << 4
    BOT = 1 << 5


class GuildFlags(IntFlag):
    """Flags de um Space, somadas no campo ``flags``."""

    OFFICIAL = 1 << 0
    PARTNER = 1 << 1
    DISCOVERY_BLOCKED = 1 << 2
    VERIFIED = 1 << 3
    DISCOVERY_AGE_WAIVED = 1 << 4


# ---------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------


class PresenceStatus(StrEnum):
    ONLINE = "ONLINE"
    IDLE = "IDLE"
    DND = "DND"
    INVISIBLE = "INVISIBLE"


class GatewayCloseCodes(IntFlag):
    UNKNOWN_ERROR = 4000
    UNKNOWN_OPCODE = 4001
    DECODE_ERROR = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    INVALID_SEQUENCE = 4007
    RATE_LIMITED = 4008
    SESSION_TIMEOUT = 4009
    INVALID_PROTOCOL_VERSION = 4012
    ACCOUNT_SUSPENDED = 4013
    BOT_SESSION_LIMIT = 4014
