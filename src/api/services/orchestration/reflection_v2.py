"""Rule-first result validation and bounded repair decisions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.api.domain.agent_protocols import AgentResult, ProposedAction

from .repair import RepairBudget


class ReflectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal[
        "pass",
        "supplement_retrieval",
        "clarify",
        "local_repair",
        "waiting_approval",
        "degrade",
        "fail",
    ]
    outcome_status: Literal[
        "succeeded",
        "partial",
        "blocked",
        "failed",
        "waiting_approval",
        "result_unknown",
    ]
    reason_codes: tuple[str, ...]
    next_budget: RepairBudget


class ReflectionEngine:
    """Deterministic checks precede any optional LLM semantic critique."""

    def evaluate(
        self,
        *,
        results: Sequence[AgentResult],
        required_evidence: bool,
        proposed_actions: Sequence[ProposedAction],
        budget: RepairBudget,
        command_statuses: Sequence[dict[str, object]] = (),
    ) -> ReflectionDecision:
        if any(item.get("status") == "result_unknown" for item in command_statuses):
            return ReflectionDecision(
                action="degrade",
                outcome_status="result_unknown",
                reason_codes=("COMMAND_RESULT_UNKNOWN",),
                next_budget=budget,
            )
        if proposed_actions:
            return ReflectionDecision(
                action="waiting_approval",
                outcome_status="waiting_approval",
                reason_codes=("PROPOSED_ACTION_REQUIRES_POLICY",),
                next_budget=budget,
            )
        if required_evidence and not any(result.evidence_refs for result in results):
            if budget.retrieval_rewrite_remaining > 0:
                return ReflectionDecision(
                    action="supplement_retrieval",
                    outcome_status="blocked",
                    reason_codes=("REQUIRED_EVIDENCE_MISSING",),
                    next_budget=budget.consume("retrieval_rewrite"),
                )
            return ReflectionDecision(
                action="clarify",
                outcome_status="blocked",
                reason_codes=("EVIDENCE_BUDGET_EXHAUSTED",),
                next_budget=budget,
            )
        if not results:
            return ReflectionDecision(
                action="fail",
                outcome_status="failed",
                reason_codes=("NO_AGENT_RESULT",),
                next_budget=budget,
            )
        succeeded = [result for result in results if result.status == "succeeded"]
        failed = [result for result in results if result.status == "failed"]
        partial = [
            result for result in results if result.status in {"partial", "blocked"}
        ]
        if succeeded and (failed or partial):
            return ReflectionDecision(
                action="degrade",
                outcome_status="partial",
                reason_codes=("MIXED_AGENT_RESULTS",),
                next_budget=budget,
            )
        if failed:
            retryable = any(
                result.error and result.error.retryable for result in failed
            )
            if retryable and budget.replan_remaining > 0:
                return ReflectionDecision(
                    action="local_repair",
                    outcome_status="blocked",
                    reason_codes=("RETRYABLE_NODE_FAILURE",),
                    next_budget=budget.consume("replan"),
                )
            return ReflectionDecision(
                action="fail",
                outcome_status="failed",
                reason_codes=("AGENT_EXECUTION_FAILED",),
                next_budget=budget,
            )
        if partial:
            return ReflectionDecision(
                action="degrade",
                outcome_status="partial",
                reason_codes=("AGENT_RESULT_PARTIAL",),
                next_budget=budget,
            )
        return ReflectionDecision(
            action="pass",
            outcome_status="succeeded",
            reason_codes=("ALL_RULE_CHECKS_PASSED",),
            next_budget=budget,
        )
