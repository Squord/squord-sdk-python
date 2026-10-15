"""MockRest: um servidor REST em memória para testar bots sem rede.

Implementa o protocolo ``Transport`` do SDK (passe em
``SquordClient(transport=...)``) e responde às rotas registradas com
padrões tipo ``GET /channels/:channel_id/messages``. Rotas não registradas
respondem ``404 NOT_FOUND`` com o envelope oficial; o header
``Authorization`` é conferido quando ``expected_token`` é definido.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..http import TransportRequest, TransportResponse

_CLOSE = object()  # sentinel interno


@dataclass(slots=True)
class MockRestCall:
    method: str
    path: str
    params: dict[str, str]
    query: dict[str, str]
    body: Any
    headers: dict[str, str]
    request_id: str | None


@dataclass(slots=True)
class MockRouteMatch:
    params: dict[str, str]
    query: dict[str, str]
    body: Any
    call: MockRestCall


RouteHandler = Any  # (match) -> (status, body) | {"status", "body", "headers"} | body


def _match_segments(pattern: list[str], path: list[str]) -> dict[str, str] | None:
    if len(pattern) != len(path):
        return None
    params: dict[str, str] = {}
    for expected, actual in zip(pattern, path, strict=False):
        if expected.startswith(":"):
            params[expected[1:]] = actual
        elif expected != actual:
            return None
    return params


class MockRest:
    """Transporte REST simulado, com registro de rotas e histórico."""

    def __init__(self, *, expected_token: str | None = None) -> None:
        self.expected_token = expected_token
        self._routes: list[tuple[str, list[str], RouteHandler]] = []
        self._calls: list[MockRestCall] = []
        self._failing: Any = None

    # ------------------------------------------------------------ --
    # Registro de rotas
    # ------------------------------------------------------------------

    def on(self, method: str, pattern: str, handler: RouteHandler) -> MockRest:
        """Registra uma rota (substitui uma rota igual já registrada).

        O handler devolve ``{"status", "body"}`` ou corpo puro (status 200).
        """
        segments = [s for s in pattern.split("/") if s]
        self._routes = [
            route for route in self._routes if not (route[0] == method.upper() and route[1] == segments)
        ]
        self._routes.append((method.upper(), segments, handler))
        return self

    def get(self, pattern: str, handler: RouteHandler) -> MockRest:
        return self.on("GET", pattern, handler)

    def post(self, pattern: str, handler: RouteHandler) -> MockRest:
        return self.on("POST", pattern, handler)

    def put(self, pattern: str, handler: RouteHandler) -> MockRest:
        return self.on("PUT", pattern, handler)

    def patch(self, pattern: str, handler: RouteHandler) -> MockRest:
        return self.on("PATCH", pattern, handler)

    def delete(self, pattern: str, handler: RouteHandler) -> MockRest:
        return self.on("DELETE", pattern, handler)

    def fail_with(self, handler: Any) -> None:
        """Força falha em todas as requisições (ex.: simular queda de rede)."""
        self._failing = handler

    def clear_failure(self) -> None:
        self._failing = None

    @property
    def call_log(self) -> list[MockRestCall]:
        """Histórico de chamadas recebidas."""
        return list(self._calls)

    @property
    def last_call(self) -> MockRestCall | None:
        return self._calls[-1] if self._calls else None

    def reset(self) -> None:
        """Remove rotas, histórico e falha forçada."""
        self._routes.clear()
        self._calls.clear()
        self._failing = None

    # ------------------------------------------------------------ --
    # Protocolo Transport
    # ------------------------------------------------------------------

    async def request(self, request: TransportRequest) -> TransportResponse:
        parsed = urlparse(request.url)
        path_segments = [s for s in parsed.path.split("/") if s]
        query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        body = request.json_body if request.json_body is not None else request.data

        call = MockRestCall(
            method=request.method,
            path=parsed.path,
            params={},
            query=query,
            body=body,
            headers=dict(request.headers),
            request_id=request.headers.get("x-request-id"),
        )
        self._calls.append(call)

        if self._failing is not None:
            result = self._failing(call)
            if hasattr(result, "throw"):
                await result.throw(ValueError("network failure"))
            raise ValueError("fetch failed (mock)")

        if self.expected_token is not None:
            expected = f"Bot {self.expected_token}"
            if request.headers.get("Authorization") != expected:
                return self._json(
                    401, {"statusCode": 401, "code": "INVALID_TOKEN", "message": "Invalid token"}
                )

        for method, pattern, handler in self._routes:
            if method != request.method:
                continue
            params = _match_segments(pattern, path_segments)
            if params is None:
                continue
            call.params = dict(params)
            match = MockRouteMatch(params=dict(params), query=query, body=body, call=call)
            response = handler(match)
            if isinstance(response, dict) and "status" in response:
                return self._json(
                    int(response.get("status", 200)),
                    response.get("body"),
                    response.get("headers") or {},
                )
            if isinstance(response, tuple):
                status, payload = response
                return self._json(int(status), payload)
            return self._json(200, response)

        return self._json(
            404,
            {
                "statusCode": 404,
                "code": "NOT_FOUND",
                "message": f"Rota não mockada: {request.method} {parsed.path}",
            },
        )

    async def close(self) -> None:
        return None

    # ------------------------------------------------------------ --

    @staticmethod
    def _json(status: int, body: Any, headers: dict[str, str] | None = None) -> TransportResponse:
        if body is None:
            payload = b""
        elif isinstance(body, (bytes, bytearray)):
            payload = bytes(body)
        else:
            payload = json.dumps(body).encode("utf-8")
        response_headers = {"x-request-id": "mock-request-id"}
        if payload:
            response_headers["content-type"] = "application/json"
        for key, value in (headers or {}).items():
            response_headers[str(key).lower()] = str(value)
        return TransportResponse(status, response_headers, payload)
