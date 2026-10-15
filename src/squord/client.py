"""``SquordClient``: o ponto central do SDK.

Valida o token contra a API (``GET /bots/@me``), conecta ao gateway,
entrega eventos tipados e expõe os managers REST. O ciclo de vida
completo — reconexão, heartbeat, resume e deduplicação — fica a cargo
do SDK.

```python
import squord
import os

client = squord.SquordClient(token=os.environ["SQUORD_BOT_TOKEN"])

@client.on("message.created")
async def on_message(message: squord.Message) -> None:
    if message.content == "!ping":
        await message.reply("Pong! 🏓")

await client.login()  # em um loop asyncio próprio
```
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

from .cache import Cache
from .enums import PresenceStatus
from .errors import SquordTypeError
from .events import EventEmitter
from .gateway import Gateway, WSConnector
from .http import DEFAULT_BASE_URL, RestClient, Transport
from .logger import get_logger, setup_logging
from .managers import (
    ApplicationCommandsManager,
    BotManager,
    ChannelsManager,
    GuildsManager,
    InteractionsManager,
    MembersManager,
    MessagesManager,
    ModerationManager,
    RolesManager,
    UploadsManager,
    UsersManager,
)
from .models import Channel, Guild, Interaction, Member, Message, Role, Thread, User
from .permissions import Permissions, has_permissions, resolve_channel_permissions
from .types import Snowflake
from .utils import assert_snowflake, is_bot_token, strip_token_prefix

#: Eventos conhecidos entregues pelo cliente (nomes reais do gateway).
KNOWN_RAW_EVENTS = frozenset(
    {
        "message.deleted",
        "message.bulk_deleted",
        "poll.vote.cast",
        "poll.vote.removed",
        "reaction.added",
        "reaction.removed",
        "member.left",
        "member.banned",
        "member.unbanned",
        "guild.deleted",
        "guild.taken_down",
        "guild.boost.added",
        "guild.boost.removed",
        "channel.deleted",
        "channel.tree.invalidated",
        "role.deleted",
        "thread.deleted",
        "emoji.created",
        "emoji.updated",
        "emoji.deleted",
        "sticker.created",
        "sticker.updated",
        "sticker.deleted",
        "guild_event.created",
        "guild_event.updated",
        "guild_event.deleted",
        "announcement.follow.created",
        "announcement.follow.deleted",
        "voice.state.updated",
        "voice.room.updated",
        "voice.member.moved",
        "voice.e2ee.bot_key_requested",
        "application_command.updated",
    }
)


class _ClientCaches:
    """Caches opcionais do cliente (TTL + limite de itens)."""

    def __init__(self, ttl_ms: float, max_entries: int) -> None:
        self.guilds: Cache[Snowflake, dict[str, Any]] = Cache(ttl_ms, max_entries)
        self.channels: Cache[Snowflake, dict[str, Any]] = Cache(ttl_ms, max_entries)
        self.members: Cache[str, dict[str, Any]] = Cache(ttl_ms, max_entries)
        self.roles: Cache[Snowflake, list[dict[str, Any]]] = Cache(ttl_ms, max_entries)


class SquordClient:
    """Cliente do bot: REST + gateway + eventos, com cache opcional."""

    def __init__(
        self,
        token: str,
        *,
        api_base_url: str = DEFAULT_BASE_URL,
        gateway_url: str | None = None,
        timeout_ms: int = 15_000,
        max_retries: int = 3,
        global_requests_per_second: int = 45,
        transport: Transport | None = None,
        ws_connector: WSConnector | None = None,
        rest_only: bool = False,
        graceful_shutdown: bool = False,
        reconnect_base_ms: float = 1_000,
        cache_ttl_ms: float = 300_000,
        cache_max_entries: int = 500,
        enable_cache: bool = False,
        logger: Any = None,
        log_level: int | None = None,
    ) -> None:
        if not token or not isinstance(token, str):
            msg = "Informe o token do bot: SquordClient(token=os.environ['SQUORD_BOT_TOKEN'])"
            raise SquordTypeError(msg)
        token = strip_token_prefix(token)
        if not is_bot_token(token):
            msg = (
                "O token do bot deve começar com sqb_ (formato sqb_<id>.<segredo>), "
                "obtido em Configurações → Desenvolvedor"
            )
            raise SquordTypeError(msg)
        if log_level is not None:
            setup_logging(log_level)

        self._token = token
        self._rest_only = rest_only
        self._graceful = graceful_shutdown
        self._logger = logger or get_logger("client")
        self._gateway: Gateway | None = None
        self._ws_connector = ws_connector
        self._gateway_url = gateway_url
        self._reconnect_base_ms = reconnect_base_ms
        self._application: dict[str, Any] | None = None
        self._user_id: Snowflake | None = None
        self._destroyed = False
        self._shutdown_signals_bound = False

        #: Emissor de eventos: ``client.on("message.created", handler)``.
        self.events = EventEmitter()
        self.on = self.events.on
        self.once = self.events.once
        self.off = self.events.off

        # REST + managers
        self.rest = RestClient(
            token,
            base_url=api_base_url,
            timeout_ms=timeout_ms,
            max_retries=max_retries,
            global_requests_per_second=global_requests_per_second,
            transport=transport,
        )
        self.messages = MessagesManager(self.rest)
        self.channels = ChannelsManager(self.rest)
        self.guilds = GuildsManager(self.rest)
        self.members = MembersManager(self.rest)
        self.roles = RolesManager(self.rest)
        self.moderation = ModerationManager(self.rest)
        self.uploads = UploadsManager(self.rest)
        self.interactions = InteractionsManager(self.rest)
        self.commands = ApplicationCommandsManager(self.rest)
        self.bot = BotManager(self.rest)
        self.users = UsersManager(self.rest)

        # Cache opcional (desativado por padrão: busca sob demanda).
        self._caches = _ClientCaches(cache_ttl_ms, cache_max_entries) if enable_cache else None

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def user_id(self) -> Snowflake | None:
        """Id da conta do bot (disponível após ``login()``)."""
        return self._user_id

    @property
    def user(self) -> User | None:
        """A conta do bot como modelo (após ``login()``)."""
        if self._application:
            return User(self, self._application.get("user") or {})
        return None

    @property
    def application(self) -> dict[str, Any] | None:
        """O bot na visão do dono (``GET /bots/@me``)."""
        return self._application

    @property
    def gateway(self) -> Gateway | None:
        return self._gateway

    @property
    def ping_ms(self) -> float | None:
        """Latência do gateway (último heartbeat → ack), em ms."""
        return self._gateway.heartbeat_latency_ms if self._gateway else None

    def is_ready(self) -> bool:
        """``True`` quando o gateway está autenticado e recebendo eventos."""
        return self._gateway is not None and self._gateway.is_ready

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def login(self) -> None:
        """Autentica e conecta.

        Valida o token (``GET /bots/@me``), conecta ao gateway (a menos que
        ``rest_only``) e emite ``ready``.
        """
        if self._destroyed:
            msg = "O cliente foi destruído"
            raise SquordTypeError(msg)
        if self._user_id is not None:
            return  # já logado

        self._logger.info("validando token do bot")
        self._application = await self.bot.fetch_current()
        self._user_id = str(self._application["user"]["id"])
        self._logger.info(
            "token validado (botId=%s, username=%s)",
            self._application.get("id"),
            self._application["user"].get("username"),
        )

        if self._rest_only:
            self._logger.info("modo REST-only: sem gateway")
            await self.events.emit(
                "ready",
                {"user": self.user, "sessionId": "", "guilds": [], "ping": None},
            )
            return

        if self._gateway is None:
            self._create_gateway()

        if self._graceful:
            self._bind_shutdown_signals(asyncio.get_running_loop())

        assert self._gateway is not None
        ready = await self._gateway.connect()
        self._user_id = str(ready.get("userId") or self._user_id)

        await self.events.emit(
            "ready",
            {
                "user": self.user,
                "sessionId": ready.get("sessionId"),
                "guilds": ready.get("guilds", []),
                "ping": self.ping_ms,
            },
        )

    async def destroy(self) -> None:
        """Encerra: fecha o gateway, cancela requisições e remove listeners."""
        if self._destroyed:
            return
        self._destroyed = True
        if self._gateway is not None:
            await self._gateway.destroy()
            self._gateway = None
        await self.rest.close()
        self.events.remove_all_listeners()

    def set_presence(
        self,
        *,
        status: PresenceStatus | str | None = None,
        custom_status: str | None = None,
        afk: bool | None = None,
    ) -> None:
        """Presença do bot: ``ONLINE``, ``IDLE``, ``DND`` ou ``INVISIBLE``."""
        if self._gateway is None:
            msg = "Conecte o gateway antes de mudar a presença (login())"
            raise SquordTypeError(msg)
        update: dict[str, Any] = {}
        if status is not None:
            update["status"] = str(status)
        if custom_status is not None:
            update["customStatus"] = custom_status
        if afk is not None:
            update["afk"] = afk
        # set_presence é async no gateway; agenda no loop
        asyncio.get_running_loop().create_task(self._gateway.set_presence(update))

    def reconnect(self) -> None:
        """Força reconexão do gateway (tenta ``resume``)."""
        if self._gateway is not None:
            self._gateway.reconnect_now()

    # ------------------------------------------------------------------
    # Permissões
    # ------------------------------------------------------------------

    async def my_permissions_in(self, channel_id: Snowflake) -> Permissions:
        """Permissões efetivas do bot em um canal (resolução local).

        Usa o cache quando habilitado. O backend continua sendo a
        autoridade final.
        """
        assert_snowflake(channel_id, "channelId")
        caches = self._caches
        channel: dict[str, Any] | None = caches.channels.get(channel_id) if caches else None
        if channel is None:
            channel = await self.channels.fetch(channel_id)
            if caches:
                caches.channels.set(channel_id, channel)
        guild_id = str(channel["guildId"])

        guild: dict[str, Any] | None = caches.guilds.get(guild_id) if caches else None
        if guild is None:
            guild = await self.guilds.fetch(guild_id)
            if caches:
                caches.guilds.set(guild_id, guild)

        roles: list[dict[str, Any]] | None = caches.roles.get(guild_id) if caches else None
        if roles is None:
            roles = await self.roles.list(guild_id)
            if caches:
                caches.roles.set(guild_id, roles)

        member_key = f"{guild_id}:{self._user_id}"
        me: dict[str, Any] | None = caches.members.get(member_key) if caches else None
        if me is None and self._user_id is not None:
            fetched = await self.members.fetch(guild_id, self._user_id)
            if fetched is not None:
                me = fetched
                if caches:
                    caches.members.set(member_key, me)
        if me is None:  # pragma: no cover — bot sempre é membro do Space instalado
            return Permissions(0)

        roles_by_id = {str(r.get("id")): r for r in roles or []}
        everyone_role = roles_by_id.get(guild_id, {})
        member_role_ids = {str(r) for r in me.get("roleIds", [])}
        role_permissions = [
            int(str(r.get("permissions", "0")))
            for rid in me.get("roleIds", [])
            if (r := roles_by_id.get(rid)) is not None
        ]
        return resolve_channel_permissions(
            everyone_permissions=int(str(everyone_role.get("permissions", "0"))),
            role_permissions=role_permissions,
            overwrites=list(channel.get("overwrites", [])),
            member_id=str(me["id"]),
            everyone_role_id=guild_id,
            member_role_ids=sorted(member_role_ids),
        )

    async def has_permissions_in(self, channel_id: Snowflake, *flags: int) -> bool:
        """Testa se o bot tem um conjunto de permissões em um canal."""
        bits = await self.my_permissions_in(channel_id)
        return has_permissions(bits, *flags)

    # ------------------------------------------------------------------
    # Gateway → eventos
    # ------------------------------------------------------------------

    def _create_gateway(self) -> None:
        gateway = Gateway(
            self._token,
            url=self._gateway_url or "wss://gateway.squord.com.br/gateway",
            connector=self._ws_connector,
            reconnect_base_ms=self._reconnect_base_ms,
        )

        gateway.on("resumed", lambda resumed: self.events.emit("resumed", resumed))
        gateway.on(
            "reconnecting",
            lambda attempt, delay_ms, code, reason: self.events.emit(
                "reconnecting",
                {"attempt": attempt, "delayMs": delay_ms, "closeCode": code, "reason": reason},
            ),
        )
        gateway.on(
            "disconnect",
            lambda code, reason, fatal: self.events.emit(
                "disconnect", {"code": code, "reason": reason, "fatal": fatal}
            ),
        )
        gateway.on(
            "invalid_session",
            lambda payload: self.events.emit(
                "warn", "Sessão do gateway não pôde ser retomada; refazendo identify"
            ),
        )

        async def on_raw(frame: dict[str, Any]) -> None:
            await self.events.emit("raw", frame)

        async def on_event(
            event_type: str, data: Any, sequence: int | None, timestamp: Any
        ) -> None:
            await self._dispatch_event(event_type, data, sequence, timestamp)

        async def on_gateway_error(error: BaseException) -> None:
            await self.events.emit("error", error)

        gateway.on("raw", on_raw)
        gateway.on("event", on_event)
        gateway.on("error", on_gateway_error)
        self._gateway = gateway

    def _bind_shutdown_signals(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._shutdown_signals_bound or sys.platform == "win32":
            return
        self._shutdown_signals_bound = True

        async def shutdown() -> None:
            self._logger.info("sinal recebido; encerrando")
            await self.destroy()
            loop.stop()

        import contextlib

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):  # pragma: no cover
                loop.add_signal_handler(
                    sig, lambda: asyncio.get_running_loop().create_task(shutdown())
                )

    async def _dispatch_event(
        self,
        event_type: str,
        data: Any,
        sequence: int | None,
        timestamp: Any,
    ) -> None:
        payload = data if isinstance(data, dict) else {}
        try:
            if event_type in {"message.created", "message.updated"}:
                await self.events.emit(event_type, Message(self, payload.get("message") or {}))
            elif event_type in {"member.joined", "member.updated"}:
                await self.events.emit(
                    event_type,
                    {
                        "guildId": payload.get("guildId"),
                        "member": Member(self, payload.get("member") or {}),
                    },
                )
            elif event_type == "guild.updated":
                await self.events.emit(event_type, Guild(self, payload.get("guild") or {}))
            elif event_type in {"channel.created", "channel.updated"}:
                await self.events.emit(event_type, Channel(self, payload.get("channel") or {}))
            elif event_type in {"role.created", "role.updated"}:
                await self.events.emit(event_type, Role(self, payload.get("role") or {}))
            elif event_type in {"thread.created", "thread.updated"}:
                await self.events.emit(event_type, Thread(self, payload.get("thread") or {}))
            elif event_type == "interaction.created":
                await self.events.emit(event_type, Interaction(self, payload))
            elif event_type in KNOWN_RAW_EVENTS:
                await self.events.emit(event_type, payload)
            else:
                await self.events.emit(
                    "unknownEvent",
                    {"type": event_type, "d": data, "s": sequence, "timestamp": timestamp},
                )
        except Exception as err:
            await self.events.emit(
                "error", err if isinstance(err, Exception) else RuntimeError(str(err))
            )
