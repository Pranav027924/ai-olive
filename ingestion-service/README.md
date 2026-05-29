# ingestion-service

HTTP intake for `LogEvent`s. Validates the incoming batch and XADDs
each event to the `inference_logs` Redis Stream for the Worker
(Phase 5) to consume. See PRD §2.3, §6.3, §7.3.

## Layout

```
ingestion_service/
  domain/
    entities/ingestion_record.py     # IngestionRecord (Phase 4.2)
    services/validator.py            # schema + business validation
  application/
    use_cases/ingest_logs.py         # IngestLogsHandler (Phase 4.2)
    ports/
      log_stream.py                  # LogStream Protocol
      auth_provider.py               # AuthProvider Protocol
  infrastructure/
    streams/redis_stream.py          # RedisStreamAdapter (Phase 4.4)
    auth/api_key_auth.py             # ApiKeyAuthProvider (Phase 4.6)
  interfaces/
    http/
      routers/logs.py                # POST /v1/logs (Phase 4.6)
      schemas.py
    main.py                          # uvicorn entry, 127.0.0.1:8001
```

## Endpoints

- `POST /v1/logs` — accepts `{"events": [LogEvent, ...]}`, returns
  202 with the ingestion ids. Requires `x-api-key` header (PRD §9.5).
- `GET /health` — liveness probe (Phase 9).

## Run locally

(Populated in Phase 4.6 once the FastAPI app exists.)

```bash
uv run python -m ingestion_service.interfaces.http.main
# → 127.0.0.1:8001
```

## Test

```bash
uv run pytest ingestion-service/tests/
```
