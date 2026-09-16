"""Multi-agent collaboration planning and evidence joining helpers.

The helpers in this module are intentionally deterministic.  They decide when
it is safe and useful to fan out to multiple specialist agents, summarize each
agent's result into a small evidence item, and join those items into one
reflection-ready bundle.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


COLLABORATION_AGENT_ROUTES = (
    "operations",
    "equipment",
    "safety",
    "forecasting",
    "document",
)

DEFAULT_MAX_COLLABORATION_AGENTS = 4
LOW_CONFIDENCE_THRESHOLD = 0.35

_ANALYSIS_KEYWORDS = (
    "analyze",
    "analysis",
    "diagnose",
    "diagnostic",
    "why",
    "root cause",
    "cause",
    "compare",
    "correlation",
    "relationship",
    "impact",
    "optimize",
    "optimization",
    "bottleneck",
    "efficiency",
    "performance",
    "improve",
    "recommend",
    "abnormal",
    "exception",
    "trend",
    "reason",
    "分析",
    "诊断",
    "原因",
    "为什么",
    "根因",
    "对比",
    "比较",
    "关联",
    "关系",
    "影响",
    "优化",
    "瓶颈",
    "效率",
    "性能",
    "改善",
    "建议",
    "异常",
    "趋势",
    "下降",
    "波动",
)

_ROUTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "operations": (
        "operation",
        "operations",
        "order",
        "orders",
        "task",
        "tasks",
        "wave",
        "waves",
        "picking",
        "packing",
        "shipping",
        "dock",
        "worker",
        "workers",
        "labor",
        "staff",
        "shift",
        "throughput",
        "出库",
        "入库",
        "订单",
        "任务",
        "波次",
        "拣货",
        "复核",
        "发货",
        "月台",
        "人员",
        "员工",
        "班次",
        "吞吐",
        "作业",
    ),
    "equipment": (
        "equipment",
        "forklift",
        "agv",
        "amr",
        "conveyor",
        "scanner",
        "charger",
        "battery",
        "telemetry",
        "maintenance",
        "asset",
        "叉车",
        "搬运车",
        "agv",
        "amr",
        "输送线",
        "输送机",
        "扫码枪",
        "电池",
        "充电",
        "设备",
        "维保",
    ),
    "safety": (
        "safety",
        "incident",
        "alarm",
        "alert",
        "hazard",
        "blocked",
        "collision",
        "near miss",
        "violation",
        "ppe",
        "安全",
        "事故",
        "告警",
        "报警",
        "隐患",
        "封锁",
        "碰撞",
        "违规",
        "风险",
    ),
    "forecasting": (
        "forecast",
        "forecasting",
        "demand",
        "capacity",
        "trend",
        "seasonal",
        "prediction",
        "replenishment",
        "inventory pressure",
        "预测",
        "需求",
        "容量",
        "产能",
        "趋势",
        "季节",
        "补货",
        "库存压力",
        "未来",
    ),
    "document": (
        "document",
        "manual",
        "sop",
        "procedure",
        "policy",
        "report",
        "knowledge",
        "file",
        "文档",
        "手册",
        "流程",
        "制度",
        "报告",
        "知识库",
        "文件",
    ),
}


def build_collaboration_plan(
    message: str,
    planner: Mapping[str, Any] | None,
    primary_route: str | None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return whether this request should fan out to multiple agents."""

    planner_data = _mapping(planner)
    context_data = _mapping(context)
    safe_primary_route = _safe_route(primary_route)
    max_agents = _resolve_max_agents(context_data)
    base = {
        "enabled": False,
        "mode": "single_agent",
        "primary_route": safe_primary_route,
        "selected_agents": _dedupe_agents([safe_primary_route])[:max_agents],
        "max_agents": max_agents,
        "reasons": [],
    }

    if _flag_disabled(context_data.get("enable_multi_agent_collaboration")):
        return {
            **base,
            "reasons": ["config_disabled"],
        }

    if safe_primary_route == "ambiguous":
        return {
            **base,
            "reasons": ["ambiguous_request"],
        }

    if _is_high_risk_or_write(planner_data):
        return {
            **base,
            "reasons": ["high_risk_or_write_action"],
        }

    if not _looks_like_cross_domain_analysis(message, planner_data):
        return {
            **base,
            "reasons": ["simple_or_single_domain_query"],
        }

    selected_agents = _select_agents(message, safe_primary_route, max_agents)
    if len(selected_agents) < 2:
        return {
            **base,
            "selected_agents": selected_agents,
            "reasons": ["insufficient_cross_domain_signal"],
        }

    return {
        "enabled": True,
        "mode": "multi_agent_evidence_join",
        "primary_route": safe_primary_route,
        "selected_agents": selected_agents,
        "max_agents": max_agents,
        "reasons": _selection_reasons(message, planner_data, selected_agents),
    }


