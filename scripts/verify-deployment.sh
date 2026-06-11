#!/usr/bin/env bash
# Post-rollout verification for AI-OLive (PRD §9.11).
#
# Runs in-cluster checks via `kubectl exec`/port-forward so it works
# without an Ingress hostname configured. Exits non-zero if any check
# fails.
#
# Usage:
#   scripts/verify-deployment.sh
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
NS=ai-olive
fails=0

log()  { printf '\033[1;34m[check]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
bad()  { printf '\033[1;31m  FAIL\033[0m %s\n' "$*"; fails=$((fails + 1)); }

# A throwaway curl pod we can exec HTTP checks from.
ensure_curl_pod() {
  if ! "$KUBECTL" -n "$NS" get pod curl-probe >/dev/null 2>&1; then
    "$KUBECTL" -n "$NS" run curl-probe --image=curlimages/curl:8.11.0 \
      --restart=Never --command -- sleep 3600 >/dev/null
    "$KUBECTL" -n "$NS" wait --for=condition=ready pod/curl-probe --timeout=60s >/dev/null
  fi
}

incluster_get() {  # incluster_get <url>
  "$KUBECTL" -n "$NS" exec curl-probe -- curl -fsS -m 5 "$1"
}

incluster_code() {  # incluster_code <url> -> http status
  "$KUBECTL" -n "$NS" exec curl-probe -- \
    curl -s -o /dev/null -w '%{http_code}' -m 5 "$1"
}

# 1. All pods Running/Completed.
log "pod status"
if "$KUBECTL" -n "$NS" get pods --no-headers \
     | awk '{print $3}' | grep -vqE 'Running|Completed'; then
  bad "some pods are not Running/Completed"
  "$KUBECTL" -n "$NS" get pods
else
  ok "all pods Running/Completed"
fi

ensure_curl_pod

# 2. Liveness on every HTTP service.
for svc_port in chat-service:8000 ingestion-service:8001 dashboard-service:8004; do
  svc="${svc_port%%:*}"; port="${svc_port##*:}"
  log "liveness ${svc}"
  if [[ "$(incluster_code "http://${svc}:${port}/health")" == "200" ]]; then
    ok "${svc} /health 200"
  else
    bad "${svc} /health not 200"
  fi
done

# 3. Readiness (dependency checks) on every HTTP service.
for svc_port in chat-service:8000 ingestion-service:8001 dashboard-service:8004; do
  svc="${svc_port%%:*}"; port="${svc_port##*:}"
  log "readiness ${svc}"
  if [[ "$(incluster_code "http://${svc}:${port}/health/ready")" == "200" ]]; then
    ok "${svc} /health/ready 200 (deps reachable)"
  else
    bad "${svc} /health/ready not 200"
  fi
done

# 4. Prometheus metrics exposed.
log "metrics endpoint (chat-service)"
if incluster_get "http://chat-service:8000/metrics" | grep -q http_requests_total; then
  ok "chat-service /metrics exposes http_requests_total"
else
  bad "chat-service /metrics missing http_requests_total"
fi

# 5. End-to-end: create a session through the chat-service.
log "e2e: create session"
created="$("$KUBECTL" -n "$NS" exec curl-probe -- \
  curl -fsS -m 8 -X POST -H 'Content-Type: application/json' \
  -d '{"title":"verify"}' http://chat-service:8000/sessions 2>/dev/null || true)"
if echo "$created" | grep -q '"id"'; then
  ok "session created: $(echo "$created" | head -c 80)…"
else
  bad "session creation failed (set DISABLE_AUTH=false? then this needs a JWT)"
fi

# 6. Dashboard returns a metric shape.
log "e2e: dashboard throughput"
if incluster_code "http://dashboard-service:8004/metrics/throughput?window=1h" | grep -q 200; then
  ok "dashboard /metrics/throughput 200"
else
  bad "dashboard /metrics/throughput not 200"
fi

"$KUBECTL" -n "$NS" delete pod curl-probe --ignore-not-found >/dev/null 2>&1 || true

echo
if [[ "$fails" -eq 0 ]]; then
  printf '\033[1;32mAll checks passed.\033[0m\n'
else
  printf '\033[1;31m%d check(s) failed.\033[0m\n' "$fails"
  exit 1
fi
