-- Ecstasy Postgres schema. Idempotent: applied by the worker on every start.

CREATE TABLE IF NOT EXISTS venues (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    config      JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    venue_id    TEXT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    doors_at    TEXT,
    location    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    venue_id     TEXT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    trust        TEXT NOT NULL,
    doc_date     DATE,
    content_hash TEXT NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT PRIMARY KEY,
    venue_id     TEXT NOT NULL,
    doc_id       TEXT NOT NULL,
    text         TEXT NOT NULL,
    header       TEXT NOT NULL,
    meta         JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chunks_venue_idx ON chunks(venue_id);

CREATE TABLE IF NOT EXISTS embedding_cache (
    content_hash TEXT NOT NULL,
    model_id     TEXT NOT NULL,
    dim          INT NOT NULL,
    vector       REAL[] NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (content_hash, model_id, dim)
);

CREATE TABLE IF NOT EXISTS observations (
    id           BIGSERIAL PRIMARY KEY,
    venue_id     TEXT NOT NULL,
    feature      TEXT NOT NULL,
    status       TEXT NOT NULL,
    source_kind  TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence   REAL,
    source_ref   TEXT NOT NULL DEFAULT '',
    observed_at  TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS obs_lookup_idx ON observations(venue_id, feature, source_kind, observed_at DESC);

CREATE TABLE IF NOT EXISTS feature_status (
    venue_id    TEXT NOT NULL,
    feature     TEXT NOT NULL,
    state       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (venue_id, feature)
);

CREATE TABLE IF NOT EXISTS alerts (
    id          BIGSERIAL PRIMARY KEY,
    venue_id    TEXT NOT NULL,
    feature     TEXT NOT NULL,
    kind        TEXT NOT NULL,
    severity    TEXT NOT NULL,
    message     TEXT NOT NULL,
    acked       BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alerts_venue_idx ON alerts(venue_id, created_at DESC);

CREATE TABLE IF NOT EXISTS reports (
    id           BIGSERIAL PRIMARY KEY,
    venue_id     TEXT NOT NULL,
    kind         TEXT NOT NULL,          -- visitor_report | staff_note | maintenance_log
    reporter     TEXT NOT NULL,
    needs        TEXT NOT NULL DEFAULT '',
    text         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | done | error
    extraction   JSONB,
    error        TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS reports_pending_idx ON reports(status, id);

CREATE TABLE IF NOT EXISTS staff_checks (
    id          BIGSERIAL PRIMARY KEY,
    venue_id    TEXT NOT NULL,
    staff_name  TEXT NOT NULL DEFAULT '',
    items       JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS answer_traces (
    id             BIGSERIAL PRIMARY KEY,
    venue_id       TEXT NOT NULL,
    question       TEXT NOT NULL,
    profile        JSONB NOT NULL,
    plan           JSONB,
    retrieved      JSONB,
    live_context   JSONB,
    answer         JSONB,
    validation     JSONB,
    mode           TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    latency_ms     INT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
