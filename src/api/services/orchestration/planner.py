"""Fast-path, HTN, and structured candidate planning for V2 requests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.api.domain.agent_protocols import MissingInput
from src.retrieval.v2.contracts import QueryEnvelope

from .complexity import ComplexityClassifier
from .htn_registry import HTNRegistry
from .models import PlanGraph, PlanNode

CandidatePlanProvider = Callable[[QueryEnvelope], Awaitable[PlanGraph]]


class PlanningResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["fast_path", "htn", "llm", "clarify"]
    plan: PlanGraph | None = None
    missing_inputs: tuple[MissingInput, ...] = ()
    reason_codes: tuple[str, ...] = ()


class PlannerV2:
    def __init__(
        self,
        htn_registry: HTNRegistry,
        candidate_plan_provider: CandidatePlanProvider | None = None,
    ) -> None:
        self._htn_registry = htn_registry
        self._candidate_plan_provider = candidate_plan_provider

    async def plan(self, query: QueryEnvelope) -> PlanningResult:
        decision = ComplexityClassifier.classify(query)
        if decision.mode == "clarify":
            return PlanningResult(
                mode="clarify",
                missing_inputs=query.missing_inputs,
                reason_codes=decision.reason_codes,
            )
        if decision.mode == "fast_path":
            return PlanningResult(
                mode="fast_path",
                plan=self._fast_path(query),
                reason_codes=decision.reason_codes,
            )
        if decision.mode == "htn":
            lowered = query.normalized_query.lower()
            if "sap" in lowered and any(term in lowered for term in ("分配", "assign")):
                template_id = "sap_assign_order.v1"
            elif "sap" in lowered and any(
                term in lowered for term in ("确认", "confirm")
            ):
                template_id = "sap_confirm_task.v1"
            elif any(term in lowered for term in ("调度", "dispatch")) and any(
                term in lowered for term in ("设备", "equipment", "eq-")
            ):
                template_id = "equipment_dispatch.v1"
            elif "重平衡" in query.normalized_query or "rebalance" in lowered:
                template_id = "rebalance_picking_tasks.v1"
            else:
                template_id = "controlled_action.v1"
            return PlanningResult(
                mode="htn",
                plan=self._htn_registry.expand(
                    template_id,
                    objective=query.normalized_query,
                ),
                reason_codes=decision.reason_codes,
            )

        if self._candidate_plan_provider is not None:
            plan = await self._candidate_plan_provider(query)
            reason_codes = (*decision.reason_codes, "structured_model_candidate")
        else:
            plan = self._hybrid_candidate(query)
            reason_codes = (*decision.reason_codes, "deterministic_safe_fallback")
        return PlanningResult(mode="llm", plan=plan, reason_codes=reason_codes)

    @staticmethod
    def _stable_plan_id(prefix: str, query: QueryEnvelope) -> str:
        digest = sha256(query.normalized_query.encode("utf-8")).hexdigest()[:20]
        return f"{prefix}-{digest}"

    def _fast_path(self, query: QueryEnvelope) -> PlanGraph:
        capability = (
            "knowledge.search"
            if query.query_type == "document_knowledge"
            else "warehouse.fact.query"
        )
        return PlanGraph(
            plan_id=self._stable_plan_id("fast", query),
            version=1,
            objective=query.normalized_query,
            nodes=(
                PlanNode(node_id="query", node_type="task", capability=capability),
                PlanNode(node_id="answer", node_type="answer", depends_on=("query",)),
            ),
        )

    def _hybrid_candidate(self, query: QueryEnvelope) -> PlanGraph:
        return PlanGraph(
            plan_id=self._stable_plan_id("candidate", query),
            version=1,
            objective=query.normalized_query,
            nodes=(
                PlanNode(
                    node_id="query_facts",
                    node_type="task",
                    capability="warehouse.fact.query",
                ),
                PlanNode(
                    node_id="query_knowledge",
                    node_type="task",
                    capability="knowledge.search",
                ),
                PlanNode(
                    node_id="join_evidence",
                    node_type="join",
                    depends_on=("query_facts", "query_knowledge"),
                    join_policy="best_effort",
                ),
                PlanNode(
                    node_id="answer",
                    node_type="answer",
                    depends_on=("join_evidence",),
                ),
            ),
        )
