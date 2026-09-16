# Agent Run Center Design

## Background

The project already has chat sessions, LangGraph checkpoint persistence, and human approval for high-risk write operations. What is still missing is a unified operations surface for an enterprise user to answer three daily questions:

- Which agent tasks are running right now?
- Which task is waiting for approval or stuck on an error?
- What exactly happened before a task created a wave, dispatched a forklift, adjusted inventory, or failed?

The new feature is a unified task execution center, called Agent Run Center. It records durable run metadata and event timelines for agent executions, links approval records and LangGraph checkpoints, and gives the UI a dedicated page for operations staff and managers.

This design follows the user's current constraint: add feature code first and do not run verification, tests, builds, or app restarts in this phase.

## Goals

- Provide a durable run ledger for agent executions.
- Provide a chronological event timeline for each run.
- Link runs with chat session IDs, LangGraph checkpoint thread IDs, and human approval IDs.
- Allow managers and admins to view all runs, cancel running runs, retry failed runs, and jump to pending approvals.
- Allow ordinary users to view only their own runs.
- Keep query-only agent actions automatic while preserving approval gates for write and high-risk operations.
- Keep the implementation scoped to the existing FastAPI backend, PostgreSQL persistence style, LangGraph execution path, and React frontend.

## Non-Goals

- Do not build a new workflow engine.
- Do not replace the existing approval system.
- Do not implement distributed cancellation across multiple backend instances in this phase.
- Do not add billing, tenant-level quota, or advanced analytics.
- Do not validate by running tests, builds, database migrations, or the local app during this phase.

## Recommended Approach

Use an independent run ledger plus event timeline.

The run ledger stores one row per agent execution attempt. The event timeline stores append-only operational events for that run. Approval records remain in the approval module and are linked from events by approval ID. LangGraph checkpointing remains the source of resumable graph state and is linked by checkpoint thread ID.

This keeps the model simple:

- `agent_runs` answers "what is the current state of this execution?"
- `agent_run_events` answers "what happened over time?"
- `approvals` answers "which risky operation needs human decision?"
- LangGraph checkpoints answer "where can the graph resume from?"

## Data Model

### agent_runs

Fields:

- `run_id`: UUID primary key.
- `session_id`: chat session UUID when the run came from chat.
- `checkpoint_thread_id`: LangGraph thread ID used for checkpoint persistence.
- `user_id`: creator ID.
- `user_role`: creator role at creation time.
- `run_type`: initial values `chat`, `agent`, `tool`, `retry`.
- `title`: short display title derived from the user request or operation name.
- `input_summary`: short Chinese summary of the original user request.
- `input_payload`: JSONB payload needed to retry or inspect the original request, with secrets and credentials excluded.
- `status`: one of `queued`, `running`, `waiting_approval`, `completed`, `failed`, `cancel_requested`, `cancelled`.
- `current_agent`: current planner or specialist agent name, if known.
- `current_tool`: current MCP or internal tool name, if known.
- `risk_level`: highest observed risk level for this run.
- `approval_count`: number of approval requests created for this run.
- `error_code`: stable error code for failed runs.
- `error_message`: human-readable failure message.
- `result_summary`: concise completion result for list display.
- `retry_of_run_id`: original run ID when this row is a retry attempt.
- `created_at`, `started_at`, `completed_at`, `updated_at`: lifecycle timestamps.
- `expires_at`: retention cutoff, default 30 days after creation.

### agent_run_events

Fields:

- `event_id`: UUID primary key.
- `run_id`: parent run ID.
- `event_type`: stable event type.
- `severity`: `info`, `warning`, or `error`.
- `agent_name`: planner or specialist agent name, if relevant.
- `tool_name`: MCP or internal tool name, if relevant.
- `approval_id`: linked approval ID, if relevant.
- `checkpoint_id`: checkpoint identifier, if available.
- `message`: short Chinese display text.
- `payload`: JSONB details for audit and debugging.
- `created_at`: event timestamp.

Core event types:

- `run.created`
- `run.started`
- `route.selected`
- `agent.started`
- `agent.completed`
- `tool.started`
- `tool.completed`
- `approval.requested`
- `approval.approved`
- `approval.rejected`
- `approval.expired`
- `checkpoint.saved`
- `run.waiting_approval`
- `run.cancel_requested`
- `run.cancelled`
- `run.retry_requested`
- `run.completed`
- `run.failed`

## Status Rules

- `queued`: run row exists but graph execution has not started.
- `running`: graph execution is active.
- `waiting_approval`: at least one high-risk operation is blocked by human approval.
- `completed`: graph reached a final successful answer.
- `failed`: graph or tool execution ended with an unhandled error.
- `cancel_requested`: user requested cancellation; execution should stop at the next graph or tool boundary.
- `cancelled`: execution stopped because cancellation was requested.

Terminal statuses are `completed`, `failed`, and `cancelled`.

`waiting_approval` can return to `running` after approval or move to `failed` after rejection/expiry when the graph cannot continue.

## Backend Components

### Run Models

Add a `src/api/services/runs/models.py` module with typed status, event, request, and response models.

### Run Repository

Add `src/api/services/runs/repository.py`.

Responsibilities:

- Create `agent_runs` and `agent_run_events` tables when the app starts.
- Insert a new run row.
- Append run events.
- Update run status and current location.
- List runs with filters and role-based scoping.
- Fetch run detail and event timeline.
- Mark cancellation requested.
- Create a retry attempt linked by `retry_of_run_id`.
- Delete expired runs and events after retention cutoff.

