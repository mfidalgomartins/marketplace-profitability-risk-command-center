CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('order', 'seller')),
    entity_id TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('critical', 'high', 'moderate', 'low')),
    status TEXT NOT NULL CHECK (
        status IN ('open', 'investigating', 'pending_approval', 'resolved', 'rejected')
    ),
    owner TEXT,
    recommended_action TEXT NOT NULL,
    decision_rationale TEXT,
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_status_priority
    ON cases (status, priority, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cases_entity
    ON cases (entity_type, entity_id);

CREATE TABLE IF NOT EXISTS case_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    event_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_case_events_case
    ON case_events (case_id, event_id);

CREATE TABLE IF NOT EXISTS case_commands (
    command_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    route TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    case_id TEXT,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    event_at TEXT NOT NULL,
    details_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    audit_hash TEXT NOT NULL UNIQUE
);

CREATE TRIGGER IF NOT EXISTS case_events_no_update
BEFORE UPDATE ON case_events
BEGIN
    SELECT RAISE(ABORT, 'case_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS case_events_no_delete
BEFORE DELETE ON case_events
BEGIN
    SELECT RAISE(ABORT, 'case_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
