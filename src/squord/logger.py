"""Logger com redação automática de segredos.

O SDK usa o ``logging`` da biblioteca padrão: nenhum handler é configurado
por padrão (convenção de bibliotecas Python). Tokens de bot (``sqb_...``)
e headers ``Authorization`` são substituídos por ``[REDACTED]`` antes de
chegar a qualquer destino. O SDK nunca registra o conteúdo de mensagens
por conta própria — só metadados operacionais.
"""

from __future__ import annotations

import logging
import re

_TOKEN_RE = re.compile(r"sqb_[A-Za-z0-9._-]+")
_AUTH_RE = re.compile(r"Bot\s+sqb_[A-Za-z0-9._-]+", re.IGNORECASE)
_JSON_TOKEN_RE = re.compile(r'"token"\s*:\s*"[^"]*"')

LOGGER_NAME = "squord"


def redact(text: str) -> str:
    """Redação aplicada a qualquer mensagem antes da entrega."""
    text = _TOKEN_RE.sub("sqb_[REDACTED]", text)
    text = _AUTH_RE.sub("Bot sqb_[REDACTED]", text)
    return _JSON_TOKEN_RE.sub('"token":"[REDACTED]"', text)


class RedactingFilter(logging.Filter):
    """Filtro de log que redige segredos no registro e nas exceções."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(arg) if isinstance(arg, str) else arg for arg in record.args)
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            if str(exc):
                exc.args = tuple(redact(a) if isinstance(a, str) else a for a in exc.args)
        return True


def get_logger(name: str | None = None) -> logging.Logger:
    """Retorna um logger do SDK com o filtro de redação instalado."""
    logger = logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger


def setup_logging(level: int = logging.INFO) -> None:
    """Conveniência para habilitar os logs do SDK em apps e exemplos."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.addFilter(RedactingFilter())
