from src.api.services.reasoning.evidence_join import (
    build_collaboration_plan,
    join_agent_evidence,
    summarize_agent_evidence,
)


def test_high_risk_write_plan_disables_multi_agent_collaboration():
    plan = {
        "intent_type": "action",
        "risk_level": "high",
        "requires_approval": True,
        "detected_actions": [{"name": "create_wave"}],
    }

    result = build_collaboration_plan(
        "create a picking wave and dispatch a forklift",
        plan,
        "operations",
    )

    assert result["enabled"] is False
    assert result["primary_route"] == "operations"
    assert "high_risk_or_write_action" in result["reasons"]


def test_complex_diagnostic_query_selects_cross_domain_agents():
    plan = {
        "intent_type": "analysis",
        "risk_level": "low",
        "requires_approval": False,
        "detected_actions": [],
    }

    result = build_collaboration_plan(
        "分析 A 仓出库效率下降，看看叉车、人员和安全告警有没有关系",
        plan,
        "operations",
    )

    assert result["enabled"] is True
    assert result["selected_agents"][:2] == ["operations", "equipment"]
    assert "safety" in result["selected_agents"]
    assert len(result["selected_agents"]) <= 4


def test_evidence_join_aggregates_confidence_and_gaps():
    equipment = summarize_agent_evidence(
        "equipment",
        {
            "natural_language": "叉车利用率偏高，低电量车辆较多。",
            "confidence": 0.8,
            "data": {"forklift": {"low_battery": 3}},
            "recommendations": ["优先调度满电叉车"],
            "response_type": "equipment_info",
        },
    )
    operations = summarize_agent_evidence(
        "operations",
        {
            "natural_language": "拣货任务积压集中在 A 区。",
            "confidence": 0.7,
            "data": {"waves": 5},
            "recommendations": ["调整波次节奏"],
            "response_type": "operations_info",
        },
    )

    bundle = join_agent_evidence(
        "分析 A 仓出库效率下降原因",
        {"route_hint": "operations"},
        "operations",
        [equipment, operations],
    )

    assert bundle["evidence_count"] == 2
    assert bundle["contributing_agents"] == ["equipment", "operations"]
    assert bundle["average_confidence"] == 0.75
    assert bundle["gaps"] == []
    assert "已汇总" in bundle["summary"]
