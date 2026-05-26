# chat-service

Conversation management for the AI-OLive platform. Owns sessions, messages,
and (later) SSE streaming + cancellation. See PRD §5.1, §6.1.

## Layout

Hexagonal / ports-and-adapters (PRD §5.2):

```
chat_service/
  domain/          # Entities, value objects, domain services. No I/O.
    entities/        session.py, message.py, attachment.py
    value_objects/   session_status.py, message_role.py, model_config.py
    services/        context_builder.py
    events/          session_created.py, message_added.py
  application/     # Use cases (commands + queries). Defines ports.
    use_cases/       create_session.py, list_sessions.py, send_text_message.py, ...
    ports/           session_repository.py, llm_client.py, cancellation_store.py, ...
  infrastructure/ # Adapters that implement ports.
    persistence/     postgres_session_repo.py, sqlalchemy_models.py
    cache/           redis_cancellation_store.py
    sdk/             sdk_llm_client.py (added Phase 3.10)
    publishers/      noop_publisher.py
  interfaces/     # Entry points.
    http/
      routers/       sessions.py, messages.py, stream.py
      dependencies.py, schemas.py
    main.py
```

Dependency rule: outer layers depend on inner layers, never the reverse.

## Status

Phase 1.1 — scaffold only. Domain, use cases, infrastructure, and HTTP are
populated in steps 1.2 through 1.9.

## Run locally

(Populated in Phase 1.9 once the FastAPI app exists.)

## Test

```bash
uv run pytest chat-service/tests/
```
