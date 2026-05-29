# worker-service

Long-running worker that drains the `inference_logs` Redis Stream into
Postgres (`logs.inference_logs` + `logs.log_errors`). See PRD §6.4, §7.3, §8.1.

## Layout

```
worker_service/
  domain/
    entities/processed_log.py        # ProcessedLog entity (Phase 5.2)
    services/
      redaction_pipeline.py          # Chain of redactors (Phase 5.2)
      cost_calculator.py             # Per PRD §6.4 — duplicated from SDK
      idempotency_checker.py         # event_id dedupe (Phase 5.2)
  application/
    use_cases/process_log_event.py   # The pipeline (Phase 5.4)
    ports/
      log_repository.py              # Postgres write port
      stream_consumer.py             # Redis Streams read port
      metrics_writer.py              # ClickHouse port (used in Phase 7.5)
  infrastructure/
    persistence/postgres_log_repo.py # Phase 5.6
    streams/redis_stream_consumer.py # Phase 5.8
    redaction/
      regex_redactor.py              # Phase 5.2
      ner_redactor.py                # Optional, opt-in (Phase 9)
  interfaces/cli/run_worker.py       # Phase 5.10
```

## Run locally

(Populated in Phase 5.10.)

```bash
uv run python -m worker_service.interfaces.cli.run_worker
```

## Test

```bash
uv run pytest worker-service/tests/
```
