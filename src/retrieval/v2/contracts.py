"""Stable inputs and outputs for the V2 retrieval pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.domain.agent_protocols import MissingInput

QueryType = Literal[
    "structured_fact",
    "document_knowledge",
    "hybrid",
    "multi_hop",
    "action_request",
]


class TimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime
    original_expression: str

    @model_validator(mode="after")
    def validate_interval(self) -> "TimeRange":
        if self.end <= self.start:
            raise ValueError("time range end must be later than start")
        return self


class ResolvedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: str = Field(min_length=1, max_length=100)
    entity_id: str = Field(min_length=1, max_length=256)
    original_text: str = Field(min_length=1, max_length=256)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class QueryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_query: str = Field(min_length=1, max_length=8000)
    normalized_query: str = Field(min_length=1, max_length=8000)
    query_type: QueryType
    entities: tuple[ResolvedEntity, ...] = ()
    time_range: TimeRange | None = None
    keywords: tuple[str, ...] = ()
    semantic_queries: tuple[str, ...] = ()
    protected_terms: tuple[str, ...] = ()
    unauthorized_terms: tuple[str, ...] = ()
    filters: dict[str, Any] = Field(default_factory=dict)
    freshness_requirement: Literal["live", "minutes", "hours", "versioned"] = "hours"
    missing_inputs: tuple[MissingInput, ...] = ()
    schema_version: str = "1.0"


RetrievalChannel = Literal["structured", "lexical", "dense"]


class RetrievalCandidate(BaseModel):
    """A channel-neutral candidate with access metadata attached."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=100_000)
    source_type: Literal[
        "structured_record", "document_chunk", "telemetry", "tool_result"
    ]
    source_locator: dict[str, Any]
    channel: RetrievalChannel
    rank: int = Field(ge=1)
    raw_score: float
    tenant_id: str = Field(min_length=1, max_length=128)
    warehouse_ids: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    parent_id: str | None = Field(default=None, max_length=256)
    neighbor_ids: tuple[str, ...] = ()
    token_count: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FusedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: RetrievalCandidate
    fused_score: float = Field(ge=0.0)
    channels: tuple[RetrievalChannel, ...]


class ContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[RetrievalCandidate, ...] = ()
    used_tokens: int = Field(default=0, ge=0)
    max_tokens: int = Field(ge=1)
    truncated: bool = False


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["succeeded", "partial", "failed"]
    context: ContextBundle
    candidates: tuple[RetrievalCandidate, ...] = ()
    degraded_channels: tuple[RetrievalChannel, ...] = ()
    errors: dict[str, str] = Field(default_factory=dict)
    schema_version: str = "1.0"
