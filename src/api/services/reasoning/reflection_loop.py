"""Deterministic planner and reflection helpers for the warehouse LangGraph.

The first version intentionally avoids adding another LLM dependency.  It gives
the graph a visible plan/review loop now, while keeping a clean seam for a
future LLM judge or evaluator.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


DEFAULT_MAX_REFLECTION_ITERATIONS = 2

VALID_AGENT_ROUTES = {
    "equipment",
    "operations",
    "safety",
    "forecasting",
    "document",
    "general",
    "ambiguous",
    "evidence_join",
}


_ACTION_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "create_wave",
        "label": "创建波次",
        "risk_level": "high",
        "route_hint": "operations",
        "keywords": (
            "create wave",
            "generate wave",
            "pick wave",
            "wave creation",
            "创建波次",
            "生成波次",
            "出库波次",
            "拣货波次",
        ),
        "required_facts": ("warehouse_or_zone", "order_scope", "time_window"),
    },
    {
        "name": "dispatch_equipment",
        "label": "调度设备/叉车",
        "risk_level": "high",
        "route_hint": "operations",
        "keywords": (
            "dispatch forklift",
            "assign forklift",
            "schedule forklift",
            "dispatch agv",
            "assign agv",
            "调度叉车",
            "安排叉车",
            "派叉车",
            "调度agv",
            "安排agv",
        ),
        "required_facts": ("warehouse_or_zone", "equipment_or_workload", "time_window"),
    },
    {
        "name": "adjust_inventory",
        "label": "调整库存",
        "risk_level": "high",
        "route_hint": "operations",
        "keywords": (
            "adjust inventory",
            "update inventory",
            "change stock",
            "set stock",
            "调整库存",
            "修改库存",
            "库存调成",
            "库存改成",
            "更改库存",
        ),
        "required_facts": ("sku", "quantity", "warehouse_or_zone"),
    },
)

_ROUTE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "safety",
        (
            "safety",
            "incident",
            "emergency",
            "fire",
            "spill",
            "leak",
            "injury",
            "安全",
            "事故",
            "火灾",
            "泄漏",
            "受伤",
            "报警",
        ),
    ),
    (
        "forecasting",
        (
            "forecast",
            "predict",
            "demand",
            "reorder",
            "trend",
            "预测",
            "需求",
            "补货",
            "趋势",
        ),
    ),
    (
        "document",
        (
            "document",
            "invoice",
            "manual",
            "pdf",
            "upload",
            "文档",
            "发票",
            "手册",
            "上传",
        ),
    ),
    (
        "operations",
        (
            "wave",
            "order",
            "pick",
            "pack",
            "putaway",
            "shift",
            "worker",
            "task",
            "create",
            "dispatch",
            "assign",
            "波次",
            "订单",
            "拣货",
            "打包",
            "上架",
            "班次",
            "员工",
            "任务",
            "创建",
            "调度",
            "安排",
        ),
    ),
    (
        "equipment",
        (
            "equipment",
            "forklift",
            "agv",
            "amr",
            "conveyor",
            "scanner",
            "sku",
            "stock",
            "inventory",
            "设备",
            "叉车",
            "输送线",
            "扫描枪",
            "库存",
            "货品",
        ),
    ),
)

_FIELD_LABELS = {
    "warehouse_or_zone": "仓库/库区",
    "order_scope": "订单范围",
    "time_window": "时间窗口",
    "equipment_or_workload": "设备编号或作业量",
    "sku": "SKU/货品",
    "quantity": "数量",
}


def build_planner_decision(
    message: str | None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact task plan from user text and request context."""

    text = (message or "").strip()
    normalized = _normalize(text)
    detected_actions = _detect_actions(normalized)
    route_hint = _detect_route_hint(normalized, detected_actions)
    required_facts = _merge_required_facts(detected_actions)
    present_facts = _detect_present_facts(text, normalized)
    missing_facts = [
        fact for fact in required_facts if fact not in present_facts
    ]
    risk_level = _highest_risk_level(detected_actions)
    intent_type = "write" if detected_actions else _detect_intent_type(normalized)

    plan_steps = [
        "理解用户意图和业务风险",
        f"优先路由到 {route_hint} 智能体",
    ]
    if detected_actions:
        plan_steps.append("识别写入/高风险动作，执行前必须保留人工审批链路")
    if missing_facts:
        plan_steps.append("执行前先补齐关键业务字段")
    else:
        plan_steps.append("使用现有工具/专家智能体获取结果")
    plan_steps.append("反思检查后再生成最终回答")

    return {
        "summary": _summarize_plan(text, route_hint, risk_level, detected_actions),
        "intent_type": intent_type,
        "risk_level": risk_level,
        "route_hint": route_hint,
        "detected_actions": detected_actions,
        "required_facts": list(required_facts),
        "present_facts": sorted(present_facts),
        "missing_facts": missing_facts,
        "requires_approval": risk_level == "high",
        "plan_steps": plan_steps,
        "max_reflection_iterations": _resolve_max_iterations(context),
    }


