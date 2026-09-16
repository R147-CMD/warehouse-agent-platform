"""Convert verified command readback into authoritative evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from src.api.domain.evidence_protocols import EntityRef
from src.api.domain.identity import AccessControl
from src.api.services.evidence_v2.models import Evidence

from .models import Command


def command_readback_evidence(command: Command) -> Evidence:
    warehouse_id = command.target.get("warehouse_id")
    target_type = str(command.target.get("resource_type") or "resource")
    target_id = str(command.target.get("resource_id") or command.action_id)
    source_system = (
        "sap_ewm" if command.capability.startswith("sap.ewm") else "external_tool"
    )
    now = datetime.now(UTC)
    return Evidence.create(
        evidence_type="execution_readback",
        source_system=source_system,
        source_locator={
            "command_id": command.command_id,
            "external_reference": command.external_reference,
        },
        content=command.readback,
        entity_refs=(
            EntityRef(
                entity_type=target_type,
                entity_id=target_id,
                source_system=source_system,
            ),
        ),
        event_time=now,
        observed_at=now,
        source_version=(
            str(command.readback["etag"])
            if command.readback.get("etag")
            else command.expected_version
        ),
        freshness="live",
        trust_level="authoritative",
        acl=AccessControl(
            tenant_id=command.tenant_id,
            warehouse_ids=(str(warehouse_id),) if warehouse_id else (),
        ),
    )
