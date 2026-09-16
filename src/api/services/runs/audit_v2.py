"""Append-only, hash-linked and redacted runtime audit events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.api.services.security.trust_boundary_v2 import redact_sensitive


class AuditEventV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_id: str
    tenant_id: str
    event_type: str
    actor_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    plan_id: str | None = None
    approval_id: str | None = None
    command_id: str | None = None
    evidence_id: str | None = None
    payload_redacted: dict[str, Any] = Field(default_factory=dict)
    previous_event_hash: str | None = None
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime


class InMemoryAuditLogV2:
    def __init__(self) -> None:
        self._events: list[AuditEventV2] = []

    async def append(
        self,
        *,
        tenant_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        **links: Any,
    ) -> AuditEventV2:
        previous = self._events[-1].event_hash if self._events else None
        created_at = datetime.now(UTC)
        redacted = redact_sensitive(payload or {})
        hash_input = json.dumps(
            {
                "tenant_id": tenant_id,
                "event_type": event_type,
                "payload": redacted,
                "links": links,
                "previous": previous,
                "created_at": created_at.isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        event = AuditEventV2(
            audit_id=str(uuid4()),
            tenant_id=tenant_id,
            event_type=event_type,
            payload_redacted=redacted,
            previous_event_hash=previous,
            event_hash=sha256(hash_input.encode("utf-8")).hexdigest(),
            created_at=created_at,
            **links,
        )
        self._events.append(event)
        return event

    async def for_run(self, tenant_id: str, run_id: str) -> tuple[AuditEventV2, ...]:
        return tuple(
            event
            for event in self._events
            if event.tenant_id == tenant_id and event.run_id == run_id
        )