def review_agent_outcome(state: Mapping[str, Any]) -> dict[str, Any]:
    """Review current graph state and decide whether to finalize, clarify, or replan."""

    context = _mapping(state.get("context"))
    message = _extract_message_text_from_state(state)
    plan = _mapping(
        state.get("planner_scratchpad")
        or context.get("planner_scratchpad")
        or build_planner_decision(message, context)
    )
    route = str(state.get("routing_decision") or "general")
    route_hint = str(plan.get("route_hint") or "general")
    iteration = _to_int(state.get("reflection_iterations"), 0) + 1
    max_iterations = _to_int(
        state.get("max_reflection_iterations")
        or plan.get("max_reflection_iterations"),
        DEFAULT_MAX_REFLECTION_ITERATIONS,
    )
    agent_responses = _mapping(state.get("agent_responses"))
    response = agent_responses.get(route)
    confidence = _extract_confidence(response, context)
    has_response = _has_meaningful_response(response)

    missing_facts = [
        str(item) for item in plan.get("missing_facts", []) if str(item).strip()
    ]
    reasons: list[str] = []

    if plan.get("risk_level") == "high" and missing_facts:
        reasons.append("高风险写入动作缺少关键业务字段")
        return {
            "action": "clarify",
            "iteration": iteration,
            "max_iterations": max_iterations,
            "route": route,
            "next_route": "ambiguous",
            "confidence": confidence,
            "reasons": reasons,
            "missing_facts": missing_facts,
            "clarifying_question": _build_clarifying_question(missing_facts),
            "clarifying_options": _build_clarifying_options(missing_facts),
        }

    if route not in VALID_AGENT_ROUTES:
        reasons.append(f"路由 {route} 不在允许的智能体列表中")
        return _replan_or_finalize(
            iteration=iteration,
            max_iterations=max_iterations,
            route=route,
            next_route=route_hint,
            confidence=confidence,
            reasons=reasons,
        )

    if route == "general" and route_hint != "general":
        reasons.append(f"当前路由为 general，但计划建议 {route_hint}")
        return _replan_or_finalize(
            iteration=iteration,
            max_iterations=max_iterations,
            route=route,
            next_route=route_hint,
            confidence=confidence,
            reasons=reasons,
        )

    if not has_response:
        reasons.append("专家智能体没有产出可用结果")
        return _replan_or_finalize(
            iteration=iteration,
            max_iterations=max_iterations,
            route=route,
            next_route=route_hint,
            confidence=confidence,
            reasons=reasons,
        )

    if confidence is not None and confidence < 0.35:
        reasons.append(f"结果置信度过低：{confidence:.2f}")
        return _replan_or_finalize(
            iteration=iteration,
            max_iterations=max_iterations,
            route=route,
            next_route=route_hint,
            confidence=confidence,
            reasons=reasons,
        )

    if confidence is not None and confidence < 0.5:
        reasons.append(f"结果置信度偏低：{confidence:.2f}，但不需要继续循环")

    if not reasons:
        reasons.append("结果具备可用回答，允许进入最终汇总")

    return {
        "action": "finalize",
        "iteration": iteration,
        "max_iterations": max_iterations,
        "route": route,
        "next_route": None,
        "confidence": confidence,
        "reasons": reasons,
        "missing_facts": missing_facts,
    }


