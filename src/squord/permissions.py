"""Permissões do Squord.

Permissões são bits de um número inteiro grande. Trafegam como **string
decimal**; em Python, ``int`` já tem precisão arbitrária, então
``Permissions`` é um ``IntFlag`` — compare, some e converta naturalmente:

    >>> bits = Permissions.VIEW_CHANNEL | Permissions.SEND_MESSAGES
    >>> str(int(bits))
    '8193'
    >>> Permissions(int("155649")) & Permissions.EMBED_LINKS
    <Permissions.EMBED_LINKS: 131072>

@see https://docs.squord.com.br/referencia/permissoes
"""

from __future__ import annotations

from enum import IntFlag
from typing import Any

from .types import APIChannelOverwrite


class Permissions(IntFlag):
    """Flags de permissão. O bit 32 (``VIEW_AUDIT_LOG``) está na tabela oficial."""

    VIEW_CHANNEL = 1 << 0
    MANAGE_CHANNELS = 1 << 1
    MANAGE_GUILD = 1 << 2
    MANAGE_ROLES = 1 << 3
    MANAGE_INVITES = 1 << 4
    VIEW_AUDIT_LOG = 1 << 5
    MANAGE_EMOJIS = 1 << 6
    MANAGE_WEBHOOKS = 1 << 7
    KICK_MEMBERS = 1 << 8
    BAN_MEMBERS = 1 << 9
    TIMEOUT_MEMBERS = 1 << 10
    CHANGE_NICKNAME = 1 << 11
    MANAGE_NICKNAMES = 1 << 12
    SEND_MESSAGES = 1 << 13
    READ_MESSAGE_HISTORY = 1 << 14
    MANAGE_MESSAGES = 1 << 15
    ATTACH_FILES = 1 << 16
    EMBED_LINKS = 1 << 17
    ADD_REACTIONS = 1 << 18
    MENTION_EVERYONE = 1 << 19
    USE_EXTERNAL_EMOJIS = 1 << 20
    PIN_MESSAGES = 1 << 21
    CONNECT = 1 << 22
    SPEAK = 1 << 23
    VIDEO = 1 << 24
    STREAM = 1 << 25
    MUTE_MEMBERS = 1 << 26
    DEAFEN_MEMBERS = 1 << 27
    MOVE_MEMBERS = 1 << 28
    PRIORITY_SPEAKER = 1 << 29
    ADMINISTRATOR = 1 << 30
    SEND_POLLS = 1 << 31
    # O bit 32 foi aposentado e nunca é reutilizado.
    CREATE_INVITE = 1 << 33
    APPROVE_JOIN_REQUESTS = 1 << 34
    FORWARD_MESSAGES = 1 << 35
    HANDLE_REPORTS = 1 << 36
    PUBLISH_ANNOUNCEMENTS = 1 << 37
    BYPASS_SLOWMODE = 1 << 38
    CREATE_THREADS = 1 << 39
    SEND_MESSAGES_IN_THREADS = 1 << 40
    MANAGE_THREADS = 1 << 41
    MANAGE_EVENTS = 1 << 42


#: Todas as permissões, somadas.
ALL_PERMISSIONS = Permissions(sum(int(flag) for flag in Permissions))


def permissions_to_string(bits: int | Permissions) -> str:
    """Converte bits para string decimal (o formato aceito pela API)."""
    return str(int(bits))


def parse_permissions(value: str | int) -> Permissions:
    """Lê uma string decimal vinda da API como ``Permissions``."""
    return Permissions(int(value))


def has_permissions(bits: int | Permissions, *flags: int | Permissions) -> bool:
    """Testa se ``bits`` inclui todas as permissões informadas."""
    base = int(bits)
    return all((base & int(flag)) == int(flag) for flag in flags)


def has_any_permission(bits: int | Permissions, *flags: int | Permissions) -> bool:
    """Testa se ``bits`` inclui pelo menos uma das permissões informadas."""
    base = int(bits)
    return any((base & int(flag)) == int(flag) for flag in flags)


def resolve_channel_permissions(
    *,
    everyone_permissions: int | Permissions,
    role_permissions: list[int | Permissions],
    overwrites: list[APIChannelOverwrite | dict[str, Any]],
    member_id: str,
    everyone_role_id: str,
    member_role_ids: list[str],
) -> Permissions:
    """Resolve as permissões efetivas de um membro em um canal.

    Segue o algoritmo oficial: base do @everyone + OR dos cargos;
    ``ADMINISTRATOR`` encerra a conta; overwrites na ordem @everyone →
    cargos (deny de todos, depois allow) → membro; sem ``VIEW_CHANNEL``,
    o resultado é zero.

    O backend continua sendo a autoridade final: o resultado local é uma
    conveniência para evitar chamadas, não uma garantia.
    """
    base = int(everyone_permissions)
    for role in role_permissions:
        base |= int(role)

    if base & int(Permissions.ADMINISTRATOR):
        return ALL_PERMISSIONS

    normalized_overwrites: list[dict[str, Any]] = [dict(o) for o in overwrites]

    # @everyone: tira os deny e depois soma os allow.
    for overwrite in normalized_overwrites:
        if overwrite.get("targetId") == everyone_role_id:
            base &= ~int(str(overwrite.get("deny", "0")))
            base |= int(str(overwrite.get("allow", "0")))
            break

    # Cargos do membro, acumulados: primeiro todos os deny, depois os allow.
    role_overwrites = [
        o
        for o in normalized_overwrites
        if o.get("targetType") == "ROLE" and o.get("targetId") in member_role_ids
    ]
    deny = 0
    allow = 0
    for overwrite in role_overwrites:
        deny |= int(str(overwrite.get("deny", "0")))
        allow |= int(str(overwrite.get("allow", "0")))
    base &= ~deny
    base |= allow

    # Overwrite do membro: o mais específico, vence os anteriores.
    for overwrite in normalized_overwrites:
        if overwrite.get("targetType") == "MEMBER" and overwrite.get("targetId") == member_id:
            base &= ~int(str(overwrite.get("deny", "0")))
            base |= int(str(overwrite.get("allow", "0")))
            break

    if not base & int(Permissions.VIEW_CHANNEL):
        return Permissions(0)
    return Permissions(base)


#: Escopo mínimo usual para um bot que lê e responde em canais.
SUGGESTED_TEXT_BOT_PERMISSIONS = (
    Permissions.VIEW_CHANNEL
    | Permissions.SEND_MESSAGES
    | Permissions.READ_MESSAGE_HISTORY
    | Permissions.EMBED_LINKS
    | Permissions.ATTACH_FILES
    | Permissions.ADD_REACTIONS
)

#: Escopo de moderação usual (exige confirmação na instalação).
SUGGESTED_MODERATION_PERMISSIONS = (
    Permissions.KICK_MEMBERS
    | Permissions.BAN_MEMBERS
    | Permissions.TIMEOUT_MEMBERS
    | Permissions.MANAGE_MESSAGES
)
