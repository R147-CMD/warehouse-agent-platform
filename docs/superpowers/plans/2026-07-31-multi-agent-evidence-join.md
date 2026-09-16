# Multi-Agent Evidence Join Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional multi-agent evidence collection and evidence joining to the LangGraph warehouse assistant.

**Architecture:** A pure reasoning service decides collaboration eligibility and joins evidence. The MCP integrated planner graph adds `collaboration_plan`, `multi_agent_collect`, and `evidence_join` nodes before the existing `reflect` node.

**Tech Stack:** Python, LangGraph, existing MCP specialist agents, existing Run Center timeline.

## Global Constraints

- Do not run tests, build, or app verification in this pass.
- Multi-agent mode is only for read/analysis requests.
- High-risk write actions stay on the existing single-agent + approval path.
- Cap selected agents to four by default.

---

### Task 1: Add collaboration/evidence service

**Files:**
- Create: `src/api/services/reasoning/evidence_join.py`
- Modify: `src/api/services/reasoning/__init__.py`
- Test: `tests/unit/test_evidence_join.py`

**Interfaces:**
- Produces: `build_collaboration_plan(message, planner, primary_route, context=None) -> dict`
- Produces: `summarize_agent_evidence(agent_name, response) -> dict`
- Produces: `join_agent_evidence(message, planner, primary_route, evidence_items) -> dict`

- [ ] Add safe eligibility rules.
- [ ] Add agent selection.
- [ ] Add evidence summarization and gap detection.

### Task 2: Wire graph nodes

**Files:**
- Modify: `src/api/graphs/mcp_integrated_planner_graph.py`

**Interfaces:**
- Adds state fields: `collaboration_plan`, `evidence_bundle`, `primary_route`
- Adds graph nodes: `_build_collaboration_plan`, `_mcp_multi_agent_collect`, `_mcp_evidence_join`
- Adds route method: `_route_after_collaboration_plan`

- [ ] Insert `collaboration_plan` after `route_intent`.
- [ ] Route to `multi_agent_collect` when enabled.
- [ ] Run selected specialist handlers concurrently with `asyncio.gather`.
- [ ] Join evidence and route to existing `reflect`.

### Task 3: Run event observability

**Files:**
- Modify: `src/api/services/runs/models.py`
- Modify: `src/api/graphs/mcp_integrated_planner_graph.py`
- Modify: `src/ui/web/src/components/runs/RunTimeline.tsx`

**Interfaces:**
- Adds event types: `multi_agent.selected`, `evidence.joined`

- [ ] Emit selected agents event.
- [ ] Emit evidence joined event.
- [ ] Add Chinese timeline labels and chips.

### Task 4: Static review only

**Files:**
- Review changed files.

- [ ] Search for placeholders/conflict markers.
- [ ] Confirm no validation commands were run.
