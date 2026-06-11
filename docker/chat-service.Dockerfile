# syntax=docker/dockerfile:1.7
# Production image for chat-service (PRD §9.8).
# Build from the repo root:
#   docker build -f docker/chat-service.Dockerfile -t ai-olive/chat-service .
#
# Multi-stage: the uv image resolves the locked workspace into /app/.venv,
# the slim runtime ships only Python + that venv + the source.

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Resolve only this service's slice of the workspace from the frozen lock.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package chat-service


FROM python:3.11-slim-bookworm AS runtime

# Non-root runtime user.
RUN useradd --create-home --uid 10001 olive

WORKDIR /app
COPY --from=builder --chown=olive:olive /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER olive
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"]

CMD ["uvicorn", "chat_service.interfaces.http.app:app", "--host", "0.0.0.0", "--port", "8000"]
