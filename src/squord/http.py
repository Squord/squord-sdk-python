"""Cliente REST do Squord (async).

Encapsula ``https://api.squord.com.br/api/v1`` com:

- autenticação por token de bot (``Authorization: Bot sqb_...``);
- timeout configurável por requisição;
- ``x-request-id`` em toda requisição (o valor volta nos erros);
- respeito aos limites de taxa: espera ``details.retryAfter`` em 429,
  observa os headers ``X-RateLimit-*`` e aplica um teto global conservador;
- retentativas para falhas transitórias (429, 5xx, rede) **somente em
  operações idempotentes ou protegidas por ``nonce``** — a regra de ouro:
  nunca repetir automaticamente uma operação sem saber se a primeira foi
  processada;
- erros tipados (veja ``squord.errors``).

O transporte HTTP é uma abstração mínima (``Transport``): a implementação
real usa ``aiohttp``; os testes injetam o ``MockRest`` de
``squord.testing``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode

from .errors import (
    NetworkError,
    RateLimitError,
    RequestTimeoutError,
    SquordAPIError,
    make_api_error,
)
from .logger import get_logger
from .types import CursorPaginationParams
from .utils import backoff_delay, new_request_id

DEFAULT_BASE_URL = "https://api.squord.com.br/api/v1"
DEFAULT_TIMEOUT_MS = 15_000
DEFAULT_MAX_RETRIES = 3


# --------------------------------------------------------------------- --
# Transporte
# ----------------------------------------------------------------------


@dataclass(slots=True)
class TransportRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    json_body: Any | None = None
    data: bytes | None = None


@dataclass(slots=True)
class TransportResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class Transport(Protocol):
    """Abstração mínima de HTTP — aiohttp na produção, mock nos testes."""

    async def request(self, request: TransportRequest) -> TransportResponse: ...

    async def close(self) -> None: ...


class AiohttpTransport:
    """Transporte real com ``aiohttp`` (uma ``ClientSession`` própria)."""

    def __init__(self) -> None:
        import aiohttp  # import tardio: mantém o aiohttp confinado aqui

        self._aiohttp = aiohttp
        self._session: aiohttp.ClientSession | None = None

    def _ensure_session(self) -> Any:
        if self._session is None or self._session.closed:
            self._session = self._aiohttp.ClientSession()
        return self._session

    async def request(self, request: TransportRequest) -> TransportResponse:
        session = self._ensure_session()
        kwargs: dict[str, Any] = {"headers": dict(request.headers)}
        if request.json_body is not None:
            kwargs["json"] = request.json_body
        elif request.data is not None:
            kwargs["data"] = request.data
        response = await session.request(request.method, request.url, **kwargs)
        try:
            body = await response.read()
            headers = {str(k): str(v) for k, v in response.headers.items()}
        finally:
            response.release()
        return TransportResponse(response.status, headers, body)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()


# --------------------------------------------------------------------- --
# Cliente REST
# ----------------------------------------------------------------------


@dataclass(slots=True)
class RequestOptions:
    query: dict[str, str | int | bool | None] | None = None
    body: Any | None = None
    request_id: str | None = None
    auth: bool = True
    #: Se a operação pode ser repetida com segurança após falha incerta
    #: (timeout de rede, 5xx). Padrão: True para GET/PUT/DELETE, False para POST.
    retryable: bool | None = None


@dataclass(slots=True)
class RestResponse:
    data: Any
    status: int
    headers: dict[str, str]
    request_id: str | None
    request: TransportRequest


@dataclass(slots=True)
class RateLimitState:
    limit: int | None = None
    remaining: int | None = None
    reset: float | None = None  # segundos Unix


class RestClient:
    """Cliente REST com política completa de erros, retries e rate limits."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        global_requests_per_second: int = 45,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self._logger = get_logger("http")
        self._transport = transport if transport is not None else AiohttpTransport()
        self._bucket_states: dict[str, RateLimitState] = {}
        self._bucket_blocked_until: dict[str, float] = {}
        self._global_window: list[float] = []
        self._global_limit = global_requests_per_second if global_requests_per_second > 0 else None
        self._closed = False

    @property
    def transport(self) -> Transport:
        """O transporte em uso (exposto para uploads e testes)."""
        return self._transport

    # -------------------------------------------------------------- --
    # Verbos
    # ------------------------------------------------------------------

    async def get(self, path: str, options: RequestOptions | None = None) -> Any:
        return await self.request("GET", path, options)

    async def post(self, path: str, body: Any = None, options: RequestOptions | None = None) -> Any:
        options = options or RequestOptions()
        options.body = body
        return await self.request("POST", path, options)

    async def put(self, path: str, body: Any = None, options: RequestOptions | None = None) -> Any:
        options = options or RequestOptions()
        options.body = body
        return await self.request("PUT", path, options)

    async def patch(
        self, path: str, body: Any = None, options: RequestOptions | None = None
    ) -> Any:
        options = options or RequestOptions()
        options.body = body
        return await self.request("PATCH", path, options)

    async def delete(self, path: str, options: RequestOptions | None = None) -> Any:
        return await self.request("DELETE", path, options)

    async def request(self, method: str, path: str, options: RequestOptions | None = None) -> Any:
        response = await self.request_raw(method, path, options)
        return response.data

    async def request_raw(
        self,
        method: str,
        path: str,
        options: RequestOptions | None = None,
    ) -> RestResponse:
        if self._closed:
            raise SquordAPIError(
                {"statusCode": 0, "code": "SDK_DESTROYED", "message": "O cliente foi destruído"}, 0
            )

        options = options or RequestOptions()
        retryable = options.retryable if options.retryable is not None else method != "POST"
        url = self._build_url(path, options.query)
        request_id = options.request_id or new_request_id()
        route_key = route_key_of(method, path)
        last_error: BaseException | None = None

        for attempt in range(self.max_retries + 1):
            await self._wait_for_bucket(route_key)
            await self._acquire_global_slot()

            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "x-request-id": request_id,
            }
            if options.auth:
                headers["Authorization"] = f"Bot {self.token}"

            transport_request = TransportRequest(
                method=method,
                url=url,
                headers=headers,
                json_body=options.body if options.body is not None else None,
            )

            try:
                response = await asyncio.wait_for(
                    self._transport.request(transport_request),
                    timeout=self.timeout_ms / 1_000,
                )
            except asyncio.TimeoutError:
                last_error = RequestTimeoutError(method, path, self.timeout_ms)
                if retryable and attempt < self.max_retries:
                    await asyncio.sleep(backoff_delay(attempt, base_ms=500, max_ms=8_000) / 1_000)
                    continue
                raise last_error from None
            except asyncio.CancelledError:
                raise
            except Exception as err:
                last_error = NetworkError(f"Falha de rede em {method} {path}: {err}", cause=err)
                if retryable and attempt < self.max_retries:
                    await asyncio.sleep(backoff_delay(attempt, base_ms=500, max_ms=8_000) / 1_000)
                    continue
                raise last_error from err

            self._record_bucket_state(route_key, response.headers)

            if 200 <= response.status < 300:
                return RestResponse(
                    data=self._parse_body(response),
                    status=response.status,
                    headers=response.headers,
                    request_id=response.headers.get("x-request-id") or request_id,
                    request=transport_request,
                )

            api_error = self._to_api_error(response)
            last_error = api_error

            if isinstance(api_error, RateLimitError):
                if attempt < self.max_retries:
                    wait_ms = api_error.retry_after * 1_000
                    self._logger.warning(
                        "rate limit, aguardando %d ms (bucket=%s)", wait_ms, api_error.bucket
                    )
                    await asyncio.sleep(wait_ms / 1_000)
                    continue
                raise RateLimitError(
                    dict(api_error.body),
                    api_error.status,
                    api_error.request_id,
                    exhausted_retries=True,
                ) from None

            if api_error.status >= 500 and retryable and attempt < self.max_retries:
                backoff_ms = backoff_delay(attempt, base_ms=500, max_ms=8_000)
                self._logger.warning("erro %d, repetindo (tentativa %d)", api_error.status, attempt)
                await asyncio.sleep(backoff_ms / 1_000)
                continue

            if (
                api_error.status == 409
                and api_error.code in {"COMMANDS_CONFLICT", "THREAD_CHANGED"}
                and attempt < self.max_retries
            ):
                await asyncio.sleep(
                    (250 + backoff_delay(attempt, base_ms=200, max_ms=2_000)) / 1_000
                )
                continue

            raise api_error

        raise last_error or SquordAPIError({"message": "Requisição falhou"}, 0)  # pragma: no cover

    async def close(self) -> None:
        """Encerra o transporte: novas requisições falham imediatamente."""
        self._closed = True
        await self._transport.close()

    def bucket_state(self, method: str, path: str) -> RateLimitState | None:
        """Estado de rate limit conhecido para uma rota (diagnóstico)."""
        return self._bucket_states.get(route_key_of(method, path))

    # -------------------------------------------------------------- --
    # Internos
    # ------------------------------------------------------------------

    def _build_url(self, path: str, query: dict[str, Any] | None) -> str:
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        pairs = [(key, str(value)) for key, value in (query or {}).items() if value is not None]
        if pairs:
            url += "?" + urlencode(pairs)
        return url

    @staticmethod
    def _parse_body(response: TransportResponse) -> Any:
        if not response.body:
            return None
        text = response.body.decode("utf-8", errors="replace")
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    @staticmethod
    def _to_api_error(response: TransportResponse) -> SquordAPIError:
        try:
            body: dict[str, Any] = json.loads(response.body) if response.body else {}
        except json.JSONDecodeError:
            body = {}
        body.setdefault("statusCode", response.status)
        body.setdefault("code", f"HTTP_{response.status}")
        body.setdefault("message", "")
        body.setdefault("requestId", response.headers.get("x-request-id"))
        return make_api_error(body, response.status, response.headers.get("x-request-id"))

    def _record_bucket_state(self, route_key: str, headers: dict[str, str]) -> None:
        limit = headers.get("x-ratelimit-limit")
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        if limit is None and remaining is None and reset is None:
            return
        state = RateLimitState(
            limit=int(limit) if limit else None,
            remaining=int(remaining) if remaining else None,
            reset=float(reset) if reset else None,
        )
        self._bucket_states[route_key] = state
        if state.remaining == 0 and state.reset is not None:
            self._bucket_blocked_until[route_key] = float(state.reset)

    async def _wait_for_bucket(self, route_key: str) -> None:
        while True:
            blocked_until = self._bucket_blocked_until.get(route_key)
            if blocked_until is None:
                return
            wait = blocked_until - time.time()
            if wait <= 0:
                del self._bucket_blocked_until[route_key]
                return
            await asyncio.sleep(wait)

    async def _acquire_global_slot(self) -> None:
        if self._global_limit is None:
            return
        while True:
            now = time.monotonic()
            self._global_window = [t for t in self._global_window if now - t < 1.0]
            if len(self._global_window) < self._global_limit:
                self._global_window.append(now)
                return
            oldest = self._global_window[0]
            await asyncio.sleep(1.0 - (now - oldest) + 0.01)


