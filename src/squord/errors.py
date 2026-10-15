"""Hierarquia de erros do SDK.

A API devolve um envelope único (``statusCode``, ``code``, ``message``,
``details``, ``requestId``). Decida pelo ``code``, nunca pela ``message``.
Todos os erros de API expõem propriedades consistentes: ``status``, ``code``,
``request_id`` e, quando aplicável, ``details`` e ``retry_after``.

@see https://docs.squord.com.br/referencia/erros
"""

from __future__ import annotations

from typing import Any

from .types import APIErrorBody


class SquordError(Exception):
    """Base de todos os erros lançados pelo SDK."""

    #: Código estável do erro, em ``SCREAMING_SNAKE``.
    code: str = "SQUORD_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class SquordAPIError(SquordError):
    """Erro devolvido pela API REST do Squord.

    Teste sempre pelo ``code`` (ex.: ``err.code == "MISSING_PERMISSION"``),
    nunca pela mensagem — ela pode mudar sem aviso.
    """

    def __init__(
        self,
        body: APIErrorBody | dict[str, Any],
        status: int,
        request_id: str | None = None,
    ) -> None:
        body = dict(body)
        self.status: int = status
        self.body: dict[str, Any] = body
        self.code: str = str(body.get("code") or f"HTTP_{status}")
        self.request_id: str | None = request_id or body.get("requestId")
        self.details: Any = body.get("details")
        super().__init__(
            str(body.get("message") or f"Erro da API do Squord (HTTP {status})"), code=self.code
        )

    @property
    def status_code(self) -> int:
        """Alias de ``status`` (formato do envelope)."""
        return self.status


class AuthenticationError(SquordAPIError):
    """``401`` — credencial ausente, inválida, trocada ou revogada."""


class InvalidTokenError(AuthenticationError):
    """``401 INVALID_TOKEN`` — token malformado ou revogado, ou bot/dono excluído/suspenso."""


class PermissionError(SquordAPIError):
    """``403`` — a credencial é válida, mas a ação não é permitida."""

    @property
    def missing_permission(self) -> str | None:
        """Nome da permissão que faltou, quando o erro é ``MISSING_PERMISSION``."""
        details = self.details if isinstance(self.details, dict) else {}
        permission = details.get("permission")
        return str(permission) if permission else None


class NotFoundError(SquordAPIError):
    """``404`` — recurso inexistente ou invisível para o bot."""


class ValidationError(SquordAPIError):
    """``422 VALIDATION_FAILED`` — corpo bem formado, mas inválido."""

    @property
    def issues(self) -> list[dict[str, Any]]:
        """Itens de validação: ``path``, ``code``, ``message`` e ``params``."""
        if isinstance(self.details, list):
            return [dict(item) for item in self.details]
        return []


class RateLimitError(SquordAPIError):
    """``429 RATE_LIMITED`` — limite de taxa. Espere ``retry_after`` segundos."""

    def __init__(
        self,
        body: APIErrorBody | dict[str, Any],
        status: int,
        request_id: str | None = None,
        exhausted_retries: bool = False,
    ) -> None:
        raw_details = body.get("details")
        details = raw_details if isinstance(raw_details, dict) else {}
        self.retry_after: int = int(details.get("retryAfter") or 1)
        self.bucket: str | None = details.get("bucket")
        self.exhausted_retries: bool = exhausted_retries
        super().__init__(body, status, request_id)


class NetworkError(SquordError):
    """Falha de rede antes de receber qualquer resposta (DNS, TCP, TLS)."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message, code="NETWORK_ERROR")
        self.__cause__ = cause


class RequestTimeoutError(SquordError):
    """A requisição excedeu o tempo limite configurado."""

    def __init__(self, method: str, path: str, timeout_ms: int) -> None:
        self.method = method
        self.path = path
        self.timeout_ms = timeout_ms
        super().__init__(
            f"A requisição {method} {path} excedeu o timeout de {timeout_ms} ms",
            code="REQUEST_TIMEOUT",
        )


class GatewayError(SquordError):
    """Erro de conexão/fechamento do gateway."""

    def __init__(
        self,
        message: str,
        *,
        close_code: int | None = None,
        reason: str | None = None,
        code: str = "GATEWAY_CLOSE",
    ) -> None:
        super().__init__(message, code=code)
        self.close_code = close_code
        self.reason = reason


class SquordTypeError(SquordError, TypeError):
    """Uso incorreto da API do SDK (argumentos inválidos no cliente)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SDK_INVALID_ARGUMENT")


def make_api_error(
    body: APIErrorBody | dict[str, Any],
    status: int,
    request_id: str | None = None,
) -> SquordAPIError:
    """Normaliza um corpo de erro na exceção apropriada da hierarquia."""
    code = str(body.get("code") or f"HTTP_{status}")
    if status == 401:
        return (
            InvalidTokenError(body, status, request_id)
            if code == "INVALID_TOKEN"
            else AuthenticationError(body, status, request_id)
        )
    if status == 403:
        return PermissionError(body, status, request_id)
    if status == 404:
        return NotFoundError(body, status, request_id)
    if status == 422:
        return ValidationError(body, status, request_id)
    if status == 429:
        return RateLimitError(body, status, request_id)
    return SquordAPIError(body, status, request_id)
