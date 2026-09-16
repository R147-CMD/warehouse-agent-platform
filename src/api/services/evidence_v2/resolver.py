"""Field-aware evidence conflict resolution."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from .models import Evidence


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected: Evidence
    alternatives: tuple[Evidence, ...] = ()
    conflicted: bool = False
    reason: str


class EvidenceResolver:
    _TRUST = {"untrusted": 0, "derived": 1, "verified": 2, "authoritative": 3}

    def __init__(
        self, *, source_priority: dict[str, tuple[str, ...]] | None = None
    ) -> None:
        self.source_priority = source_priority or {}

    def resolve(self, evidence: Sequence[Evidence], *, field: str) -> Resolution:
        if not evidence:
            raise ValueError("at least one evidence item is required")
        priority = self.source_priority.get(field, ())

        def key(item: Evidence):
            source_rank = (
                len(priority) - priority.index(item.ref.source_system)
                if item.ref.source_system in priority
                else 0
            )
            timestamp = item.ref.event_time or item.ref.observed_at
            return (
                source_rank,
                self._TRUST[item.ref.trust_level],
                timestamp.timestamp(),
                item.ref.source_version or "",
                item.ref.evidence_id,
            )

        ordered = sorted(evidence, key=key, reverse=True)
        values = {
            self._field_value(item, field)
            for item in ordered
            if self._field_value(item, field) is not None
        }
        reason = "source_priority" if priority else "trust_freshness_version"
        return Resolution(
            selected=ordered[0],
            alternatives=tuple(ordered[1:]),
            conflicted=len(values) > 1,
            reason=reason,
        )

    @staticmethod
    def _field_value(item: Evidence, field: str):
        return (
            item.content.get(field) if isinstance(item.content, dict) else item.content
        )
