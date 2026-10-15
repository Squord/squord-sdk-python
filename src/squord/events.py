"""Event emitter assíncrono, sem dependências externas.

Suporta ``on``, ``once``, ``off`` e ``emit`` — este último **assíncrono**:
handlers síncronos e assíncronos são aceitos, executados em ordem de
registro, e erros são capturados e entregues ao evento ``error`` da mesma
instância, sem derrubar o loop de eventos.
"""

from __future__ import annotations

import contextlib
import inspect
from collections import defaultdict
from collections.abc import Callable
from typing import Any, overload

EventHandler = Callable[..., Any]


class EventEmitter:
    """Emitter tipado por convenção: nomes de evento em ``str``."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    @overload
    def on(self, event: str, handler: EventHandler) -> Callable[[], None]: ...

    @overload
    def on(self, event: str) -> Callable[[EventHandler], EventHandler]: ...

    def on(
        self,
        event: str,
        handler: EventHandler | None = None,
    ) -> Callable[[], None] | Callable[[EventHandler], EventHandler]:
        """Registra um handler — nos dois estilos:

        .. code-block:: python

            dispose = client.on("ready", handler)      # retorna função que remove

            @client.on("ready")                        # ou como decorador
            async def on_ready(event): ...
        """
        if handler is not None:
            self._handlers[event].append(handler)

            def dispose() -> None:
                self.off(event, handler)

            return dispose

        def decorator(fn: EventHandler) -> EventHandler:
            self._handlers[event].append(fn)
            return fn

        return decorator

    def once(self, event: str, handler: EventHandler) -> Callable[[], None]:
        """Registra um handler que é removido após a primeira chamada."""
        called = False

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal called
            if not called:
                called = True
                self.off(event, wrapper)
                return handler(*args, **kwargs)
            return None

        wrapper.__name__ = getattr(handler, "__name__", "once_handler")
        return self.on(event, wrapper)

    def off(self, event: str, handler: EventHandler) -> None:
        """Remove um handler (ou todos do evento, se omitido)."""
        if handler is None:
            self._handlers.pop(event, None)
            return
        with contextlib.suppress(ValueError):
            self._handlers[event].remove(handler)

    def remove_all_listeners(self) -> None:
        self._handlers.clear()

    def listener_count(self, event: str) -> int:
        return len(self._handlers.get(event, ()))

    async def emit(self, event: str, *args: Any) -> bool:
        """Emite um evento; executa os handlers em ordem.

        Erros de handler (síncronos ou assíncronos) são capturados e
        reemitidos no evento ``error`` — nunca propagam para o emissor,
        exceto quando o próprio evento ``error`` falha.
        """
        handlers = list(self._handlers.get(event, ()))
        for handler in handlers:
            try:
                result = handler(*args)
                if inspect.isawaitable(result):
                    await result
            except Exception as err:
                if event == "error":
                    raise
                error = err if isinstance(err, Exception) else RuntimeError(str(err))
                await self.emit("error", error)
        return bool(handlers)
