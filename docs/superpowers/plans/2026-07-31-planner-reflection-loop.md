# Planner + Reflection Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded Planner + Reflection loop to the MCP LangGraph workflow.

**Architecture:** Keep the deterministic planning/reflection logic in a small reasoning service. The MCP graph imports it and adds `plan_task` and `reflect` nodes around the existing route/agent/synthesis flow.

**Tech Stack:** Python, LangGraph `StateGraph`, existing run timeline events, existing React Run Center.

## Global Constraints

- Do not run validation commands in this pass.
- Do not introduce a new LLM/model dependency.
- Keep approval interrupt as the write-operation safety gate.
- Keep the loop bounded with default `max_reflection_iterations = 2`.

---

### Task 1: Pure planner/reflection service

**Files:**
- Create: `src/api/services/reasoning/reflection_loop.py`
- Modify: `src/api/services/reasoning/__init__.py`
- Test: `tests/unit/test_reflection_loop.py`

**Interfaces:**
- Produces: `build_planner_decision(message: str | None, context: Mapping[str, Any] | None = None) -> dict[str, Any]`
- Produces: `review_agent_outcome(state: Mapping[str, Any]) -> dict[str, Any]`

- [ ] Create deterministic planning and reflection helpers.
- [ ] Add unit-test examples for high-risk clarification, route mismatch replan, and normal finalize.

### Task 2: Wire LangGraph nodes

**Files:**
- Modify: `src/api/graphs/mcp_integrated_planner_graph.py`

**Interfaces:**
- Consumes: `build_planner_decision`
- Consumes: `review_agent_outcome`
- Produces graph nodes: `_plan_task`, `_mcp_reflect`, `_route_after_reflection`

- [ ] Add state fields for planner and reflection data.
- [ ] Add `plan_task` before `route_intent`.
- [ ] Route all specialist agents into `reflect`.
- [ ] Route reflection decisions to `synthesize`, `ambiguous`, or `route_intent`.
- [ ] Support `reflection_next_route` as a one-shot route hint during replanning.

### Task 3: Run Center observability

**Files:**
- Modify: `src/api/services/runs/models.py`
- Modify: `src/api/graphs/mcp_integrated_planner_graph.py`

**Interfaces:**
- Produces event types: `plan.created`, `reflection.reviewed`, `reflection.replan`, `reflection.clarification_requested`

- [ ] Emit plan-created event with risk and route hint.
- [ ] Emit reflection event with action, confidence, reasons, and loop iteration.

### Task 4: Frontend timeline polish

**Files:**
- Modify: `src/ui/web/src/components/runs/RunTimeline.tsx`

**Interfaces:**
- Consumes event payload fields from run events.

- [ ] Add Chinese labels for new event types.
- [ ] Surface reflection action/reasons as small chips/details in the timeline.

### Task 5: Static scope review only

**Files:**
- Review changed files only.

**Interfaces:**
- No runtime execution.

- [ ] Inspect modified files for obvious placeholder text and accidental broad changes.
- [ ] Report that validation was intentionally not run.
