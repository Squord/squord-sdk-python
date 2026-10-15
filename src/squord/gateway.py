"""Gateway do Squord: WebSocket que entrega eventos em tempo real.

Ciclo de vida (https://docs.squord.com.br/gateway/visao-geral):

1. Abre a conexão; o servidor envia ``hello`` (intervalo de heartbeat).
2. O bot envia ``identify`` com o token em até 15 segundos.
3. O servidor responde ``ready``; os eventos passam a chegar.
4. O bot envia ``heartbeat`` a cada ``heartbeatIntervalMs``; o servidor
   responde ``heartbeat.ack``. Se o ack de um heartbeat não chega até o
   próximo, a conexão é considerada **zumbi** e é refeita com ``resume``.
5. Após uma queda, o bot reconecta e envia ``resume`` com a última
   sequência; o servidor reenvia os eventos perdidos e depois envia
   ``resumed``. Se não puder retomar, responde ``invalid_session`` na
   mesma conexão, e o bot faz ``identify`` de novo.

Códigos de fechamento seguem a tabela oficial: 4004/4013/4014 não são
retomáveis; 4001/4002/4005/4012 são erros do bot; os demais reconectam com
backoff exponencial e jitter, tentando ``resume``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from .enums import PresenceStatus
from .errors import GatewayError
from .events import EventEmitter
from .logger import get_logger
from .types import (
    GatewayHello,
    GatewayPresenceUpdate,
    GatewayReady,
    GatewayResumed,
)
from .utils import backoff_delay, new_request_id

DEFAULT_URL = "wss://gateway.squord.com.br/gateway"
PROTOCOL_VERSION = 1

FATAL_CLOSE_CODES = {4004, 4013, 4014}
BOT_BUG_CLOSE_CODES = {4001, 4002, 4005, 4012}


class WSClosed(Exception):
    """A conexão fechou com o código/reason informados."""

    def __init__(self, code: int = 1000, reason: str = "") -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket fechou (código {code}{f': {reason}' if reason else ''})")


class WSConnection(Protocol):
    """Conexão WebSocket mínima usada pelo gateway (aiohttp ou mock)."""

    async def send_str(self, payload: str) -> None: ...

    async def close(self, code: int = 1000, reason: str = "") -> None: ...

    def frames(self) -> AsyncIterator[str]:
        """Iterador de frames de texto; levanta ``WSClosed`` ao fechar."""


WSConnector = Callable[[str], Awaitable[WSConnection]]


# ------------------------------------------------------------------ --
# Implementação com aiohttp
# ---------------------------------------------------------------------


class AiohttpWSConnection:
    """Adapta ``ClientWebSocketResponse`` do aiohttp ao protocolo interno."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws

    async def send_str(self, payload: str) -> None:
        await self._ws.send_str(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        await self._ws.close(code=code, message=reason.encode() if reason else None)

    def frames(self) -> AsyncIterator[str]:
        return self._iter_frames()

    async def _iter_frames(self) -> AsyncIterator[str]:
        import aiohttp

        ws = self._ws
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                yield str(msg.data)
            elif msg.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSED,
            ):
                raise WSClosed(int(msg.data or 1000), str(msg.extra or ""))
        raise WSClosed(1000, "")


async def aiohttp_ws_connector() -> WSConnector:
    """Fábrica padrão de conexões: ``aiohttp`` com sessão própria."""
    import aiohttp

    session = aiohttp.ClientSession()

    async def connect(url: str) -> WSConnection:
        ws = await session.ws_connect(url)
        return AiohttpWSConnection(ws)

    return connect


# ------------------------------------------------------------------ --
# Gateway
# ---------------------------------------------------------------------


class GatewayStatus(str):
    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    DESTROYED = "destroyed"


