-- Migration: 008_execution_async_v2.sql
-- Upgrade an existing execution V2 schema with delayed retry scheduling.

ALTER TABLE commands_v2
ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;

ALTER TABLE commands_v2
ADD COLUMN IF NOT EXISTS evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb;

DROP INDEX IF EXISTS commands_v2_dispatch_idx;
CREATE INDEX IF NOT EXISTS commands_v2_dispatch_idx
ON commands_v2(status, next_attempt_at, lease_expires_at, created_at);

CREATE INDEX IF NOT EXISTS outbox_events_v2_claim_idx
ON outbox_events_v2(delivered_at, available_at, lease_expires_at, created_at);
