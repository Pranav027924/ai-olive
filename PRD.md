# LLM Inference Logging & Ingestion Platform — Project Specification

> **This document is the source of truth.** Every decision, architecture diagram, design pattern, and build step is captured here. Read this before writing code. Update this when decisions change. The agent building this project should treat this file as persistent memory and refer to it across sessions.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Functional Requirements](#2-functional-requirements)
3. [Non-Functional Requirements](#3-non-functional-requirements)
4. [High-Level Architecture (HLD)](#4-high-level-architecture-hld)
5. [Service Boundaries & Domain Model](#5-service-boundaries--domain-model)
6. [Low-Level Architecture (LLD) per Service](#6-low-level-architecture-lld-per-service)
7. [Data Contracts](#7-data-contracts)
8. [Database Schemas](#8-database-schemas)
9. [Cross-Cutting Concerns](#9-cross-cutting-concerns)
10. [Design Patterns Catalog](#10-design-patterns-catalog)
11. [Development Best Practices](#11-development-best-practices)
12. [Test Strategy](#12-test-strategy)
13. [Sequential Build Plan](#13-sequential-build-plan)
14. [Definition of Done](#14-definition-of-done)
15. [Appendix: Tech Choices & Rationale](#15-appendix-tech-choices--rationale)

---

## 1. Project Overview

### 1.1 What we're building

A microservice-based platform consisting of:

- A **multi-modal chatbot** (text, voice, file inputs) that talks to LLM providers.
- A **lightweight SDK** that wraps every LLM call and captures inference metadata.
- An **ingestion pipeline** that receives logs in near real-time, validates and processes them.
- A **storage layer** for chat state, inference logs, and analytics.
- A **dashboard** for latency, throughput, and error metrics.

### 1.2 Why this shape

We separate the user-facing hot path (chat) from the analytics cold path (logging) so that telemetry never slows down a conversation. Each service owns one bounded context, can be deployed independently, scaled independently, and rewritten independently. Domain-Driven Design keeps the boundaries crisp and the internals testable.

### 1.3 Success criteria

A user can have a multi-turn streaming conversation with voice/text/file input. Every LLM call produces a structured log row in the database within seconds. The dashboard shows real-time p50/p95/p99 latency, throughput, and error rate per model. A single `docker compose up` brings up the full stack. Each service has its own test suite that runs in under a minute. The architecture supports adding a new LLM provider in under an hour.

---

## 2. Functional Requirements

### 2.1 Chatbot

- Multi-turn conversations with a rolling context window (last 20 messages by default, configurable).
- Streaming responses via Server-Sent Events.
- Text input (JSON body).
- Voice input (audio upload → transcription → message).
- File input (PDF, DOCX, XLSX, CSV, TXT, MD, images) — parsed and included in LLM context.
- Cancel a conversation mid-stream (partial output is preserved).
- List conversations with pagination and status filter.
- Resume a conversation (open by ID, history is rehydrated).
- Multi-provider support: OpenAI, Anthropic, Google, DeepSeek behind one interface.

### 2.2 SDK

- Single `LLMClient` interface with provider adapters.
- Captures: model, provider, latency, time-to-first-token, prompt tokens, completion tokens, status, timestamps, session ID, message ID, input/output previews (truncated), error type/message, raw provider metadata.
- Sends batched logs to ingestion endpoint asynchronously without blocking the chat path.
- Bounded in-memory queue with disk spill on overflow.
- Configurable batch size, flush interval, retry policy.

### 2.3 Ingestion

- HTTP API accepting one log or a batch.
- Schema validation (Pydantic).
- API key authentication.
- Enqueues to Redis Streams; returns 202 with ingestion IDs.
- No synchronous database writes on the hot path.

### 2.4 Worker

- Consumes from Redis Streams consumer group.
- Idempotency check on `event_id`.
- PII redaction on previews (regex baseline, pluggable NER).
- Cost computation per model.
- Transactional write to Postgres (OLTP).
- Batched insert to ClickHouse (OLAP).
- Acknowledges messages only after successful write.
- Dead-letter handling after N failed retries.

### 2.5 Dashboard

- p50/p95/p99 latency by model over time.
- Throughput per minute (requests/min).
- Error rate by status code.
- Token usage and cost by model.
- Drill down into individual failed inferences.

### 2.6 UI

- Session list pane with status badges and last-message previews.
- New conversation button.
- Text input with attachments (file picker, drag-and-drop).
- Voice recording button using browser MediaRecorder.
- Streaming token rendering with typing indicator.
- Cancel button while streaming.
- Resume conversation by clicking any session.
- Separate dashboard route for metrics.

---

## 3. Non-Functional Requirements

- **Latency:** P95 time-to-first-token under 2 seconds for streaming responses. Logging never adds more than 5 ms to the chat hot path.
- **Throughput target (demo):** 100 concurrent chat sessions; 50 logs/second sustained ingestion.
- **Availability target:** Chat plane stays available even if the ingestion plane is down — logs queue locally and replay.
- **Scalability:** Every service is stateless except where explicitly noted (Postgres, Redis, ClickHouse, MinIO are stateful). Horizontal scaling is the default.
- **Observability:** Structured logs, request IDs propagated across services, Prometheus metrics on every service, `/health` endpoint.
- **Security:** API key auth for inter-service calls, JWT for user-facing endpoints, secrets via environment variables only, no secrets in code.
- **Data retention:** Postgres keeps inference logs 90 days, then archived. ClickHouse uses TTL to drop rows older than 90 days. Chat sessions retained indefinitely unless soft-deleted.

---

## 4. High-Level Architecture (HLD)

### 4.1 Service topology

```
┌────────────────────────────────────────────────────────────────────────┐
│                              CHAT PLANE                                │
│  ┌─────────────┐         ┌─────────────────────────────────────────┐  │
│  │   React UI  │ ◀────▶  │  Chat Service  (FastAPI + SSE)          │  │
│  └─────────────┘         │  - sessions, messages, streaming        │  │
│                          │  - cancellation                          │  │
│                          └────────────┬────────────────────────────┘  │
│                                       │                                │
│                                       │ uses                           │
│                                       ▼                                │
│                          ┌──────────────────────────────┐              │
│                          │  Logging SDK (in-process)    │              │
│                          │  - provider adapters         │              │
│                          │  - metadata capture          │              │
│                          │  - async batched emitter     │              │
│                          └────────────┬─────────────────┘              │
└───────────────────────────────────────┼────────────────────────────────┘
                                        │ HTTP (batched, async)
                                        ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          INGESTION PLANE                               │
│  ┌────────────────────┐         ┌──────────────────┐                   │
│  │ Ingestion Service  │ ──XADD▶ │  Redis Streams   │                   │
│  │ (FastAPI)          │         │ inference_logs   │                   │
│  │ - auth, validate   │         └────────┬─────────┘                   │
│  └────────────────────┘                  │                             │
│                                          │ XREADGROUP                  │
│                                          ▼                             │
│                          ┌─────────────────────────────────┐           │
│                          │  Worker Service                 │           │
│                          │  - dedupe, redact, enrich       │           │
│                          │  - persist                      │           │
│                          └────────┬───────────────┬────────┘           │
└───────────────────────────────────┼───────────────┼────────────────────┘
                                    │               │
                                    ▼               ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          STORAGE PLANE                                 │
│  ┌──────────────────────┐       ┌──────────────────────────┐          │
│  │  Postgres (OLTP)     │       │  ClickHouse (OLAP)       │          │
│  │  - sessions          │       │  - inference_metrics     │          │
│  │  - messages          │       │  - dashboard queries     │          │
│  │  - attachments       │       │                          │          │
│  │  - inference_logs    │       │                          │          │
│  └──────────────────────┘       └──────────────────────────┘          │
│  ┌──────────────────────┐                                              │
│  │  MinIO (S3)          │                                              │
│  │  - voice clips       │                                              │
│  │  - uploaded files    │                                              │
│  └──────────────────────┘                                              │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                          AUXILIARY SERVICES                            │
│  ┌──────────────────────┐       ┌──────────────────────────┐          │
│  │  Media Service       │       │  Dashboard Service       │          │
│  │  - transcription     │       │  - metrics queries       │          │
│  │  - file parsing      │       │  - serves UI dashboard   │          │
│  │  (arq workers)       │       │                          │          │
│  └──────────────────────┘       └──────────────────────────┘          │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.2 End-to-end flow for a single chat turn

1. User types in the UI. The UI POSTs the message to the Chat Service.
2. Chat Service persists the user message and creates a pending assistant message.
3. Chat Service opens an SSE stream and calls the Logging SDK's `LLMClient.complete()`.
4. SDK dispatches to the right provider adapter (Anthropic/OpenAI/etc.) and starts streaming.
5. Tokens stream from provider → SDK → Chat Service → UI in near real-time.
6. The cancellation flag is checked between token batches; if set, the stream stops and partial content is saved.
7. When the stream completes, SDK builds a `LogEvent` and pushes it onto its in-process queue.
8. The async emitter batches events and POSTs them to the Ingestion Service.
9. Ingestion Service validates, XADDs to Redis Streams, returns 202.
10. Worker reads the stream, dedupes on `event_id`, redacts PII, computes cost, writes to Postgres, batches to ClickHouse, ACKs the message.
11. Dashboard reads aggregated metrics from ClickHouse.

### 4.3 Why this shape

- **Decoupling:** Chat path stays fast because logging is fire-and-forget over async HTTP.
- **Independent scaling:** Each plane scales on its own metrics — chat scales on RPS, ingestion on log volume, worker on Redis lag.
- **Fault isolation:** Ingestion or worker downtime never breaks chat.
- **Storage specialization:** OLTP for sessions, OLAP for analytics, object storage for blobs.

### 4.4 Failure modes (summary)

| Failure | Behavior |
|---|---|
| LLM provider 5xx | SDK captures error, chat returns error to UI, log row written with status=error |
| Ingestion API down | SDK retries with backoff, then spills events to local disk for replay |
| Redis down | Ingestion returns 503, SDK retries |
| Worker crashes mid-batch | Message not ACKed, Redis redelivers to another consumer, idempotency prevents duplicate row |
| Postgres down | Worker fails, message redelivered, alerts fire on lag |
| ClickHouse down | Buffer fills in worker memory, backpressure triggers, Postgres writes continue |
| User cancels | Redis flag set, stream stops, partial output persisted with status=cancelled |

---

## 5. Service Boundaries & Domain Model

We use **Domain-Driven Design**. Each service owns a bounded context with its own ubiquitous language and persistence.

### 5.1 Bounded contexts

| Service | Bounded Context | Ubiquitous Language |
|---|---|---|
| Chat Service | Conversation management | Session, Message, Attachment, Turn, Stream |
| Logging SDK | Inference observation | LogEvent, Provider, Adapter, Emitter, Tracker |
| Ingestion Service | Log intake | Payload, IngestionRecord, Stream, Acknowledgement |
| Worker Service | Log processing | LogProcessor, RedactionPipeline, CostCalculator, Idempotency |
| Media Service | Multi-modal preprocessing | Audio, Transcript, Document, Parser, ExtractedContent |
| Dashboard Service | Metrics reporting | Metric, Aggregation, TimeBucket, Percentile |

### 5.2 Per-service layering (Hexagonal / Clean Architecture)

Each service follows the same four-layer structure:

```
service/
  domain/          # Pure business logic, no I/O. Entities, value objects, domain services.
  application/    # Use cases, command/query handlers, orchestration. Depends only on domain.
  infrastructure/ # Adapters: DB, HTTP clients, message queues, external APIs.
  interfaces/     # Entry points: HTTP routers, CLI, workers. Translate to application layer.
```

Dependency rule: **outer layers depend on inner layers; never the reverse.** Domain never imports infrastructure. Application defines ports (interfaces); infrastructure provides adapters.

### 5.3 Aggregates and entities (per context)

**Chat Service:**
- `Session` (aggregate root): owns Messages, has Status, has SystemPrompt, has Provider/Model.
- `Message` (entity within Session): role, content, seq, status.
- `Attachment` (entity): kind, S3 key, parse status.

**Logging SDK:**
- `LogEvent` (value object): immutable, fully self-contained, has event_id for idempotency.

**Ingestion:**
- `IngestionRecord` (entity): receives a LogEvent, attaches ingestion_id, dispatches to stream.

**Worker:**
- `ProcessedLog` (entity): one inference log after enrichment.
- `RedactionPolicy` (domain service): pluggable strategy.

**Media:**
- `Audio` and `Document` entities, both produce `ExtractedContent` value objects.

### 5.4 Inter-service communication

- **Synchronous HTTP:** UI → Chat, SDK → Ingestion. Use when an immediate response is required.
- **Asynchronous messaging:** Ingestion → Worker via Redis Streams. Use for fire-and-forget pipelines.
- **Shared database:** Forbidden across services. Each service owns its tables. If multiple services need the same data, replicate via events.
- **Shared library:** Only `shared/contracts/` containing Pydantic schemas. No business logic, no infrastructure code.

---

## 6. Low-Level Architecture (LLD) per Service

### 6.1 Chat Service

**Layers:**

```
chat-service/
  domain/
    entities/
      session.py            # Session aggregate
      message.py            # Message entity
      attachment.py         # Attachment entity
    value_objects/
      session_status.py
      message_role.py
      model_config.py
    services/
      context_builder.py    # Builds rolling context window for LLM
    events/
      session_created.py
      message_added.py
  application/
    use_cases/
      create_session.py
      send_text_message.py
      stream_assistant_response.py
      cancel_stream.py
      list_sessions.py
      resume_session.py
    ports/
      session_repository.py    # Interface
      llm_client.py            # Interface (provided by SDK)
      cancellation_store.py    # Interface
      event_publisher.py       # Interface
  infrastructure/
    persistence/
      postgres_session_repo.py
      sqlalchemy_models.py
    cache/
      redis_cancellation_store.py
    sdk/
      sdk_llm_client.py        # Wraps the Logging SDK
    publishers/
      noop_publisher.py        # Or kafka/redis pubsub later
  interfaces/
    http/
      routers/
        sessions.py
        messages.py
        stream.py
      dependencies.py
      schemas.py               # Pydantic request/response
    main.py
```

**Key design patterns:**

- **Repository pattern** for `SessionRepository`. Domain defines the interface; infrastructure implements it.
- **Strategy pattern** for cancellation store (Redis now, could swap to in-memory for tests).
- **Adapter pattern** for the LLM client (wraps the SDK so the application layer doesn't know about HTTP/providers).
- **CQRS-lite:** Commands (`SendTextMessage`) and queries (`ListSessions`) are separate use case classes.
- **Domain events:** `SessionCreated`, `MessageAdded` are published in-process. A publisher port allows external broadcasting later.

**Flow for `POST /chat/{id}/messages`:**

```
HTTP router → SendTextMessageHandler (application) →
  SessionRepository.get(id) → Session.add_user_message() →
  SessionRepository.save(session) → returns message_id
```

**Flow for `GET /chat/{id}/stream`:**

```
HTTP router → StreamAssistantResponseHandler (application) →
  SessionRepository.get(id) → ContextBuilder.build(session) →
  LLMClient.complete(context) → for each token:
    check CancellationStore.is_cancelled(id) →
    yield token to SSE →
  on completion or cancel: Session.add_assistant_message() →
  SessionRepository.save(session)
```

### 6.2 Logging SDK

**Structure:**

```
logging-sdk/
  domain/
    entities/
      log_event.py            # Pydantic, immutable, has event_id
    value_objects/
      provider.py             # Enum
      status.py               # Enum
    services/
      cost_calculator.py      # Domain logic, no I/O
  application/
    tracker.py                # Context manager that builds LogEvent
    emitter_port.py           # Interface
  infrastructure/
    providers/
      base_adapter.py
      anthropic_adapter.py
      openai_adapter.py
      gemini_adapter.py
      deepseek_adapter.py
    emitters/
      http_emitter.py         # Batched async HTTP
      file_emitter.py         # For local dev/testing
      composite_emitter.py    # Tee to multiple
    storage/
      disk_spill.py           # Overflow handling
  client.py                   # Public API: LLMClient
```

**Key design patterns:**

- **Adapter pattern** for providers — each adapter normalizes a provider's API into a uniform async generator yielding `chunk` and `usage` events.
- **Strategy pattern** for emitters — `HTTPEmitter`, `FileEmitter`, `CompositeEmitter` all implement `EmitterPort`.
- **Context manager** (`Tracker`) wraps the LLM call and guarantees a LogEvent is built on every path (success, error, cancel).
- **Producer-consumer** with a bounded `asyncio.Queue` between the synchronous call site and the async HTTP flush task.
- **Circuit breaker** around HTTP emission — after N consecutive failures, open the breaker and spill to disk until a probe succeeds.

**Public API:**

```python
client = LLMClient(provider="anthropic", model="claude-opus-4-7", emitter=HTTPEmitter(...))

async for token in client.complete(session_id, message_id, messages):
    yield token
# LogEvent emitted automatically on exit
```

### 6.3 Ingestion Service

**Structure:**

```
ingestion-service/
  domain/
    entities/
      ingestion_record.py
    services/
      validator.py            # Schema + business rule validation
  application/
    use_cases/
      ingest_logs.py
    ports/
      log_stream.py           # Interface
      auth_provider.py        # Interface
  infrastructure/
    streams/
      redis_stream.py         # Implements LogStream
    auth/
      api_key_auth.py
  interfaces/
    http/
      routers/
        logs.py
      schemas.py              # Reuses shared/contracts/log_event.py
    main.py
```

**Key design patterns:**

- **Port-Adapter:** `LogStream` is a port; `RedisStreamAdapter` is one implementation. Could swap to Kafka by writing a new adapter.
- **Pipeline:** validate → authenticate → enqueue. Each step is a small function with one responsibility.

### 6.4 Worker Service

**Structure:**

```
worker-service/
  domain/
    entities/
      processed_log.py
    services/
      redaction_pipeline.py    # Chain of redactors
      cost_calculator.py
      idempotency_checker.py
  application/
    use_cases/
      process_log_event.py
    ports/
      log_repository.py
      metrics_writer.py
      stream_consumer.py
  infrastructure/
    persistence/
      postgres_log_repo.py
    analytics/
      clickhouse_metrics_writer.py
    streams/
      redis_stream_consumer.py
    redaction/
      regex_redactor.py
      ner_redactor.py          # Optional, opt-in
  interfaces/
    cli/
      run_worker.py            # Long-running process entry point
```

**Key design patterns:**

- **Chain of responsibility** for the redaction pipeline — each redactor processes text and passes to the next.
- **Strategy pattern** for cost calculation per provider/model (table-driven).
- **Repository pattern** for log persistence.
- **Saga / transactional outbox alternative:** since we write to two stores (Postgres and ClickHouse), we use Postgres as the source of truth and treat ClickHouse as a derived projection. If ClickHouse write fails, the row in Postgres is still authoritative and a backfill job can rebuild ClickHouse.
- **At-least-once delivery + idempotency key:** the consumer group plus the `event_id` uniqueness constraint give us exactly-once *effective* semantics.

**Processing pipeline:**

```
XREADGROUP → parse LogEvent →
  IdempotencyChecker.exists(event_id)? → skip
  RedactionPipeline.redact(event.input_preview, event.output_preview)
  CostCalculator.compute(event)
  Postgres tx: insert log → insert error if any
  ClickHouseBuffer.append(metric_row)
  XACK
```

### 6.5 Media Service

**Structure:**

```
media-service/
  domain/
    entities/
      audio.py
      document.py
    value_objects/
      extracted_content.py
    services/
      transcriber.py            # Port
      document_parser.py        # Port
  application/
    use_cases/
      transcribe_audio.py
      parse_document.py
  infrastructure/
    transcription/
      whisper_transcriber.py
    parsing/
      pdf_parser.py
      docx_parser.py
      xlsx_parser.py
      image_describer.py
    storage/
      s3_storage.py
  interfaces/
    workers/
      arq_tasks.py
    http/
      routers/
        upload.py
```

**Key design patterns:**

- **Strategy pattern** with a parser registry keyed by MIME type.
- **Factory** for transcriber selection (local Whisper vs OpenAI API).
- **Pipeline:** upload → validate MIME → store → enqueue parse job → notify on completion.

### 6.6 Dashboard Service

**Structure:**

```
dashboard-service/
  domain/
    value_objects/
      time_range.py
      percentile.py
    services/
      metric_query.py
  application/
    use_cases/
      get_latency_percentiles.py
      get_throughput.py
      get_error_rate.py
      get_cost_summary.py
    ports/
      metrics_reader.py
  infrastructure/
    analytics/
      clickhouse_reader.py
  interfaces/
    http/
      routers/
        metrics.py
      schemas.py
    main.py
```

Read-only service. No writes. All queries go to ClickHouse.

---

## 7. Data Contracts

### 7.1 `LogEvent` (shared)

```python
# shared/contracts/log_event.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

class LogEvent(BaseModel):
    event_id: UUID                          # idempotency key
    session_id: UUID
    message_id: Optional[UUID]
    provider: Literal["openai", "anthropic", "gemini", "deepseek"]
    model: str
    status: Literal["success", "error", "cancelled", "timeout"]
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    ttft_ms: Optional[int]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    input_preview: str = Field(max_length=500)
    output_preview: str = Field(max_length=500)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    http_status: Optional[int] = None
    raw_metadata: dict = Field(default_factory=dict)
    sdk_version: str
```

### 7.2 Inter-service HTTP contracts

- **Chat Service** exposes: `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`, `PATCH /sessions/{id}`, `DELETE /sessions/{id}`, `POST /chat/{id}/messages`, `GET /chat/{id}/stream`, `POST /chat/{id}/cancel`, `POST /chat/{id}/files`, `POST /chat/{id}/voice`.
- **Ingestion Service** exposes: `POST /v1/logs` (auth: `x-api-key`).
- **Dashboard Service** exposes: `GET /metrics/latency`, `GET /metrics/throughput`, `GET /metrics/errors`, `GET /metrics/cost`.
- **All services** expose: `GET /health`, `GET /metrics` (Prometheus).

All requests and responses are typed with Pydantic. Errors return RFC 7807 problem details.

### 7.3 Async contract: Redis Streams

- Stream name: `inference_logs`
- Consumer group: `log_processors`
- Message fields: `event` (JSON-serialized LogEvent), `ingestion_id` (UUID)
- MAXLEN ~ 1_000_000 (approximate)

---

## 8. Database Schemas

### 8.1 Postgres (owned by Chat Service for sessions/messages; owned by Worker Service for inference_logs)

> Note on ownership: in a strict microservice setup these would be two separate Postgres databases. For the demo we use one Postgres instance with separate schemas (`chat`, `logs`) to make local dev practical. Production deployment can split them.

```sql
-- Schema: chat
CREATE TABLE chat.users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat.sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES chat.users(id),
    title TEXT,
    system_prompt TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active','cancelled','completed','archived','deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON chat.sessions (user_id, updated_at DESC) WHERE status != 'deleted';

CREATE TABLE chat.messages (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat.sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content TEXT NOT NULL,
    seq INT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','complete','cancelled','error')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, seq)
);
CREATE INDEX ON chat.messages (session_id, seq);

CREATE TABLE chat.attachments (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat.sessions(id) ON DELETE CASCADE,
    message_id UUID REFERENCES chat.messages(id),
    kind TEXT NOT NULL CHECK (kind IN ('file','audio','image')),
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    s3_key TEXT NOT NULL,
    parse_status TEXT NOT NULL CHECK (parse_status IN ('pending','complete','failed')),
    parsed_text TEXT,
    transcript TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Schema: logs
CREATE TABLE logs.inference_logs (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    message_id UUID,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    latency_ms INT NOT NULL,
    ttft_ms INT,
    prompt_tokens INT,
    completion_tokens INT,
    input_preview TEXT,
    output_preview TEXT,
    cost_usd NUMERIC(12,6),
    raw_metadata JSONB,
    sdk_version TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
) PARTITION BY RANGE (started_at);

CREATE INDEX ON logs.inference_logs (session_id, started_at DESC);
CREATE INDEX ON logs.inference_logs (model, started_at DESC);
CREATE INDEX ON logs.inference_logs (status, started_at DESC) WHERE status != 'success';

CREATE TABLE logs.log_errors (
    id UUID PRIMARY KEY,
    log_id UUID NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT,
    http_status INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 8.2 ClickHouse (owned by Worker, read by Dashboard)

```sql
CREATE TABLE inference_metrics (
    started_at DateTime,
    provider LowCardinality(String),
    model LowCardinality(String),
    status LowCardinality(String),
    latency_ms UInt32,
    ttft_ms Nullable(UInt32),
    prompt_tokens UInt32,
    completion_tokens UInt32,
    cost_usd Float32,
    session_id UUID
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(started_at)
ORDER BY (provider, model, started_at)
TTL started_at + INTERVAL 90 DAY;
```

### 8.3 Schema design tradeoffs

- **JSONB for `raw_metadata`** — provider-specific fields that we don't query on directly (finish_reason, system_fingerprint, tool_calls). Lets the schema evolve without migrations.
- **First-class columns for queryables** — provider, model, status, latency are columns (indexed), not nested in JSONB.
- **`log_errors` separate from `inference_logs`** — keeps the hot table narrow; errors are minority of rows.
- **Monthly partitions on `inference_logs`** — easy archival, fast pruning of old partitions.
- **ClickHouse `LowCardinality`** — dictionary encoding for provider/model/status, huge speedup on group-by.
- **`ORDER BY (provider, model, started_at)`** — matches the dashboard's primary query shape.
- **`message_id` nullable on `inference_logs`** — a call that errors before any message is created still produces a log.

---

## 9. Cross-Cutting Concerns

### 9.1 Configuration

Pydantic `BaseSettings` per service, reading from environment variables. A `.env.example` at the root and per service. Never commit real secrets. Production deployment uses Kubernetes Secrets.

### 9.2 Logging

`structlog` everywhere. Every log line has: `service`, `request_id`, `session_id` (when known), `user_id` (when known), `event`, plus event-specific fields. JSON output in production, console in dev.

### 9.3 Tracing and request IDs

Every inbound request gets a `request_id` (from `X-Request-Id` header or generated). It's propagated to all downstream HTTP calls and included in every log line and every emitted event.

### 9.4 Metrics

Prometheus `/metrics` on every service. Standard counters: requests_total, errors_total, request_duration_seconds histogram. Service-specific: `chat_active_streams`, `sdk_emitter_queue_size`, `worker_lag_messages`, `ingestion_xadd_failures_total`.

### 9.5 Authentication

- User-facing endpoints: JWT in `Authorization: Bearer ...`.
- Inter-service: API key in `x-api-key` header.
- No password handling; for the demo, JWTs are minted via a stub `/auth/login` endpoint that takes an email. Real OIDC integration is left as a future task.

### 9.6 Error handling

- RFC 7807 problem details for all HTTP errors.
- Never leak stack traces to clients.
- Every exception path is logged with full context.
- Domain exceptions are distinct types: `SessionNotFound`, `InvalidProvider`, etc.

### 9.7 Concurrency model

Async I/O end to end. SQLAlchemy 2.x async. httpx async. asyncio for the SDK queue. arq for background tasks. Never call blocking code from a handler.

---

## 10. Design Patterns Catalog

This is the canonical list of patterns we use. When in doubt, pick from this list rather than inventing a new pattern.

### 10.1 Structural

- **Hexagonal / Ports & Adapters** — every service has a domain core with ports (interfaces); infrastructure provides adapters.
- **Repository** — `SessionRepository`, `LogRepository`. Domain defines, infrastructure implements.
- **Adapter** — provider adapters in the SDK, MIME-keyed parsers in Media Service.
- **Aggregate Root** — `Session` is the only entry point for modifying its messages.
- **Value Object** — `LogEvent`, `ExtractedContent`, `TimeRange`. Immutable, equality by value.

### 10.2 Behavioral

- **Strategy** — cancellation store (Redis vs in-memory), emitters (HTTP vs file), redactors (regex vs NER).
- **Chain of Responsibility** — redaction pipeline.
- **Command / Query (CQRS-lite)** — commands and queries are separate use cases; no shared "service" classes.
- **Observer / Domain Events** — `SessionCreated`, `MessageAdded` published in-process; can wire to external bus later.
- **Template Method** — base provider adapter defines the call lifecycle; subclasses fill in provider specifics.

### 10.3 Concurrency

- **Producer-Consumer** — SDK queue, Redis Streams between Ingestion and Worker.
- **Circuit Breaker** — SDK HTTP emitter, downstream provider calls.
- **Bulkhead** — separate connection pools per external dependency so one slow service doesn't exhaust resources for others.
- **Backpressure** — bounded queue in SDK; if full, spill to disk rather than drop or OOM.

### 10.4 Reliability

- **Idempotency Key** — `event_id` on every LogEvent.
- **At-least-once + dedupe** — Redis Streams + idempotency check = effective exactly-once.
- **Dead-letter queue** — failed events after N retries land on `inference_logs_dlq` stream.
- **Outbox pattern (lite)** — Postgres is source of truth; ClickHouse is a derived projection rebuildable from Postgres.

### 10.5 Anti-patterns to avoid

- Shared database across services.
- Domain layer importing from infrastructure.
- Synchronous chains of microservice calls (build async messaging instead).
- "God services" that own multiple bounded contexts.
- Business logic in HTTP routers or DB models.

---

## 11. Development Best Practices

### 11.1 Code style

- Python 3.11+.
- `ruff` for linting and formatting.
- `mypy --strict` for type checking. Type hints on every public function.
- No bare `except:`. No `print()`. No commented-out code in PRs.
- Docstrings on public modules, classes, and non-trivial functions.

### 11.2 Project layout

- Monorepo. Each service is a Python package with its own `pyproject.toml`.
- Shared code lives in `shared/contracts/` (Pydantic models only) and `shared/testing/` (test fixtures).
- No service imports from another service. They only import from `shared/`.

### 11.3 Dependency management

- `uv` or `poetry` (pick one and stick with it; recommendation: `uv` for speed).
- Pin major versions in `pyproject.toml`, exact versions in `uv.lock`.
- Renovate or Dependabot for updates.

### 11.4 Commits

- **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`).
- **Small commits.** Each commit compiles, passes tests, and represents one logical change.
- **Atomic.** Don't mix feature work and refactors in the same commit.
- Reference the build-plan step in the commit body (e.g. `Refs: Phase 1.2`).

### 11.5 Branching and PRs

- Trunk-based development. Short-lived feature branches (< 2 days).
- PRs are small (< 400 lines diff when possible). One reviewer minimum.
- CI runs on every push: lint, type-check, unit tests, integration tests for the changed service.
- Merge only when green.

### 11.6 Documentation

- Every service has a `README.md` with: purpose, endpoints, env vars, how to run locally, how to test.
- Architecture decisions go in `docs/adr/NNNN-title.md` (ADR format).
- This `PROJECT_SPEC.md` is updated when an ADR changes any major decision.

### 11.7 Definition of Ready (before starting work)

- Acceptance criteria are written.
- Affected ports/adapters are identified.
- Test cases are listed.
- The build-plan step is identified.

---

## 12. Test Strategy

We do **Test-Driven Development**. Write the failing test first, then the minimal code to pass it, then refactor.

### 12.1 The test pyramid

```
            ╱─────╲
           ╱ E2E   ╲              ← few, slow, broad
          ╱─────────╲
         ╱ Contract ╲             ← inter-service contracts
        ╱─────────────╲
       ╱  Integration  ╲          ← service + its real DB
      ╱─────────────────╲
     ╱      Unit          ╲       ← many, fast, isolated
    ────────────────────────
```

### 12.2 Unit tests

- **Scope:** domain entities, value objects, domain services, use cases (with mocked ports).
- **Speed:** millisecond-fast. No I/O. No network.
- **Tool:** `pytest` + `pytest-asyncio` for async code.
- **Coverage target:** 90%+ on domain and application layers.
- **Naming:** `test_<unit>_<behavior>_<expected>`. Example: `test_session_add_user_message_increments_seq`.

### 12.3 Integration tests

- **Scope:** infrastructure adapters against real dependencies (Postgres, Redis, ClickHouse, MinIO).
- **Tool:** `testcontainers-python` to spin up real containers per test session.
- **Speed:** seconds. Tens of tests per service, not hundreds.
- **What to test:** repository CRUD, stream produce/consume, S3 upload/download, idempotency under concurrent inserts.

### 12.4 Contract tests

- **Scope:** verify the wire format between services matches `shared/contracts/`.
- **Tool:** Pydantic round-trip + golden fixtures. Optionally `schemathesis` against OpenAPI.
- **Goal:** if the SDK builds a `LogEvent` and the Ingestion Service parses one, they agree on the schema.

### 12.5 End-to-end tests

- **Scope:** full stack via `docker compose`. One happy-path test per major user flow.
- **Tool:** `pytest` + `httpx` against the running compose stack, plus a thin Playwright suite for the UI.
- **Flows covered:**
  1. Create session → send text → stream response → verify log row appears in Postgres.
  2. Upload audio → wait for transcript → send → stream response → log row.
  3. Upload file → send referencing file → stream response → log row.
  4. Start stream → cancel → verify status=cancelled and partial output saved.
  5. List sessions → resume by ID → continue conversation.

### 12.6 TDD discipline

For every feature:

1. Write the failing test (red).
2. Write the minimum code to pass (green).
3. Refactor while keeping tests green (refactor).
4. Commit.

Tests are written **before** the code they verify. PRs without tests fail review.

### 12.7 Test data

- Factory pattern with `factory-boy` or hand-rolled factories.
- Never share fixture state between tests. Each test creates what it needs.
- Database is reset between integration tests via transactional rollback.

### 12.8 Performance / load tests

- `locust` scripts in `tests/load/`.
- Run before each release: 100 concurrent chat streams, 50 logs/sec sustained, 5-minute window.
- Track p50/p95/p99 of TTFT and ingestion latency. Fail the build if regressions exceed threshold.

---

## 13. Sequential Build Plan

The build is split into 9 phases. **Do not start phase N+1 until phase N is fully complete: all tests pass, all definition-of-done items checked.**

Each phase has steps. Each step is one TDD cycle (or a small batch of them) and one commit. Don't batch steps.

---

### Phase 0 — Foundations (Days 0–1)

**Goal:** repo, tooling, shared contracts, local infrastructure all running. Nothing functional yet.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 0.1 | Initialize monorepo, root `Makefile`, `.gitignore`, `.editorconfig`, `pyproject.toml` workspace | n/a | `chore: scaffold monorepo` |
| 0.2 | Add `ruff`, `mypy`, `pre-commit` config | n/a | `chore: add lint and type-check tooling` |
| 0.3 | Add `docker-compose.yml` with Postgres, Redis, MinIO; `make up` and `make down` | n/a | `chore: local infra via docker compose` |
| 0.4 | Create `shared/contracts/log_event.py` with `LogEvent` Pydantic model | yes | `feat(contracts): add LogEvent schema` |
| 0.5 | Tests for LogEvent: required fields, optional fields, validation errors | yes | `test(contracts): cover LogEvent validation` |
| 0.6 | Add CI workflow: lint + type-check + tests on push | n/a | `chore(ci): add CI workflow` |

**Definition of done:** `make test` runs the LogEvent tests and they pass. CI is green. `docker compose up` brings up Postgres/Redis/MinIO and they're reachable.

---

### Phase 1 — Chat Service: blocking version (Days 2–5)

**Goal:** a working chatbot with session and message management, calling one LLM provider directly. No streaming, no logging, no SDK yet.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 1.1 | Scaffold `chat-service/` with hexagonal layout | n/a | `feat(chat): scaffold service layout` |
| 1.2 | Domain: `Session` aggregate, `Message` entity, value objects, invariants | yes | `feat(chat-domain): add Session aggregate` |
| 1.3 | Tests for Session: create, add message, status transitions, invariants | yes | `test(chat-domain): cover Session behavior` |
| 1.4 | Application: `CreateSession`, `ListSessions`, `SendTextMessage` use cases with mocked ports | yes | `feat(chat-app): add session use cases` |
| 1.5 | Tests for use cases: happy path, not-found, validation errors | yes | `test(chat-app): cover session use cases` |
| 1.6 | Infrastructure: `PostgresSessionRepository` + Alembic migration for `chat.sessions`, `chat.messages` | yes | `feat(chat-infra): postgres session repo + migrations` |
| 1.7 | Integration tests for the repo using testcontainers Postgres | yes | `test(chat-infra): integration tests for session repo` |
| 1.8 | Infrastructure: direct LLM client (single provider, no SDK yet) | yes | `feat(chat-infra): direct LLM client` |
| 1.9 | Interfaces: HTTP routers for sessions and messages (blocking, returns full response) | yes | `feat(chat-http): session and message endpoints` |
| 1.10 | HTTP tests against the running app (TestClient) | yes | `test(chat-http): cover session and message endpoints` |
| 1.11 | E2E test: create session, send message, get response | yes | `test(e2e): chat happy path` |

**Definition of done:** you can `curl POST /sessions` then `curl POST /chat/{id}/messages` and get an assistant reply back. All tests pass.

---

### Phase 2 — Streaming and cancellation (Days 6–7)

**Goal:** replace blocking response with SSE. Add cancellation.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 2.1 | Domain: `StreamingResponse` value object with cancellation invariants | yes | `feat(chat-domain): streaming response value object` |
| 2.2 | Application: `StreamAssistantResponse` use case | yes | `feat(chat-app): streaming use case` |
| 2.3 | Tests for streaming use case with mocked LLM client (yields tokens) | yes | `test(chat-app): cover streaming use case` |
| 2.4 | Infrastructure: streaming LLM client (real provider, async generator) | yes | `feat(chat-infra): streaming LLM client` |
| 2.5 | Application: `CancelStream` use case + `CancellationStore` port | yes | `feat(chat-app): cancellation use case` |
| 2.6 | Infrastructure: `RedisCancellationStore` | yes | `feat(chat-infra): redis cancellation store` |
| 2.7 | Interfaces: SSE endpoint for streaming, cancel endpoint | yes | `feat(chat-http): SSE streaming + cancel` |
| 2.8 | E2E: stream a response token-by-token; e2e cancel mid-stream | yes | `test(e2e): streaming and cancellation` |

**Definition of done:** tokens stream in real time; cancellation flips status and saves partial output. Integration tests verify both paths.

---

### Phase 3 — Logging SDK with file emitter (Days 8–10)

**Goal:** SDK wraps LLM calls and writes `LogEvent`s to a local JSONL file. Chat Service uses the SDK instead of its direct LLM client.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 3.1 | Scaffold `logging-sdk/` with layered layout | n/a | `feat(sdk): scaffold sdk package` |
| 3.2 | Domain: `LogEvent` already in shared; add `CostCalculator` domain service | yes | `feat(sdk-domain): cost calculator` |
| 3.3 | Tests for CostCalculator: known models, unknown model fallback | yes | `test(sdk-domain): cover cost calculator` |
| 3.4 | Infrastructure: base `ProviderAdapter`, first concrete adapter (Anthropic or OpenAI) | yes | `feat(sdk-infra): first provider adapter` |
| 3.5 | Tests for adapter using a fake provider HTTP server | yes | `test(sdk-infra): adapter integration tests` |
| 3.6 | Application: `Tracker` context manager that builds a LogEvent | yes | `feat(sdk-app): tracker context manager` |
| 3.7 | Tests for Tracker: success, error, cancel paths all build a LogEvent | yes | `test(sdk-app): cover tracker paths` |
| 3.8 | Infrastructure: `FileEmitter` writing JSONL | yes | `feat(sdk-infra): file emitter` |
| 3.9 | Public API: `LLMClient` class | yes | `feat(sdk): LLMClient public API` |
| 3.10 | Wire SDK into Chat Service via `SdkLlmClient` adapter; remove direct LLM client | yes | `refactor(chat): use logging SDK` |
| 3.11 | E2E: send a message, verify a LogEvent line appears in the JSONL file | yes | `test(e2e): SDK file emitter` |

**Definition of done:** every chat turn produces one LogEvent in the JSONL file with all metadata populated. Chat behavior is unchanged.

---

### Phase 4 — Ingestion Service (Days 11–13)

**Goal:** SDK ships logs over HTTP to a real ingestion service; events land in Redis Streams.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 4.1 | Scaffold `ingestion-service/` | n/a | `feat(ingestion): scaffold service` |
| 4.2 | Domain + application: `IngestLogs` use case, `LogStream` port, validator | yes | `feat(ingestion-app): ingest use case` |
| 4.3 | Tests for use case with in-memory stream port | yes | `test(ingestion-app): cover ingest use case` |
| 4.4 | Infrastructure: `RedisStreamAdapter` implementing `LogStream` | yes | `feat(ingestion-infra): redis stream adapter` |
| 4.5 | Integration tests against testcontainers Redis | yes | `test(ingestion-infra): cover redis adapter` |
| 4.6 | Interfaces: `POST /v1/logs` with API key auth | yes | `feat(ingestion-http): logs endpoint` |
| 4.7 | HTTP tests: 202 on valid batch, 401 on bad key, 422 on bad payload | yes | `test(ingestion-http): cover logs endpoint` |
| 4.8 | SDK: `HttpEmitter` with bounded queue, batching, retry, backoff | yes | `feat(sdk-infra): HTTP emitter` |
| 4.9 | SDK: `CompositeEmitter` (tee to HTTP + file) and circuit breaker | yes | `feat(sdk-infra): composite emitter and breaker` |
| 4.10 | Wire HTTP emitter into Chat Service config | yes | `feat(chat): use HTTP emitter` |
| 4.11 | E2E: send chat → events appear in Redis Stream | yes | `test(e2e): SDK → ingestion → redis` |

**Definition of done:** XLEN on `inference_logs` increases after each chat turn. Chat path latency unchanged. SDK falls back to file when ingestion is unreachable.

---

### Phase 5 — Worker Service + Postgres persistence (Days 14–16)

**Goal:** events are consumed from Redis Streams, processed, and written to Postgres.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 5.1 | Scaffold `worker-service/`; migration for `logs.inference_logs` + `logs.log_errors` | n/a | `feat(worker): scaffold + migrations` |
| 5.2 | Domain: `ProcessedLog`, `RedactionPipeline`, `IdempotencyChecker` | yes | `feat(worker-domain): processing domain` |
| 5.3 | Tests for redaction pipeline (regex emails/phones/cc) | yes | `test(worker-domain): cover redactors` |
| 5.4 | Application: `ProcessLogEvent` use case with mocked ports | yes | `feat(worker-app): process log use case` |
| 5.5 | Tests: happy path, duplicate event_id (skip), error event creates log_error | yes | `test(worker-app): cover use case paths` |
| 5.6 | Infrastructure: `PostgresLogRepository` | yes | `feat(worker-infra): postgres log repo` |
| 5.7 | Integration tests against Postgres | yes | `test(worker-infra): cover log repo` |
| 5.8 | Infrastructure: Redis Streams consumer with consumer group | yes | `feat(worker-infra): redis stream consumer` |
| 5.9 | Integration tests: produce + consume + ack | yes | `test(worker-infra): cover consumer` |
| 5.10 | Interfaces: `run_worker` CLI entry point with graceful shutdown | yes | `feat(worker-cli): worker entrypoint` |
| 5.11 | Idempotency test: deliver same event twice, exactly one row | yes | `test(e2e): worker idempotency` |
| 5.12 | E2E: chat → SDK → ingestion → worker → Postgres row visible | yes | `test(e2e): full logging pipeline` |

**Definition of done:** every chat turn produces a row in `logs.inference_logs` within seconds. Worker handles duplicate delivery without creating duplicate rows.

---

### Phase 6 — Multimodal: voice and files (Days 17–20)

**Goal:** Media Service handles voice transcription and file parsing. Chat Service includes parsed content in LLM context.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 6.1 | Scaffold `media-service/`; add MinIO client, attachments migration | n/a | `feat(media): scaffold + attachments table` |
| 6.2 | Domain: `Audio`, `Document`, `ExtractedContent` | yes | `feat(media-domain): domain types` |
| 6.3 | Application: `ParseDocument` use case with MIME-keyed parser registry | yes | `feat(media-app): parse document use case` |
| 6.4 | Tests with sample PDF, DOCX, XLSX, image fixtures | yes | `test(media-app): cover parsers` |
| 6.5 | Application: `TranscribeAudio` use case | yes | `feat(media-app): transcribe audio use case` |
| 6.6 | Tests with sample audio (faster-whisper offline) | yes | `test(media-app): cover transcriber` |
| 6.7 | Infrastructure: S3 storage adapter, arq tasks | yes | `feat(media-infra): s3 + arq tasks` |
| 6.8 | Interfaces: `POST /chat/{id}/files`, `POST /chat/{id}/voice` on Chat Service that delegates to Media | yes | `feat(chat-http): file and voice endpoints` |
| 6.9 | Domain: `ContextBuilder` now includes parsed attachments | yes | `feat(chat-domain): context with attachments` |
| 6.10 | E2E: upload PDF → ask about it → response references content | yes | `test(e2e): file in conversation` |
| 6.11 | E2E: upload audio → transcript appears → reply generated | yes | `test(e2e): voice in conversation` |

**Definition of done:** voice and file inputs both work end-to-end and are reflected in the LLM response. Background workers process media without blocking the chat path.

---

### Phase 7 — Multi-provider + Dashboard (Days 21–23)

**Goal:** support multiple providers via config; add ClickHouse + Dashboard Service.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 7.1 | Add adapters for the remaining providers (OpenAI/Gemini/DeepSeek) | yes | `feat(sdk-infra): additional provider adapters` |
| 7.2 | Tests for each adapter against fake servers | yes | `test(sdk-infra): cover all adapters` |
| 7.3 | Chat Service: provider/model selectable per session | yes | `feat(chat): per-session provider/model` |
| 7.4 | Add ClickHouse to compose; migration for `inference_metrics` | n/a | `chore(infra): clickhouse + schema` |
| 7.5 | Worker: ClickHouse buffered writer with periodic flush | yes | `feat(worker-infra): clickhouse buffer writer` |
| 7.6 | Tests: rows appear in CH after flush; failure leaves Postgres intact | yes | `test(worker-infra): cover clickhouse path` |
| 7.7 | Scaffold `dashboard-service/` | n/a | `feat(dashboard): scaffold service` |
| 7.8 | Application: latency-percentiles, throughput, error-rate, cost use cases | yes | `feat(dashboard-app): metric use cases` |
| 7.9 | Tests with fake metrics reader | yes | `test(dashboard-app): cover metric use cases` |
| 7.10 | Infrastructure: ClickHouse reader | yes | `feat(dashboard-infra): clickhouse reader` |
| 7.11 | Interfaces: `/metrics/*` HTTP endpoints | yes | `feat(dashboard-http): metric endpoints` |
| 7.12 | E2E: generate load → dashboard endpoints return correct shapes | yes | `test(e2e): dashboard end-to-end` |

**Definition of done:** dashboard returns real numbers for at least three metrics. Switching providers on a new session works without code changes.

---

### Phase 8 — UI (Days 24–27)

**Goal:** React UI for chat, conversation list, cancellation, dashboard.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 8.1 | Scaffold `ui/` (Vite + React + TS + Tailwind) | n/a | `feat(ui): scaffold app` |
| 8.2 | API client with typed methods generated from OpenAPI | yes | `feat(ui): typed API client` |
| 8.3 | Session list view; component tests | yes | `feat(ui): session list` |
| 8.4 | Chat view with SSE token streaming | yes | `feat(ui): chat view with streaming` |
| 8.5 | Cancel button wired to cancel endpoint | yes | `feat(ui): cancel control` |
| 8.6 | File upload via drag-drop + file picker | yes | `feat(ui): file uploads` |
| 8.7 | Voice recorder using MediaRecorder; show transcription status | yes | `feat(ui): voice input` |
| 8.8 | Dashboard route with charts (Recharts) | yes | `feat(ui): dashboard view` |
| 8.9 | Playwright tests for the five flows in 12.5 | yes | `test(e2e-ui): cover main flows` |

**Definition of done:** full UI demo of every feature. Playwright suite passes against the running compose stack.

---

### Phase 9 — Hardening and deployment (Days 28–30)

**Goal:** make it deployable, observable, secure.

| # | Step | Test first? | Commit message |
|---|---|---|---|
| 9.1 | structlog config + request_id middleware in every service | yes | `feat(obs): structured logging + request ids` |
| 9.2 | Prometheus `/metrics` on every service | yes | `feat(obs): prometheus metrics` |
| 9.3 | `/health` endpoints checking all dependencies | yes | `feat(obs): health endpoints` |
| 9.4 | JWT auth on Chat Service endpoints | yes | `feat(auth): JWT on user endpoints` |
| 9.5 | API key rotation support in Ingestion | yes | `feat(auth): api key rotation` |
| 9.6 | Dead-letter stream for poison messages | yes | `feat(worker): dead-letter handling` |
| 9.7 | Load test scripts (locust) for chat + ingestion | n/a | `test(load): chat and ingestion scripts` |
| 9.8 | Dockerfile per service; multi-stage builds | n/a | `chore(infra): production dockerfiles` |
| 9.9 | docker-compose.prod.yml with healthchecks + resource limits | n/a | `chore(infra): compose prod config` |
| 9.10 | Kubernetes manifests (Deployment, Service, Ingress, ConfigMap, Secret) | n/a | `chore(infra): k8s manifests` |
| 9.11 | Deploy to a k3s cluster; verify all flows | n/a | `chore(deploy): k3s rollout` |

**Definition of done:** the whole platform runs on a real cluster behind a real URL. Load tests pass. Dashboards show real traffic.

---

## 14. Definition of Done

For **every** step in the build plan:

- [ ] Tests are written first and they fail before the implementation exists.
- [ ] Implementation is the minimum needed to pass the tests.
- [ ] All tests in the affected service pass (`make test-<service>`).
- [ ] Linter and type checker pass (`make check`).
- [ ] The commit message follows Conventional Commits and references the build-plan step.
- [ ] Changes to public contracts are reflected in `shared/contracts/` and in this spec.
- [ ] Any new env var is documented in the service's `.env.example` and `README.md`.

For **every** phase:

- [ ] All steps committed.
- [ ] Full E2E test for the phase passes against `docker compose up`.
- [ ] Any architecture decision changes have an ADR in `docs/adr/`.
- [ ] This spec is updated if anything material changed.

---

## 15. Appendix: Tech Choices & Rationale

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Async I/O is mature; ecosystem is best for LLM/data work |
| HTTP framework | FastAPI | Async-first; Pydantic-native; OpenAPI for free |
| ORM | SQLAlchemy 2.x async | Mature; async support is solid; works with Alembic |
| Migrations | Alembic | Standard with SQLAlchemy |
| Validation | Pydantic v2 | Fast; integrates with FastAPI; shared contract layer |
| Background jobs | arq | Redis-based; async-native; lighter than Celery |
| Message queue | Redis Streams | Consumer groups give at-least-once + partitioning; no Kafka ops overhead for demo |
| Cache | Redis | Reused for cancellation flags and consumer groups |
| OLTP DB | Postgres 16 | Best general-purpose RDBMS; JSONB; partitioning |
| OLAP DB | ClickHouse | Industry standard for log analytics; very fast group-bys |
| Object storage | MinIO (local) / S3 (prod) | S3 API standard; MinIO matches it locally |
| Transcription | faster-whisper | Local; no API cost; good enough for demo |
| Frontend | Vite + React + TS + Tailwind | Fast dev experience; types end to end |
| Frontend charts | Recharts | Simple; declarative; good defaults |
| Tests | pytest + testcontainers + Playwright | Standard for Python/web; real deps in CI |
| Lint/format | ruff | Fast; replaces black + isort + flake8 |
| Types | mypy --strict | Catches contract drift between layers |
| Packaging | uv | Fast resolver; lockfile-first |
| Container | Docker + Compose | Universal local dev story |
| Orchestration | Kubernetes (k3s) | Self-hosted demo; manifests transfer to any cluster |
| Observability | structlog + Prometheus | Standard combo; structured logs + scrape metrics |
| AuthN | JWT (user) + API key (service) | Simple; sufficient for demo; swap to OIDC later |

---

## End of spec

When in doubt: re-read this document. If reality diverges from the spec, update the spec first, then change the code. The spec is the source of truth.