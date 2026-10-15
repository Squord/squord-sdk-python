"""Modelos hidratados: mensagem, canal, thread, membro, cargo, Space e interação.

Cada modelo envolve o payload cru (``raw``) e expõe propriedades e métodos
de alto nível. Os métodos chamam os managers do cliente (injetados), sem
impor que quem programa conheça os endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .builders import resolve_message_edit_payload, resolve_message_payload
from .enums import MemberType, UserFlags
from .types import Snowflake, user_mention

if TYPE_CHECKING:
    from .client import SquordClient


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class _Model:
    """Base: payload cru + referência ao cliente."""

    def __init__(self, client: SquordClient, raw: dict[str, Any]) -> None:
        self._client = client
        self.raw: dict[str, Any] = dict(raw)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.raw == other.raw

    def __repr__(self) -> str:
        name = type(self).__name__
        ident = self.raw.get("id") or self.raw.get("userId") or "?"
        return f"<{name} id={ident!r}>"


class User(_Model):
    """Conta de usuário (pessoa ou bot)."""

    @property
    def data(self) -> dict[str, Any]:
        return self.raw

    @property
    def id(self) -> Snowflake:
        return str(self.raw["id"])

    @property
    def username(self) -> str:
        return str(self.raw.get("username", ""))

    @property
    def display_name(self) -> str:
        return str(self.raw.get("displayName", ""))

    @property
    def avatar_url(self) -> str | None:
        return self.raw.get("avatarUrl")

    @property
    def flags(self) -> int:
        return int(self.raw.get("flags") or 0)

    @property
    def is_bot(self) -> bool:
        """``True`` para contas de bot (flag ``BOT``)."""
        return bool(self.flags & int(UserFlags.BOT))

    @property
    def is_verified_bot(self) -> bool:
        return bool(self.flags & int(UserFlags.VERIFIED_BOT))

    @property
    def deleted(self) -> bool:
        return bool(self.raw.get("deleted"))

    @property
    def suspended(self) -> bool:
        return bool(self.raw.get("suspended"))

    @property
    def mention(self) -> str:
        """Menção ``<@id>`` para usar no conteúdo de mensagens."""
        return user_mention(self.id)

    async def member_of(self, guild_id: Snowflake) -> Member | None:
        """Busca o membro correspondente em um Space (``None`` se não for)."""
        data = await self._client.members.fetch(guild_id, self.id, raise_not_found=False)
        if data is None:
            return None
        return Member(self._client, data)


class Member(_Model):
    """Perfil de um usuário dentro de um Space."""

    @property
    def data(self) -> dict[str, Any]:
        return self.raw

    @property
    def id(self) -> Snowflake:
        """Id da participação (não confundir com o id da conta)."""
        return str(self.raw["id"])

    @property
    def guild_id(self) -> Snowflake:
        return str(self.raw["guildId"])

    @property
    def user_id(self) -> Snowflake:
        return str(self.raw["userId"])

    @property
    def user(self) -> User:
        return User(self._client, self.raw.get("user") or {})

    @property
    def nickname(self) -> str | None:
        return self.raw.get("nickname")

    @property
    def display_name(self) -> str:
        """Nome efetivo: apelido no Space ou ``displayName``."""
        return str(self.raw.get("nickname") or self.user.display_name)

    @property
    def role_ids(self) -> list[Snowflake]:
        return [str(r) for r in self.raw.get("roleIds", [])]

    @property
    def joined_at(self) -> datetime | None:
        return _iso(self.raw.get("joinedAt"))

    @property
    def timeout_until(self) -> datetime | None:
        return _iso(self.raw.get("timeoutUntil"))

    @property
    def is_timed_out(self) -> bool:
        until = self.timeout_until
        return until is not None and until > datetime.now(timezone.utc)

    @property
    def is_bot(self) -> bool:
        return self.raw.get("type") == MemberType.BOT

    @property
    def mention(self) -> str:
        return user_mention(self.user_id)

    async def fetch(self) -> Member:
        data = await self._client.members.fetch(self.guild_id, self.user_id)
        return Member(self._client, data)

    async def fetch_roles(self) -> list[Role]:
        roles = await self._client.roles.list(self.guild_id)
        member_ids = set(self.role_ids) | {self.guild_id}
        return [Role(self._client, r) for r in roles if str(r.get("id")) in member_ids]

    async def add_role(self, role_id: Snowflake) -> None:
        await self._client.members.add_role(self.guild_id, self.user_id, role_id)

    async def remove_role(self, role_id: Snowflake) -> None:
        await self._client.members.remove_role(self.guild_id, self.user_id, role_id)

    async def set_nickname(self, nickname: str | None) -> Member:
        data = await self._client.members.edit(self.guild_id, self.user_id, {"nickname": nickname})
        return Member(self._client, data)

    async def timeout(self, until: datetime) -> Member:
        """Aplica timeout até a data (``TIMEOUT_MEMBERS``)."""
        data = await self._client.members.edit(
            self.guild_id,
            self.user_id,
            {"timeoutUntil": until.astimezone(timezone.utc).isoformat()},
        )
        return Member(self._client, data)

    async def remove_timeout(self) -> Member:
        data = await self._client.members.edit(self.guild_id, self.user_id, {"timeoutUntil": None})
        return Member(self._client, data)

    async def kick(self, reason: str | None = None) -> None:
        """Expulsa o membro (``KICK_MEMBERS``); ele pode voltar com novo convite."""
        await self._client.members.kick(self.guild_id, self.user_id, reason)

    async def ban(self, *, reason: str | None = None, delete_message_seconds: int = 0) -> None:
        """Bane o membro (``BAN_MEMBERS``), podendo apagar histórico recente."""
        await self._client.moderation.ban(
            self.guild_id,
            self.user_id,
            reason=reason,
            delete_message_seconds=delete_message_seconds,
        )


class Role(_Model):
    """Um cargo do Space (hierárquico por ``position``)."""

    @property
    def data(self) -> dict[str, Any]:
        return self.raw

    @property
    def id(self) -> Snowflake:
        return str(self.raw["id"])

    @property
    def guild_id(self) -> Snowflake:
        return str(self.raw["guildId"])

    @property
    def name(self) -> str:
        return str(self.raw.get("name", ""))

    @property
    def color(self) -> str | None:
        return self.raw.get("color")

    @property
    def position(self) -> int:
        return int(self.raw.get("position") or 0)

    @property
    def permissions(self) -> int:
        """Bits de permissão como ``int`` (a API envia string decimal)."""
        return int(str(self.raw.get("permissions", "0")))

    @property
    def managed(self) -> bool:
        return bool(self.raw.get("managed"))

    @property
    def mentionable(self) -> bool:
        return bool(self.raw.get("mentionable"))

    @property
    def is_everyone(self) -> bool:
        """``True`` para o cargo @everyone (id igual ao do Space)."""
        return self.id == self.guild_id

    @property
    def mention(self) -> str:
        """Menção ``<@&id>``; só notifica se o cargo for mencionável."""
        return f"<@&{self.id}>"


class Guild(_Model):
    """Um Space (comunidade), com o bloco ``self`` do bot."""

    @property
    def data(self) -> dict[str, Any]:
        return self.raw

    @property
    def id(self) -> Snowflake:
        return str(self.raw["id"])

    @property
    def name(self) -> str:
        return str(self.raw.get("name", ""))

    @property
    def slug(self) -> str:
        return str(self.raw.get("slug", ""))

    @property
    def owner_id(self) -> Snowflake:
        return str(self.raw.get("ownerId", ""))

    @property
    def member_count(self) -> int:
        return int(self.raw.get("memberCount") or 0)

    @property
    def icon_url(self) -> str | None:
        return self.raw.get("iconUrl")

    @property
    def boost_count(self) -> int:
        return int(self.raw.get("boostCount") or 0)

    @property
    def self_info(self) -> dict[str, Any]:
        """O bot neste Space: ``memberId``, ``roleIds``, ``permissions``."""
        return dict(self.raw.get("self") or {})

    @property
    def self_permissions(self) -> int:
        return int(str((self.raw.get("self") or {}).get("permissions", "0")))

    async def fetch(self) -> Guild:
        data = await self._client.guilds.fetch(self.id)
        return Guild(self._client, data)

    async def fetch_channel_tree(self) -> list[dict[str, Any]]:
        """Árvore de canais do Space, agrupada por categorias."""
        nodes = await self._client.channels.fetch_tree(self.id)
        return [
            {
                "category": Channel(self._client, node["category"])
                if node.get("category")
                else None,
                "channels": [Channel(self._client, c) for c in node.get("channels", [])],
            }
            for node in nodes
        ]

    async def fetch_roles(self) -> list[Role]:
        roles = await self._client.roles.list(self.id)
        return [Role(self._client, r) for r in roles]

    async def fetch_member(self, user_id: Snowflake) -> Member:
        data = await self._client.members.fetch(self.id, user_id)
        return Member(self._client, data)


class Channel(_Model):
    """Canal de texto, anúncios, categoria, fórum, voz ou palco."""

    @property
    def data(self) -> dict[str, Any]:
        return self.raw

    @property
    def id(self) -> Snowflake:
        return str(self.raw["id"])

    @property
    def guild_id(self) -> Snowflake:
        return str(self.raw["guildId"])

    @property
    def name(self) -> str:
        return str(self.raw.get("name", ""))

    @property
    def type(self) -> str:
        return str(self.raw.get("type", ""))

    @property
    def topic(self) -> str | None:
        return self.raw.get("topic")

    @property
    def is_private(self) -> bool:
        return bool(self.raw.get("isPrivate"))

    @property
    def rate_limit_per_user(self) -> int:
        """Modo lento em segundos (0 desligado)."""
        return int(self.raw.get("rateLimitPerUser") or 0)

    @property
    def chat_enabled(self) -> bool:
        return bool(self.raw.get("chatEnabled"))

    @property
    def last_message_id(self) -> Snowflake | None:
        value = self.raw.get("lastMessageId")
        return str(value) if value else None

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    @property
    def is_text(self) -> bool:
        return self.type in {"TEXT", "ANNOUNCEMENT"}

    @property
    def is_voice(self) -> bool:
        return self.type in {"VOICE", "STAGE"}

    @property
    def is_forum(self) -> bool:
        return self.type == "FORUM"

    async def fetch(self) -> Channel:
        data = await self._client.channels.fetch(self.id)
        return Channel(self._client, data)

    async def send(
        self,
        payload: str | dict[str, Any],
        *,
        nonce: str | None = None,
    ) -> Message:
        """Envia uma mensagem (idempotente por ``nonce`` automático)."""
        data = await self._client.messages.send(self.id, payload, nonce=nonce)
        return Message(self._client, data)

    async def send_file(
        self,
        *,
        path: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        content: str | None = None,
    ) -> Message:
        """Envia um anexo (fluxo completo de upload) com texto opcional."""
        attachment_id = await self._client.uploads.upload_for_attachment(
            guild_id=self.guild_id, path=path, data=data, filename=filename
        )
        payload: dict[str, Any] = {"attachmentIds": [attachment_id]}
        if content:
            payload["content"] = content
        return await self.send(payload)

    async def fetch_message(self, message_id: Snowflake) -> Message:
        data = await self._client.messages.fetch(self.id, message_id)
        return Message(self._client, data)

    async def fetch_messages(
        self,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> dict[str, Any]:
        page = await self._client.messages.list(self.id, limit=limit, before=before, after=after)
        page["items"] = [Message(self._client, m) for m in list(page.get("items", []))]
        return page

    async def fetch_pins(self) -> list[Message]:
        items = await self._client.messages.list_pins(self.id)
        return [Message(self._client, m) for m in list(items)]

    async def create_thread(self, name: str, *, auto_archive_minutes: int | None = None) -> Thread:
        body: dict[str, Any] = {"name": name}
        if auto_archive_minutes is not None:
            body["autoArchiveMinutes"] = auto_archive_minutes
        data = await self._client.channels.create_thread(self.id, body)
        return Thread(self._client, data)

    async def fetch_threads(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        archived: str | None = None,
        tag_id: Snowflake | None = None,
    ) -> dict[str, Any]:
        page = await self._client.channels.list_threads(
            self.id, cursor=cursor, limit=limit, archived=archived, tag_id=tag_id
        )
        page["items"] = [Thread(self._client, t) for t in page.get("items", [])]
        return page


class Thread(_Model):
    """Uma thread ou post de fórum (o ``id`` vale como ``channelId``)."""

    @property
    def data(self) -> dict[str, Any]:
        return self.raw

    @property
    def id(self) -> Snowflake:
        return str(self.raw["id"])

    @property
    def guild_id(self) -> Snowflake:
        return str(self.raw["guildId"])

    @property
    def parent_id(self) -> Snowflake:
        return str(self.raw["parentId"])

    @property
    def name(self) -> str:
        return str(self.raw.get("name", ""))

    @property
    def owner_id(self) -> Snowflake:
        return str(self.raw.get("ownerId", ""))

    @property
    def is_forum_post(self) -> bool:
        return bool(self.raw.get("isForumPost"))

    @property
    def archived(self) -> bool:
        return bool(self.raw.get("archived"))

    @property
    def locked(self) -> bool:
        return bool(self.raw.get("locked"))

    @property
    def message_count(self) -> int:
        return int(self.raw.get("messageCount") or 0)

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    async def send(self, payload: str | dict[str, Any], *, nonce: str | None = None) -> Message:
        data = await self._client.messages.send(self.id, payload, nonce=nonce)
        return Message(self._client, data)

    async def fetch_message(self, message_id: Snowflake) -> Message:
        data = await self._client.messages.fetch(self.id, message_id)
        return Message(self._client, data)


class Message(_Model):
    """Uma mensagem, com ações de alto nível."""

    @property
    def data(self) -> dict[str, Any]:
        return self.raw

    @property
    def id(self) -> Snowflake:
        return str(self.raw["id"])

    @property
    def guild_id(self) -> Snowflake | None:
        value = self.raw.get("guildId")
        return str(value) if value else None

    @property
    def channel_id(self) -> Snowflake:
        return str(self.raw["channelId"])

    @property
    def author_id(self) -> Snowflake:
        return str(self.raw["authorId"])

    @property
    def author(self) -> User:
        return User(self._client, self.raw.get("author") or {})

    @property
    def type(self) -> str:
        return str(self.raw.get("type", ""))

    @property
    def content(self) -> str:
        return str(self.raw.get("content", ""))

    @property
    def reply_to_id(self) -> Snowflake | None:
        value = self.raw.get("replyToId")
        return str(value) if value else None

    @property
    def pinned(self) -> bool:
        return bool(self.raw.get("pinned"))

    @property
    def moderated(self) -> bool:
        return bool(self.raw.get("moderated"))

    @property
    def attachments(self) -> list[dict[str, Any]]:
        return list(self.raw.get("attachments", []))

    @property
    def embeds(self) -> list[dict[str, Any]]:
        return list(self.raw.get("embeds", []))

    @property
    def components(self) -> list[dict[str, Any]]:
        return list(self.raw.get("components", []))

    @property
    def reactions(self) -> list[dict[str, Any]]:
        return list(self.raw.get("reactions", []))

    @property
    def created_at(self) -> datetime | None:
        return _iso(self.raw.get("createdAt"))

    @property
    def author_display_name(self) -> str:
        """Nome efetivo do autor (apelido no Space ou ``displayName``)."""
        return str(self.raw.get("memberNickname") or self.author.display_name)

    @property
    def from_me(self) -> bool:
        """``True`` se a mensagem veio do próprio bot."""
        me = self._client.user_id
        return me is not None and self.author_id == me

    @property
    def mentions_me(self) -> bool:
        """``True`` se o bot foi mencionado (``<@id>`` no conteúdo)."""
        me = self._client.user_id
        mentions = (self.raw.get("mentions") or {}).get("userIds", [])
        return me is not None and str(me) in {str(u) for u in mentions}

    @property
    def mentioned_user_ids(self) -> list[Snowflake]:
        """Ids mencionados (só as menções que valeram)."""
        return [str(u) for u in (self.raw.get("mentions") or {}).get("userIds", [])]

    @property
    def mentioned_role_ids(self) -> list[Snowflake]:
        return [str(r) for r in (self.raw.get("mentions") or {}).get("roleIds", [])]

    @property
    def mentions_everyone(self) -> bool:
        return bool((self.raw.get("mentions") or {}).get("everyone"))

    async def fetch(self) -> Message:
        data = await self._client.messages.fetch(self.channel_id, self.id)
        return Message(self._client, data)

    async def fetch_channel(self) -> Channel | Thread | None:
        data = await self._client.channels.fetch(self.channel_id, raise_not_found=False)
        if data is None:
            return None
        if data.get("type") == "THREAD":
            return Thread(self._client, data)
        return Channel(self._client, data)

    async def reply(
        self,
        payload: str | dict[str, Any],
        *,
        nonce: str | None = None,
    ) -> Message:
        """Responde a mensagem (usa ``replyToId``). Idempotente por ``nonce``."""
        body = resolve_message_payload(payload)
        body["replyToId"] = self.id
        data = await self._client.messages.send(self.channel_id, body, nonce=nonce)
        return Message(self._client, data)

    async def edit(self, payload: str | dict[str, Any]) -> Message:
        """Edita a mensagem (só mensagens do próprio bot)."""
        body = resolve_message_edit_payload(payload)
        data = await self._client.messages.edit(self.channel_id, self.id, body)
        return Message(self._client, data)

    async def delete(self) -> None:
        """Apaga (a do bot sempre; de outros, com ``MANAGE_MESSAGES``)."""
        await self._client.messages.delete(self.channel_id, self.id)

    async def react(self, emoji: str) -> None:
        """Reage com um emoji Unicode ou ``<:nome:id>``."""
        await self._client.messages.react(self.channel_id, self.id, emoji)

    async def remove_reaction(self, emoji: str) -> None:
        await self._client.messages.remove_reaction(self.channel_id, self.id, emoji)

    async def pin(self) -> None:
        await self._client.messages.pin(self.channel_id, self.id)

    async def unpin(self) -> None:
        await self._client.messages.unpin(self.channel_id, self.id)

    async def start_thread(self, name: str) -> Thread:
        """Cria uma thread a partir desta mensagem (texto e anúncios)."""
        data = await self._client.channels.create_thread_from_message(
            self.channel_id, self.id, {"name": name}
        )
        return Thread(self._client, data)


class Interaction(_Model):
    """Interação: comando de barra usado ou clique em componente.

    Responda em até ~10 s (o app avisa "não respondeu" depois disso);
    use ``defer()`` + followup para trabalho demorado. A janela total é de
    15 minutos; o limite é 5 respostas (callback + follow-ups) por 5 s.
    """

    @property
    def data(self) -> dict[str, Any]:
        return self.raw

    @property
    def id(self) -> str:
        return str(self.raw["id"])

    @property
    def token(self) -> str:
        """Credencial da interação (15 minutos de validade). Trate como segredo."""
        return str(self.raw["token"])

    @property
    def type(self) -> str:
        return str(self.raw.get("type"))

    @property
    def guild_id(self) -> Snowflake:
        return str(self.raw["guildId"])

    @property
    def channel_id(self) -> Snowflake:
        return str(self.raw["channelId"])

    @property
    def user(self) -> User:
        return User(self._client, self.raw.get("user") or {})

    @property
    def member(self) -> Member | None:
        raw = self.raw.get("member")
        if raw is None:
            return None
        return Member(self._client, raw)

    @property
    def is_command(self) -> bool:
        return self.type == "COMMAND"

    @property
    def is_component(self) -> bool:
        return self.type == "COMPONENT"

    @property
    def command(self) -> dict[str, Any] | None:
        return self.raw.get("command")

    @property
    def component(self) -> dict[str, Any] | None:
        return self.raw.get("component")

    @property
    def custom_id(self) -> str | None:
        raw = self.component
        return str(raw.get("customId")) if raw else None

    @property
    def values(self) -> list[str]:
        """Valores escolhidos em um menu (vazio em botões)."""
        raw = self.component
        return [str(v) for v in (raw or {}).get("values", [])]

    # ------------------------------------------------------------- --
    # Opções do comando
    # ------------------------------------------------------------------

    @property
    def options(self) -> list[dict[str, Any]]:
        """Opções preenchidas da invocação (já validadas pelo Squord)."""
        return list((self.command or {}).get("options", []))

    def _get_option(self, name: str) -> Any:
        for option in self.options:
            if option.get("name") == name:
                return option.get("value")
        return None

    def get_string(self, name: str, *, required: bool = False) -> str | None:
        value = self._get_option(name)
        if isinstance(value, str):
            return value
        if required:
            msg = f'A opção obrigatória "{name}" não veio como STRING'
            raise ValueError(msg)
        return None

    def get_integer(self, name: str, *, required: bool = False) -> int | None:
        value = self._get_option(name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if required:
            msg = f'A opção obrigatória "{name}" não veio como INTEGER'
            raise ValueError(msg)
        return None

    def get_boolean(self, name: str, *, required: bool = False) -> bool | None:
        value = self._get_option(name)
        if isinstance(value, bool):
            return value
        if required:
            msg = f'A opção obrigatória "{name}" não veio como BOOLEAN'
            raise ValueError(msg)
        return None

    def get_id(self, name: str, *, required: bool = False) -> Snowflake | None:
        """Opção ``USER``/``CHANNEL``/``ROLE``: o valor é o id (string)."""
        value = self._get_option(name)
        if isinstance(value, str):
            return value
        if required:
            msg = f'A opção obrigatória "{name}" não veio como USER/CHANNEL/ROLE'
            raise ValueError(msg)
        return None

    # ------------------------------------------------------------- --
    # Respostas
    # ------------------------------------------------------------------

    async def reply(
        self,
        payload: str | dict[str, Any],
        *,
        ephemeral: bool = False,
    ) -> None:
        """Primeira resposta como mensagem (``409 ALREADY_ACKNOWLEDGED`` vira ok)."""
        body = resolve_message_payload(payload)
        if ephemeral:
            body["ephemeral"] = True
        await self._client.interactions.reply(self.id, self.token, body)

    async def reply_ephemeral(self, payload: str | dict[str, Any]) -> None:
        """Resposta efêmera: só quem invocou vê; não é salva; só botões de link."""
        await self.reply(payload, ephemeral=True)

    async def defer(self) -> None:
        """``DEFERRED``: mostra o bot "pensando" enquanto o trabalho roda."""
        await self._client.interactions.defer(self.id, self.token)

    async def update(self, payload: str | dict[str, Any]) -> None:
        """``UPDATE`` (só componente): edita a mensagem que tinha o componente."""
        body = resolve_message_edit_payload(payload)
        await self._client.interactions.update(self.id, self.token, body)

    async def acknowledge(self) -> None:
        """``DEFERRED_UPDATE`` (só componente): confirma o clique sem mudar nada."""
        await self._client.interactions.acknowledge_component(self.id, self.token)

    async def followup(
        self,
        payload: str | dict[str, Any],
        *,
        ephemeral: bool = False,
    ) -> None:
        """Mensagem extra depois da primeira resposta."""
        body = resolve_message_payload(payload)
        if ephemeral:
            body["ephemeral"] = True
        await self._client.interactions.followup(self.id, self.token, body)

    async def fetch_component_message(self) -> Message | None:
        """Busca a mensagem do componente clicado (quando ``is_component``)."""
        raw = self.component
        if not raw:
            return None
        message_id = str(raw.get("messageId"))
        data = await self._client.messages.fetch(self.channel_id, message_id, raise_not_found=False)
        if data is None:
            return None
        return Message(self._client, data)
