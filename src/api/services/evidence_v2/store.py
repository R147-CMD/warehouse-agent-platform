"""Append-only evidence storage interface and fast in-memory implementation."""

from __future__ import annotations

from typing import Protocol

from src.api.domain.identity import IdentityContext

from .models import Evidence


def _can_read(item: Evidence, identity: IdentityContext) -> bool:
    acl = item.ref.acl
    return (
        acl.tenant_id == identity.tenant_id
        and set(acl.required_scopes).issubset(identity.scopes)
        and (
            not acl.warehouse_ids
            or bool(set(acl.warehouse_ids) & set(identity.warehouse_scope))
        )
    )


class EvidenceStore(Protocol):
    async def append(self, evidence: Evidence) -> None: ...

    async def get(
        self, evidence_id: str, identity: IdentityContext
    ) -> Evidence | None: ...

    async def query(
        self,
        identity: IdentityContext,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> tuple[Evidence, ...]: ...


class InMemoryEvidenceStore:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}

    async def append(self, evidence: Evidence) -> None:
        existing = self._items.get(evidence.ref.evidence_id)
        if existing is not None and existing != evidence:
            raise ValueError(
                "immutable evidence ID already exists with different content"
            )
        self._items.setdefault(evidence.ref.evidence_id, evidence)

    async def get(self, evidence_id: str, identity: IdentityContext) -> Evidence | None:
        item = self._items.get(evidence_id)
        return item if item is not None and _can_read(item, identity) else None

    async def query(
        self,
        identity: IdentityContext,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> tuple[Evidence, ...]:
        result = []
        for item in self._items.values():
            if not _can_read(item, identity):
                continue
            if entity_type is not None and not any(
                ref.entity_type == entity_type for ref in item.ref.entity_refs
            ):
                continue
            if entity_id is not None and not any(
                ref.entity_id == entity_id for ref in item.ref.entity_refs
            ):
                continue
            result.append(item)
        return tuple(sorted(result, key=lambda item: item.ref.evidence_id))