def route_key_of(method: str, path: str) -> str:
    """Chave de bucket: método + caminho com ids substituídos.

    ``POST /channels/{id}/messages`` para qualquer canal.
    """
    segments = path.split("/")
    normalized = ["{id}" if seg.isdigit() and len(seg) >= 5 else seg for seg in segments]
    return f"{method} {'/'.join(normalized)}"


# --------------------------------------------------------------------- --
# Paginação por cursor
# ----------------------------------------------------------------------


PageFetcher = Callable[..., Awaitable[Any]]


async def paginate(
    fetch_page: Callable[[dict[str, Any]], Awaitable[Any]],
    first_params: CursorPaginationParams | None = None,
    *,
    direction: str = "before",
) -> AsyncIterator[Any]:
    """Percorre as páginas de uma lista, emitindo os itens um a um.

    ``fetch_page`` recebe ``limit``/``before``/``after`` e devolve o
    formato ``{items, prevCursor, nextCursor, hasMore}`` da plataforma.
    """
    params: dict[str, Any] = dict(first_params or {})
    seen_cursors: set[str] = set()

    while True:
        page = await fetch_page(params)
        items = page.get("items", []) if isinstance(page, dict) else []
        for item in items:
            yield item
        if not isinstance(page, dict) or not page.get("hasMore"):
            return

        next_cursor = page.get("prevCursor" if direction == "before" else "nextCursor")
        if not next_cursor or next_cursor in seen_cursors:
            return
        seen_cursors.add(next_cursor)

        params.pop("before", None)
        params.pop("after", None)
        params["before" if direction == "before" else "after"] = next_cursor


__all__ = [
    "DEFAULT_BASE_URL",
    "AiohttpTransport",
    "PageFetcher",
    "RateLimitState",
    "RequestOptions",
    "RestClient",
    "RestResponse",
    "Transport",
    "TransportRequest",
    "TransportResponse",
    "paginate",
    "route_key_of",
]
