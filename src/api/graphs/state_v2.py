"""Typed LangGraph state and deterministic reducers for the V2 runtime."""

from __future__ import annotations

from typing import Annotated, Any, Iterable, TypedDict

from src.api.domain.agent_protocols import AgentResult, ProposedAction
from src.api.domain.evidence_protocols import EvidenceRef
from src.api.domain.identity import IdentityContext
from src.api.services.runs.context_v2 import RunExecutionContextV2


def merge_agent_results(
    current: Iterable[AgentResult] | None,
    updates: Iterable[AgentResult] | None,
) -> list[AgentResult]:
    """Merge results by task ID; a newer node update replaces its old snapshot."""

    indexed = {item.task_id: item for item in current or ()}
    indexed.update({item.task_id: item for item in updates or ()})
    return [indexed[key] for key in sorted(indexed)]


def merge_evidence_refs(
    current: Iterable[EvidenceRef] | None,
    updates: Iterable[EvidenceRef] | None,
) -> list[EvidenceRef]:
    """Deduplicate immutable evidence references by evidence ID."""

    indexed = {item.evidence_id: item for item in current or ()}
    indexed.update({item.evidence_id: item for item in updates or ()})
    return [indexed[key] for key in sorted(indexed)]


def merge_proposed_actions(
    current: Iterable[ProposedAction] | None,
    updates: Iterable[ProposedAction] | None,
) -> list[ProposedAction]:
    """Deduplicate proposed actions without executing them."""

    indexed = {item.action_id: item for item in current or ()}
    indexed.update({item.action_id: item for item in updates or ()})
    return [indexed[key] for key in sorted(indexed)]


def append_events(
    current: Iterable[dict[str, Any]] | None,
    updates: Iterable[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Append ordered runtime events emitted by sequential graph nodes."""

    return [*(current or ()), *(updates or ())]


class WarehouseGraphStateV2(TypedDict, total=False):
    """Small orchestration state; large payloads remain in external stores."""

    identity: IdentityContext
    run: RunExecutionContextV2
    request: dict[str, Any]
    status: str
    stage: str
    planning_mode: str
    query: Any
    memory_context: Any
    memory_write_report: Any
    plan: Any
    compiled_plan: Any
    ready_node_ids: list[str]
    node_runs: dict[str, Any]
    agent_results: Annotated[list[AgentResult], merge_agent_results]
    evidence_refs: Annotated[list[EvidenceRef], merge_evidence_refs]
    proposed_actions: Annotated[list[ProposedAction], merge_proposed_actions]
    claims: list[Any]
    citations: list[Any]
    command_statuses: list[dict[str, Any]]
    approvals: dict[str, Any]
    repair_budget: dict[str, int]
    reflection_decision: Any
    final_answer: dict[str, Any]
    errors: list[dict[str, Any]]
    events: Annotated[list[dict[str, Any]], append_events]
