# Deploying AI-OLive (PRD §9.8–9.11)

Two targets: a single-host **compose-prod** rehearsal and a **k3s**
cluster rollout. Both build from the same per-service Dockerfiles in
`docker/`.

## A. Compose-prod (single host)

```bash
cp .env.example .env
# Set for production: DISABLE_AUTH=false, a >=32-byte JWT_SECRET,
# INGESTION_API_KEYS, real POSTGRES/MINIO/CLICKHOUSE passwords, provider keys.

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps   # all healthy?
```

Migrations run automatically as the `chat-migrate` / `worker-migrate`
one-shot services. Apply the ClickHouse schema once:

```bash
make migrate-clickhouse CLICKHOUSE_HTTP=http://127.0.0.1:8123
```

UI on http://localhost:8080, chat API on :8000, dashboard on :8004.

## B. k3s cluster

Prereqs: a k3s cluster, `kubectl` pointed at it, `docker` locally, and
(for image import) the `k3s` CLI on the cluster host. For a default k3s
(Traefik) see the Ingress note in `k8s/README.md`.

```bash
# 1. Secret (gitignored once filled in)
cp k8s/11-secret.example.yaml k8s/11-secret.yaml && $EDITOR k8s/11-secret.yaml

# 2. Build + import + apply + migrate + wait
scripts/k3s-rollout.sh                 # IMPORT_METHOD=registry IMAGE_REGISTRY=... for a registry

# 3. Verify
scripts/verify-deployment.sh
```

`verify-deployment.sh` checks pod status, every service's `/health` and
`/health/ready`, Prometheus `/metrics`, a live session-create, and a
dashboard metric — exiting non-zero on any failure.

## Manual flow verification (the five UI flows, §12.5)

Point a browser at the Ingress host (or `kubectl -n ai-olive port-forward
svc/ui 8080:8080`):

1. Create a session (pick a provider).
2. Send a message → watch the streamed reply.
3. Cancel a long stream mid-flight.
4. Upload a PDF → it's parsed and referenced on the next turn.
5. Open the dashboard → latency/throughput/error-rate/cost render.

Under load (`load/`), the dashboard and each service's `/metrics` should
move.

## Rollback

```bash
kubectl -n ai-olive rollout undo deployment/<name>
# or full teardown:
kubectl delete -k k8s/ && kubectl delete -f k8s/11-secret.yaml
```
