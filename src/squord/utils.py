"""Utilidades: validação de ids, backoff, split de argumentos, nonce."""

from __future__ import annotations

import random
import re
import uuid
from collections.abc import Iterator
from pathlib import Path

from .errors import SquordTypeError

_SNOWFLAKE_RE = re.compile(r"^\d{1,20}$")
_LEGACY_ID_RE = re.compile(r"^[0-9a-f]{24}$", re.IGNORECASE)


# ------------------------------------------------------------------ --
# Ids
# ---------------------------------------------------------------------


def is_valid_snowflake(value: str) -> bool:
    """Verifica se um valor parece um id válido do Squord."""
    return isinstance(value, str) and bool(_SNOWFLAKE_RE.match(value) or _LEGACY_ID_RE.match(value))


def assert_snowflake(value: str, label: str = "id") -> str:
    """Levanta ``SquordTypeError`` se o id não tiver o formato de id do Squord."""
    if not is_valid_snowflake(value):
        msg = (
            f"{label} inválido: {value!r} — ids do Squord são strings "
            "(Snowflake decimal ou hex de 24 caracteres)"
        )
        raise SquordTypeError(msg)
    return value


def compare_snowflakes(a: str, b: str) -> int:
    """Compara dois ids por ordem numérica (seguro com ids grandes)."""
    try:
        ia, ib = int(a), int(b)
        return (ia > ib) - (ia < ib)
    except ValueError:
        return (a > b) - (a < b)


# ------------------------------------------------------------------ --
# Tokens e ids de requisição
# ---------------------------------------------------------------------


def is_bot_token(token: str) -> bool:
    """Verifica o formato ``sqb_<id>.<segredo>``."""
    return bool(isinstance(token, str) and re.match(r"^sqb_.+\..+", token))


def strip_token_prefix(token: str) -> str:
    return token[4:] if token.startswith("Bot ") else token


def new_request_id() -> str:
    """Gera um id de requisição (rastreável no header ``x-request-id``)."""
    return str(uuid.uuid4())


def new_nonce() -> str:
    """Gera uma chave de idempotência (``nonce``) para envio de mensagens."""
    return uuid.uuid4().hex[:32]


# ------------------------------------------------------------------ --
# Backoff exponencial com jitter (1 s, 2 s, 4 s ... até 60 s, + aleatório)
# ---------------------------------------------------------------------


def backoff_delay(
    attempt: int,
    *,
    base_ms: float = 1_000,
    factor: float = 2,
    max_ms: float = 60_000,
    jitter: float = 0.25,
) -> float:
    """Calcula a espera (ms) para a tentativa ``attempt`` (0-based)."""
    bounded = min(attempt, 16)
    exp = min(base_ms * factor**bounded, max_ms)
    jitter_amount = exp * jitter * (random.uniform(0, 1) * 2 - 1)
    return max(250.0, round(exp + jitter_amount))


def backoff_sequence(**kwargs: float) -> Iterator[float]:
    """Gerador infinito de esperas de backoff."""
    attempt = 0
    while True:
        yield backoff_delay(attempt, **kwargs)
        attempt += 1


# ------------------------------------------------------------------ --
# Argumentos de comandos de texto
# ---------------------------------------------------------------------


def split_arguments(raw: str) -> list[str]:
    """Divide argumentos de uma linha, respeitando aspas simples e duplas."""
    args: list[str] = []
    current: list[str] = []
    in_quote: str | None = None

    for char in raw:
        if in_quote:
            if char == in_quote:
                in_quote = None
            else:
                current.append(char)
            continue
        if char in {'"', "'"}:
            in_quote = char
            continue
        if char.isspace():
            if current:
                args.append("".join(current))
                current = []
            continue
        current.append(char)

    if current:
        args.append("".join(current))
    return args


# ------------------------------------------------------------------ --
# Uploads: dedução de content-type por extensão
# ---------------------------------------------------------------------


_CONTENT_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "wav": "audio/wav",
    "pdf": "application/pdf",
    "txt": "text/plain",
    "json": "application/json",
    "csv": "text/csv",
    "md": "text/markdown",
    "zip": "application/zip",
}


def guess_content_type(filename: str) -> str:
    """Deduz o content-type pelo nome do arquivo (padrão: octet-stream)."""
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return _CONTENT_TYPES.get(extension, "application/octet-stream")


def read_file_bytes(path: str | Path) -> bytes:
    """Lê um arquivo do disco em bytes (usado pelos uploads)."""
    return Path(path).read_bytes()
