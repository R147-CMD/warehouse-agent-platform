from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from src.api.services.execution.models import OutboxEvent
from src.api.services.execution.outbox_relay import OutboxRelay
from src.api.services.execution.store import InMemoryExecutionStore


@pytest.mark.asyncio
async def test_two_relays_publish_an_outbox_event_only_once() -> None:
    store = InMemoryExecutionStore()
    event = OutboxEvent(
        event_id="event-1",
        command_id="command-1",
        created_at=datetime.now(UTC),
    )
    store.outbox[event.event_id] = event
    published: list[tuple[str, str]] = []

    async def publish(event_id: str, command_id: str) -> None:
        await asyncio.sleep(0)
        published.append((event_id, command_id))

    reports = await asyncio.gather(
        OutboxRelay(store, publish, relay_id="relay-1").publish_batch(limit=10),
        OutboxRelay(store, publish, relay_id="relay-2").publish_batch(limit=10),
    )

    assert published == [("event-1", "command-1")]
    assert sum(report.delivered for report in reports) == 1


@pytest.mark.asyncio
async def test_publish_failure_releases_event_for_a_later_relay() -> None:
    store = InMemoryExecutionStore()
    event = OutboxEvent(
        event_id="event-2",
        command_id="command-2",
        created_at=datetime.now(UTC),
    )
    store.outbox[event.event_id] = event

    async def fail_publish(_event_id: str, _command_id: str) -> None:
        raise ConnectionError("broker unavailable")

    report = await OutboxRelay(store, fail_publish, relay_id="relay-1").publish_batch(
        limit=10
    )

    assert report.failed == 1
    assert (await store.pending_outbox())[0].claimed_by is None
