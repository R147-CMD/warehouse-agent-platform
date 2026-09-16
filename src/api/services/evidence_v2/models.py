"""Stored evidence model with payload separated from its portable reference."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.api.domain.evidence_protocols import (
    EntityRef,
    EvidenceRef,
    EvidenceType,
    TrustLevel,
)
from src.api.domain.identity import AccessControl


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: EvidenceRef
    content: dict[str, Any] | str

    @classmethod
    def create(
        cls,
        *,
        evidence_type: EvidenceType,
        source_system: str,
        source_locator: dict[str, Any],
        content: dict[str, Any] | str,
        observed_at: datetime,
        trust_level: TrustLevel,
        acl: AccessControl,
        entity_refs: tuple[EntityRef, ...] = (),
        event_time: datetime | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        source_version: str | None = None,
        freshness: str = "fresh",
    ) -> "Evidence":
        canonical_content = json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        content_hash = sha256(canonical_content.encode("utf-8")).hexdigest()
        identity_payload = json.dumps(
            {
                "type": evidence_type,
                "source": source_system,
                "locator": source_locator,
                "source_version": source_version,
                "content_hash": content_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        evidence_id = "ev-" + sha256(identity_payload.encode("utf-8")).hexdigest()[:32]
        return cls(
            ref=EvidenceRef(
                evidence_id=evidence_id,
                evidence_type=evidence_type,
                source_system=source_system,
                source_locator=source_locator,
                entity_refs=entity_refs,
                event_time=event_time,
                observed_at=observed_at,
                valid_from=valid_from,
                valid_to=valid_to,
                source_version=source_version,
                freshness=freshness,
                trust_level=trust_level,
                content_hash=content_hash,
                acl=acl,
            ),
            content=content,
        )
