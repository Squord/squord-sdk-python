"""Cache em memória opcional: TTL por item, limite de itens e invalidação.

O padrão do SDK é armazenar apenas o necessário, com acesso sob demanda
aos demais dados. O cache **nunca** substitui a API: um item pode estar
defasado, e o backend continua sendo a autoridade.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class _Entry(Generic[V]):
    __slots__ = ("expires_at", "value")

    def __init__(self, value: V, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at


class Cache(Generic[K, V]):
    """Cache com TTL, limite de itens e promoção LRU-ish no acesso."""

    def __init__(
        self,
        ttl_ms: float = 300_000,
        max_size: int = 1_000,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_ms = ttl_ms
        self.max_size = max_size
        self._clock = clock
        self._store: dict[K, _Entry[V]] = {}

    def get(self, key: K) -> V | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if self._clock() >= entry.expires_at:
            del self._store[key]
            return None
        # Re-inserir promove o item a "mais recente" (dict preserva ordem).
        del self._store[key]
        self._store[key] = entry
        return entry.value

    def set(self, key: K, value: V, ttl_ms: float | None = None) -> None:
        if self.max_size <= 0:
            return
        ttl = self.ttl_ms if ttl_ms is None else ttl_ms
        expires = self._clock() + ttl if ttl != float("inf") else float("inf")
        self._store.pop(key, None)
        self._store[key] = _Entry(value, expires)
        self._evict()

    def has(self, key: K) -> bool:
        return self.get(key) is not None

    def delete(self, key: K) -> bool:
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        self._sweep()
        return len(self._store)

    def items(self) -> Iterator[tuple[K, V]]:
        now = self._clock()
        for key in list(self._store):
            entry = self._store[key]
            if now < entry.expires_at:
                yield key, entry.value
            else:
                del self._store[key]

    def _evict(self) -> None:
        while len(self._store) > self.max_size:
            oldest = next(iter(self._store))
            del self._store[oldest]

    def _sweep(self) -> None:
        now = self._clock()
        for key in list(self._store):
            if now >= self._store[key].expires_at:
                del self._store[key]
