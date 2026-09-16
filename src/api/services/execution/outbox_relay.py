"""Lease-safe transactional-outbox publisher."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .store import ExecutionStore


class PublishReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claimed: int = Field(ge=0)
    delivered: int = Field(ge=0)
    failed: int = Field(ge=0)


class OutboxRelay:
    def __init__(
        self,
        store: ExecutionStore,
        publish: Callable[[str, str], object],
        *,
        relay_id: str | None = None,
        lease_seconds: int = 30,
    ) -> None:
        self.store = store
        self.publish = publish
        self.relay_id = relay_id or f"relay-{uuid4()}"
        self.lease_seconds = lease_seconds

    async def publish_batch(self, *, limit: int = 100) -> PublishReport:
        events = await self.store.claim_outbox(self.relay_id, limit, self.lease_seconds)
        delivered = 0
        failed = 0
        for event in events:
            try:
                result = self.publish(event.event_id, event.command_id)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                failed += 1
                await self.store.release_outbox(event.event_id, self.relay_id)
                continue
            await self.store.mark_delivered(
                event.model_copy(update={"delivered_at": datetime.now(UTC)})
            )
            delivered += 1
        return PublishReport(claimed=len(events), delivered=delivered, failed=failed)

    async def relay_once(self) -> int:
        """Backward-compatible single-batch API used by local harnesses."""

        return (await self.publish_batch()).delivered
