# Load tests (PRD §9.7)

[Locust](https://locust.io) scripts for the two write-heavy hot paths.

Locust isn't a workspace dependency — run it on demand with `uvx`:

```bash
# Ingestion: POST /v1/logs hot path (auth + Redis XADD)
INGESTION_API_KEY=local-dev-ingestion-key \
uvx --from locust locust -f load/locustfile_ingestion.py \
  --host http://127.0.0.1:8001 \
  --users 50 --spawn-rate 10 --run-time 2m --headless

# Chat: session + message + SSE stream hot path
uvx --from locust locust -f load/locustfile_chat.py \
  --host http://127.0.0.1:8000 \
  --users 20 --spawn-rate 5 --run-time 2m --headless
```

Drop `--headless` to open the Locust web UI on http://127.0.0.1:8089.

## Prerequisites

- `make up` (+ `make up-analytics` for the full pipeline) and migrations
  applied (`make migrate-all`).
- The target service running (chat on :8000, ingestion on :8001).
- For the chat test against a live provider, set the provider API key on
  the chat-service and expect real LLM cost. For pure throughput, point
  `CHAT_MODEL` at a stub model.

## What to watch

While a run is in flight, the dashboard (`/metrics/*`) and each service's
Prometheus `/metrics` endpoint should show the load: request counts climb,
latency histograms fill in, and (for the ingestion test's ~25% synthetic
errors) the dashboard error-rate rises.
