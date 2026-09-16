"""Feature-gated LangGraph entry point for the warehouse V2 runtime.

This increment performs governed query understanding, planning, compilation,
and READY-set calculation. It intentionally has no external side effects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.api.graphs.state_v2 import WarehouseGraphStateV2
from src.api.services.orchestration.capability_registry import (
    CapabilityRegistry,
    build_default_capability_registry,
)
from src.api.services.orchestration.agent_executor import AgentExecutorRegistry
from src.api.services.orchestration.compiler import PlanCompiler
from src.api.services.orchestration.coordinator import Coordinator
from src.api.services.orchestration.htn_registry import (
    HTNRegistry,
    build_default_htn_registry,
)
from src.api.services.orchestration.planner import PlannerV2
from src.api.services.orchestration.reflection_v2 import ReflectionEngine
from src.api.services.orchestration.repair import RepairBudget
from src.api.services.orchestration.answer_synthesis import AnswerSynthesizer
from src.api.services.memory_v2.loader import MemoryLoader
from src.api.services.memory_v2.models import MemoryContext, MemoryWriteReport
from src.api.services.memory_v2.writer import MemoryWriter
from src.retrieval.v2.query_understanding import QueryUnderstandingService


def _event(event_type: str, stage: str) -> dict[str, Any]:
    return {
        "type": event_type,
        "stage": stage,
        "occurred_at": datetime.now(UTC).isoformat(),
    }


class WarehouseGraphRuntimeV2:
    """Own V2 graph dependencies while keeping node methods independently testable."""

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        htn_registry: HTNRegistry | None = None,
        executors: AgentExecutorRegistry | None = None,
        memory_loader: MemoryLoader | None = None,
        memory_writer: MemoryWriter | None = None,
    ) -> None:
        self.capability_registry = (
            capability_registry or build_default_capability_registry()
        )
        self.query_understanding = QueryUnderstandingService()
        self.planner = PlannerV2(htn_registry or build_default_htn_registry())
        self.compiler = PlanCompiler(self.capability_registry)
        self.execution_enabled = executors is not None
        self.coordinator = Coordinator(executors)
        self.reflection = ReflectionEngine()
        self.answer_synthesizer = AnswerSynthesizer()
        self.memory_loader = memory_loader
        self.memory_writer = memory_writer

    def ingress(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        message = str(state.get("request", {}).get("message", "")).strip()
        if not message:
            raise ValueError("message cannot be blank")
        return {
            "status": "running",
            "stage": "ingress",
            "events": [_event("run.started", "ingress")],
        }

    def understand(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        run = state["run"]
        query = self.query_understanding.parse(
            str(state["request"]["message"]),
            state["identity"],
            run.created_at,
        )
        return {
            "stage": "understood",
            "query": query,
            "events": [_event("query.understood", "understood")],
        }

    async def load_memory(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        request = dict(state["request"])
        context = dict(request.get("context") or {})
        if self.memory_loader is None:
            memory_context = MemoryContext()
        else:
            try:
                memory_context = await self.memory_loader.load(
                    state["identity"],
                    str(request["message"]),
                    conversation_id=state["run"].conversation_id,
                    now=state["run"].created_at,
                )
            except Exception:
                memory_context = MemoryContext(warnings=("memory_loader_unavailable",))
        context["memory"] = memory_context.to_prompt_context()
        request["context"] = context
        return {
            "stage": "memory_loaded",
            "request": request,
            "memory_context": memory_context,
            "events": [_event("memory.loaded", "memory_loaded")],
        }

    async def plan(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        result = await self.planner.plan(state["query"])
        if result.plan is None:
            raise ValueError("planning requires clarification before execution")
        return {
            "stage": "planned",
            "planning_mode": result.mode,
            "plan": result.plan,
            "events": [_event("plan.created", "planned")],
        }

    def compile(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        compiled = self.compiler.compile(state["plan"], state["identity"])
        return {
            "stage": "compiled",
            "compiled_plan": compiled,
            "events": [_event("plan.compiled", "compiled")],
        }

    def coordinate(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        node_runs = Coordinator.advance_control_nodes(
            state["plan"], state.get("node_runs", {})
        )
        ready = Coordinator.ready_nodes(state["plan"], node_runs)
        return {
            "stage": "coordinated",
            "node_runs": node_runs,
            "ready_node_ids": [node.node_id for node in ready],
            "events": [_event("coordination.ready", "coordinated")],
        }

    def route_after_coordinate(self, state: WarehouseGraphStateV2) -> str:
        if not self.execution_enabled:
            return "answer"
        nodes = {node.node_id: node for node in state["plan"].nodes}
        if any(
            nodes[node_id].node_type == "task"
            for node_id in state.get("ready_node_ids", [])
        ):
            return "execute"
        return "reflect"

    async def execute(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        update = await self.coordinator.execute_ready(
            compiled=state["compiled_plan"],
            run=state["run"],
            identity=state["identity"],
            request=state["request"],
            node_runs=state.get("node_runs", {}),
            previous_results=tuple(state.get("agent_results", [])),
        )
        return {
            "stage": "executing",
            "node_runs": update.node_runs,
            "agent_results": list(update.results),
            "evidence_refs": [
                evidence
                for result in update.results
                for evidence in result.evidence_refs
            ],
            "proposed_actions": [
                action
                for result in update.results
                for action in result.proposed_actions
            ],
            "events": [_event("agent.execution.completed", "executing")],
        }

    def reflect(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        budget = RepairBudget.model_validate(state.get("repair_budget", {}))
        decision = self.reflection.evaluate(
            results=tuple(state.get("agent_results", [])),
            required_evidence=bool(
                state.get("request", {}).get("require_evidence", False)
            ),
            proposed_actions=tuple(state.get("proposed_actions", [])),
            budget=budget,
            command_statuses=tuple(state.get("command_statuses", [])),
        )
        return {
            "stage": "reflected",
            "reflection_decision": decision,
            "repair_budget": decision.next_budget.model_dump(mode="python"),
            "events": [_event("reflection.completed", "reflected")],
        }

    def answer(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        ready = state.get("ready_node_ids", [])
        results = state.get("agent_results", [])
        if results:
            decision = state.get("reflection_decision")
            if decision is not None:
                final_answer = self.answer_synthesizer.synthesize(
                    decision,
                    results=results,
                    claims=tuple(state.get("claims", [])),
                    citations=tuple(state.get("citations", [])),
                    command_statuses=tuple(state.get("command_statuses", [])),
                )
            else:
                succeeded = [
                    result for result in results if result.status == "succeeded"
                ]
                failed = [result for result in results if result.status == "failed"]
                status = (
                    "succeeded"
                    if succeeded and not failed
                    else "partial" if succeeded else "failed"
                )
                final_answer = {
                    "status": status,
                    "message": "\n".join(result.summary for result in results),
                }
        else:
            final_answer = {
                "status": "partial",
                "message": "V2 plan compiled; domain execution is not enabled yet.",
            }
        final_answer.update(
            {
                "plan_id": state["plan"].plan_id,
                "ready_node_ids": ready,
            }
        )
        return {
            "stage": "answered",
            "final_answer": final_answer,
            "events": [_event("answer.generated", "answered")],
        }

    async def write_memory(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        if self.memory_writer is None:
            report = MemoryWriteReport(status="skipped")
            event_type = "memory.write.skipped"
        else:
            try:
                report = await self.memory_writer.extract_and_store(
                    dict(state), state["identity"]
                )
                event_type = "memory.write.completed"
            except Exception:
                report = MemoryWriteReport(
                    status="failed", error_code="MEMORY_WRITE_UNAVAILABLE"
                )
                event_type = "memory.write.failed"
        return {
            "stage": "memory_written",
            "memory_write_report": report,
            "events": [_event(event_type, "memory_written")],
        }

    def finalize(self, state: WarehouseGraphStateV2) -> WarehouseGraphStateV2:
        return {
            "status": "completed",
            "stage": "finalized",
            "events": [_event("run.completed", "finalized")],
        }


def build_warehouse_graph_v2(
    checkpointer: BaseCheckpointSaver | None = None,
    runtime: WarehouseGraphRuntimeV2 | None = None,
) -> CompiledStateGraph:
    """Compile the side-effect-free V2 graph entry point."""

    runtime = runtime or WarehouseGraphRuntimeV2()
    workflow = StateGraph(WarehouseGraphStateV2)
    workflow.add_node("ingress", runtime.ingress)
    workflow.add_node("load_memory", runtime.load_memory)
    workflow.add_node("understand", runtime.understand)
    workflow.add_node("plan", runtime.plan)
    workflow.add_node("compile", runtime.compile)
    workflow.add_node("coordinate", runtime.coordinate)
    workflow.add_node("execute", runtime.execute)
    workflow.add_node("reflect", runtime.reflect)
    workflow.add_node("answer", runtime.answer)
    workflow.add_node("write_memory", runtime.write_memory)
    workflow.add_node("finalize", runtime.finalize)
    workflow.set_entry_point("ingress")
    workflow.add_edge("ingress", "load_memory")
    workflow.add_edge("load_memory", "understand")
    workflow.add_edge("understand", "plan")
    workflow.add_edge("plan", "compile")
    workflow.add_edge("compile", "coordinate")
    workflow.add_conditional_edges(
        "coordinate",
        runtime.route_after_coordinate,
        {"execute": "execute", "reflect": "reflect", "answer": "answer"},
    )
    workflow.add_edge("execute", "coordinate")
    workflow.add_edge("reflect", "answer")
    workflow.add_edge("answer", "write_memory")
    workflow.add_edge("write_memory", "finalize")
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=checkpointer)
