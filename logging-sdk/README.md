# olive-sdk

In-process Python SDK that wraps LLM calls and captures inference
metadata as `LogEvent`s for the AI-OLive platform. See PRD §2.2, §6.2.

## Layout

```
olive_sdk/
  domain/
    services/cost_calculator.py    # provider+model → USD (Phase 3.2)
  application/
    tracker.py                     # async context manager → LogEvent (Phase 3.6)
    emitter_port.py                # EmitterPort Protocol (Phase 3.6/3.8)
  infrastructure/
    providers/
      base_adapter.py              # Protocol (Phase 3.4)
      anthropic_adapter.py         # Phase 3.4
    emitters/
      file_emitter.py              # JSONL writer (Phase 3.8)
      http_emitter.py              # batched async HTTP (Phase 4)
      composite_emitter.py         # Phase 4
  client.py                        # public LLMClient (Phase 3.9)
```

The wire-format `LogEvent` lives in `shared/contracts/contracts/log_event.py`
(PRD §7.1) — the SDK consumes it without redefining.

## Status

Phase 3.1 — scaffold only. Code lands in 3.2–3.9; chat-service wires
the SDK in 3.10.

## Test

```bash
uv run pytest logging-sdk/tests/
```
