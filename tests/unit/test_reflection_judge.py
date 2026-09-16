from src.api.services.reasoning.reflection_judge import (
    merge_rule_and_judge_decisions,
    parse_llm_judge_response,
)


def test_parse_llm_judge_response_extracts_json_from_code_fence():
    raw = """
    ```json
    {
      "decision": "replan",
      "quality_score": 0.42,
      "route_score": 0.3,
      "safety_score": 0.95,
      "confidence": 0.8,
      "reasons": ["缺少设备状态数据"],
      "missing_information": ["设备状态"],
      "next_route": "equipment"
    }
    ```
    """

    result = parse_llm_judge_response(raw)

    assert result["decision"] == "replan"
    assert result["quality_score"] == 0.42
    assert result["next_route"] == "equipment"


def test_rule_clarify_cannot_be_overridden_by_judge_finalize():
    rule_decision = {
        "action": "clarify",
        "reasons": ["高风险写入动作缺少关键业务字段"],
        "missing_facts": ["warehouse_or_zone"],
        "iteration": 1,
        "max_iterations": 2,
        "route": "operations",
    }
    judge_result = {
        "decision": "finalize",
        "quality_score": 0.99,
        "route_score": 0.99,
        "safety_score": 0.99,
        "confidence": 0.9,
        "reasons": ["模型认为可以回答"],
    }

    merged = merge_rule_and_judge_decisions(rule_decision, judge_result)

    assert merged["action"] == "clarify"
    assert merged["llm_judge"]["safety_override_blocked"] is True


def test_judge_replan_can_strengthen_rule_finalize():
    rule_decision = {
        "action": "finalize",
        "reasons": ["规则检查通过"],
        "iteration": 1,
        "max_iterations": 2,
        "route": "general",
    }
    judge_result = {
        "decision": "replan",
        "quality_score": 0.31,
        "route_score": 0.25,
        "safety_score": 0.9,
        "confidence": 0.8,
        "reasons": ["当前回答没有使用设备状态数据"],
        "next_route": "equipment",
    }

    merged = merge_rule_and_judge_decisions(rule_decision, judge_result)

    assert merged["action"] == "replan"
    assert merged["next_route"] == "equipment"
    assert merged["llm_judge"]["quality_score"] == 0.31
