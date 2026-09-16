-- Migration: 004_agent_runtime_v2.sql
-- Description: Add V2 run identity and state-version metadata without replacing legacy run tables.
-- Version: 0.4.0
-- Created: 2026-09-07T00:00:00Z

-- The legacy repository historically created this table at application startup.
-- Defining it here makes the migration safe on a clean database as well.
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id UUID PRIMARY KEY,
    session_id TEXT,
    checkpoint_thread_id TEXT,
    user_id BIGINT NOT NULL,
    username TEXT NOT NULL,
    user_role TEXT NOT NULL,
    run_type TEXT NOT NULL,
    title TEXT NOT NULL,
    input_summary TEXT,
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    current_agent TEXT,
    current_tool TEXT,
    risk_level TEXT,
    approval_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    result_summary TEXT,
    retry_of_run_id UUID REFERENCES agent_runs(run_id),
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT agent_runs_status_check CHECK (
        status IN (
            'queued', 'running', 'waiting_approval', 'completed',
            'failed', 'cancel_requested', 'cancelled'
        )
    ),
    CONSTRAINT agent_runs_type_check CHECK (
        run_type IN ('chat', 'agent', 'tool', 'retry')
    )
);

CREATE TABLE IF NOT EXISTS agent_run_contexts_v2 (
    run_id UUID PRIMARY KEY REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    state_schema_version TEXT NOT NULL DEFAULT '1.0',
    graph_version TEXT NOT NULL DEFAULT 'warehouse-v2',
    plan_id TEXT,
    plan_version INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agent_run_contexts_v2_plan_version_check
        CHECK (plan_version IS NULL OR plan_version > 0),
    CONSTRAINT agent_run_contexts_v2_request_unique UNIQUE (tenant_id, request_id),
    CONSTRAINT agent_run_contexts_v2_thread_unique UNIQUE (tenant_id, thread_id),
    CONSTRAINT agent_run_contexts_v2_trace_unique UNIQUE (tenant_id, trace_id)
);

CREATE INDEX IF NOT EXISTS agent_run_contexts_v2_conversation_idx
ON agent_run_contexts_v2 (tenant_id, conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_run_contexts_v2_plan_idx
ON agent_run_contexts_v2 (tenant_id, plan_id, plan_version)
WHERE plan_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS agent_state_schema_versions (
    schema_version TEXT PRIMARY KEY,
    graph_version TEXT NOT NULL,
    status TEXT NOT NULL,
    migration_handler TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agent_state_schema_versions_status_check
        CHECK (status IN ('active', 'read_only', 'retired'))
);

INSERT INTO agent_state_schema_versions (
    schema_version,
    graph_version,
    status,
    migration_handler
)
VALUES ('1.0', 'warehouse-v2', 'active', NULL)
ON CONFLICT (schema_version) DO NOTHING;
