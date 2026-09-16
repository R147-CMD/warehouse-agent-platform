"""Contracts for conversation memory and governed long-term memory."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.domain.identity import AccessControl

MemoryType = Literal["preference", "stable_constraint", "business_glossary", "summary"]
MemorySource = Literal["user", "system", "approved_summary"]


class MemoryItem(BaseModel):
    """One versioned, traceable and access-controlled long-term memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str = Field(min_length=1, max_length=128)
    memory_key: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    memory_type: MemoryType
    content: str = Field(min_length=1, max_length=4_000)
    source: MemorySource
    source_refs: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    acl: AccessControl
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    deleted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "MemoryItem":
        if self.acl.tenant_id != self.tenant_id:
            raise ValueError("memory ACL tenant must match memory tenant")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("memory expiry must be after creation")
        return self


class ConversationTurn(BaseModel):
    """Short-term conversation state; it is not a long-term business fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=256)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)
    created_at: datetime
    expires_at: datetime


class MemoryCandidate(BaseModel):
    """Untrusted candidate emitted by UI or an optional extraction provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_key: str = Field(min_length=1, max_length=200)
    memory_type: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=4_000)
    source: str = Field(min_length=1, max_length=100)
    user_confirmed: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    ttl_seconds: int | None = Field(default=None, ge=1, le=31_536_000)
    source_refs: tuple[str, ...] = ()
    warehouse_ids: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()


class MemoryBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tokens: int = Field(default=400, ge=1, le=8_000)
    max_items: int = Field(default=5, ge=0, le=100)
    max_recent_turns: int = Field(default=6, ge=0, le=50)
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class MemoryContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recent_turns: tuple[ConversationTurn, ...] = ()
    long_term_items: tuple[MemoryItem, ...] = ()
    estimated_tokens: int = Field(default=0, ge=0)
    truncated: bool = False
    warnings: tuple[str, ...] = ()

    def to_prompt_context(self) -> dict[str, Any]:
        return {
            "recent_turns": [
                {"role": item.role, "content": item.content}
                for item in self.recent_turns
            ],
            "long_term": [
                {
                    "key": item.memory_key,
                    "type": item.memory_type,
                    "content": item.content,
                    "version": item.version,
                }
                for item in self.long_term_items
            ],
        }


class MemoryRejection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_key: str
    reason_code: str


class MemoryWriteReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["succeeded", "partial", "skipped", "failed"]
    stored_memory_ids: tuple[str, ...] = ()
    rejections: tuple[MemoryRejection, ...] = ()
    short_term_turns_written: int = Field(default=0, ge=0)
    error_code: str | None = None

    @property
    def stored_count(self) -> int:
        return len(self.stored_memory_ids)

    @property
    def rejected_count(self) -> int:
        return len(self.rejections)
