-- Migration: 005_evidence_retrieval_v2.sql
-- Versioned document, index, evidence, claim and citation storage.

CREATE TABLE IF NOT EXISTS documents_v2 (
    document_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    source_hash CHAR(64) NOT NULL,
    parser_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('uploaded','parsing','quality_failed','parsed','indexed','deleted')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, source_hash, parser_version)
);

CREATE TABLE IF NOT EXISTS document_elements_v2 (
    element_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents_v2(document_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    element_type TEXT NOT NULL,
    heading_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    bbox JSONB,
    reading_order INTEGER NOT NULL,
    parser TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    content TEXT NOT NULL,
    source_hash CHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks_v2 (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents_v2(document_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    parent_id TEXT NOT NULL,
    previous_chunk_id TEXT,
    next_chunk_id TEXT,
    chunk_type TEXT NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count > 0),
    page_numbers JSONB NOT NULL,
    element_ids JSONB NOT NULL,
    acl JSONB NOT NULL,
    parser_version TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    embedding_version TEXT,
    source_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS document_chunks_v2_parent_idx ON document_chunks_v2(tenant_id, parent_id);

CREATE TABLE IF NOT EXISTS index_versions_v2 (
    index_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    backend TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    embedding_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('building','shadow','active','retired','failed')),
    document_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    UNIQUE (tenant_id, alias, index_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS index_versions_v2_one_active_idx
ON index_versions_v2(tenant_id, alias) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS evidence_v2 (
    evidence_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_locator JSONB NOT NULL,
    entity_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    event_time TIMESTAMPTZ,
    observed_at TIMESTAMPTZ NOT NULL,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    source_version TEXT,
    freshness TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    content JSONB NOT NULL,
    acl JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);
CREATE INDEX IF NOT EXISTS evidence_v2_source_idx ON evidence_v2(tenant_id, source_system, observed_at DESC);

CREATE TABLE IF NOT EXISTS claims_v2 (
    claim_id TEXT PRIMARY KEY,
    run_id UUID REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    statement TEXT NOT NULL,
    subject JSONB,
    predicate TEXT,
    value JSONB,
    event_time TIMESTAMPTZ,
    supporting_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    opposing_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS citations_v2 (
    citation_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims_v2(claim_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_v2(evidence_id),
    label TEXT NOT NULL,
    locator JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (claim_id, evidence_id)
);