async def review_agent_outcome_with_judge(state: Mapping[str, Any]) -> dict[str, Any]:
    """Run deterministic reflection, then optionally strengthen it with LLM Judge."""

    rule_decision = review_agent_outcome(state)
    from .reflection_judge import evaluate_with_llm_judge

    return await evaluate_with_llm_judge(state, rule_decision)


def _detect_actions(normalized: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for definition in _ACTION_DEFINITIONS:
        keyword_match = any(keyword in normalized for keyword in definition["keywords"])
        phrase_match = _matches_action_phrase(str(definition["name"]), normalized)
        if keyword_match or phrase_match:
            actions.append(
                {
                    "name": definition["name"],
                    "label": definition["label"],
                    "risk_level": definition["risk_level"],
                    "route_hint": definition["route_hint"],
                }
            )
    return actions


def _matches_action_phrase(action_name: str, normalized: str) -> bool:
    if action_name == "create_wave":
        return (
            any(word in normalized for word in ("create", "generate", "生成", "创建"))
            and any(word in normalized for word in ("wave", "波次"))
        )
    if action_name == "dispatch_equipment":
        return (
            any(
                word in normalized
                for word in ("dispatch", "assign", "schedule", "调度", "安排", "派")
            )
            and any(word in normalized for word in ("forklift", "agv", "amr", "叉车", "设备"))
        )
    if action_name == "adjust_inventory":
        return (
            any(
                word in normalized
                for word in ("adjust", "update", "change", "set", "调整", "修改", "更改")
            )
            and any(word in normalized for word in ("inventory", "stock", "sku", "库存"))
        )
    return False


def _detect_route_hint(normalized: str, detected_actions: list[dict[str, Any]]) -> str:
    if detected_actions:
        return str(detected_actions[0].get("route_hint") or "operations")
    for route, keywords in _ROUTE_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return route
    return "general"


def _detect_intent_type(normalized: str) -> str:
    if any(word in normalized for word in ("analyze", "compare", "optimize", "分析", "比较", "优化")):
        return "analysis"
    return "read"


def _merge_required_facts(detected_actions: list[dict[str, Any]]) -> tuple[str, ...]:
    required: list[str] = []
    action_names = {action["name"] for action in detected_actions}
    for definition in _ACTION_DEFINITIONS:
        if definition["name"] not in action_names:
            continue
        for fact in definition["required_facts"]:
            if fact not in required:
                required.append(fact)
    return tuple(required)


def _detect_present_facts(original: str, normalized: str) -> set[str]:
    present: set[str] = set()
    if re.search(r"\b(zone|area|warehouse)\s*[a-z0-9-]*\b", normalized) or re.search(
        r"[\u4e00-\u9fa5a-zA-Z0-9_-]*(仓|库区|区域)", original
    ):
        present.add("warehouse_or_zone")
    if "order" in normalized or "订单" in original or re.search(r"\bso[-_]?\d+\b", normalized):
        present.add("order_scope")
    if any(word in normalized for word in ("today", "tomorrow", "morning", "afternoon", "tonight")) or any(
        word in original for word in ("今天", "明天", "上午", "下午", "晚上", "本周", "立刻", "马上")
    ) or re.search(r"\d{1,2}[:：]\d{2}", original):
        present.add("time_window")
    if any(word in normalized for word in ("forklift", "agv", "amr", "worker", "task")) or any(
        word in original for word in ("叉车", "AGV", "AMR", "人员", "员工", "任务", "作业量")
    ):
        present.add("equipment_or_workload")
    if "sku" in normalized or re.search(r"\b[a-z]{2,}[-_]?\d{2,}\b", normalized):
        present.add("sku")
    if re.search(r"\d+(\.\d+)?", original):
        present.add("quantity")
    return present


def _highest_risk_level(detected_actions: list[dict[str, Any]]) -> str:
    if any(action.get("risk_level") == "high" for action in detected_actions):
        return "high"
    if detected_actions:
        return "medium"
    return "low"


def _summarize_plan(
    text: str,
    route_hint: str,
    risk_level: str,
    detected_actions: list[dict[str, Any]],
) -> str:
    action_labels = [str(action["label"]) for action in detected_actions]
    action_text = "、".join(action_labels) if action_labels else "查询/分析"
    trimmed = text[:80] + "..." if len(text) > 80 else text
    return f"识别为{action_text}请求，建议路由 {route_hint}，风险等级 {risk_level}。原始请求：{trimmed}"


def _build_clarifying_question(missing_facts: list[str]) -> str:
    labels = [_FIELD_LABELS.get(fact, fact) for fact in missing_facts]
    return (
        "这个操作属于高风险仓库写入动作。为了避免误创建/误调度/误改库存，"
        f"请先补充：{'、'.join(labels)}。"
    )


def _build_clarifying_options(missing_facts: list[str]) -> list[str]:
    return [f"补充{_FIELD_LABELS.get(fact, fact)}" for fact in missing_facts]


def _replan_or_finalize(
    *,
    iteration: int,
    max_iterations: int,
    route: str,
    next_route: str,
    confidence: float | None,
    reasons: list[str],
) -> dict[str, Any]:
    if iteration <= max_iterations:
        return {
            "action": "replan",
            "iteration": iteration,
            "max_iterations": max_iterations,
            "route": route,
            "next_route": next_route if next_route in VALID_AGENT_ROUTES else "general",
            "confidence": confidence,
            "reasons": reasons,
            "missing_facts": [],
        }
    return {
        "action": "finalize",
        "iteration": iteration,
        "max_iterations": max_iterations,
        "route": route,
        "next_route": None,
        "confidence": confidence,
        "reasons": [*reasons, "已达到反思轮次上限，进入最终汇总"],
        "missing_facts": [],
    }


def _extract_message_text_from_state(state: Mapping[str, Any]) -> str:
    messages = state.get("messages")
    if not isinstance(messages, list) or not messages:
        return ""
    latest = messages[-1]
    return str(getattr(latest, "content", latest) or "")


def _extract_confidence(response: Any, context: Mapping[str, Any]) -> float | None:
    if isinstance(response, Mapping):
        value = response.get("confidence")
    elif hasattr(response, "confidence"):
        value = getattr(response, "confidence")
    else:
        structured = context.get("structured_response")
        value = structured.get("confidence") if isinstance(structured, Mapping) else None
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_meaningful_response(response: Any) -> bool:
    if response is None:
        return False
    if isinstance(response, str):
        text = response.strip().lower()
        return bool(text) and "no message to process" not in text
    if isinstance(response, Mapping):
        natural_language = response.get("natural_language")
        if isinstance(natural_language, str) and natural_language.strip():
            return True
        data = response.get("data")
        if isinstance(data, Mapping) and data:
            return True
        return bool(response)
    return True


def _resolve_max_iterations(context: Mapping[str, Any] | None) -> int:
    return _to_int(
        _mapping(context).get("max_reflection_iterations"),
        DEFAULT_MAX_REFLECTION_ITERATIONS,
    )


def _to_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(parsed, 5))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _normalize(text: str) -> str:
    return text.casefold()
