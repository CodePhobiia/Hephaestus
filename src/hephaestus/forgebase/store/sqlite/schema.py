"""SQLite schema definition and initialization for ForgeBase."""
from __future__ import annotations

import aiosqlite

SCHEMA_SQL = """
-- Vaults
CREATE TABLE IF NOT EXISTS fb_vaults (
    vault_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    head_revision_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS fb_vault_revisions (
    revision_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    parent_revision_id TEXT,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    causation_event_id TEXT,
    summary TEXT NOT NULL DEFAULT ''
);

-- Canonical entity heads
CREATE TABLE IF NOT EXISTS fb_canonical_heads (
    vault_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    PRIMARY KEY (vault_id, entity_kind, entity_id)
);

-- Sources
CREATE TABLE IF NOT EXISTS fb_sources (
    source_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    format TEXT NOT NULL,
    origin_locator TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_source_versions (
    source_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]',
    url TEXT,
    raw_artifact_hash TEXT NOT NULL,
    raw_artifact_size INTEGER NOT NULL,
    raw_artifact_mime TEXT NOT NULL,
    normalized_hash TEXT,
    normalized_size INTEGER,
    normalized_mime TEXT,
    content_hash TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    trust_tier TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    PRIMARY KEY (source_id, version)
);

-- Pages
CREATE TABLE IF NOT EXISTS fb_pages (
    page_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    page_type TEXT NOT NULL,
    page_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_run TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fb_pages_vault_key ON fb_pages (vault_id, page_key);

CREATE TABLE IF NOT EXISTS fb_page_versions (
    page_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_size INTEGER NOT NULL,
    content_mime TEXT NOT NULL,
    content_hash_sha TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    compiled_from TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (page_id, version)
);

-- Claims
CREATE TABLE IF NOT EXISTS fb_claims (
    claim_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_claim_versions (
    claim_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL,
    support_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    validated_at TEXT NOT NULL,
    fresh_until TEXT,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    PRIMARY KEY (claim_id, version)
);

-- Claim provenance
CREATE TABLE IF NOT EXISTS fb_claim_supports (
    support_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_segment TEXT,
    strength REAL NOT NULL,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_claim_derivations (
    derivation_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    parent_claim_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL
);

-- Links
CREATE TABLE IF NOT EXISTS fb_links (
    link_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_link_versions (
    link_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    label TEXT,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    PRIMARY KEY (link_id, version)
);

-- Workbooks (= branches)
CREATE TABLE IF NOT EXISTS fb_workbooks (
    workbook_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    created_by_run TEXT
);

-- Branch heads (COW overrides)
CREATE TABLE IF NOT EXISTS fb_branch_page_heads (
    workbook_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    base_version INTEGER NOT NULL,
    PRIMARY KEY (workbook_id, page_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_claim_heads (
    workbook_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    base_version INTEGER NOT NULL,
    PRIMARY KEY (workbook_id, claim_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_link_heads (
    workbook_id TEXT NOT NULL,
    link_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    base_version INTEGER NOT NULL,
    PRIMARY KEY (workbook_id, link_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_source_heads (
    workbook_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    base_version INTEGER NOT NULL,
    PRIMARY KEY (workbook_id, source_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_claim_support_heads (
    workbook_id TEXT NOT NULL,
    support_id TEXT NOT NULL,
    created_on_branch INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workbook_id, support_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_claim_derivation_heads (
    workbook_id TEXT NOT NULL,
    derivation_id TEXT NOT NULL,
    created_on_branch INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workbook_id, derivation_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_tombstones (
    workbook_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    tombstoned_at TEXT NOT NULL,
    PRIMARY KEY (workbook_id, entity_kind, entity_id)
);

-- Merge
CREATE TABLE IF NOT EXISTS fb_merge_proposals (
    merge_id TEXT PRIMARY KEY,
    workbook_id TEXT NOT NULL,
    vault_id TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    target_revision_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    resulting_revision TEXT,
    proposed_at TEXT NOT NULL,
    resolved_at TEXT,
    proposed_by_type TEXT NOT NULL,
    proposed_by_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_merge_conflicts (
    conflict_id TEXT PRIMARY KEY,
    merge_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    base_version INTEGER NOT NULL,
    branch_version INTEGER NOT NULL,
    canonical_version INTEGER NOT NULL,
    resolution TEXT,
    resolved_at TEXT
);

-- Jobs
CREATE TABLE IF NOT EXISTS fb_jobs (
    job_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    workbook_id TEXT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TEXT,
    leased_until TEXT,
    heartbeat_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    created_by_run TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fb_jobs_idemp ON fb_jobs (idempotency_key);

-- Lint findings
CREATE TABLE IF NOT EXISTS fb_lint_findings (
    finding_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    vault_id TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    page_id TEXT,
    claim_id TEXT,
    description TEXT NOT NULL,
    suggested_action TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    resolved_at TEXT
);

-- Run integration
CREATE TABLE IF NOT EXISTS fb_run_refs (
    ref_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    run_type TEXT NOT NULL,
    upstream_system TEXT NOT NULL,
    upstream_ref TEXT,
    source_hash TEXT,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    sync_error TEXT,
    synced_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_run_artifacts (
    ref_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (ref_id, entity_kind, entity_id)
);

-- Domain events (outbox)
CREATE TABLE IF NOT EXISTS fb_domain_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_version INTEGER,
    vault_id TEXT NOT NULL,
    workbook_id TEXT,
    run_id TEXT,
    causation_id TEXT,
    correlation_id TEXT,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_fb_events_aggregate ON fb_domain_events (aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_fb_events_vault ON fb_domain_events (vault_id);

-- Event deliveries
CREATE TABLE IF NOT EXISTS fb_event_deliveries (
    event_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    last_error TEXT,
    delivered_at TEXT,
    PRIMARY KEY (event_id, consumer_name)
);
CREATE INDEX IF NOT EXISTS idx_fb_deliveries_pending ON fb_event_deliveries (consumer_name, status, next_attempt_at);
"""


async def initialize_schema(db: aiosqlite.Connection) -> None:
    """Create all ForgeBase tables."""
    await db.executescript(SCHEMA_SQL)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.commit()
