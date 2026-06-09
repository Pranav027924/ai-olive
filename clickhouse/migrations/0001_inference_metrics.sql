-- Phase 7.4 — analytics table for dashboard metrics (PRD §8.2).
--
-- One row per inference (mirrors a subset of the LogEvent contract).
-- The worker batches rows into ClickHouse asynchronously after a
-- successful Postgres insert; the dashboard service then queries
-- this table for percentiles, throughput, error-rate, and cost.

CREATE TABLE IF NOT EXISTS inference_metrics
(
    event_id          UUID,
    session_id        UUID,
    provider          LowCardinality(String),
    model             LowCardinality(String),
    status            LowCardinality(String),
    started_at        DateTime64(3, 'UTC'),
    finished_at       DateTime64(3, 'UTC'),
    latency_ms        UInt32,
    ttft_ms           Nullable(UInt32),
    prompt_tokens     UInt32,
    completion_tokens UInt32,
    cost_usd          Float64
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY (provider, model, started_at, event_id)
TTL toDateTime(started_at) + INTERVAL 180 DAY;
