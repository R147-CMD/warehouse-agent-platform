-- Migration: 007_memory_audit_v2.sql
-- Tenant-scoped memory and append-only audit linkage.

CREATE TABLE IF NOT EXISTS agent_memory_v2 (
    memory_id TEXT PRIMARY KEY,
    memory_key TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK (memory_type IN ('preference','stable_constraint','business_glossary','summary')),
    content TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('user','system','approved_summary')),
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    acl JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    UNIQUE (tenant_id, user_id, memory_key)
);
CREATE INDEX IF NOT EXISTS agent_memory_v2_scope_idx ON agent_memory_v2(tenant_id, user_id, expires_at) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS conversation_turns_v2 (
    turn_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS conversation_turns_v2_scope_idx
ON conversation_turns_v2 (
    tenant_id, user_id, conversation_id, created_at DESC
);
CREATE INDEX IF NOT EXISTS conversation_turns_v2_expiry_idx
ON conversation_turns_v2 (expires_at);

CREATE TABLE IF NOT EXISTS agent_audit_events_v2 (
    audit_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT,
    run_id UUID REFERENCES agent_runs(run_id) ON DELETE SET NULL,
    trace_id TEXT,
    plan_id TEXT,
    approval_id UUID,
    command_id UUID,
    evidence_id TEXT,
    payload_redacted JSONB NOT NULL DEFAULT '{}'::jsonb,
    previous_event_hash CHAR(64),
    event_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS agent_audit_events_v2_run_idx ON agent_audit_events_v2(tenant_id, run_id, created_at);

CREATE OR REPLACE FUNCTION prevent_agent_audit_mutation_v2()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'agent_audit_events_v2 is append-only';
END;
$$;

DROP TRIGGER IF EXISTS agent_audit_events_v2_no_update ON agent_audit_events_v2;
CREATE TRIGGER agent_audit_events_v2_no_update
BEFORE UPDATE OR DELETE ON agent_audit_events_v2
FOR EACH ROW EXECUTE FUNCTION prevent_agent_audit_mutation_v2();
