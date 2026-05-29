"""ingestion-service — HTTP intake for LogEvents (PRD §6.3).

Accepts batches of LogEvent rows over ``POST /v1/logs``, validates them
with Pydantic, and XADDs them to the ``inference_logs`` Redis Stream
for the Worker (Phase 5) to consume. No DB writes on the hot path
(PRD §2.3).

Hexagonal layering (PRD §5.2):

- ``domain``        : IngestionRecord, Validator (no I/O).
- ``application``   : IngestLogs use case, LogStream + AuthProvider ports.
- ``infrastructure``: RedisStreamAdapter, ApiKeyAuthProvider.
- ``interfaces``    : FastAPI router.
"""
