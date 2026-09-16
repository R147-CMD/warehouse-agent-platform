# LLM Reflection Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional LLM Judge review to the existing LangGraph Reflection Loop.

**Architecture:** Keep rule reflection as the deterministic baseline. Add `reflection_judge.py` as a small service that builds a safe prompt, calls the existing NIM client, parses strict JSON, and merges the result without allowing LLM output to bypass safety rules.

**Tech Stack:** Python, LangGraph, existing NVIDIA NIM client, React Run Center.

## Global Constraints

- Do not run tests, build, or app verification in this pass.
- Do not introduce a new external SDK.
- Rule reflection remains the safety baseline.
- LLM Judge is read-only and cannot execute or approve tools.

---

### Task 1: Add LLM Judge service

**Files:**
- Create: `src/api/services/reasoning/reflection_judge.py`
- Modify: `src/api/services/reasoning/reflection_loop.py`
- Modify: `src/api/services/reasoning/__init__.py`

**Interfaces:**
- Produces: `evaluate_with_llm_judge(state: Mapping[str, Any], rule_decision: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `parse_llm_judge_response(content: str) -> dict[str, Any]`
- Produces: `merge_rule_and_judge_decisions(rule_decision: Mapping[str, Any], judge_result: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `review_agent_outcome_with_judge(state: Mapping[str, Any]) -> dict[str, Any]`

- [ ] Create a safe state summarizer for judge prompts.
- [ ] Add NIM call with timeout and fallback.
- [ ] Add strict JSON parsing.
- [ ] Add safety-preserving merge logic.

### Task 2: Wire LangGraph reflect node

**Files:**
- Modify: `src/api/graphs/mcp_integrated_planner_graph.py`

**Interfaces:**
- Consumes: `review_agent_outcome_with_judge`

- [ ] Replace rule-only reflection call with async LLM Judge wrapper.
- [ ] Include judge scores and status in reflection run events.

### Task 3: Display judge scores

**Files:**
- Modify: `src/ui/web/src/components/runs/RunTimeline.tsx`

**Interfaces:**
- Consumes run event payload fields: `judge_status`, `quality_score`, `route_score`, `safety_score`

- [ ] Add compact chips for judge status and scores.

### Task 4: Add tests as executable examples

**Files:**
- Modify: `tests/unit/test_reflection_loop.py`
- Create: `tests/unit/test_reflection_judge.py`

**Interfaces:**
- Tests parse/merge behavior without network calls.

- [ ] Add parser and merge tests.
- [ ] Do not run tests in this pass.
