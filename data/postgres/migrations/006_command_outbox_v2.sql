-- Migration: 006_command_outbox_v2.sql
-- Approval-bound commands and transactional outbox.

CREATE TABLE IF NOT EXISTS proposed_actions_v2 (
    tenant_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    run_id UUID NOT NULL,
    requester_id TEXT NOT NULL,
    requester_context JSONB NOT NULL,
    action_payload JSONB NOT NULL,
    action_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, action_id)
);
CREATE INDEX IF NOT EXISTS proposed_actions_v2_run_idx
ON proposed_actions_v2 (tenant_id, run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS approvals_v2 (
    approval_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    run_id UUID,
    requester_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action_hash CHAR(64) NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','expired','consumed')),
    required_approvals SMALLINT NOT NULL DEFAULT 1 CHECK (required_approvals BETWEEN 1 AND 2),
    approver_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS approvals_v2_pending_idx ON approvals_v2(tenant_id, expires_at) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS commands_v2 (
    command_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    run_id UUID,
    approval_id UUID NOT NULL REFERENCES approvals_v2(approval_id),
    capability TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action_hash CHAR(64) NOT NULL,
    idempotency_key TEXT NOT NULL,
    target JSONB NOT NULL,
    arguments JSONB NOT NULL,
    expected_version TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','failed','result_unknown','cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    external_reference TEXT,
    readback JSONB,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    error JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS commands_v2_dispatch_idx ON commands_v2(status, next_attempt_at, lease_expires_at, created_at);

CREATE TABLE IF NOT EXISTS command_attempts_v2 (
    attempt_id UUID PRIMARY KEY,
    command_id UUID NOT NULL REFERENCES commands_v2(command_id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    worker_id TEXT NOT NULL,
    status TEXT NOT NULL,
    request_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_metadata JSONB,
    error_category TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    UNIQUE (command_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS outbox_events_v2 (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_by TEXT,
    lease_expires_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS outbox_events_v2_pending_idx ON outbox_events_v2(available_at, created_at) WHERE delivered_at IS NULL;

CREATE TABLE IF NOT EXISTS inbox_dedup_v2 (
    consumer TEXT NOT NULL,
    message_id TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer, message_id)
);
