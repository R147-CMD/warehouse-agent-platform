"""Build atomic claims only from evidence that contains the asserted value."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Any

from src.api.domain.evidence_protocols import Claim, EntityRef

from .models import Evidence


class ClaimValidator:
    _TRUST_CONFIDENCE = {
        "untrusted": 0.25,
        "derived": 0.6,
        "verified": 0.9,
        "authoritative": 0.98,
    }

    def validate(
        self,
        *,
        statement: str,
        subject: EntityRef | None,
        predicate: str,
        value: Any,
        evidence: Sequence[Evidence],
    ) -> Claim:
        supporting: list[Evidence] = []
        opposing: list[Evidence] = []
        for item in evidence:
            actual = (
                item.content.get(predicate) if isinstance(item.content, dict) else None
            )
            if actual == value:
                supporting.append(item)
            elif actual is not None:
                opposing.append(item)
        if supporting and opposing:
            status = "conflicted"
        elif supporting:
            status = "supported"
        else:
            status = "unsupported"
        confidence = max(
            (self._TRUST_CONFIDENCE[item.ref.trust_level] for item in supporting),
            default=0.0,
        )
        claim_key = f"{subject}|{predicate}|{value}|{statement}"
        return Claim(
            claim_id="cl-" + sha256(claim_key.encode("utf-8")).hexdigest()[:32],
            statement=statement,
            subject=subject,
            predicate=predicate,
            value=value,
            event_time=(supporting[0].ref.event_time if supporting else None),
            supporting_evidence=tuple(item.ref for item in supporting),
            opposing_evidence=tuple(item.ref for item in opposing),
            confidence=confidence,
            status=status,
        )
