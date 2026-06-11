# Kubernetes manifests (PRD §9.10)

A self-contained namespace (`ai-olive`) with infra (Postgres, Redis,
MinIO, ClickHouse as single-replica StatefulSets), one-shot migration
Jobs, the four app services + worker, the nginx UI, and an Ingress.

Files are numbered by apply order; `kustomization.yaml` ties them
together (the Secret is deliberately excluded — see below).

## Apply

```bash
# 1. Secrets (never commit the filled-in copy — it is gitignored)
cp k8s/11-secret.example.yaml k8s/11-secret.yaml
$EDITOR k8s/11-secret.yaml            # real passwords, JWT_SECRET (>=32B), API keys
kubectl apply -f k8s/11-secret.yaml

# 2. Everything else
kubectl apply -k k8s/

# 3. Re-run migration Jobs after each image bump
kubectl -n ai-olive delete job chat-migrate worker-migrate clickhouse-migrate --ignore-not-found
kubectl apply -f k8s/30-migrations.yaml
```

## Images

Manifests reference `ai-olive/<service>:latest` with
`imagePullPolicy: IfNotPresent`. Build and make them available to the
cluster (for k3s, import into containerd) — see `scripts/k3s-rollout.sh`.

## Ingress

`50-ingress.yaml` assumes **ingress-nginx** and uses a rewrite so
`/api/chat/*` and `/api/dashboard/*` reach the backends while `/` serves
the UI (mirrors the dev vite proxy). `proxy-buffering: "off"` keeps SSE
streaming unbuffered.

Default **k3s ships Traefik**, not ingress-nginx. Either:
- install ingress-nginx and disable Traefik, or
- replace the Ingress with a Traefik `IngressRoute` + a `StripPrefix`
  middleware for the two `/api/*` prefixes.

Set your hostname on the Ingress (`spec.rules[0].host`, default
`olive.local`).

## Probes

- HTTP services: liveness `GET /health`, readiness `GET /health/ready`
  (the readiness check pings that service's dependencies).
- Worker: exec probe opening a TCP socket to Redis (no HTTP server).
