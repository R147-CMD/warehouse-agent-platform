from src.api.services.reasoning.reflection_loop import (
    build_planner_decision,
    review_agent_outcome,
)


def test_high_risk_wave_creation_requires_clarification():
    plan = build_planner_decision("创建今天下午的出库波次")
    state = {
        "messages": ["创建今天下午的出库波次"],
        "routing_decision": "operations",
        "agent_responses": {
            "operations": {
                "natural_language": "准备创建波次",
                "confidence": 0.9,
            }
        },
        "context": {"planner_scratchpad": plan},
        "planner_scratchpad": plan,
        "reflection_iterations": 0,
        "max_reflection_iterations": 2,
    }

    decision = review_agent_outcome(state)

    assert decision["action"] == "clarify"
    assert "warehouse_or_zone" in decision["missing_facts"]


def test_general_route_replans_to_planner_hint():
    plan = build_planner_decision("查看今天 A 仓叉车状态")
    state = {
        "messages": ["查看今天 A 仓叉车状态"],
        "routing_decision": "general",
        "agent_responses": {
            "general": {
                "natural_language": "普通回答",
                "confidence": 0.8,
            }
        },
        "context": {"planner_scratchpad": plan},
        "planner_scratchpad": plan,
        "reflection_iterations": 0,
        "max_reflection_iterations": 2,
    }

    decision = review_agent_outcome(state)

    assert decision["action"] == "replan"
    assert decision["next_route"] == "equipment"


def test_normal_equipment_result_finalizes():
    plan = build_planner_decision("查看 A 仓叉车状态")
    state = {
        "messages": ["查看 A 仓叉车状态"],
        "routing_decision": "equipment",
        "agent_responses": {
            "equipment": {
                "natural_language": "A 仓叉车运行正常",
                "confidence": 0.82,
            }
        },
        "context": {"planner_scratchpad": plan},
        "planner_scratchpad": plan,
        "reflection_iterations": 0,
        "max_reflection_iterations": 2,
    }

    decision = review_agent_outcome(state)

    assert decision["action"] == "finalize"
