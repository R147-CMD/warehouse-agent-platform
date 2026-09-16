"""Answer status assembly from validated results, claims, citations and commands."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.api.domain.agent_protocols import AgentResult
from src.api.domain.evidence_protocols import Citation, Claim

from .reflection_v2 import ReflectionDecision


class AnswerSynthesizer:
    _STATUS_PREFIXES = {
        "waiting_approval": "该操作已生成待审批动作，等待人工审批，当前未执行。",
        "result_unknown": "请求已提交，但无法确认外部系统最终状态，请先回查后再判断是否完成。",
        "blocked": "当前无法继续执行该任务，请补充信息或处理阻塞原因。",
        "partial": "任务部分完成，以下结果不代表所有步骤均已完成。",
        "failed": "任务执行失败，以下内容仅为已获得的结果。",
    }

    def synthesize(
        self,
        decision: ReflectionDecision,
        *,
        results: Sequence[AgentResult],
        claims: Sequence[Claim] = (),
        citations: Sequence[Citation] = (),
        command_statuses: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        supported_claim_ids = {
            claim.claim_id for claim in claims if claim.status == "supported"
        }
        safe_citations = [
            citation.model_dump(mode="json")
            for citation in citations
            if citation.claim_id in supported_claim_ids
        ]
        summaries = [result.summary for result in results]
        prefix = self._STATUS_PREFIXES.get(decision.outcome_status)
        message_parts = ([prefix] if prefix else []) + summaries
        return {
            "status": decision.outcome_status,
            "message": "\n".join(message_parts),
            "reason_codes": list(decision.reason_codes),
            "claims": [claim.model_dump(mode="json") for claim in claims],
            "citations": safe_citations,
            "commands": list(command_statuses),
        }
