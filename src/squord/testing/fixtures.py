"""Fixtures: payloads de exemplo no formato real da API, para testes."""

from __future__ import annotations

from typing import Any


def user(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Uma pessoa (Ana, dos exemplos da documentação)."""
    payload: dict[str, Any] = {
        "id": "1300000000000000020",
        "username": "ana",
        "displayName": "Ana",
        "avatarUrl": None,
        "avatarAnimatedUrl": None,
        "nameStyle": None,
        "flags": 0,
        "deleted": False,
        "suspended": False,
        "premium": False,
    }
    payload.update(overrides or {})
    return payload


def bot_user(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """A conta do bot."""
    return user(
        {
            "id": "1300000000000000010",
            "username": "bot~meubot",
            "displayName": "Meu Bot",
            "flags": 32,
            **(overrides or {}),
        }
    )


def member(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Um membro de um Space."""
    payload: dict[str, Any] = {
        "id": "1300000000000000011",
        "guildId": "1300000000000000001",
        "userId": "1300000000000000020",
        "user": user(),
        "type": "INTERNAL",
        "nickname": None,
        "avatarUrl": None,
        "avatarAnimatedUrl": None,
        "bannerUrl": None,
        "bannerAnimatedUrl": None,
        "bio": None,
        "bioEmojis": [],
        "nameStyle": None,
        "profileFont": None,
        "profileTheme": None,
        "roleIds": [],
        "joinedAt": "2026-10-01T10:00:00.000Z",
        "timeoutUntil": None,
        "deaf": False,
        "mute": False,
        "pending": False,
        "boostingSince": None,
        "createdAt": "2026-10-01T10:00:00.000Z",
        "updatedAt": "2026-10-01T10:00:00.000Z",
    }
    payload.update(overrides or {})
    return payload


def channel(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Um canal de texto."""
    payload: dict[str, Any] = {
        "id": "1300000000000000040",
        "guildId": "1300000000000000001",
        "categoryId": None,
        "name": "geral",
        "type": "TEXT",
        "position": 0,
        "topic": None,
        "topicUpdatedAt": None,
        "topicUpdatedById": None,
        "isPrivate": False,
        "rateLimitPerUser": 0,
        "bitrate": None,
        "userLimit": None,
        "chatEnabled": True,
        "lastMessageId": None,
        "overwrites": [],
        "availableTags": [],
        "requireTag": False,
        "defaultAutoArchiveMinutes": None,
        "createdAt": "2026-10-01T10:00:00.000Z",
        "updatedAt": "2026-10-01T10:00:00.000Z",
    }
    payload.update(overrides or {})
    return payload


def role(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """O cargo @everyone de um Space novo (padrões da documentação)."""
    payload: dict[str, Any] = {
        "id": "1300000000000000001",
        "guildId": "1300000000000000001",
        "name": "@everyone",
        "color": None,
        "position": 0,
        "permissions": "1685839112193",
        "hoist": False,
        "mentionable": False,
        "managed": False,
        "managedKind": None,
        "botId": None,
        "icon": None,
        "selfAssignable": False,
        "createdAt": "2026-10-01T10:00:00.000Z",
        "updatedAt": "2026-10-01T10:00:00.000Z",
    }
    payload.update(overrides or {})
    return payload


def guild(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Um Space com o bloco ``self`` do bot."""
    payload: dict[str, Any] = {
        "id": "1300000000000000001",
        "ownerId": "1300000000000000009",
        "name": "Meu Space",
        "slug": "meu-space",
        "description": None,
        "iconUrl": None,
        "iconAnimatedUrl": None,
        "bannerUrl": None,
        "bannerAnimatedUrl": None,
        "bannerPlaceholder": None,
        "defaultChannelId": "1300000000000000040",
        "systemChannelId": None,
        "visibility": "PUBLIC",
        "verificationLevel": "NONE",
        "accessMode": "LINK",
        "requireVerifiedEmail": False,
        "requireTwoFactor": False,
        "moderationMfaRequired": False,
        "joinRequestRoleIds": [],
        "requireJoinMessage": False,
        "joinRequestRetryDays": 0,
        "memberCount": 2,
        "flags": 0,
        "planId": "free",
        "vanityLapsesAt": None,
        "vanityInvite": False,
        "boostCount": 0,
        "boostLevel": 0,
        "boostMessages": False,
        "discoveryCategory": None,
        "locale": None,
        "rules": [],
        "rulesUpdatedAt": None,
        "discoverable": False,
        "discoverableSince": None,
        "minAccountAgeDays": 0,
        "createdAt": "2026-10-01T10:00:00.000Z",
        "updatedAt": "2026-10-01T10:00:00.000Z",
        "self": {
            "memberId": "1300000000000000012",
            "roleIds": ["1300000000000000031"],
            "permissions": "155649",
            "isOwner": False,
        },
    }
    payload.update(overrides or {})
    return payload


def message(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Uma mensagem com autor."""
    payload: dict[str, Any] = {
        "id": "1300000000000000100",
        "guildId": "1300000000000000001",
        "channelId": "1300000000000000040",
        "authorId": "1300000000000000020",
        "type": "DEFAULT",
        "content": "Olá!",
        "replyToId": None,
        "attachments": [],
        "embeds": [],
        "components": [],
        "interaction": None,
        "mentions": {"userIds": [], "roleIds": [], "channelIds": [], "everyone": False},
        "reactions": [],
        "pinned": False,
        "editedAt": None,
        "deletedAt": None,
        "moderated": False,
        "nonce": None,
        "call": None,
        "poll": None,
        "forward": None,
        "relay": None,
        "relayedCount": None,
        "stickers": [],
        "emojis": [],
        "thread": None,
        "automod": None,
        "createdAt": "2026-10-05T14:30:00.000Z",
        "updatedAt": "2026-10-05T14:30:00.000Z",
        "author": user(),
        "memberNickname": None,
        "memberAvatarUrl": None,
        "memberNameStyle": None,
        "replyTo": None,
    }
    payload.update(overrides or {})
    return payload


def command_interaction(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Uma interação de comando (``interaction.created`` com ``COMMAND``)."""
    payload: dict[str, Any] = {
        "id": "1300000000000000400",
        "token": "tk_9f2c1d7e8a4b",
        "type": "COMMAND",
        "guildId": "1300000000000000001",
        "channelId": "1300000000000000040",
        "user": user(),
        "member": member(),
        "command": {"id": "1300000000000000500", "name": "ping", "options": []},
        "createdAt": "2026-10-05T14:40:00.000Z",
    }
    payload.update(overrides or {})
    return payload


def component_interaction(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Uma interação de componente (``COMPONENT``)."""
    payload: dict[str, Any] = {
        "id": "1300000000000000401",
        "token": "tk_1b3d5f7a9c2e",
        "type": "COMPONENT",
        "guildId": "1300000000000000001",
        "channelId": "1300000000000000040",
        "user": user(),
        "member": member(),
        "component": {
            "messageId": "1300000000000000100",
            "customId": "confirmar",
            "type": "button",
            "values": [],
        },
        "createdAt": "2026-10-05T14:41:00.000Z",
    }
    payload.update(overrides or {})
    return payload


def command(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Um comando de aplicação registrado."""
    payload: dict[str, Any] = {
        "id": "1300000000000000500",
        "botId": "1300000000000000010",
        "guildId": None,
        "name": "ping",
        "description": "Verifica a latência do bot",
        "options": [],
        "updatedAt": "2026-10-05T14:00:00.000Z",
    }
    payload.update(overrides or {})
    return payload


def bot(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Um bot na visão do dono (``GET /bots/@me``)."""
    payload: dict[str, Any] = {
        "id": "1300000000000000010",
        "user": bot_user(),
        "description": "Bot de exemplo",
        "ownerUsername": "ana",
        "public": False,
        "verified": False,
        "installCount": 1,
        "termsUrl": None,
        "privacyUrl": None,
        "createdAt": "2026-10-01T10:00:00.000Z",
        "intents": 13,
    }
    payload.update(overrides or {})
    return payload


def upload_reservation(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """A resposta da reserva de upload (``{upload, target}``)."""
    payload: dict[str, Any] = {
        "upload": {
            "id": "1300000000000000300",
            "scope": "attachments",
            "filename": "relatorio.pdf",
            "contentType": "application/pdf",
            "size": 12,
            "status": "PENDING",
            "url": None,
            "thumbnailUrl": None,
            "guildId": "1300000000000000001",
            "storageKey": "attachments/key",
            "scanStatus": "NOT_REQUIRED",
            "animated": False,
            "animatedUrl": None,
            "createdAt": "2026-10-05T12:00:00.000Z",
            "expiresAt": "2026-10-05T13:15:00.000Z",
        },
        "target": {
            "uploadUrl": "https://media-mock.example/attachments/key",
            "method": "PUT",
            "headers": {"Content-Type": "application/pdf"},
            "storageKey": "attachments/key",
            "publicUrl": "https://media.squord.com.br/attachments/key",
            "expiresAt": "2026-10-05T12:15:00.000Z",
        },
    }
    payload.update(overrides or {})
    return payload


def upload_ready(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Um upload confirmado (``READY``)."""
    payload: dict[str, Any] = {
        "id": "1300000000000000300",
        "scope": "attachments",
        "filename": "relatorio.pdf",
        "contentType": "application/pdf",
        "size": 12,
        "status": "READY",
        "url": "https://media.squord.com.br/attachments/key",
        "thumbnailUrl": None,
        "guildId": "1300000000000000001",
        "storageKey": "attachments/key",
        "scanStatus": "NOT_REQUIRED",
        "animated": False,
        "animatedUrl": None,
        "createdAt": "2026-10-05T12:00:00.000Z",
        "expiresAt": "2026-10-05T13:15:00.000Z",
    }
    payload.update(overrides or {})
    return payload
