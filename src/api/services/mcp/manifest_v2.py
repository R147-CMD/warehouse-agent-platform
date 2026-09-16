"""Versioned MCP Tool Manifest used by planning, policy and invocation."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MCPToolManifestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2_000)
    provider_id: str = Field(min_length=1, max_length=200)
    capability: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=64)
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_scopes: tuple[str, ...] = ()
    supported_tenants: tuple[str, ...] = ()
    risk_level: Literal["low", "medium", "high", "critical"]
    read_write_mode: Literal["read", "propose", "write"]
    health_status: Literal["available", "degraded", "unavailable"] = "available"
    timeout_seconds: float = Field(default=15.0, gt=0.0, le=300.0)

    @classmethod
    def create(cls, **values: Any) -> "MCPToolManifestV2":
        schemas = json.dumps(
            {
                "input": values["input_schema"],
                "output": values["output_schema"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            **values,
            schema_hash=sha256(schemas.encode("utf-8")).hexdigest(),
        )
