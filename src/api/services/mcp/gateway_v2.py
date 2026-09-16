"""Governed MCP discovery and invocation gateway."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.api.domain.identity import IdentityContext
from src.api.services.monitoring.tracing_v2 import trace_span

from .manifest_v2 import MCPToolManifestV2
from .schema_validation_v2 import validate_schema


class MCPInvocationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: str
    provider_id: str
    schema_hash: str
    data: Any
    trust_level: Literal["untrusted"] = "untrusted"
    trace_id: str | None = None
    span_id: str | None = None


class MCPGatewayV2:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[MCPToolManifestV2, Callable[..., Any]]] = {}

    def register(
        self, manifest: MCPToolManifestV2, handler: Callable[..., Any]
    ) -> None:
        if manifest.tool_id in self._tools:
            raise ValueError(f"duplicate MCP tool: {manifest.tool_id}")
        self._tools[manifest.tool_id] = (manifest, handler)

    def discover(
        self,
        identity: IdentityContext,
        *,
        capability: str | None = None,
    ) -> tuple[MCPToolManifestV2, ...]:
        result = []
        for manifest, _ in self._tools.values():
            if capability and manifest.capability != capability:
                continue
            if manifest.health_status == "unavailable":
                continue
            if (
                manifest.supported_tenants
                and identity.tenant_id not in manifest.supported_tenants
            ):
                continue
            if not set(manifest.required_scopes).issubset(identity.scopes):
                continue
            result.append(manifest)
        return tuple(sorted(result, key=lambda item: (item.capability, item.tool_id)))

    async def invoke(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        identity: IdentityContext,
        *,
        allow_side_effects: bool = False,
    ) -> MCPInvocationResult:
        registered = self._tools.get(tool_id)
        if registered is None:
            raise LookupError(f"MCP tool not found: {tool_id}")
        manifest, handler = registered
        if manifest.health_status == "unavailable":
            raise RuntimeError("MCP provider is unavailable")
        if (
            manifest.supported_tenants
            and identity.tenant_id not in manifest.supported_tenants
        ):
            raise PermissionError("MCP tool is not available for this tenant")
        if not set(manifest.required_scopes).issubset(identity.scopes):
            raise PermissionError("MCP tool scope denied")
        if manifest.read_write_mode == "write" and not allow_side_effects:
            raise PermissionError("MCP side effects are disabled in the Agent process")
        validate_schema(arguments, manifest.input_schema)
        context = {
            "tenant_id": identity.tenant_id,
            "user_id": identity.user_id,
            "warehouse_scope": identity.warehouse_scope,
        }

        async def call():
            result = handler(arguments, context)
            return await result if inspect.isawaitable(result) else result

        with trace_span(
            "mcp.tool.invoke",
            {"tool_id": manifest.tool_id, "provider_id": manifest.provider_id},
        ) as span:
            data = await asyncio.wait_for(call(), timeout=manifest.timeout_seconds)
        validate_schema(data, manifest.output_schema)
        return MCPInvocationResult(
            tool_id=manifest.tool_id,
            provider_id=manifest.provider_id,
            schema_hash=manifest.schema_hash,
            data=data,
            trace_id=span.trace_id,
            span_id=span.span_id,
        )
