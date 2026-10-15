"""MockGateway: um gateway do Squord simulado em memória.

Fala o protocolo real — ``hello``, ``identify``, ``ready``, ``heartbeat``,
``heartbeat.ack``, ``resume``, ``resumed``, ``invalid_session``,
``reconnect`` — para testar o ciclo de vida do cliente (login,
reconexão, resume, deduplicação) sem rede. Passe o conector em
``SquordClient(ws_connector=gateway.ws_connector)``.

Os eventos emitidos são guardados num buffer global com sequência ``s``
crescente, como o histórico do gateway real (até 500 eventos), e o
``resume`` reenvia tudo que veio depois do ``lastSequence`` informado.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from ..gateway import WSClosed

_CLOSE = "__close__"


class _ConnectionState:
    """Estado de uma conexão do lado "servidor"."""

    def __init__(self) -> None:
        self.authenticated = False
        self.session_id: str | None = None


class MockWebSocket:
    """Lado cliente da conexão: implementa o protocolo interno do gateway."""

    def __init__(self, server: MockGatewayServer) -> None:
        self._server = server
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._state = _ConnectionState()
        self._closed = False

    # ----- lado SDK (protocolo WSConnection) -----

    async def send_str(self, payload: str) -> None:
        if self._closed:
            return
        if len(payload.encode("utf-8")) > 65_536:
            self.mark_close(1009, "frame too large")
            return
        try:
            frame: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            self.mark_close(4002, "decode error")
            return
        self._server.handle_frame(self, frame)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self._closed:
            return
        self._server.handle_client_close(self, code, reason)
        self._finish_close(code, reason)

    def frames(self) -> AsyncIterator[str]:
        return self._iter_frames()

    async def _iter_frames(self) -> AsyncIterator[str]:
        while True:
            item = await self._queue.get()
            if isinstance(item, tuple) and len(item) == 3 and item[0] == _CLOSE:
                raise WSClosed(item[1], item[2])
            yield str(item)

    # ----- lado servidor -----

    def receive(self, frame: dict[str, Any]) -> None:
        if not self._closed:
            self._queue.put_nowait(json.dumps(frame))

    def mark_close(self, code: int, reason: str) -> None:
        """Fecha a conexão por decisão do servidor (entrega o close ao SDK)."""
        self._finish_close(code, reason)

    def _finish_close(self, code: int, reason: str) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put_nowait((_CLOSE, code, reason))


class MockGatewayServer:
    """Servidor de gateway simulado: um conector, muitas asserções."""

    def __init__(
        self,
        *,
        heartbeat_interval_ms: int = 30_000,
        token: str | None = None,
        ready: dict[str, Any] | None = None,
        refuse_resume_once: bool = False,
        suppress_heartbeat_ack: bool = False,
    ) -> None:
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.token = token
        self.ready_payload = ready or {}
        self.suppress_heartbeat_ack = suppress_heartbeat_ack
        self._refuse_resume_pending = refuse_resume_once
        self._connections: set[MockWebSocket] = set()
        self._event_buffer: list[tuple[str, Any, int]] = []
        self._sequence = 0
        self._known_sessions: set[str] = set()

    # ------------------------------------------------------------- --
    # Conector (protocolo esperado pelo Gateway)
    # ------------------------------------------------------------------

    async def ws_connector(self, url: str) -> MockWebSocket:
        path = url.split("?")[0]
        if not path.rstrip("/").endswith("/gateway"):
            msg = f"MockGateway: caminho inválido {url} (use wss://.../gateway)"
            raise ValueError(msg)
        socket = MockWebSocket(self)
        self._connections.add(socket)
        # hello imediato, como o real
        socket.receive(
            {
                "op": "hello",
                "d": {
                    "heartbeatIntervalMs": self.heartbeat_interval_ms,
                    "sessionId": f"mock-{id(socket):x}",
                    "protocolVersion": 1,
                },
                "timestamp": 0,
            }
        )
        return socket

    # ------------------------------------------------------------- --
    # Estado e diagnóstico
    # ------------------------------------------------------------------

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def last_sequence(self) -> int:
        return self._event_buffer[-1][2] if self._event_buffer else 0

    @property
    def total_events(self) -> int:
        return self._sequence

    # ------------------------------------------------------------- --
    # API de simulação
    # ------------------------------------------------------------------

    def emit_event(self, event_type: str, data: Any) -> None:
        """Emite um evento durável: buffer com ``s`` crescente + entrega."""
        self._sequence += 1
        self._event_buffer.append((event_type, data, self._sequence))
        if len(self._event_buffer) > 500:
            self._event_buffer.pop(0)
        for socket in list(self._connections):
            if socket._state.authenticated:
                socket.receive(
                    {
                        "op": "event",
                        "type": event_type,
                        "d": data,
                        "s": self._sequence,
                        "timestamp": 0,
                    }
                )

    def send_event_with_sequence(self, event_type: str, data: Any, sequence: int) -> None:
        """Envia um evento com sequência arbitrária (treina a deduplicação)."""
        for socket in list(self._connections):
            if socket._state.authenticated:
                socket.receive(
                    {"op": "event", "type": event_type, "d": data, "s": sequence, "timestamp": 0}
                )

    def send_frame(self, frame: dict[str, Any]) -> None:
        """Envia um frame cru às conexões autenticadas (sem ``s``)."""
        for socket in list(self._connections):
            if socket._state.authenticated:
                socket.receive({**frame, "timestamp": 0})

    def close_all(self, code: int, reason: str) -> None:
        """Fecha as conexões com um código (ex.: 4009 para treinar resume)."""
        for socket in list(self._connections):
            self.handle_client_close(socket, code, reason, by_server=True)
            socket.mark_close(code, reason)

    def request_reconnect(self, reason: str = "gateway shutting down") -> None:
        """Pede reconexão (frame ``reconnect`` + fechamento 4007, como o real)."""
        for socket in list(self._connections):
            socket.receive(
                {"op": "reconnect", "d": {"reason": reason, "resumable": True}, "timestamp": 0}
            )
        self.close_all(4007, reason)

    def expire_history(self) -> None:
        """Descarta o histórico (o próximo resume falha com ``invalid_session``)."""
        self._event_buffer.clear()

    def reset(self) -> None:
        self._connections.clear()
        self._event_buffer.clear()
        self._sequence = 0
        self._known_sessions.clear()
        self._refuse_resume_pending = False

    # ------------------------------------------------------------- --
    # "Servidor"
    # ------------------------------------------------------------------

    def handle_frame(self, socket: MockWebSocket, frame: dict[str, Any]) -> None:
        op = frame.get("op")
        data = frame.get("d") or {}
        state = socket._state

        if op == "identify":
            if state.authenticated:
                socket.mark_close(4005, "already authenticated")
                return
            if self.token is not None and data.get("token") != self.token:
                socket.mark_close(4004, "invalid token")
                return
            session_id = f"mock-{id(socket):x}"
            self._known_sessions.add(session_id)
            state.authenticated = True
            state.session_id = session_id
            socket.receive(
                {
                    "op": "ready",
                    "d": {
                        "sessionId": session_id,
                        "userId": self.ready_payload.get("userId", "1300000000000000010"),
                        "guilds": self.ready_payload.get("guilds", []),
                        "resumeGatewayUrl": "wss://gateway.squord.com.br/gateway",
                    },
                    "timestamp": 0,
                }
            )
            return

        if op == "resume":
            session_id = str(data.get("sessionId"))
            last_sequence = int(data.get("lastSequence") or 0)
            if self._refuse_resume_pending:
                self._refuse_resume_pending = False
                socket.receive({"op": "invalid_session", "d": {"resumable": False}, "timestamp": 0})
                return
            if session_id not in self._known_sessions:
                socket.receive({"op": "invalid_session", "d": {"resumable": False}, "timestamp": 0})
                return
            state.authenticated = True
            state.session_id = session_id
            replay = [(t, d, s) for (t, d, s) in self._event_buffer if s > last_sequence]
            for event_type, event_data, sequence in replay:
                socket.receive(
                    {
                        "op": "event",
                        "type": event_type,
                        "d": event_data,
                        "s": sequence,
                        "timestamp": 0,
                    }
                )
            last = replay[-1][2] if replay else last_sequence
            socket.receive(
                {
                    "op": "resumed",
                    "d": {"sessionId": session_id, "replayed": len(replay), "sequence": last},
                    "timestamp": 0,
                }
            )
            return

        if op == "heartbeat":
            if not state.authenticated:
                socket.mark_close(4003, "not authenticated")
                return
            if not self.suppress_heartbeat_ack:
                socket.receive(
                    {"op": "heartbeat.ack", "d": {"sequence": self.last_sequence}, "timestamp": 0}
                )
            return

        # presence.update, subscribe, unsubscribe, typing.start,
        # voice.state.update: aceitos e ignorados, como o real.

    def handle_client_close(
        self, socket: MockWebSocket, code: int, reason: str, *, by_server: bool = False
    ) -> None:
        self._connections.discard(socket)
        socket._state = _ConnectionState()
