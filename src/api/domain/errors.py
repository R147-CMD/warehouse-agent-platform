"""Normalized error categories for agent, retrieval, and tool boundaries."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    CONTRACT = "contract_error"
    INTERNAL = "internal"


class AgentError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=100)
    category: ErrorCategory
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
