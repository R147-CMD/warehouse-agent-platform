# LLM Reflection Judge Design

## Goal

Upgrade the existing deterministic Reflection Loop with an optional LLM Judge. The graph should still keep rule-based reflection as the safety baseline, but use the configured NVIDIA NIM LLM to perform deeper review of plan quality, route correctness, answer usefulness, and safety/compliance.

## Design

The existing `reflect` LangGraph node remains the single integration point. It will:

1. Run the current deterministic `review_agent_outcome` rule review.
2. If the request is not blocked by a hard safety rule and LLM Judge is enabled, call the configured NIM LLM.
3. Ask the LLM to return strict JSON with:
   - `decision`: `finalize`, `clarify`, or `replan`
   - `quality_score`
   - `route_score`
   - `safety_score`
   - `confidence`
   - `reasons`
   - `missing_information`
   - `next_route`
4. Merge the LLM decision with the rule decision.

## Safety policy

The LLM Judge cannot weaken deterministic safety decisions:

- If the rule engine requires `clarify` for missing high-risk fields, the final decision stays `clarify`.
- If the LLM response is malformed, times out, or the API key is missing, the graph falls back to the rule decision.
- The judge is read-only. It does not execute tools and does not approve write actions.

## Configuration

- `LLM_REFLECTION_JUDGE_ENABLED=true|false`, default `true`
- `LLM_REFLECTION_JUDGE_TIMEOUT`, default `25`
- request context can set `enable_llm_reflection_judge=false` to skip LLM judging for a run

## Observability

Run Center reflection events should expose:

- judge mode/status
- quality score
- route score
- safety score
- LLM reasons
- whether the result used rule fallback

## Non-goals

- No new model provider SDK.
- No new database table.
- No runtime validation in this pass.
