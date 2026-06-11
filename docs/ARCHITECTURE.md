# AI-OLive — Architecture & System Overview

> A detailed walkthrough of what this project is, how it is built, what it
> contains, how it is structured, and how the pieces fit together.
>
> The authoritative design spec is [PRD.md](../PRD.md); this document is the
> narrated, implementation-accurate companion to it. Where the two differ,
> the code and this document reflect what was actually built.

---

## Table of contents

1. [What AI-OLive is](#1-what-ai-olive-is)
2. [The big picture](#2-the-big-picture)
3. [End-to-end flows](#3-end-to-end-flows)
4. [How it is built — principles & stack](#4-how-it-is-built--principles--stack)
5. [The monorepo: workspace & package graph](#5-the-monorepo-workspace--package-graph)
6. [Repository structure](#6-repository-structure)
7. [The services in detail](#7-the-services-in-detail)
8. [How things are linked: the contracts](#8-how-things-are-linked-the-contracts)
9. [Data stores & ownership](#9-data-stores--ownership)
10. [Cross-cutting concerns](#10-cross-cutting-concerns)
11. [Testing strategy](#11-testing-strategy)
12. [Running it locally](#12-running-it-locally)
13. [Deployment](#13-deployment)
14. [How it was built — phase history](#14-how-it-was-built--phase-history)
15. [Glossary](#15-glossary)
16. [Reading guide for engineers](#16-reading-guide-for-engineers)

---

## 1. What AI-OLive is

**AI-OLive is an LLM Inference Logging & Ingestion Platform.** It is two things
fused into one product:

1. **A multi-modal chat application** — users hold streaming conversations with
   large language models from four providers (Anthropic, OpenAI, Google Gemini,
   DeepSeek), can upload documents (PDF/DOCX) and voice clips, and can cancel a
   reply mid-stream.

2. **An observability pipeline for those LLM calls** — every inference is
   captured (provider, model, tokens, latency, time-to-first-token, cost,
   redacted previews), shipped through a durable queue, deduplicated and
   persisted, mirrored into an analytics column store, and surfaced on a
   dashboard (latency percentiles, throughput, error rate, cost by provider).

### The problem it solves

Teams running LLMs in production need to *use* the models and *understand* what
those models are doing — how slow, how expensive, how often they fail, broken
down by provider and model. AI-OLive demonstrates a production-grade way to do
both, with the logging concern cleanly decoupled from the chat concern via an
in-process SDK and an asynchronous ingestion pipeline, so that capturing
telemetry never slows down or breaks the user-facing chat.

### The shape, in one sentence

A React UI talks to a **Chat Service**; the Chat Service streams LLM tokens to
the user while an embedded **Logging SDK** fires a `LogEvent` to an **Ingestion
Service**, which pushes it onto a **Redis Stream**; a **Worker Service** drains
the stream, dedupes/redacts/prices each event, writes it to **Postgres** and
mirrors a metric row to **ClickHouse**; a **Dashboard Service** reads ClickHouse
and serves aggregate metrics back to the UI.

---

## 2. The big picture

### 2.1 Service topology

```
                                  ┌─────────────────────────────┐
                                  │            UI (React)        │
                                  │   Vite · TS · Tailwind       │
                                  │   http://localhost:5173      │
                                  └───────┬──────────────┬───────┘
                          /api/chat/*     │              │   /api/dashboard/*
                                          ▼              ▼
                            ┌───────────────────┐   ┌────────────────────┐
                            │   Chat Service     │   │ Dashboard Service   │
                            │   FastAPI :8000    │   │ FastAPI :8004       │
                            │   sessions,        │   │ /metrics/*          │
                            │   messages, SSE,   │   │ (read-only)         │
                            │   uploads, JWT     │   └─────────┬──────────┘
                            └───┬───────┬───────┘             │ reads
                  embeds        │       │ stores               ▼
            ┌─────────────────┐ │       │            ┌───────────────────┐
            │  Logging SDK    │◀┘       │            │    ClickHouse      │
            │ (olive-sdk)     │         ▼            │  inference_metrics │
            │ provider adapters         Postgres     └─────────▲─────────┘
            │ + Tracker       │      chat schema               │ mirrors
            └───────┬─────────┘      (sessions,                │
              POST  │ LogEvent        messages,        ┌───────┴──────────┐
                    ▼                 attachments)     │  Worker Service   │
            ┌───────────────────┐         ▲           │  drain loop       │
            │ Ingestion Service │         │ writes    │  dedupe·redact·    │
            │ FastAPI :8001     │         │           │  price·persist     │
            │ x-api-key auth    │         └───────────┤  + dead-letter     │
            └───────┬───────────┘     logs schema     └───────▲───────────┘
                    │ XADD                (inference_logs,             │
                    ▼                      log_errors)                 │ XREADGROUP
            ┌───────────────────────────────────────────────┐         │
            │   Redis  ·  Stream "inference_logs"  ───────────────────┘
            │          ·  consumer group "log_processors"   │
            │          ·  DLQ stream "inference_logs_dlq"   │
            │          ·  cancellation flags (chat)         │
            └───────────────────────────────────────────────┘

      Object storage:  MinIO (S3-compatible)  ← chat uploads (PDF/audio blobs)
      Media library:   media-service (parsing + transcription), imported by chat
```

### 2.2 The seven deployable units

| Unit | Kind | Port | Responsibility |
|---|---|---|---|
| **ui** | React SPA (nginx in prod) | 5173 / 8080 | Chat, session list, uploads, dashboard |
| **chat-service** | FastAPI | 8000 | Sessions, messages, SSE streaming, cancel, uploads, auth |
| **ingestion-service** | FastAPI | 8001 | Validated log intake → Redis Stream |
| **worker-service** | Async CLI consumer | — | Drain stream → Postgres + ClickHouse |
| **dashboard-service** | FastAPI | 8004 | Read-only analytics over ClickHouse |
| *(logging-sdk)* | Library | — | Embedded inside chat-service |
| *(media-service)* | Library | — | Imported by chat-service for parse/transcribe |

### 2.3 Backing infrastructure

| Store | Role |
|---|---|
| **Postgres 16** | System of record: `chat` schema (sessions/messages/attachments) + `logs` schema (inference_logs/log_errors, partitioned) |
| **Redis 7** | Durable work queue (Streams), worker consumer group, dead-letter stream, chat cancellation flags |
| **MinIO** | S3-compatible object storage for uploaded file/voice blobs |
| **ClickHouse** | Column store for analytics (`inference_metrics`), written by the worker, read by the dashboard |

---

## 3. End-to-end flows

### 3.1 A single chat turn (the heart of the system)

1. **User sends a message.** UI → `POST /api/chat/{id}/messages`. The Chat
   Service appends a `user` message to the session and returns `201`. No LLM
   call happens here.
2. **User opens the stream.** UI → `GET /api/chat/{id}/stream` (Server-Sent
   Events). The Chat Service:
   - builds the LLM context (rolling window of prior messages + system prompt +
     any *completed* attachment text),
   - calls the **Logging SDK**'s `LLMClient.complete(...)`, which routes to the
     right provider adapter based on the session's `provider`,
   - relays each token to the browser as an SSE `chunk` event,
   - between tokens, polls a Redis **cancellation flag**; if set, it stops with
     `state=cancelled`,
   - on completion, persists the `assistant` message and emits a `finished`
     event.
3. **Telemetry fires automatically.** When the SDK's `Tracker` async-context
   exits, it builds a `LogEvent` (tokens, latency, ttft, cost, redacted
   previews) and hands it to the configured **emitter**, which `POST`s it to the
   **Ingestion Service** (and also tees a copy to a local JSONL file for dev).
4. **Ingestion → queue.** Ingestion validates the batch, authenticates the
   `x-api-key`, and `XADD`s each event onto the Redis stream `inference_logs`
   (trimmed with an approximate `MAXLEN`).
5. **Worker → stores.** The Worker's drain loop `XREADGROUP`s a batch, and per
   event: checks idempotency (in-memory + Postgres), redacts previews, computes
   cost, writes a row to `logs.inference_logs` (and `logs.log_errors` on
   failures), then buffers a metric row and flushes it to ClickHouse
   `inference_metrics`. Successfully handled messages are `XACK`ed; poison
   (unparseable) messages go to the dead-letter stream then get acked; transient
   failures are left un-acked for redelivery.
6. **Dashboard reads.** UI → `GET /api/dashboard/metrics/*?window=1h|24h|7d`.
   The Dashboard Service runs `quantile`/`count`/`sum` queries against
   ClickHouse and returns latency percentiles, throughput, error rate, and cost
   by provider.

### 3.2 Cancellation

`POST /api/chat/{id}/cancel` sets a flag in the Redis cancellation store. The
in-flight streaming generator checks it between tokens and finishes the message
with `status=cancelled`. The SSE `finished` event carries the partial content.

### 3.3 File / voice upload

1. `POST /api/chat/{id}/files` (or `/voice`) — multipart upload.
2. Chat Service writes the blob to **MinIO** under
   `sessions/{id}/attachments/{aid}/{filename}`, inserts an `attachments` row
   with `parse_status=pending`, and returns `202 Accepted` immediately.
3. A FastAPI **BackgroundTask** runs the **media-service** use case: documents
   go through the PDF/DOCX parser; audio goes through the faster-whisper
   transcriber. The extracted text is written back to the attachment row and
   `parse_status` flips to `complete` (or `failed`).
4. On the next chat turn, the `ContextBuilder` folds every *completed*
   attachment's text into the system prompt, so the model can reference the
   upload.

---

## 4. How it is built — principles & stack

### 4.1 Architectural principles

- **Hexagonal architecture (Ports & Adapters) per service.** Every service is
  layered `domain → application → infrastructure → interfaces`, and the
  **dependency rule** only ever points inward. The domain knows nothing about
  FastAPI, SQLAlchemy, Redis, or any provider SDK.
  - **domain** — entities, value objects, domain services, domain errors. Pure
    Python, no I/O.
  - **application** — use cases (orchestration) and **ports** (Protocols
    describing what the use case needs: a repository, an LLM client, a stream).
  - **infrastructure** — concrete **adapters** implementing the ports
    (Postgres repos, Redis adapters, provider SDK wrappers, S3 client).
  - **interfaces** — the delivery mechanism: FastAPI routers, the worker CLI,
    HTTP dependency wiring.
- **Domain-Driven Design.** Each service is a **bounded context** (Chat,
  Logging, Ingestion, Processing/Worker, Media, Analytics) with its own
  aggregates (`Session`, `Attachment`, `ProcessedLog`, …) and its own database
  ownership. Services never share tables; they share *contracts*.
- **Test-Driven Development.** ~446 tests written red-green per build step:
  fast unit tests against fakes, integration tests against real Postgres/Redis
  via testcontainers, and end-to-end tests against the compose stack.
- **Strict typing & linting everywhere.** `mypy --strict` and `ruff`
  (lint + format) gate every change via `make check`.
- **Async all the way.** FastAPI + `async`/`await`, SQLAlchemy 2.x async +
  asyncpg, `redis.asyncio`, pure-ASGI middleware (so SSE streaming is never
  buffered).

### 4.2 Technology stack

| Concern | Choice |
|---|---|
| Language / runtime | Python 3.11+, `asyncio` |
| Package / workspace | **uv** workspace (one lockfile, many member packages) |
| Web framework | FastAPI + Uvicorn |
| Validation / models | Pydantic v2 (+ pydantic-settings for config) |
| Relational DB | Postgres 16, SQLAlchemy 2.x async, asyncpg, Alembic migrations |
| Queue | Redis 7 Streams (consumer groups) |
| Object storage | MinIO / S3 (aioboto3) |
| Analytics store | ClickHouse (aiochclient) |
| LLM providers | `anthropic`, `openai`, `google-genai` SDKs (DeepSeek via OpenAI-compatible API) |
| Transcription | faster-whisper |
| Doc parsing | pypdf, python-docx |
| Observability | structlog (JSON), Prometheus (`prometheus-client`) |
| Auth | PyJWT (HS256) for users; API-key allow-list for inter-service |
| Frontend | React 18, Vite, TypeScript, Tailwind, TanStack Query, Zustand, Recharts, shadcn-style components |
| Testing | pytest, pytest-asyncio, testcontainers, Vitest + Testing Library, Playwright, Locust |
| Containers / orchestration | Docker (multi-stage), docker-compose (dev + prod), Kubernetes manifests, k3s rollout |

---

## 5. The monorepo: workspace & package graph

AI-OLive is a single **uv workspace** with nine member packages plus the UI.
There is one `uv.lock` for the whole repo; each member has its own
`pyproject.toml` declaring its dependencies, and workspace members depend on one
another via `{ workspace = true }` sources.

### 5.1 Shared (library) packages

| Package | Import name | Purpose |
|---|---|---|
| `shared/contracts` | `contracts` (`olive-contracts`) | The `LogEvent` Pydantic model — the cross-service wire contract |
| `shared/observability` | `olive_obs` (`olive-obs`) | structlog config, request-id middleware, Prometheus middleware, health endpoints |
| `shared/testing` | `testing_support` (`olive-testing`) | Shared test helpers |
| `logging-sdk` | `olive_sdk` (`olive-sdk`) | The in-process logging SDK + provider adapters |
| `media-service` | `media_service` | Parsing + transcription library (imported by chat) |

### 5.2 Dependency edges (who imports whom)

```
olive-contracts ──────────────┐ (LogEvent)
   ▲          ▲                │
   │          │                ▼
olive-sdk   ingestion-svc   worker-svc ── olive-obs
   ▲                            │             ▲
   │                            └─────────────┤
chat-service ── media-service                 │
   │   │            ▲                          │
   │   └── olive-obs┘                          │
   └── olive-sdk                               │
                                               │
dashboard-service ─────────────────────────────┘ (olive-obs)
```

Key edges:
- **chat-service** imports `olive-sdk` (to call LLMs + log), `media-service`
  (to parse/transcribe uploads), `olive-obs` (observability), and
  `olive-contracts` (transitively).
- **olive-sdk** and **ingestion-service** and **worker-service** all depend on
  `olive-contracts` because the `LogEvent` is the shared currency between them.
- **olive-obs** is imported by every runnable service (chat, ingestion, worker,
  dashboard) for logging/metrics/health.
- The **domain layers never import infrastructure** — that's enforced by code
  review and the layering, and verified by mypy boundaries.

---

## 6. Repository structure

```
AI-OLive/
├── PRD.md                      # Source-of-truth product/design spec
├── README.md                   # Quick start
├── DEPLOY.md                   # Deploy runbook (compose-prod + k3s)
├── Makefile                    # install / check / lint / typecheck / test / up / migrate / worker
├── pyproject.toml              # uv workspace root + shared tool config (ruff, mypy, pytest)
├── uv.lock                     # single lockfile for the whole workspace
├── docker-compose.yml          # Local infra: Postgres, Redis, MinIO, ClickHouse(profile)
├── docker-compose.prod.yml     # Full containerised stack (services + infra + migrations)
│
├── shared/
│   ├── contracts/              # olive-contracts: LogEvent (the wire contract)
│   ├── observability/          # olive-obs: structlog, request-id, Prometheus, health
│   └── testing/                # olive-testing: shared fixtures
│
├── logging-sdk/                # olive-sdk
│   └── olive_sdk/
│       ├── domain/services/    # CostCalculator
│       ├── application/         # Tracker (LogEvent lifecycle), EmitterPort
│       ├── infrastructure/
│       │   ├── providers/       # Anthropic / OpenAI / Gemini / DeepSeek adapters
│       │   └── emitters/        # File, HTTP (batched, retry, circuit-breaker), Composite
│       └── client.py            # public LLMClient
│
├── chat-service/               # The chat plane (largest service)
│   ├── chat_service/
│   │   ├── domain/             # Session, Message, Attachment, StreamingResponse, VOs, errors
│   │   ├── application/         # use cases (create/list session, send msg, stream, cancel,
│   │   │   │                    #   upload/process attachment) + ports
│   │   │   ├── ports/           # SessionRepository, LLMClient, CancellationStore, AttachmentRepository
│   │   │   └── use_cases/
│   │   ├── infrastructure/      # Postgres repos, Redis cancel store, SDK client wrapper,
│   │   │   │                    #   JWT verifier, S3/whisper/parsers (via media-service)
│   │   │   ├── persistence/  cache/  sdk/  auth/
│   │   ├── interfaces/http/     # FastAPI app, routers (sessions, messages, stream, attachments),
│   │   │                        #   dependency wiring, schemas
│   │   └── config.py
│   └── alembic/                 # chat schema migrations
│
├── ingestion-service/          # HTTP intake → Redis Streams
│   └── ingestion_service/{domain,application,infrastructure,interfaces}/
│
├── worker-service/             # Stream consumer → Postgres + ClickHouse
│   ├── worker_service/
│   │   ├── domain/             # ProcessedLog, CostCalculator, RedactionPipeline, IdempotencyChecker
│   │   ├── application/         # ProcessLogEvent use case, WorkerLoop, ports
│   │   │   └── ports/           # LogRepository, StreamConsumer, MetricsSink, DeadLetterSink
│   │   ├── infrastructure/      # Postgres repo, Redis consumer + DLQ, ClickHouse sink, redactors
│   │   └── interfaces/cli/      # run_worker entry point
│   └── alembic/                 # logs schema migrations (separate alembic_version table)
│
├── media-service/              # Parsing + transcription (library, imported by chat)
│   └── media_service/{domain,application,infrastructure}/
│       ├── infrastructure/parsing/        # PdfParser, DocxParser
│       ├── infrastructure/transcription/  # FasterWhisperTranscriber
│       └── infrastructure/storage/        # S3 + in-memory ObjectStorage
│
├── dashboard-service/          # Read-only analytics API
│   └── dashboard_service/{domain,application,infrastructure,interfaces}/
│       └── infrastructure/clickhouse/     # ClickHouseMetricsReader
│
├── ui/                         # React + Vite + TS + Tailwind SPA
│   ├── src/
│   │   ├── api/                # typed client + SSE reader
│   │   ├── features/           # sessions, chat, uploads, dashboard
│   │   ├── components/ui/      # shadcn-style Button/Card
│   │   └── routes/
│   └── tests-e2e/              # Playwright specs
│
├── clickhouse/migrations/      # inference_metrics schema (applied over HTTP)
├── docker/                     # Per-service multi-stage Dockerfiles + nginx.conf
├── k8s/                        # Kustomize manifests (namespace, config, infra, jobs, deploys, ingress)
├── load/                       # Locust load-test scripts (chat + ingestion)
├── scripts/                    # dev-local.sh, k3s-rollout.sh, verify-deployment.sh
├── tests/e2e/                  # Cross-service end-to-end tests
└── docs/                       # This document + ADRs
```

---

## 7. The services in detail

### 7.1 Chat Service (`chat-service`, FastAPI :8000)

**Bounded context:** conversations. The user-facing plane.

- **Domain:** `Session` (aggregate root — owns its `Message` list and status
  lifecycle), `Message`, `Attachment` (with a `pending → complete/failed`
  state machine), `StreamingResponse` value object, plus value objects
  (`MessageRole`, `MessageStatus`, `SessionStatus`, `ModelConfig`,
  `AttachmentKind`, `ParseStatus`) and the `ContextBuilder` domain service.
- **Application ports:** `SessionRepository`, `AttachmentRepository`,
  `LLMClient`, `CancellationStore`.
- **Use cases:** create/list session, send text message, **stream assistant
  response** (an async generator yielding `StreamStarted/Chunk/Finished`),
  cancel stream, upload attachment, process attachment.
- **Infrastructure adapters:** `PostgresSessionRepository`,
  `PostgresAttachmentRepository`, `RedisCancellationStore`, `SdkLlmClient`
  (wraps `olive-sdk`, routing per-session provider to the right API key),
  `JwtVerifier`, and — through `media-service` — the parsers, whisper
  transcriber and S3 object storage.
- **Endpoints:** `POST /auth/register`, `POST /auth/login`,
  `POST/GET /sessions`, `GET/DELETE /sessions/{id}`,
  `POST /chat/{id}/messages`, `GET /chat/{id}/stream` (SSE),
  `POST /chat/{id}/cancel`, `POST /sessions/{id}/files`,
  `POST /sessions/{id}/voice`, plus `/health`, `/health/ready`, `/metrics`.
- **Auth:** bcrypt accounts + HS256 JWT — login mints a token (`JwtIssuer`),
  `get_current_user_id` verifies it (`JwtVerifier`). `DISABLE_AUTH=true`
  (local/demo) falls back to a fixed dev user; production requires a Bearer token.
- **Owns:** the `chat` Postgres schema.

### 7.2 Logging SDK (`logging-sdk` / `olive-sdk`, library)

**Bounded context:** capturing inference telemetry — embedded *inside*
chat-service, not a network hop.

- **`LLMClient`** is the public surface: `async for token in client.complete(...)`.
- **Provider adapters** (`ProviderAdapter` Protocol) normalise each vendor SDK
  into a uniform stream of `ChunkEvent`s followed by one `UsageEvent`:
  `AnthropicAdapter`, `OpenAIAdapter`, `GeminiAdapter`, `DeepSeekAdapter`
  (DeepSeek subclasses OpenAI against `api.deepseek.com`).
- **`Tracker`** is an async context manager that times the call, accumulates
  tokens, computes cost via `CostCalculator`, and on exit builds a `LogEvent`
  and hands it to an **emitter**.
- **Emitters** (`EmitterPort`): `FileEmitter` (JSONL), `HttpEmitter` (bounded
  queue, batched, retry, wrapped in a `CircuitBreaker`), `CompositeEmitter`
  (tees to both). The chat-service uses Composite (HTTP → ingestion + file for
  local inspection).
- **Why embedded:** logging must never add a network hop to the user's latency;
  it rides along in-process and ships telemetry asynchronously.

### 7.3 Ingestion Service (`ingestion-service`, FastAPI :8001)

**Bounded context:** the front door to the telemetry pipeline.

- **`POST /v1/logs`** accepts a batch of `LogEvent`s, authenticates via
  `x-api-key` (an **allow-list** supporting zero-downtime key rotation,
  compared with `hmac.compare_digest`), validates, and `XADD`s each onto the
  Redis stream via `RedisStreamAdapter` (approximate `MAXLEN` trim).
- Thin by design: validate, auth, enqueue. No business logic, no database.
- **Owns:** nothing persistent; it is a producer onto Redis.

### 7.4 Worker Service (`worker-service`, async CLI)

**Bounded context:** processing — the durable, exactly-once-effective heart of
the pipeline. No HTTP server.

- **`WorkerLoop`** repeatedly `XREADGROUP`s a batch (consumer group
  `log_processors`) and processes each message through the
  **`ProcessLogEvent`** use case:
  - **idempotency** — skip if already seen (in-memory cache + Postgres
    existence check) so redelivery is safe,
  - **redaction** — scrub previews via a `RedactionPipeline` of regex redactors
    (emails, credit cards, …),
  - **pricing** — recompute `cost_usd` via `CostCalculator`,
  - **persist** — write `logs.inference_logs` (+ `logs.log_errors` on errors),
  - **mirror** — buffer a row and flush to ClickHouse via
    `ClickHouseMetricsSink` (best-effort; a ClickHouse outage never rolls back
    the Postgres write).
- **Failure semantics:** successful + poison messages are `XACK`ed; **poison**
  (unparseable) messages are first routed to the **dead-letter stream**
  (`inference_logs_dlq`) with diagnostics; **transient** failures are left
  un-acked so Redis redelivers them. Idle/blocking read timeouts are tolerated.
- **Owns:** the `logs` Postgres schema (partitioned `inference_logs`) and writes
  to ClickHouse `inference_metrics`.

### 7.5 Media Service (`media-service`, library)

**Bounded context:** media extraction — imported by chat-service, run in-process
as FastAPI BackgroundTasks.

- **Document parsing** (`DocumentParser` Protocol + `ParserRegistry` strategy):
  `PdfParser` (pypdf) and `DocxParser` (python-docx), each wrapped in
  `asyncio.to_thread`.
- **Transcription** (`Transcriber` Protocol): `FasterWhisperTranscriber` (lazy
  model load; empty transcript ⇒ `TranscriptionFailed`).
- **Object storage** (`ObjectStorage` Protocol): `S3ObjectStorage` (aioboto3 /
  MinIO) + `InMemoryObjectStorage` (tests/dev).
- Produces an `ExtractedContent` value object (text + metadata) consumed by the
  chat-service's `ProcessAttachment` use case.

### 7.6 Dashboard Service (`dashboard-service`, FastAPI :8004)

**Bounded context:** analytics — read-only over ClickHouse.

- **Use cases:** latency percentiles (p50/p95/p99), throughput, error rate, cost
  by provider — each resolves a `WindowKey` (`1h`/`24h`/`7d`) to time bounds and
  delegates to a `MetricsReader` port.
- **Adapter:** `ClickHouseMetricsReader` (aiochclient) issues `quantile`,
  `count`, `countIf`, and `GROUP BY provider` queries.
- **Endpoints:** `GET /metrics/{latency,throughput,error-rate,cost}?window=…`.
- **Owns:** nothing — it only reads the worker-owned ClickHouse table.

### 7.7 UI (`ui`, React SPA)

A ChatGPT-style two-pane app: a persistent **Sidebar** (olive ring logo, a
prominent New-chat button, Dashboard, chat search, the recents list with a
per-chat `···` Delete menu) and a **main column** with a **TopBar** (provider
picker, light/dark theme toggle, account menu → log out) above the active view.

- **Routes:** `/login` (outside the shell), then a `Shell` layout route wrapping
  the home empty-state (serif greeting + composer + suggestion chips), the chat
  view (SSE streaming, cancel, `+` attach for file/voice), and the dashboard
  (Recharts + headline stats, window picker).
- **Auth:** a persisted Zustand **auth store** holds the JWT; `src/api/client.ts`
  attaches `Authorization: Bearer …` to every request and the SSE fetch, and a
  global **401 → /login** redirect handles both modes — no login needed when the
  backend runs `DISABLE_AUTH=true`, login required when it's `false`. A **prefs
  store** persists the chosen provider + theme.
- **Data layer:** TanStack Query for server state, a hand-written typed client,
  and a custom **SSE reader** (`src/api/sse.ts`) on `fetch` + `ReadableStream`
  (not `EventSource`, because the chat-service uses named events
  `started`/`chunk`/`finished`).
- **Dev:** Vite proxies `/api/chat/*` → :8000 and `/api/dashboard/*` → :8004.
  **Prod:** the UI's nginx serves the static bundle **and reverse-proxies**
  `/api/chat` + `/api/dashboard` to the backends, so the whole app is one origin
  (`:8080`).

---

## 8. How things are linked: the contracts

Services are decoupled at runtime; what binds them is a small set of explicit
contracts.

### 8.1 `LogEvent` — the shared wire model

Defined once in `shared/contracts/contracts/log_event.py` and imported by the
SDK (producer), the ingestion service (HTTP body), and the worker (stream
payload). It is `frozen`, `extra="forbid"`, and keyed by `event_id` for
idempotency. Fields: ids, `provider`, `model`, `status`, timestamps,
`latency_ms`, `ttft_ms`, token counts, truncated previews, error fields,
`raw_metadata`, `sdk_version`. Because all three services share this exact type,
a change to the contract is a single, type-checked edit.

### 8.2 HTTP contracts

- UI ⇄ Chat: REST + SSE (`text/event-stream` with named events).
- UI ⇄ Dashboard: REST (`/metrics/*`).
- Chat (SDK) → Ingestion: `POST /v1/logs` with `x-api-key`.

### 8.3 The async contract: Redis Streams

- Stream `inference_logs`, consumer group `log_processors` — the durable
  hand-off from ingestion (producer) to worker (consumer). At-least-once
  delivery; the worker makes it effectively-once via idempotency.
- Stream `inference_logs_dlq` — poison messages with diagnostics.
- Cancellation flags — chat sets/reads a per-session key the streaming loop
  polls.

### 8.4 Ports & adapters (intra-service linking)

Inside a service, the application layer depends on **ports** (Protocols), and
the interfaces layer wires concrete **adapters** at startup via FastAPI
dependency providers. That is why the same use case runs against a real Postgres
repo in production and an in-memory fake in unit tests — the link is the port,
not the implementation.

---

## 9. Data stores & ownership

Each store has exactly one owning service; no service reads another's tables
directly (the dashboard reads ClickHouse, which the worker owns — a deliberate
read-model split).

### 9.1 Postgres — `chat` schema (owned by Chat Service)

- `users` (email + bcrypt `password_hash` for login), `sessions`, `messages`
  (FK to sessions, `CASCADE`), `attachments` (FK to sessions; `kind`,
  `parse_status`, `s3_key`, `parsed_text`, `transcript`). Managed by
  chat-service's Alembic migrations.

### 9.2 Postgres — `logs` schema (owned by Worker Service)

- `inference_logs` — **range-partitioned** by `started_at`, composite PK
  `(id, started_at)`; `log_errors` for failed inferences. Managed by
  worker-service's Alembic migrations, which use a *separate*
  `alembic_version_worker` table so the two services' migration histories don't
  collide on the shared database.

### 9.3 ClickHouse — `inference_metrics` (owned by Worker, read by Dashboard)

- `MergeTree`, monthly partitions, ordered by `(provider, model, started_at,
  event_id)`, 180-day TTL. The analytics read-model. Schema in
  `clickhouse/migrations/`.

### 9.4 Redis & MinIO

- **Redis** — the `inference_logs` stream + consumer group, the DLQ stream, and
  chat cancellation flags.
- **MinIO** — `olive-attachments` bucket; blobs at
  `sessions/{id}/attachments/{aid}/{filename}`.

---

## 10. Cross-cutting concerns

All of these live in **`olive-obs`** (shared/observability) and are wired into
every runnable service with a single `install_observability(app, …)` call.

- **Structured logging.** structlog emitting JSON, with `merge_contextvars` so
  every line carries the active `request_id`, and the service name stamped on
  each event. stdlib logging is routed through the same renderer.
- **Request correlation.** A **pure-ASGI** `RequestIdMiddleware` (deliberately
  not Starlette's `BaseHTTPMiddleware`, which would buffer the body and break
  SSE) echoes/generates `X-Request-ID` and binds it into contextvars.
- **Metrics.** A pure-ASGI `PrometheusMiddleware` records
  `http_requests_total` and `http_request_duration_seconds`, labelled by the
  **route template** (not the raw path) to bound cardinality; exposed at
  `/metrics`.
- **Health.** `/health` (liveness, always 200 while up) and `/health/ready`
  (readiness — runs each registered dependency check: chat→Postgres+Redis,
  ingestion→Redis, dashboard→ClickHouse; returns 503 with a per-dependency
  breakdown on failure). These map directly to Kubernetes liveness/readiness
  probes.
- **Security.** Users: email/password accounts — `POST /auth/register` +
  `POST /auth/login` hash with **bcrypt** and mint an **HS256 JWT** (`JwtIssuer`);
  every protected route verifies the Bearer token via `get_current_user_id`
  (`JwtVerifier`). `DISABLE_AUTH=true` keeps a dev-user bypass for local/demo.
  Inter-service: an API-key **allow-list** in ingestion enabling zero-downtime
  rotation, constant-time compared.
- **Resilience.** Idempotent worker processing; dead-letter stream for poison
  messages; best-effort analytics that never rolls back the system of record;
  circuit breaker + bounded retry in the SDK's HTTP emitter; tolerant blocking
  reads in the worker.

---

## 11. Testing strategy

~446 Python test functions plus the UI suites, layered by speed and scope:

- **Unit tests** — domain logic and use cases against in-memory fakes
  (millisecond-fast, no I/O). The bulk of the suite.
- **Integration tests** — real Postgres and Redis spun up per run via
  **testcontainers** (repository adapters, the stream consumer). Skipped
  automatically when Docker isn't available.
- **End-to-end tests** (`tests/e2e/`) — exercise the wired stack: the full
  logging pipeline, worker idempotency, and the dashboard against live
  ClickHouse. Live-LLM e2e tests are gated on `ANTHROPIC_API_KEY` and skip
  without it.
- **UI** — Vitest + React Testing Library for components/hooks; **Playwright**
  for the five main flows against the running stack.
- **Load** — Locust scripts (`load/`) for the ingestion and chat hot paths.

Quality gates: `make check` runs `ruff check`, `ruff format --check`, and
`mypy --strict` across the whole workspace; `make test` runs pytest.

---

## 12. Running it locally

```bash
# 0. one-time
make install                         # uv sync the workspace
cp .env.example .env                 # then add a provider key, e.g. ANTHROPIC_API_KEY=...

# 1. infrastructure (Postgres, Redis, MinIO + ClickHouse)
make up && make up-analytics

# 2. schema
make migrate-all                     # chat + worker Postgres migrations
make migrate-clickhouse              # analytics table
#    (create the MinIO bucket 'olive-attachments' once)

# 3. app processes (chat:8000, ingestion:8001, dashboard:8004, worker, ui:5173)
scripts/dev-local.sh up
scripts/dev-local.sh status          # pids + health
```

Open **http://localhost:5173** (use `localhost` — Vite binds IPv6). Without a
provider key, everything works except the live LLM reply; the whole
logging→analytics pipeline can be exercised with a synthetic `LogEvent` posted
to ingestion.

Key Make targets: `make check` (lint+types), `make test`, `make up` / `down`,
`make migrate*`, `make worker`.

---

## 13. Deployment

Two targets, both building from the per-service multi-stage Dockerfiles in
`docker/` (uv builder → slim non-root runtime). See [DEPLOY.md](../DEPLOY.md).

- **Single host:** `docker-compose.prod.yml` — all services + infra, with
  healthchecks, resource limits, dependency-ordered startup, and one-shot
  migration jobs. Production flags (`DISABLE_AUTH=false`, a ≥32-byte
  `JWT_SECRET`, `INGESTION_API_KEYS`) come from `.env`.
- **Kubernetes / k3s:** `k8s/` is a kustomize set (namespace, ConfigMap, Secret
  template, infra StatefulSets, migration Jobs, Deployments+Services with
  liveness/readiness probes and Prometheus scrape annotations, worker exec
  probe, Ingress with SSE-safe prefix rewrite). `scripts/k3s-rollout.sh` builds,
  ships, applies, migrates, and waits; `scripts/verify-deployment.sh` runs
  post-rollout health + smoke checks.

---

## 14. How it was built — phase history

The system was built in nine phases, each strictly test-driven, each ending in a
working slice:

| Phase | Theme |
|---|---|
| 0 | Workspace, tooling, CI, compose infra |
| 1 | Chat Service skeleton: sessions, messages, Postgres |
| 2 | SSE streaming + cancellation |
| 3 | Logging SDK: Anthropic adapter, Tracker, emitters |
| 4 | Ingestion Service: HTTP intake → Redis Streams |
| 5 | Worker Service: drain, dedupe, redact, persist |
| 6 | Media: voice + document upload, parse, transcribe, context injection |
| 7 | Multi-provider (OpenAI/Gemini/DeepSeek) + ClickHouse + Dashboard |
| 8 | React UI (chat, uploads, dashboard) + Playwright |
| 9 | Hardening: structlog/request-id, Prometheus, health, JWT, API-key rotation, dead-letter, load tests, Dockerfiles, compose-prod, k8s, k3s |

A bring-up pass after Phase 9 wired the worker→ClickHouse sink end-to-end and
fixed the datetime/event-loop/redis-timeout issues that only surface when the
whole stack runs together.

---

## 15. Glossary

- **Aggregate** — a cluster of domain objects treated as one unit with a root
  (e.g. `Session` owns its `Message`s).
- **Port / Adapter** — a Protocol describing a dependency (port) and its
  concrete implementation (adapter); the seam that keeps the domain pure.
- **Bounded context** — a service-sized slice of the domain with its own model
  and data ownership.
- **`LogEvent`** — the immutable, shared telemetry record for one inference.
- **Idempotency** — processing the same `event_id` twice has no extra effect;
  what makes at-least-once delivery safe.
- **Poison message** — a stream entry that can't be parsed into a `LogEvent`;
  routed to the dead-letter queue instead of being retried forever.
- **Read model** — ClickHouse `inference_metrics`, a query-optimized projection
  of the write model (`logs.inference_logs`) the dashboard reads from.
- **SSE** — Server-Sent Events; the one-way HTTP stream used to push LLM tokens
  to the browser.

---

## 16. Reading guide for engineers

A concrete path from zero to productive in this repo. Follow it in order; it's
designed so each step builds on the last.

### 16.1 The 30-minute orientation

1. **`PRD.md` §1–4** — the *why*, the requirements, and the intended shape. It's
   the source of truth.
2. **This document §1–3** — what it is, the topology diagram, and the
   end-to-end flows.
3. Skim **§4** (principles) and **§6** (repo structure) so the folder names mean
   something.

### 16.2 The one mental model that unlocks everything

Every service is the **same four layers**, with one rule: **dependencies point
inward** (outer layers know inner ones, never the reverse).

```
 interfaces  ──►  application  ──►  domain
 (FastAPI/CLI)    (use cases +       (pure types
       │           ports)             & logic)
       └────────►  infrastructure ───┘
                   (adapters: Postgres, Redis, S3, provider SDKs)
```

- **domain/** — entities, value objects, domain services. Pure Python, no I/O.
- **application/** — `use_cases/` (orchestration) and `ports/` (Protocols that
  describe what a use case needs).
- **infrastructure/** — adapters that *implement* the ports against real tech.
- **interfaces/** — the delivery edge: FastAPI routers / the worker CLI, plus
  `dependencies.py` that wires ports to adapters.

Read one service this way and you've effectively read them all.

### 16.3 Read one vertical slice first — "send a message, get a streamed reply"

Open these in order; together they are the entire user-facing path, top to
bottom, and they demonstrate the layering:

1. `chat-service/.../interfaces/http/routers/messages.py` — `POST /chat/{id}/messages` (append the user turn).
2. `chat-service/.../interfaces/http/routers/stream.py` — `GET /chat/{id}/stream` (the SSE entry).
3. `chat-service/.../interfaces/http/dependencies.py` — how every port gets its concrete adapter (the wiring hub).
4. `chat-service/.../application/use_cases/stream_assistant_response.py` — the orchestration: an async generator yielding `StreamStarted/Chunk/Finished`, polling cancellation, persisting the message.
5. `chat-service/.../application/ports/llm_client.py` — the **port** the use case depends on (not a concrete class).
6. `chat-service/.../infrastructure/sdk/sdk_llm_client.py` — the **adapter**: maps domain types to the SDK and picks the provider's API key.
7. `logging-sdk/olive_sdk/client.py` — `LLMClient.complete`.
8. `logging-sdk/olive_sdk/infrastructure/providers/anthropic_adapter.py` — a provider call normalised into `chunk` + `usage` events.
9. `logging-sdk/olive_sdk/application/tracker.py` — builds and emits the `LogEvent` when the call finishes.
10. `chat-service/.../domain/{entities/session.py, services/context_builder.py}` — the aggregate + the context window/attachment injection.

### 16.4 Then the telemetry slice — "where the LogEvent goes"

1. `olive_sdk` Tracker → `infrastructure/emitters/http_emitter.py` → `POST /v1/logs`.
2. `ingestion-service/.../routers/logs.py` → `infrastructure/streams/redis_stream.py` (`XADD`).
3. `worker-service/.../interfaces/cli/run_worker.py` (wiring) → `application/worker_loop.py` (the drain loop).
4. `worker-service/.../use_cases/process_log_event.py` (idempotency → redact → price) → `infrastructure/persistence/postgres_log_repo.py` + `infrastructure/clickhouse/clickhouse_metrics_sink.py`.
5. `dashboard-service/.../use_cases/metric_queries.py` → `infrastructure/clickhouse/clickhouse_metrics_reader.py`.

That's the whole observability half. With §16.3 + §16.4 you've seen every moving
part of the platform.

### 16.5 "Open these first" per service

| Service | The files that define it |
|---|---|
| chat-service | `domain/entities/session.py`, `application/use_cases/stream_assistant_response.py`, `interfaces/http/dependencies.py`, `interfaces/http/routers/` |
| logging-sdk | `client.py`, `application/tracker.py`, `infrastructure/providers/base_adapter.py` |
| ingestion-service | `interfaces/http/routers/logs.py`, `infrastructure/streams/redis_stream.py` |
| worker-service | `application/worker_loop.py`, `application/use_cases/process_log_event.py`, `interfaces/cli/run_worker.py` |
| media-service | `application/use_cases/parse_document.py`, `infrastructure/transcription/faster_whisper_transcriber.py` |
| dashboard-service | `application/use_cases/metric_queries.py`, `infrastructure/clickhouse/clickhouse_metrics_reader.py` |
| ui | `src/App.tsx`, `src/features/chat/ChatView.tsx`, `src/api/client.ts`, `src/api/sse.ts` |
| shared | `contracts/log_event.py` (the wire contract), `observability/olive_obs/` |

### 16.6 How to trace any request in four hops

`router (interfaces)` → `Depends(...)` provider in `dependencies.py` →
`use case (application)` → `port` → `adapter (infrastructure)`. Domain objects
are what flow through. If you can find these four files for a request, you
understand it.

### 16.7 Conventions you'll see everywhere

- **Packages:** `olive-` prefix for shared libraries (`olive-contracts`,
  `olive-sdk`, `olive-obs`, `olive-testing`); runnable services are `<name>-service`.
- **Use cases:** a `<Verb><Noun>Handler` class with a frozen `Command`/`Result`
  dataclass and an `async def handle(...)`.
- **Ports vs adapters:** ports are `Protocol`s in `application/ports/`; adapters
  live in `infrastructure/` and are named after the technology (`PostgresX`,
  `RedisX`, `S3X`, `Bcrypt…`).
- **Config:** one `pydantic-settings` `BaseSettings` per service, env-driven;
  the running services read the repo-root `.env`.
- **Tests:** unit tests (in-memory fakes) beside the code; integration tests
  using **testcontainers** in `tests/infrastructure/`; cross-service e2e in
  `/tests/e2e/`; UI in `ui/src/**.test.tsx` + Playwright in `ui/tests-e2e/`.
- **Async everywhere**, and middleware is **pure-ASGI** (never
  `BaseHTTPMiddleware`) so SSE streaming isn't buffered.

### 16.8 Gotchas worth knowing up front

- **SSE:** the request-id / Prometheus middlewares had to be pure-ASGI — a
  buffering middleware silently breaks token streaming.
- **Worker = exactly-once-effective:** safe under at-least-once delivery via
  idempotency; unparseable messages go to the dead-letter stream; transient
  failures are left un-acked to redeliver.
- **ClickHouse** wants **naive-UTC** datetimes (a `+00:00` offset fails to parse).
- **chat & worker share one Postgres** but own different schemas and keep
  **separate Alembic version tables** so their histories don't collide.
- **`olive_obs`** lazy-imports its FastAPI helpers so the worker (which has no
  FastAPI) can still `import olive_obs` for logging.
- **Two URL layers:** browser→nginx (`/api/*`, single origin) is distinct from
  service→service (`postgres`, `ingestion-service:8001`, …); the `.env`
  host/URL values are dev-mode and are overridden in `docker-compose.prod.yml`.

### 16.9 Run it, then change something

```bash
make install                                   # uv sync the workspace
make up && make up-analytics                   # infra
make migrate-all && make migrate-clickhouse    # schema
scripts/dev-local.sh up                        # run the services + UI
make check          # ruff + mypy (must pass before committing)
make test           # pytest across the workspace
```

A good first change to prove you understand the flow: add a field to a metric
endpoint — touch the ClickHouse reader query, the use-case result dataclass, the
HTTP schema, and the React dashboard, then watch it appear end-to-end.

