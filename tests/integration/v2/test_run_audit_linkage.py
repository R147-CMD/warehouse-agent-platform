from __future__ import annotations

import pytest

from src.api.services.monitoring.audit_v2 import AuditWriter


@pytest.mark.asyncio
async def test_audit_events_are_append_only_and_link_run_command_and_evidence() -> None:
    writer = AuditWriter()
    first = await writer.append(
        {
            "tenant_id": "tenant-a",
            "event_type": "command.approved",
            "run_id": "run-1",
            "command_id": "cmd-1",
            "payload": {"password": "secret", "status": "approved"},
        }
    )
    second = await writer.append(
        {
            "tenant_id": "tenant-a",
            "event_type": "execution.readback",
            "run_id": "run-1",
            "command_id": "cmd-1",
            "evidence_id": "ev-1",
            "payload": {"status": "succeeded"},
        }
    )

    events = await writer.for_run("tenant-a", "run-1")
    assert [event.event_type for event in events] == [
        "command.approved",
        "execution.readback",
    ]
    assert second.previous_event_hash == first.event_hash
    assert first.payload_redacted["password"] == "[REDACTED]"
    with pytest.raises(AttributeError):
        getattr(writer, "update")
