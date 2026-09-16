from __future__ import annotations

from src.api.domain.agent_protocols import AgentResult, ProposedAction, ResourceRef
from src.api.services.orchestration.reflection_v2 import ReflectionEngine
from src.api.services.orchestration.repair import RepairBudget


def result(status="succeeded", *, evidence=()):
    return AgentResult(
        task_id="run:node",
        status=status,
        summary="done",
        evidence_refs=evidence,
        confidence=0.9,
        error=None,
    )


def test_reflection_requests_retrieval_once_then_clarifies() -> None:
    engine = ReflectionEngine()

    first = engine.evaluate(
        results=(result(),),
        required_evidence=True,
        proposed_actions=(),
        budget=RepairBudget(),
    )
    exhausted = engine.evaluate(
        results=(result(),),
        required_evidence=True,
        proposed_actions=(),
        budget=RepairBudget(retrieval_rewrite_remaining=0),
    )

    assert first.action == "supplement_retrieval"
    assert exhausted.action == "clarify"


def test_reflection_never_executes_a_proposed_action() -> None:
    proposal = ProposedAction(
        action_id="a1",
        capability="equipment.dispatch",
        target=ResourceRef(resource_type="equipment", resource_id="EQ-1"),
        arguments={"zone": "A"},
        expected_effect="dispatch equipment",
        risk_level="high",
        idempotency_key="eq-1-zone-a",
    )

    decision = ReflectionEngine().evaluate(
        results=(result(),),
        required_evidence=False,
        proposed_actions=(proposal,),
        budget=RepairBudget(),
    )

    assert decision.action == "waiting_approval"
    assert decision.reason_codes == ("PROPOSED_ACTION_REQUIRES_POLICY",)


def test_reflection_marks_mixed_results_partial() -> None:
    failed = AgentResult(
        task_id="run:failed",
        status="failed",
        summary="failed",
        confidence=0,
        error={
            "code": "UPSTREAM_TIMEOUT",
            "category": "timeout",
            "message": "timeout",
            "retryable": True,
        },
    )
    decision = ReflectionEngine().evaluate(
        results=(result(), failed),
        required_evidence=False,
        proposed_actions=(),
        budget=RepairBudget(reflection_remaining=0),
    )
    assert decision.action == "degrade"
    assert decision.outcome_status == "partial"
