"""Authenticated identity and access scopes propagated through V2 workflows."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


def _nonempty_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(
        dict.fromkeys(value.strip() for value in values if value.strip())
    )
    return normalized


class IdentityContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    username: str | None = Field(default=None, max_length=200)
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    warehouse_scope: tuple[str, ...] = ()
    authenticated_at: datetime

    @field_validator("tenant_id", "user_id")
    @classmethod
    def validate_required_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("identity identifiers cannot be blank")
        return normalized

    @field_validator("roles", "scopes", "warehouse_scope")
    @classmethod
    def normalize_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _nonempty_unique(value)


class AccessControl(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    warehouse_ids: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    classification: DataClassification = DataClassification.INTERNAL

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tenant_id cannot be blank")
        return normalized

    @field_validator("warehouse_ids", "required_scopes")
    @classmethod
    def normalize_access_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _nonempty_unique(value)