class Gateway(EventEmitter):
    """Sessão do gateway com reconexão, resume e heartbeat."""

    def __init__(
        self,
        token: str,
        *,
        url: str = DEFAULT_URL,
        connector: WSConnector | None = None,
        auto_reconnect: bool = True,
        reconnect_base_ms: float = 1_000,
        logger: Any = None,
    ) -> None:
        super().__init__()
        self.url = url
        self.token = token
        self._connector: WSConnector | None = connector
        self.auto_reconnect = auto_reconnect
        self.reconnect_base_ms = reconnect_base_ms
        self._logger = logger or get_logger("gateway")

        self.status: str = GatewayStatus.IDLE
        self.heartbeat_latency_ms: float | None = None
        self.reconnect_count = 0
        self.events_received = 0
        self.events_dropped = 0

        self._session_id: str | None = None
        self._resume_url: str | None = None
        self._last_sequence: int | None = None
        self._established = False
        self._conn: WSConnection | None = None
        self._destroyed = False
        self._closing_by_client = False
        self._reconnect_requested = False
        self._awaiting_ack = False
        self._heartbeat_interval_ms: float | None = None
        self._sent_at: float | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._ready_future: asyncio.Future[GatewayReady] | None = None
        self._reconnect_attempts = 0

    # ------------------------------------------------------------ --
    # API pública
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def sequence(self) -> int | None:
        return self._last_sequence

    @property
    def is_ready(self) -> bool:
        return self.status == GatewayStatus.READY

    async def connect(self) -> GatewayReady:
        """Conecta e resolve quando a sessão está pronta.

        Em quedas transitórias segue tentando com backoff — só é rejeitada
        em erros não retomáveis (token inválido/revogado, conta suspensa,
        sessões demais, erro de protocolo) ou se o gateway for destruído.
        """
        if self._destroyed:
            raise GatewayError("O gateway foi destruído", code="GATEWAY_DESTROYED")
        if self.is_ready:
            raise GatewayError("O gateway já está conectado", code="GATEWAY_CONNECTED")
        if self._run_task is not None and not self._run_task.done():
            raise GatewayError("Conexão em andamento", code="GATEWAY_CONNECTING")

        if self._connector is None:
            self._connector = await aiohttp_ws_connector()

        self._closing_by_client = False
        loop = asyncio.get_running_loop()
        self._ready_future = loop.create_future()
        self._run_task = asyncio.create_task(self._run(), name="squord-gateway")
        assert self._ready_future is not None
        return await self._ready_future

    async def destroy(self) -> None:
        """Fecha a conexão, encerra reconexões e descarta a sessão."""
        if self._destroyed:
            return
        self._destroyed = True
        self._closing_by_client = True
        self._stop_heartbeat()
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
        if self._conn is not None:
            with contextlib.suppress(Exception):
                await self._conn.close(1000, "client shutdown")
            self._conn = None
        if self._run_task is not None:
            self._run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._run_task
            self._run_task = None
        self.status = GatewayStatus.DESTROYED
        if self._ready_future is not None and not self._ready_future.done():
            self._ready_future.set_exception(
                GatewayError("Gateway destruído", code="GATEWAY_DESTROYED")
            )

    def invalidate_session(self) -> None:
        """Descarta a sessão: a próxima conexão fará ``identify`` limpo."""
        self._session_id = None
        self._resume_url = None
        self._last_sequence = None

    def reconnect_now(self) -> None:
        """Força reconexão imediata (que tentará ``resume``)."""
        self._reconnect_requested = True
        if self._conn is not None:
            self._run_task_close_soon()

    def _run_task_close_soon(self) -> None:
        asyncio.get_running_loop().create_task(self._close_conn(4000, "manual reconnect"))

    async def _close_conn(self, code: int, reason: str) -> None:
        conn = self._conn
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close(code, reason)

    async def set_presence(self, presence: GatewayPresenceUpdate | dict[str, Any]) -> None:
        """Envia ``presence.update``. Vale também nas próximas conexões."""
        if self._conn is None:
            raise GatewayError(
                "Sem conexão para atualizar a presença", code="GATEWAY_NOT_CONNECTED"
            )
        await self._send("presence.update", dict(presence))

    # ------------------------------------------------------------ --
    # Loop principal
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        assert self._connector is not None  # garantido por connect()
        while not self._destroyed:
            self.status = (
                GatewayStatus.RECONNECTING if self._session_id else GatewayStatus.CONNECTING
            )
            try:
                conn = await self._connector(self._resume_url or self.url)
            except Exception as err:
                if not await self._handle_connect_failure(err):
                    return
                continue

            self._conn = conn
            try:
                async for frame in conn.frames():
                    await self._handle_frame(frame)
            except WSClosed as closed:
                self._conn = None
                if not await self._handle_close(closed.code, closed.reason):
                    return
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self._conn = None
                self._stop_heartbeat()
                await self.emit(
                    "error",
                    GatewayError(f"Erro inesperado no gateway: {err}", code="GATEWAY_UNEXPECTED"),
                )
                if not await self._handle_close(1006, str(err)):
                    return

            if self._destroyed or not self.auto_reconnect:
                self.status = GatewayStatus.DISCONNECTED
                return
            await self._backoff_and_retry()

    async def _handle_connect_failure(self, err: BaseException) -> bool:
        """Trata falha na abertura do socket. Retorna ``False`` para parar.

        Falhas transitórias não rejeitam ``connect()``: o loop segue com
        backoff, como a documentação recomenda. Só rejeita quando não há
        reconexão automática (ou o gateway foi destruído).
        """
        self._established = False
        if self._destroyed:
            self.status = GatewayStatus.DISCONNECTED
            return False
        if not self.auto_reconnect:
            self.status = GatewayStatus.DISCONNECTED
            if self._ready_future is not None and not self._ready_future.done():
                self._ready_future.set_exception(
                    GatewayError(
                        f"Não foi possível conectar ao gateway: {err}",
                        close_code=None,
                        code="GATEWAY_CONNECT_FAILED",
                    )
                )
            return False
        await self._backoff_and_retry()
        return True

    async def _backoff_and_retry(self) -> None:
        attempt = self._reconnect_attempts
        delay_ms = backoff_delay(attempt, base_ms=self.reconnect_base_ms)
        self._reconnect_attempts += 1
        self.reconnect_count += 1
        self.status = GatewayStatus.RECONNECTING
        await self.emit("reconnecting", attempt, delay_ms, None, "backoff")
        self._logger.info("reconectando (tentativa %d, aguardando %.0f ms)", attempt, delay_ms)
        await asyncio.sleep(delay_ms / 1_000)

    async def _handle_close(self, code: int, reason: str) -> bool:
        """Classifica um fechamento. Retorna ``False`` para parar o loop."""
        self._stop_heartbeat()
        was_established = self._established
        self._established = False

        if self._reconnect_requested:
            self._reconnect_requested = False
            await self.emit("disconnect", code, reason, False)
            return True  # o loop reconecta (resume)

        if self._destroyed or self._closing_by_client:
            self._closing_by_client = False
            await self.emit("disconnect", code, reason, False)
            if self._ready_future is not None and not self._ready_future.done():
                self._ready_future.set_exception(WSClosed(code, reason))
            return False

        fatal = code in FATAL_CLOSE_CODES
        bot_bug = code in BOT_BUG_CLOSE_CODES
        await self.emit("disconnect", code, reason, fatal or bot_bug)

        if fatal or bot_bug:
            error = GatewayError(
                describe_close(code, reason, fatal, bot_bug),
                close_code=code,
                reason=reason,
                code="GATEWAY_FATAL" if fatal else "GATEWAY_BOT_BUG",
            )
            await self.emit("error", error)
            self.status = GatewayStatus.DISCONNECTED
            if self._ready_future is not None and not self._ready_future.done():
                self._ready_future.set_exception(error)
            return False

        handshake_sem_reconexao = not was_established and not self.auto_reconnect
        if (
            handshake_sem_reconexao
            and self._ready_future is not None
            and not self._ready_future.done()
        ):
            self._ready_future.set_exception(
                GatewayError(
                    f"A conexão fechou antes do identify ser confirmado (código {code})",
                    close_code=code,
                    reason=reason,
                )
            )
        return True

    # ------------------------------------------------------------ --
    # Frames
    # ------------------------------------------------------------------

    async def _handle_frame(self, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            self._logger.warning("frame não-JSON recebido; ignorado")
            return
        await self.emit("raw", frame)

        op = frame.get("op")
        data = frame.get("d") or {}

        if op == "hello":
            await self._handle_hello(data)
        elif op == "ready":
            await self._handle_ready(data)
        elif op == "resumed":
            await self._handle_resumed(data)
        elif op == "heartbeat.ack":
            self._awaiting_ack = False
            if self._sent_at is not None:
                self.heartbeat_latency_ms = (
                    asyncio.get_running_loop().time() - self._sent_at
                ) * 1_000
            await self.emit("heartbeat.ack", data.get("sequence"))
        elif op == "invalid_session":
            await self.emit("invalid_session", data)
            self.invalidate_session()
            # A conexão continua aberta: identify imediato (prazo de 15 s reinicia).
            await self._send("identify", {"token": self.token, "protocolVersion": PROTOCOL_VERSION})
        elif op == "reconnect":
            await self.emit("server_reconnect", data)
            self._arm_reconnect_watchdog()
        elif op == "error":
            await self.emit("server_error", data)
        elif op == "event":
            await self._handle_event(frame)
        else:  # pragma: no cover — protocolo futuro
            self._logger.debug("opcode desconhecido: %s", op)

    async def _handle_hello(self, data: GatewayHello | dict[str, Any]) -> None:
        interval = int(data.get("heartbeatIntervalMs") or 30_000)
        self._heartbeat_interval_ms = interval
        if self._session_id is not None:
            await self._send(
                "resume",
                {
                    "token": self.token,
                    "sessionId": self._session_id,
                    "lastSequence": self._last_sequence or 0,
                },
            )
        else:
            await self._send("identify", {"token": self.token, "protocolVersion": PROTOCOL_VERSION})
        self._start_heartbeat()

    async def _handle_ready(self, data: GatewayReady | dict[str, Any]) -> None:
        self._session_id = str(data.get("sessionId"))
        self._resume_url = data.get("resumeGatewayUrl") or self.url
        self._last_sequence = None
        self._established = True
        self._reconnect_attempts = 0
        self.status = GatewayStatus.READY
        self._logger.info("sessão pronta (%s)", self._session_id)
        await self.emit("ready", data)
        self._resolve_ready(data)

    async def _handle_resumed(self, data: GatewayResumed | dict[str, Any]) -> None:
        self._session_id = str(data.get("sessionId"))
        self._established = True
        self._reconnect_attempts = 0
        self.status = GatewayStatus.READY
        self._logger.info("sessão retomada (%d eventos reenviados)", int(data.get("replayed") or 0))
        await self.emit("resumed", data)
        self._resolve_ready(
            {
                "sessionId": self._session_id,
                "userId": "",
                "guilds": [],
                "resumeGatewayUrl": self._resume_url or self.url,
            }
        )

    async def _handle_event(self, frame: dict[str, Any]) -> None:
        self.events_received += 1
        sequence = frame.get("s")
        if isinstance(sequence, int):
            if self._last_sequence is not None and sequence <= self._last_sequence:
                self.events_dropped += 1
                return
            self._last_sequence = sequence
        await self.emit(
            "event",
            frame.get("type"),
            frame.get("d"),
            sequence,
            frame.get("timestamp"),
        )

    def _resolve_ready(self, ready: GatewayReady | dict[str, Any]) -> None:
        if self._ready_future is not None and not self._ready_future.done():
            self._ready_future.set_result(dict(ready))  # type: ignore[arg-type]

    def _arm_reconnect_watchdog(self) -> None:
        """O fechamento 4007 chega em seguida; watchdog fecha se não vier."""

        async def watchdog() -> None:
            await asyncio.sleep(5)
            if not self._destroyed and self._conn is not None:
                self._logger.warning("watchdog de reconexão disparado")
                with contextlib.suppress(Exception):
                    await self._conn.close(4000, "reconnect watchdog")

        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
        self._watchdog_task = asyncio.create_task(watchdog())

    # ------------------------------------------------------------ --
    # Heartbeat
    # ------------------------------------------------------------------

    def _start_heartbeat(self) -> None:
        self._stop_heartbeat()
        if self._heartbeat_interval_ms is None:
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="squord-heartbeat")

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        self._awaiting_ack = False

    async def _heartbeat_loop(self) -> None:
        interval = self._heartbeat_interval_ms or 30_000
        # Espalha o primeiro heartbeat por uma fração aleatória do intervalo,
        # para que uma reconexão em massa não chegue toda junta.
        first = interval * random.uniform(0.25, 1.0)
        await asyncio.sleep(first / 1_000)
        while not self._destroyed:
            if self._awaiting_ack:
                # Zumbi: o heartbeat anterior não foi confirmado dentro de um
                # intervalo — fechar e retomar, como a documentação manda.
                self._logger.warning("sem heartbeat.ack; conexão zumbi, reconectando")
                await self._close_conn(4000, "zombie connection")
                return
            self._sent_at = asyncio.get_running_loop().time()
            await self._send("heartbeat", {"s": self._last_sequence})
            self._awaiting_ack = True
            await asyncio.sleep(interval / 1_000)

    # ------------------------------------------------------------ --

    async def _send(self, op: str, data: Any) -> None:
        conn = self._conn
        if conn is None:
            return
        payload = json.dumps({"op": op, "d": data, "requestId": new_request_id()})
        if len(payload.encode("utf-8")) > 65_536:
            await self.emit(
                "error",
                GatewayError(f"Frame {op} excede 65536 bytes e não foi enviado"),
            )
            return
        await conn.send_str(payload)

    # Latência via heartbeat
    @property
    def ping_ms(self) -> float | None:
        return self.heartbeat_latency_ms


def describe_close(code: int, reason: str, fatal: bool, bot_bug: bool) -> str:
    """Mensagem de fechamento fiel à tabela oficial de códigos."""
    if fatal:
        if code == 4004:
            return (
                f"O token foi recusado (4004{f': {reason}' if reason else ''}). Ele foi trocado, "
                "revogado, ou o bot/dono foi excluído ou suspenso. Não reconecte com o mesmo token."
            )
        if code == 4014:
            return "O bot já tem 2 sessões simultâneas (4014). Feche uma das sessões antes de reconectar."
        return (
            f"A conta do bot está suspensa (4013{f': {reason}' if reason else ''}). Não reconecte."
        )
    if bot_bug:
        return f"Erro de protocolo do bot (código {code}{f': {reason}' if reason else ''}). Corrija o código antes de tentar de novo."
    return f"Conexão do gateway fechou (código {code}{f': {reason}' if reason else ''})."


__all__ = [
    "DEFAULT_URL",
    "AiohttpWSConnection",
    "Gateway",
    "GatewayStatus",
    "PresenceStatus",
    "WSClosed",
    "WSConnection",
    "WSConnector",
    "aiohttp_ws_connector",
]
