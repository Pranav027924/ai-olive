# AI-OLive — LLM Inference Logging & Ingestion Platform

A microservice-based platform: multi-modal chatbot + logging SDK + ingestion pipeline + analytics dashboard.

The full design, requirements, and build plan live in [PRD.md](./PRD.md). **That document is the source of truth.** Read it before contributing.

## Repository layout

```
chat-service/         FastAPI: sessions, messages, SSE streaming
logging-sdk/          In-process SDK that captures inference metadata
ingestion-service/    FastAPI: log intake, Redis Streams producer
worker-service/       Async consumer: dedupe, redact, persist
media-service/        Transcription + file parsing (arq workers)
dashboard-service/    Metrics API (reads ClickHouse)
ui/                   React + Vite + TS frontend
shared/contracts/     Pydantic data contracts (cross-service)
shared/testing/       Shared test fixtures and helpers
tests/e2e/            End-to-end test suite (docker compose stack)
tests/load/           Locust load test scripts
docs/adr/             Architecture decision records
```

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Docker + Docker Compose (for local infra: Postgres / Redis / MinIO / ClickHouse)

## Quick start

```bash
make install   # sync workspace deps via uv
make up        # bring up local infra (Postgres, Redis, MinIO)
make test      # run all tests
make check     # lint + typecheck
make down      # tear down local infra
```

See `make help` for the full list of targets.

## Status

Build progresses through 9 sequential phases per the PRD. Current phase: **Phase 0 — Foundations** (scaffolding).
