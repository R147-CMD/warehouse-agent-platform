"""Optional LLM judge for LangGraph reflection decisions.

The deterministic reflection rules remain the safety baseline.  This module
only strengthens reflection quality: it may request clarification/replanning,
but it cannot override hard safety clarifications from the rule layer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Mapping
from typing import Any

from src.api.utils.log_utils import sanitize_log_data

from .reflection_loop import VALID_AGENT_ROUTES


logger = logging.getLogger(__name__)

VALID_JUDGE_DECISIONS = {"finalize", "clarify", "replan"}
DEFAULT_JUDGE_TIMEOUT_SECONDS = 25.0


async def evaluate_with_llm_judge(
    state: Mapping[str, Any],
    rule_decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a safety-preserving reflection decision enriched by an LLM judge."""

    if _is_hard_rule_clarification(rule_decision):
        merged = merge_rule_and_judge_decisions(
            rule_decision,
            {
                "status": "skipped",
                "mode": "rule_safety_gate",
                "decision": rule_decision.get("action", "clarify"),
                "reasons": ["规则层要求先补齐高风险动作字段，LLM Judge 不参与覆盖。"],
            },
        )
        return merged

    context = _mapping(state.get("context"))
    if not _judge_enabled(context):
        return _attach_judge_status(
            rule_decision,
            status="disabled",
            mode="rule_fallback",
            reasons=["LLM Reflection Judge 已通过配置关闭。"],
        )

    if not os.getenv("NVIDIA_API_KEY", "").strip():
        return _attach_judge_status(
            rule_decision,
            status="skipped",
            mode="rule_fallback",
            reasons=["NVIDIA_API_KEY 未配置，使用规则反思结果。"],
        )

    try:
        prompt = _build_judge_prompt(state, rule_decision)
        from src.api.services.llm.nim_client import get_nim_client

        client = await get_nim_client()
        response = await asyncio.wait_for(
            client.generate_response(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a strict warehouse operations Agent judge. "
                            "Return only valid JSON. Do not execute tools."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=900,
                max_retries=1,
            ),
            timeout=_judge_timeout(context),
        )
        judge_result = parse_llm_judge_response(response.content)
        judge_result["status"] = "ok"
        judge_result["mode"] = "llm_judge"
        judge_result["model"] = response.model
        return merge_rule_and_judge_decisions(rule_decision, judge_result)
    except Exception as exc:
        logger.warning(
            "LLM Reflection Judge failed, using rule decision: %s",
            sanitize_log_data(str(exc)),
        )
        return _attach_judge_status(
            rule_decision,
            status="fallback",
            mode="rule_fallback",
            reasons=[f"LLM Judge 调用失败：{sanitize_log_data(str(exc), max_length=160)}"],
        )