def summarize_agent_evidence(agent_name: str, response: Any) -> dict[str, Any]:
    """Convert a specialist response into a compact evidence item."""

    response_data = _mapping(response)
    if response_data:
        natural_language = _preview(response_data.get("natural_language"), 900)
        response_type = str(response_data.get("response_type") or "unknown")
        data = _mapping(response_data.get("data"))
        recommendations = _string_list(response_data.get("recommendations"))[:5]
        confidence = _coerce_float(response_data.get("confidence"))
        actions_taken = _string_list(response_data.get("actions_taken"))[:10]
        tools_used = _string_list(response_data.get("mcp_tools_used"))[:10]
        has_error = response_type == "error" or bool(data.get("error"))
        has_result = (bool(natural_language) or bool(data)) and not has_error
        return {
            "agent_name": str(agent_name),
            "summary": natural_language,
            "confidence": confidence,
            "response_type": response_type,
            "data_keys": list(data.keys())[:20],
            "recommendations": recommendations,
            "actions_taken": actions_taken,
            "tools_used": tools_used,
            "has_result": has_result,
            "error": str(data.get("error")) if data.get("error") else None,
        }

    if response is None:
        return _empty_evidence(agent_name, "no_response")

    text = _preview(response, 900)
    return {
        "agent_name": str(agent_name),
        "summary": text,
        "confidence": getattr(response, "confidence", None),
        "response_type": getattr(response, "response_type", "text"),
        "data_keys": [],
        "recommendations": [],
        "actions_taken": [],
        "tools_used": [],
        "has_result": bool(text),
        "error": None,
    }


