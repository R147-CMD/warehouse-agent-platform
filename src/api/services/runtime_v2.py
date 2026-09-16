"""Composition root for the feature-gated V2 Agent platform."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import re

from langgraph.checkpoint.base import BaseCheckpointSaver

from src.api.agents.v2.catalog import build_specialist_executors
from src.api.agents.v2.action_proposals import build_default_action_proposal_handlers
from src.api.domain.agent_protocols import AgentResult, AgentTask
from src.api.domain.evidence_protocols import EntityRef
from src.api.domain.identity import AccessControl, IdentityContext
from src.api.graphs.warehouse_graph_v2 import (
    WarehouseGraphRuntimeV2,
    build_warehouse_graph_v2,
)
from src.api.services.evidence_v2.models import Evidence
from src.api.services.evidence_v2.store import EvidenceStore, InMemoryEvidenceStore
from src.api.services.mcp.gateway_v2 import MCPGatewayV2
from src.api.services.execution.control_plane import ControlledExecutionService
from src.api.services.memory_v2.loader import MemoryLoader
from src.api.services.memory_v2.writer import MemoryWriter
from src.api.services.runs.context_v2 import RunIdentityFactory
from src.retrieval.v2.pipeline import RetrievalPipeline
from src.retrieval.v2.query_understanding import QueryUnderstandingService


class WarehouseAgentPlatformV2:
    """Wire planners and Agents to injected domain/MCP/retrieval providers."""

    def __init__(
        self,
        *,
        retrieval: RetrievalPipeline | None = None,
        evidence_store: EvidenceStore | None = None,
        mcp_gateway: MCPGatewayV2 | None = None,
        capability_handlers: dict[str, Any] | None = None,
        mcp_tool_bindings: dict[str, str] | None = None,
        mcp_argument_builders: dict[str, Any] | None = None,
        control_plane: ControlledExecutionService | None = None,
        memory_loader: MemoryLoader | None = None,
        memory_writer: MemoryWriter | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.evidence_store = evidence_store or InMemoryEvidenceStore()
        self.mcp_gateway = mcp_gateway
        self.control_plane = control_plane
        handlers = build_default_action_proposal_handlers()
        handlers.update(capability_handlers or {})
        if retrieval is not None:
            handlers.setdefault("knowledge.search", self._knowledge_search)
        for capability, tool_id in (mcp_tool_bindings or {}).items():
            builder = (mcp_argument_builders or {}).get(capability)
            handlers.setdefault(capability, self._mcp_handler(tool_id, builder))
        executors = build_specialist_executors(handlers)
        self.runtime = WarehouseGraphRuntimeV2(
            executors=executors,
            memory_loader=memory_loader,
            memory_writer=memory_writer,
        )
        self.graph = build_warehouse_graph_v2(
            checkpointer=checkpointer,
            runtime=self.runtime,
        )

    async def process(
        self,
        message: str,
        identity: IdentityContext,
        *,
        conversation_id: str,
        request_id: str | None = None,
        require_evidence: bool = False,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run = RunIdentityFactory.create(
            conversation_id, identity, request_id=request_id
        )
        result = await self.graph.ainvoke(
            {
                "run": run,
                "identity": identity,
                "request": {
                    "message": message,
                    "context": context or {},
                    "require_evidence": require_evidence,
                },
                "status": "queued",
                "events": [],
                "repair_budget": {},
            },
            config={"configurable": {"thread_id": run.thread_id}},
        )
        if self.control_plane is not None and result.get("proposed_actions"):
            await self.control_plane.register(
                run.run_id,
                identity,
                tuple(result["proposed_actions"]),
            )
        return result

    async def _knowledge_search(self, task: AgentTask) -> AgentResult:
        if self.retrieval is None:
            raise RuntimeError("retrieval pipeline is unavailable")
        query = QueryUnderstandingService().parse(
            str(task.inputs.get("query") or task.objective),
            task.identity,
            datetime.now(UTC),
        )
        # A knowledge capability always uses document channels even when a
        # short Agent objective was classified conservatively.
        if query.query_type == "structured_fact":
            query = query.model_copy(update={"query_type": "document_knowledge"})
        retrieval_result = await self.retrieval.retrieve(query, task.identity)
        evidence_refs = []
        for candidate in retrieval_result.context.items:
            entity_refs = tuple(
                EntityRef(
                    entity_type=str(item.get("entity_type", "entity")),
                    entity_id=str(item.get("entity_id", candidate.candidate_id)),
                    source_system=str(
                        candidate.metadata.get("source_system") or candidate.channel
                    ),
                )
                for item in candidate.metadata.get("entity_refs", [])
            )
            evidence = Evidence.create(
                evidence_type=candidate.source_type,
                source_system=str(
                    candidate.metadata.get("source_system") or candidate.channel
                ),
                source_locator=candidate.source_locator,
                content=candidate.metadata.get("record", candidate.content),
                entity_refs=entity_refs,
                observed_at=datetime.now(UTC),
                source_version=candidate.metadata.get("source_version"),
                freshness="fresh",
                trust_level="verified",
                acl=AccessControl(
                    tenant_id=task.identity.tenant_id,
                    warehouse_ids=candidate.warehouse_ids,
                    required_scopes=candidate.required_scopes,
                ),
            )
            await self.evidence_store.append(evidence)
            evidence_refs.append(evidence.ref)
        status = (
            "succeeded"
            if retrieval_result.status == "succeeded"
            else "partial" if evidence_refs else "failed"
        )
        if status == "failed":
            from src.api.domain.errors import AgentError, ErrorCategory

            error = AgentError(
                code="RETRIEVAL_UNAVAILABLE",
                category=ErrorCategory.DEPENDENCY_UNAVAILABLE,
                message="No retrieval channel returned evidence",
                retryable=True,
                details=retrieval_result.errors,
            )
        else:
            error = None
        return AgentResult(
            task_id=task.task_id,
            status=status,
            summary=(
                f"Retrieved {len(evidence_refs)} governed knowledge source(s)."
                if evidence_refs
                else "No governed knowledge source was available."
            ),
            data={
                "candidate_ids": [
                    item.candidate_id for item in retrieval_result.context.items
                ],
                "degraded_channels": list(retrieval_result.degraded_channels),
            },
            evidence_refs=tuple(evidence_refs),
            confidence=0.9 if evidence_refs else 0.0,
            error=error,
        )

    def _mcp_handler(self, tool_id: str, argument_builder=None):
        async def handler(task: AgentTask) -> AgentResult:
            if self.mcp_gateway is None:
                raise RuntimeError("MCP gateway is unavailable")
            arguments = argument_builder(task) if argument_builder else task.inputs
            result = await self.mcp_gateway.invoke(tool_id, arguments, task.identity)
            parsed = QueryUnderstandingService().parse(
                task.objective, task.identity, datetime.now(UTC)
            )
            evidence = Evidence.create(
                evidence_type="tool_result",
                source_system=result.provider_id,
                source_locator={
                    "tool_id": result.tool_id,
                    "schema_hash": result.schema_hash,
                },
                content=result.data,
                entity_refs=tuple(
                    EntityRef(
                        entity_type=item.entity_type,
                        entity_id=item.entity_id,
                        source_system=result.provider_id,
                    )
                    for item in parsed.entities
                ),
                observed_at=datetime.now(UTC),
                freshness="live",
                trust_level="verified",
                acl=AccessControl(
                    tenant_id=task.identity.tenant_id,
                    warehouse_ids=task.identity.warehouse_scope,
                ),
            )
            await self.evidence_store.append(evidence)
            return AgentResult(
                task_id=task.task_id,
                status="succeeded",
                summary=f"MCP tool {tool_id} returned a result.",
                data={
                    "tool_id": tool_id,
                    "result": result.data,
                    "trust": result.trust_level,
                },
                evidence_refs=(evidence.ref,),
                confidence=0.85,
            )

        return handler


def sap_stock_arguments(task: AgentTask) -> dict[str, Any]:
    sku = next(
        (
            entity.entity_id
            for entity in QueryUnderstandingService()
            .parse(task.objective, task.identity, datetime.now(UTC))
            .entities
            if entity.entity_type == "sku"
        ),
        None,
    )
    return {"product": sku, "limit": 50}


def sap_orders_arguments(task: AgentTask) -> dict[str, Any]:
    match = re.search(
        r"(?:订单|order)\s*(?:WO-)?(\d{6,20})", task.objective, re.IGNORECASE
    )
    return {"order_id": match.group(1) if match else None, "limit": 50}
