"""Chat service — conversation management bounded context.

See PRD §5.1 (bounded context), §6.1 (LLD), and §8.1 (Postgres schema).

Layering follows hexagonal / ports-and-adapters (PRD §5.2):

- ``domain``        : entities, value objects, domain services. No I/O.
- ``application``   : use cases (command/query handlers). Defines ports.
- ``infrastructure``: adapters that implement ports (DB, cache, LLM, ...).
- ``interfaces``    : HTTP routers, CLI entry points.

Dependency rule: outer layers depend on inner layers; never the reverse.
"""
