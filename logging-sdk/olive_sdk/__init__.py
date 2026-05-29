"""olive_sdk — in-process logging SDK for LLM calls (PRD §6.2).

Public API:
    from olive_sdk.client import LLMClient

Layering follows the same hexagonal split as the chat-service
(PRD §5.2):

- ``domain``        : pure business logic (cost calculation, etc.)
- ``application``   : Tracker context manager + emitter port
- ``infrastructure``: provider adapters, file/HTTP emitters

The wire-format ``LogEvent`` is shared via ``contracts.log_event``
(PRD §7.1) — the SDK does not redefine it.
"""
