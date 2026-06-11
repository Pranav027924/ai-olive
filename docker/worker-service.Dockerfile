# syntax=docker/dockerfile:1.7
# Production image for worker-service (PRD §9.8).
#   docker build -f docker/worker-service.Dockerfile -t ai-olive/worker-service .
#
# The worker is a stream consumer, not an HTTP server: no EXPOSE/HEALTHCHECK
# here — Kubernetes uses an exec probe (redis reachability) instead.

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package worker-service


FROM python:3.11-slim-bookworm AS runtime

RUN useradd --create-home --uid 10001 olive

WORKDIR /app
COPY --from=builder --chown=olive:olive /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER olive

CMD ["python", "-m", "worker_service.interfaces.cli.run_worker"]
