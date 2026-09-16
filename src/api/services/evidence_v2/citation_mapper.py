"""Stable mapping from validated claims to source locators."""

from __future__ import annotations

from hashlib import sha256

from src.api.domain.evidence_protocols import Citation, Claim


class CitationMapper:
    def map(self, claim: Claim) -> tuple[Citation, ...]:
        citations = []
        for evidence in claim.supporting_evidence:
            citation_id = (
                "ci-"
                + sha256(
                    f"{claim.claim_id}:{evidence.evidence_id}".encode("utf-8")
                ).hexdigest()[:32]
            )
            citations.append(
                Citation(
                    citation_id=citation_id,
                    claim_id=claim.claim_id,
                    evidence_id=evidence.evidence_id,
                    label=f"{evidence.source_system} / {evidence.evidence_type}",
                    locator=evidence.source_locator,
                )
            )
        return tuple(citations)
