"""Public append-only audit writer for the V2 runtime."""

from __future__ import annotations

from typing import Any

from src.api.services.runs.audit_v2 import AuditEventV2, InMemoryAuditLogV2


class AuditWriter:
    """Normalize event input and delegate to the hash-linked audit log."""

    def __init__(self, backend: InMemoryAuditLogV2 | None = None) -> None:
        self._backend = backend or InMemoryAuditLogV2()

    async def append(self, event: dict[str, Any]) -> AuditEventV2:
        if not event.get("tenant_id") or not event.get("event_type"):
            raise ValueError("audit events require tenant_id and event_type")
        payload = event.get("payload")
        links = {
            key: event[key]
            for key in (
                "actor_id",
                "run_id",
                "trace_id",
                "plan_id",
                "approval_id",
                "command_id",
                "evidence_id",
            )
            if event.get(key) is not None
        }
        return await self._backend.append(
            tenant_id=str(event["tenant_id"]),
            event_type=str(event["event_type"]),
            payload=payload if isinstance(payload, dict) else {},
            **links,
        )

    async def for_run(self, tenant_id: str, run_id: str) -> tuple[AuditEventV2, ...]:
        return await self._backend.for_run(tenant_id, run_id)
