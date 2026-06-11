#!/usr/bin/env bash
# Local dev process manager for the AI-OLive app services.
#
# Infra (Postgres/Redis/MinIO/ClickHouse) is managed by docker compose
# via `make up && make up-analytics`. This script runs the Python/UI
# processes on top of it.
#
#   scripts/dev-local.sh up       # start ingestion, chat, dashboard, worker, ui
#   scripts/dev-local.sh down      # stop them
#   scripts/dev-local.sh restart   # down + up
#   scripts/dev-local.sh status    # pids + health
#
# Logs: /tmp/olive-logs/<service>.log
set -euo pipefail
cd "$(dirname "$0")/.."

LOGS=/tmp/olive-logs
mkdir -p "$LOGS"

start() {
  echo "starting app services (logs in $LOGS)…"
  nohup uv run uvicorn ingestion_service.interfaces.http.app:app --host 127.0.0.1 --port 8001 >"$LOGS/ingestion.log" 2>&1 &
  nohup uv run uvicorn chat_service.interfaces.http.app:app --host 127.0.0.1 --port 8000 >"$LOGS/chat.log" 2>&1 &
  nohup uv run uvicorn dashboard_service.interfaces.http.app:app --host 127.0.0.1 --port 8004 >"$LOGS/dashboard.log" 2>&1 &
  nohup uv run python -m worker_service.interfaces.cli.run_worker >"$LOGS/worker.log" 2>&1 &
  ( cd ui && nohup npm run dev >"$LOGS/ui.log" 2>&1 & )
  sleep 8
  status
  echo "UI: http://localhost:5173   (use 'localhost', vite binds IPv6)"
}

stop() {
  echo "stopping app services…"
  pkill -f "uvicorn (ingestion_service|chat_service|dashboard_service)" 2>/dev/null || true
  pkill -f "worker_service.interfaces.cli.run_worker" 2>/dev/null || true
  pkill -f "vite" 2>/dev/null || true
  echo "stopped."
}

status() {
  for p in ingestion_service chat_service dashboard_service run_worker vite; do
    pgrep -f "$p" >/dev/null && echo "  $p: UP" || echo "  $p: DOWN"
  done
  for hp in chat:8000 ingestion:8001 dashboard:8004; do
    name="${hp%%:*}"; port="${hp##*:}"
    code=$(curl -s -o /dev/null -w '%{http_code}' -m 4 "http://127.0.0.1:${port}/health" 2>/dev/null || echo 000)
    echo "  ${name} /health: ${code}"
  done
}

case "${1:-status}" in
  up|start)   start ;;
  down|stop)  stop ;;
  restart)    stop; sleep 1; start ;;
  status)     status ;;
  *) echo "usage: $0 {up|down|restart|status}"; exit 1 ;;
esac
