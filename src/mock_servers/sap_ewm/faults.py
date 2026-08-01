"""One-shot deterministic fault injection for SAP EWM protocol tests."""

from __future__ import annotations

import asyncio
from collections import Counter

from pydantic import BaseModel, Field


class FaultSpec(BaseModel):
    operation: str = Field(min_length=1)
    status_code: int | None = Field(default=None, ge=400, le=599)
    delay_ms: int = Field(default=0, ge=0, le=30_000)
    apply_then_timeout: bool = False


class FaultController:
    """Store one fault and count calls using a single async lock."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._next: FaultSpec | None = None
        self._request_counts: Counter[str] = Counter()

    async def set_next(self, spec: FaultSpec) -> None:
        async with self._lock:
            self._next = spec

    async def take(self, operation: str) -> FaultSpec | None:
        async with self._lock:
            self._request_counts[operation] += 1
            if self._next is None or self._next.operation not in {
                operation,
                "*",
            }:
                return None
            spec = self._next
            self._next = None
            return spec

    async def counts(self) -> dict[str, int]:
        async with self._lock:
            return dict(self._request_counts)

    async def reset(self) -> None:
        async with self._lock:
            self._next = None
            self._request_counts.clear()
