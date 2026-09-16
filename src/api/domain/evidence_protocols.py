"""Traceable evidence, atomic claim, and citation contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .identity import AccessControl

EvidenceType = Literal[
    "structured_record",
    "document_chunk",
    "telemetry",
    "tool_result",
    "execution_readback",
    "derived_analysis",
]
TrustLevel = Literal["untrusted", "derived", "verified", "authoritative"]
ClaimStatus = Literal["supported", "partially_supported", "conflicted", "unsupported"]


class EntityRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: str = Field(min_length=1, max_length=100)
    entity_id: str = Field(min_length=1, max_length=256)
    source_system: str | None = Field(default=None, max_length=100)


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=128)
    evidence_type: EvidenceType
    source_system: str = Field(min_length=1, max_length=100)
    source_locator: dict[str, Any]
    entity_refs: tuple[EntityRef, ...] = ()
    event_time: datetime | None = None
    observed_at: datetime
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_version: str | None = Field(default=None, max_length=128)
    freshness: Literal["live", "fresh", "stale", "unknown"] = "unknown"
    trust_level: TrustLevel
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    acl: AccessControl

    @model_validator(mode="after")
    def validate_interval(self) -> "EvidenceRef":
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be earlier than valid_from")
        return self


class EvidenceRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_type: str = Field(min_length=1, max_length=100)
    entity_types: tuple[str, ...] = ()
    minimum_trust: TrustLevel = "verified"
    maximum_age_seconds: int | None = Field(default=None, gt=0)
    required: bool = True


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=4000)
    subject: EntityRef | None = None
    predicate: str | None = Field(default=None, max_length=200)
    value: Any | None = None
    event_time: datetime | None = None
    supporting_evidence: tuple[EvidenceRef, ...] = ()
    opposing_evidence: tuple[EvidenceRef, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    status: ClaimStatus

    @model_validator(mode="after")
    def validate_support(self) -> "Claim":
        if self.status == "supported" and not self.supporting_evidence:
            raise ValueError("supported claims require supporting evidence")
        if self.status == "conflicted" and not self.opposing_evidence:
            raise ValueError("conflicted claims require opposing evidence")
        return self


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(min_length=1, max_length=128)
    claim_id: str = Field(min_length=1, max_length=128)
    evidence_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=500)
    locator: dict[str, Any] = Field(default_factory=dict)