### Run Manager

Add `src/api/services/runs/manager.py`.

Responsibilities:

- Provide a small business API around the repository.
- Normalize status transitions.
- Emit standard events for graph, agent, tool, approval, retry, and cancellation milestones.
- Keep failure behavior fail-closed: if run event persistence fails, the agent execution should not be allowed to silently perform risky writes without approval context.

### Run Context

Add `src/api/services/runs/context.py`.

Use Python context variables to make `run_id`, `session_id`, `checkpoint_thread_id`, and current user context available to graph nodes, tool gateways, and approval code without threading extra parameters through every call.

## Integration Points

### Chat Router

When a chat request starts, create an `agent_runs` row before invoking the LangGraph planner.

The chat router should:

- Generate or reuse a run ID.
- Set run context around graph execution.
- Mark the run `running`.
- Mark it `completed`, `failed`, or `cancelled` when execution ends.
- Return `run_id` in chat responses so the frontend can link messages to the Run Center.

### LangGraph Planner

Instrument the existing MCP-integrated planner graph.

The graph should emit:

- route selection events
- agent start and completion events
- failure events
- checkpoint save markers when checkpoint metadata is available

Cancellation should be cooperative. Nodes should check the current run status at safe boundaries and raise a local `RunCancelled` exception if status is `cancel_requested`.

### Tool and Approval Gateway

The existing approval gateway already intercepts write and high-risk operations. Extend it to attach the current `run_id` to approval records and emit events when approval is requested, approved, rejected, or expired.

Query-only tool execution remains automatic.

Write and high-risk operations still require approval by manager or admin.

Each risky operation is approved independently.

### Retry

Retry creates a new run attempt instead of mutating the original run.

Rules:

- Only terminal `failed` runs are retryable.
- Retry is allowed for manager/admin and for the original user if the original operation scope permits it.
- The retry row stores `retry_of_run_id`.
- The retry attempts to resume from the latest safe LangGraph checkpoint for the original checkpoint thread.
- If no checkpoint is available, retry starts a new execution attempt from the original sanitized `input_payload` when available.
- Retry does not reuse previous human approvals. Any write or high-risk operation must request a fresh approval during the retry attempt.
- The original run remains unchanged for audit clarity.

### Cancellation

Cancellation is a request, not a guarantee of instant rollback.

Rules:

- `POST /runs/{run_id}/cancel` sets status to `cancel_requested` and emits `run.cancel_requested`.
- In-process graph execution checks the status at node and tool boundaries.
- If cancellation is observed, execution raises `RunCancelled`, emits `run.cancelled`, and marks the run `cancelled`.
- Already completed external writes are not rolled back by this feature.
- Pending approvals for a cancelled run should be expired or marked no longer actionable.

## API

Add `src/api/routers/runs.py`.

Endpoints:

- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/events`
- `POST /api/v1/runs/{run_id}/cancel`
- `POST /api/v1/runs/{run_id}/retry`

List filters:

- `status`
- `run_type`
- `user_id` for manager/admin
- `from`
- `to`
- `page`
- `page_size`

Authorization:

- `admin` and `manager` can see all runs and perform cancel/retry.
- ordinary users can see their own runs.
- ordinary users can cancel their own non-terminal runs.
- approval actions remain limited to `admin` and `manager`.

## Frontend

Add a task center page under the existing React app, with Chinese UI copy.

Recommended file additions:

- `src/ui/web/src/pages/AgentRunCenter.tsx`
- `src/ui/web/src/components/runs/RunStatusBadge.tsx`
- `src/ui/web/src/components/runs/RunTimeline.tsx`

Extend:

- `src/ui/web/src/services/api.ts`
- `src/ui/web/src/App.tsx` or the existing routing file
- `src/ui/web/src/components/Layout.tsx` or the active navigation component
- chat UI to display a run link when `run_id` is present

Main page behavior:

- Show run list with status, title, requester, current agent/tool, created time, duration, and result/error summary.
- Filter by status and search keyword.
- Open a run detail panel or detail route.
- Show a chronological timeline.
- Show "去审批" when a run is waiting for approval.
- Show "取消" for non-terminal runs the current user may cancel.
- Show "重试" for failed runs the current user may retry.

## Retention

Run records and events expire after 30 days by default.

Add a lightweight cleanup job during app lifecycle, similar to the approval expiry worker style already present in the project.

## Error Handling

- Unknown run ID returns 404.
- Unauthorized access returns 403.
- Invalid status transitions return 409.
- Cancel on terminal run returns 409.
- Retry on non-failed run returns 409.
- Event append failures should be logged and surfaced to the run manager. Risky write operations must continue to rely on approval fail-closed behavior.

## Implementation Order

1. Add run models, context, repository, manager, and cancellation exception.
2. Register repository initialization and cleanup lifecycle.
3. Add run APIs and include the router in FastAPI.
4. Instrument chat execution and graph execution.
5. Link approval lifecycle to run events.
6. Add frontend API client methods.
7. Add Run Center UI and navigation.
8. Add chat message run links.

## Deferred Verification

Per user instruction, this phase does not run:

- backend tests
- frontend tests
- build commands
- local app restart
- browser validation
- database migration execution

The implementation should still be written so that a later verification phase can run those checks cleanly.