def join_agent_evidence(
    message: str,
    planner: Mapping[str, Any] | None,
    primary_route: str | None,
    evidence_items: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Join specialist evidence into a reflection-ready bundle."""

    planner_data = _mapping(planner)
    safe_primary_route = _safe_route(primary_route)
    items = [dict(item) for item in evidence_items]
    contributing = [
        str(item.get("agent_name"))
        for item in items
        if item.get("has_result") and item.get("agent_name")
    ]
    confidence_values = [
        value
        for value in (_coerce_float(item.get("confidence")) for item in items)
        if value is not None
    ]
    average_confidence = (
        round(sum(confidence_values) / len(confidence_values), 2)
        if confidence_values
        else 0.0
    )
    expected_agents = _expected_agents(planner_data, safe_primary_route, contributing)
    missing_agents = [
        agent for agent in expected_agents if agent not in set(contributing)
    ]
    low_confidence_agents = [
        str(item.get("agent_name"))
        for item in items
        if item.get("has_result")
        and _coerce_float(item.get("confidence")) is not None
        and _coerce_float(item.get("confidence")) < LOW_CONFIDENCE_THRESHOLD
    ]
    gaps = _build_gaps(contributing, missing_agents, low_confidence_agents)

    return {
        "summary": _build_summary(contributing, average_confidence, items, gaps),
        "primary_route": safe_primary_route,
        "contributing_agents": contributing,
        "evidence_count": len(contributing),
        "average_confidence": average_confidence,
        "coverage": {
            "expected_agents": expected_agents,
            "contributing_agents": contributing,
            "missing_agents": missing_agents,
            "low_confidence_agents": low_confidence_agents,
        },
        "gaps": gaps,
        "evidence_items": items,
        "question": _preview(message, 500),
    }


def _select_agents(message: str, primary_route: str, max_agents: int) -> list[str]:
    normalized = _normalize(message)
    selected: list[str] = []
    if primary_route in COLLABORATION_AGENT_ROUTES:
        selected.append(primary_route)

    for route in COLLABORATION_AGENT_ROUTES:
        if any(keyword in normalized for keyword in _ROUTE_KEYWORDS[route]):
            selected.append(route)

    # Complex warehouse diagnostics often need operations + equipment even when
    # the user's wording only strongly names one side of the problem.
    if _has_any_keyword(normalized, _ANALYSIS_KEYWORDS):
        selected.extend(["operations", "equipment"])

    return _dedupe_agents(selected)[:max_agents]


def _selection_reasons(
    message: str,
    planner: Mapping[str, Any],
    selected_agents: list[str],
) -> list[str]:
    reasons = ["analysis_or_diagnostic_query", "cross_domain_evidence_needed"]
    if planner.get("intent_type"):
        reasons.append(f"intent_type:{planner.get('intent_type')}")
    if selected_agents:
        reasons.append(f"selected:{','.join(selected_agents)}")
    if _has_any_keyword(_normalize(message), ("优化", "optimize", "efficiency", "效率")):
        reasons.append("optimization_signal")
    return reasons


def _looks_like_cross_domain_analysis(
    message: str,
    planner: Mapping[str, Any],
) -> bool:
    intent_type = str(planner.get("intent_type") or "").casefold()
    if intent_type in {"analysis", "diagnostic", "optimization"}:
        return True
    return _has_any_keyword(_normalize(message), _ANALYSIS_KEYWORDS)


def _is_high_risk_or_write(planner: Mapping[str, Any]) -> bool:
    if str(planner.get("risk_level") or "").casefold() == "high":
        return True
    if bool(planner.get("requires_approval")):
        return True
    detected_actions = planner.get("detected_actions")
    return isinstance(detected_actions, list) and len(detected_actions) > 0


def _expected_agents(
    planner: Mapping[str, Any],
    primary_route: str,
    contributing: list[str],
) -> list[str]:
    selected = _string_list(planner.get("selected_agents"))
    if selected:
        return _dedupe_agents(selected)
    if contributing:
        return _dedupe_agents(contributing)
    return _dedupe_agents([primary_route])


def _build_gaps(
    contributing: list[str],
    missing_agents: list[str],
    low_confidence_agents: list[str],
) -> list[str]:
    gaps: list[str] = []
    if not contributing:
        gaps.append("未获得可用专家证据")
    if missing_agents:
        gaps.append(f"未获得这些智能体证据：{'、'.join(missing_agents)}")
    if low_confidence_agents:
        gaps.append(f"这些智能体置信度偏低：{'、'.join(low_confidence_agents)}")
    return gaps


def _build_summary(
    contributing: list[str],
    average_confidence: float,
    items: list[dict[str, Any]],
    gaps: list[str],
) -> str:
    if not contributing:
        return "未能汇总到可用的多智能体证据，请补充条件或切回单智能体诊断。"

    recommendations: list[str] = []
    highlights: list[str] = []
    for item in items:
        recommendations.extend(_string_list(item.get("recommendations")))
        if item.get("has_result") and item.get("summary"):
            highlights.append(
                f"{item.get('agent_name')}：{_preview(item.get('summary'), 160)}"
            )
    highlight_text = (
        f"证据要点：{'；'.join(highlights[:3])}。"
        if highlights
        else ""
    )
    recommendation_text = (
        f"关键建议：{'；'.join(_dedupe_text(recommendations)[:3])}。"
        if recommendations
        else ""
    )
    gap_text = f"待补证据：{'；'.join(gaps)}。" if gaps else ""
    return (
        f"已汇总{'、'.join(contributing)} {len(contributing)} 个智能体证据，"
        f"平均置信度 {int(round(average_confidence * 100))}%。"
        f"{highlight_text}{recommendation_text}{gap_text}"
    )


def _safe_route(route: str | None) -> str:
    route_text = str(route or "general")
    if route_text in {*COLLABORATION_AGENT_ROUTES, "general", "ambiguous"}:
        return route_text
    return "general"


def _resolve_max_agents(context: Mapping[str, Any]) -> int:
    value = context.get("max_collaboration_agents")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_COLLABORATION_AGENTS
    return max(2, min(parsed, 5))


def _dedupe_agents(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    allowed = set(COLLABORATION_AGENT_ROUTES)
    for value in values:
        text = str(value or "").strip()
        if text in allowed and text not in result:
            result.append(text)
    return result


def _dedupe_text(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _empty_evidence(agent_name: str, error: str | None = None) -> dict[str, Any]:
    return {
        "agent_name": str(agent_name),
        "summary": "",
        "confidence": None,
        "response_type": "empty",
        "data_keys": [],
        "recommendations": [],
        "actions_taken": [],
        "tools_used": [],
        "has_result": False,
        "error": error,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(parsed, 1.0))


def _preview(value: Any, limit: int = 300) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _normalize(message: str) -> str:
    return str(message or "").casefold()


def _has_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    return any(str(keyword).casefold() in text for keyword in keywords)


def _flag_disabled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.casefold() in {"0", "false", "no", "off", "disabled"}
    return not bool(value)