def parse_llm_judge_response(content: str) -> dict[str, Any]:
    """Parse and normalize the LLM judge JSON response."""

    raw = (content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(raw[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("LLM judge response must be a JSON object.")

    decision = str(parsed.get("decision") or parsed.get("action") or "finalize").lower()
    if decision not in VALID_JUDGE_DECISIONS:
        decision = "finalize"

    return {
        "decision": decision,
        "quality_score": _score(parsed.get("quality_score"), 0.7),
        "route_score": _score(parsed.get("route_score"), 0.7),
        "safety_score": _score(parsed.get("safety_score"), 0.8),
        "confidence": _score(parsed.get("confidence"), 0.7),
        "reasons": _string_list(parsed.get("reasons")),
        "missing_information": _string_list(
            parsed.get("missing_information") or parsed.get("missing_facts")
        ),
        "next_route": _valid_route(parsed.get("next_route")),
        "raw_decision": parsed,
    }


def merge_rule_and_judge_decisions(
    rule_decision: Mapping[str, Any],
    judge_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge rule and LLM decisions without weakening deterministic safety."""

    merged = dict(rule_decision)
    judge_summary = _judge_summary(judge_result)
    rule_action = str(rule_decision.get("action") or "finalize")
    judge_decision = str(judge_result.get("decision") or rule_action).lower()
    if judge_decision not in VALID_JUDGE_DECISIONS:
        judge_decision = rule_action

    if _is_hard_rule_clarification(rule_decision) and judge_decision != "clarify":
        judge_summary["safety_override_blocked"] = True
        merged["llm_judge"] = judge_summary
        merged["reasons"] = _merge_reasons(
            rule_decision.get("reasons"),
            ["LLM Judge 试图放行，但规则层要求先追问，已保持 clarify。"],
        )
        return merged

    if judge_result.get("status") in {"disabled", "skipped", "fallback"}:
        merged["llm_judge"] = judge_summary
        return merged

    if judge_decision == "clarify":
        merged["action"] = "clarify"
        merged["next_route"] = "ambiguous"
        merged["missing_facts"] = _string_list(
            judge_result.get("missing_information")
            or rule_decision.get("missing_facts")
        )
        if merged["missing_facts"]:
            merged["clarifying_question"] = _judge_clarifying_question(
                merged["missing_facts"]
            )
            merged["clarifying_options"] = [
                f"补充{item}" for item in merged["missing_facts"]
            ]
    elif judge_decision == "replan":
        merged["action"] = "replan"
        merged["next_route"] = _valid_route(judge_result.get("next_route")) or _valid_route(
            rule_decision.get("next_route")
        ) or "general"
    elif rule_action in VALID_JUDGE_DECISIONS:
        merged["action"] = rule_action

    merged["confidence"] = judge_summary.get("confidence", merged.get("confidence"))
    merged["reasons"] = _merge_reasons(
        rule_decision.get("reasons"),
        judge_result.get("reasons"),
    )
    merged["llm_judge"] = judge_summary
    return merged


def _build_judge_prompt(
    state: Mapping[str, Any],
    rule_decision: Mapping[str, Any],
) -> str:
    snapshot = _safe_state_snapshot(state, rule_decision)
    return f"""
Evaluate this warehouse Agent execution. Decide whether the graph should:
- finalize: answer is good enough and safe
- clarify: missing critical information must be requested from the user
- replan: route/tool/result quality is weak, so the graph should try another route

Hard requirements:
- Never approve unsafe write actions.
- If tool evidence is missing for an analytical claim, prefer replan or clarify.
- If the user request is high-risk and required facts are missing, prefer clarify.
- Return JSON only.

Allowed next_route values: equipment, operations, safety, forecasting, document, general, ambiguous.

Execution snapshot:
{json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)}

Return this exact JSON shape:
{{
  "decision": "finalize|clarify|replan",
  "quality_score": 0.0,
  "route_score": 0.0,
  "safety_score": 0.0,
  "confidence": 0.0,
  "reasons": ["short reason"],
  "missing_information": [],
  "next_route": null
}}
"""


def _safe_state_snapshot(
    state: Mapping[str, Any],
    rule_decision: Mapping[str, Any],
) -> dict[str, Any]:
    context = _mapping(state.get("context"))
    plan = _mapping(state.get("planner_scratchpad") or context.get("planner_scratchpad"))
    route = str(state.get("routing_decision") or "general")
    agent_responses = _mapping(state.get("agent_responses"))
    response = agent_responses.get(route)
    structured_response = _mapping(context.get("structured_response"))

    return {
        "user_message": _preview(_extract_user_message(state), 500),
        "planner": {
            "summary": plan.get("summary"),
            "intent_type": plan.get("intent_type"),
            "risk_level": plan.get("risk_level"),
            "route_hint": plan.get("route_hint"),
            "missing_facts": plan.get("missing_facts", []),
            "requires_approval": plan.get("requires_approval"),
        },
        "route": route,
        "routing_confidence": state.get("routing_confidence"),
        "agent_response": _summarize_agent_response(response),
        "tools_used": context.get("mcp_tools_used", []),
        "tool_result_keys": list(_mapping(context.get("tool_execution_results")).keys())[:20],
        "actions_taken": structured_response.get("actions_taken") or context.get("actions_taken", []),
        "rule_reflection": {
            "action": rule_decision.get("action"),
            "reasons": rule_decision.get("reasons", []),
            "missing_facts": rule_decision.get("missing_facts", []),
            "next_route": rule_decision.get("next_route"),
            "iteration": rule_decision.get("iteration"),
            "max_iterations": rule_decision.get("max_iterations"),
        },
    }


def _summarize_agent_response(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return {
            "natural_language": _preview(response.get("natural_language"), 700),
            "confidence": response.get("confidence"),
            "response_type": response.get("response_type"),
            "recommendation_count": len(response.get("recommendations") or []),
            "data_keys": list(_mapping(response.get("data")).keys())[:20],
        }
    if response is None:
        return {"natural_language": None, "confidence": None, "response_type": None}
    return {
        "natural_language": _preview(response, 700),
        "confidence": getattr(response, "confidence", None),
        "response_type": getattr(response, "response_type", None),
    }


def _attach_judge_status(
    rule_decision: Mapping[str, Any],
    *,
    status: str,
    mode: str,
    reasons: list[str],
) -> dict[str, Any]:
    merged = dict(rule_decision)
    merged["llm_judge"] = {
        "status": status,
        "mode": mode,
        "decision": rule_decision.get("action", "finalize"),
        "quality_score": None,
        "route_score": None,
        "safety_score": None,
        "confidence": merged.get("confidence"),
        "reasons": reasons,
        "missing_information": [],
        "next_route": merged.get("next_route"),
        "used_rule_fallback": True,
        "safety_override_blocked": False,
    }
    return merged


def _judge_summary(judge_result: Mapping[str, Any]) -> dict[str, Any]:
    status = str(judge_result.get("status") or "ok")
    return {
        "status": status,
        "mode": str(judge_result.get("mode") or "llm_judge"),
        "model": judge_result.get("model"),
        "decision": str(judge_result.get("decision") or "finalize"),
        "quality_score": judge_result.get("quality_score"),
        "route_score": judge_result.get("route_score"),
        "safety_score": judge_result.get("safety_score"),
        "confidence": judge_result.get("confidence"),
        "reasons": _string_list(judge_result.get("reasons")),
        "missing_information": _string_list(judge_result.get("missing_information")),
        "next_route": _valid_route(judge_result.get("next_route")),
        "used_rule_fallback": status in {"disabled", "skipped", "fallback"},
        "safety_override_blocked": False,
    }


def _is_hard_rule_clarification(rule_decision: Mapping[str, Any]) -> bool:
    if str(rule_decision.get("action")) != "clarify":
        return False
    reasons = " ".join(_string_list(rule_decision.get("reasons")))
    return "高风险" in reasons or bool(rule_decision.get("missing_facts"))


def _judge_enabled(context: Mapping[str, Any]) -> bool:
    context_value = context.get("enable_llm_reflection_judge")
    if context_value is not None:
        if isinstance(context_value, str):
            return context_value.lower() not in {"0", "false", "no", "off"}
        return bool(context_value)
    return os.getenv("LLM_REFLECTION_JUDGE_ENABLED", "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _judge_timeout(context: Mapping[str, Any]) -> float:
    value = context.get("llm_reflection_judge_timeout") or os.getenv(
        "LLM_REFLECTION_JUDGE_TIMEOUT",
        DEFAULT_JUDGE_TIMEOUT_SECONDS,
    )
    try:
        return max(3.0, min(float(value), 90.0))
    except (TypeError, ValueError):
        return DEFAULT_JUDGE_TIMEOUT_SECONDS


def _extract_user_message(state: Mapping[str, Any]) -> str:
    messages = state.get("messages")
    if not isinstance(messages, list) or not messages:
        return ""
    for message in reversed(messages):
        content = getattr(message, "content", message)
        if content:
            return str(content)
    return ""


def _judge_clarifying_question(missing_information: list[str]) -> str:
    if not missing_information:
        return "我需要更多信息才能安全继续，请补充关键业务条件。"
    return f"我需要先补充这些信息才能继续：{'、'.join(missing_information)}。"


def _merge_reasons(first: Any, second: Any) -> list[str]:
    merged: list[str] = []
    for reason in [*_string_list(first), *_string_list(second)]:
        if reason not in merged:
            merged.append(reason)
    return merged


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _score(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed > 1.0 and parsed <= 5.0:
        parsed = parsed / 5.0
    elif parsed > 5.0 and parsed <= 100.0:
        parsed = parsed / 100.0
    return max(0.0, min(parsed, 1.0))


def _valid_route(value: Any) -> str | None:
    route = str(value or "").lower()
    return route if route in VALID_AGENT_ROUTES else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _preview(value: Any, limit: int) -> str:
    text = sanitize_log_data(str(value or ""), max_length=limit)
    return text if len(text) <= limit else text[:limit]
