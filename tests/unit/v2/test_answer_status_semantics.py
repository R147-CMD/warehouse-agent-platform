from __future__ import annotations

from src.api.domain.agent_protocols import AgentResult
from src.api.services.orchestration.answer_synthesis import AnswerSynthesizer
from src.api.services.orchestration.reflection_v2 import ReflectionDecision
from src.api.services.orchestration.repair import RepairBudget


def _result(summary: str = "已查询库存") -> AgentResult:
    return AgentResult(
        task_id="run:query",
        status="succeeded",
        summary=summary,
        confidence=0.9,
    )


def _decision(status: str, reason: str = "TEST") -> ReflectionDecision:
    return ReflectionDecision(
        action="pass" if status == "succeeded" else "degrade",
        outcome_status=status,
        reason_codes=(reason,),
        next_budget=RepairBudget(),
    )


def test_waiting_approval_answer_does_not_claim_action_completed() -> None:
    answer = AnswerSynthesizer().synthesize(
        _decision("waiting_approval"),
        results=(_result("已生成设备调度方案，尚未执行"),),
        command_statuses=({"status": "pending", "command_id": "cmd-1"},),
    )

    assert answer["status"] == "waiting_approval"
    assert "等待人工审批" in answer["message"]
    assert "已执行" not in answer["message"]


def test_result_unknown_answer_is_explicit_about_external_state() -> None:
    answer = AnswerSynthesizer().synthesize(
        _decision("result_unknown", "WRITE_RESPONSE_LOST"),
        results=(_result("已提交 SAP 更新请求"),),
        command_statuses=({"status": "result_unknown", "command_id": "cmd-2"},),
    )

    assert answer["status"] == "result_unknown"
    assert "无法确认外部系统最终状态" in answer["message"]
    assert "执行成功" not in answer["message"]


def test_blocked_answer_explains_that_workflow_cannot_continue() -> None:
    answer = AnswerSynthesizer().synthesize(
        _decision("blocked", "EVIDENCE_BUDGET_EXHAUSTED"),
        results=(_result(),),
    )

    assert answer["status"] == "blocked"
    assert "当前无法继续" in answer["message"]
