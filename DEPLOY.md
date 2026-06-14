# Deploying AI-OLive

The whole project — UI + all 4 services + worker + Postgres/Redis/MinIO/
ClickHouse — runs from **one command**. The UI's nginx reverse-proxies the
API, so everything is reachable from a **single URL** (`http://HOST:8080`).
No Vercel, no per-service wiring.

---

## 1. Run the whole project (one command)

Works the same on your laptop or any Linux server with Docker.

```bash
# 0. prerequisites: Docker + Docker Compose, and the repo cloned.

# 1. configuration
cp .env.example .env
#    Edit .env and set:
#      ANTHROPIC_API_KEY=sk-ant-...        (or another provider key)
#      POSTGRES_PASSWORD / MINIO_ROOT_PASSWORD / CLICKHOUSE_PASSWORD
#      S3_ACCESS_KEY=olive  S3_SECRET_KEY=<same as MINIO_ROOT_PASSWORD>
#    Leave DISABLE_AUTH=true for a demo (no login screen exists yet).

# 2. build + start everything (first build ~10 min: the chat image
#    includes faster-whisper)
docker compose -f docker-compose.prod.yml up -d --build

# 3. watch it come up
docker compose -f docker-compose.prod.yml ps
```

That command also runs, in order: the Postgres migrations (chat + worker),
creates the MinIO bucket, and creates the ClickHouse table — all as one-shot
init services. When it settles, every container is `running` or
`exited (0)` (the init ones).

**Open the app:** http://localhost:8080

Quick checks:
```bash
curl http://localhost:8080/api/chat/health        # {"status":"ok"}
curl http://localhost:8080/api/dashboard/health    # {"status":"ok"}
```

Stop / reset:
```bash
docker compose -f docker-compose.prod.yml down            # stop (keep data)
docker compose -f docker-compose.prod.yml down -v         # stop + wipe data
```

---

## 2. Put it on the internet — CI/CD to AWS EC2

GitHub Actions builds the images, pushes them to **GHCR**, and deploys them to
your EC2 box over SSH. Caddy gives you **automatic HTTPS** on your domain.

- **CI** (`.github/workflows/ci.yml`) runs on every push/PR: ruff, mypy,
  pytest, and the UI (lint/typecheck/test/build). Nothing to configure.
- **CD** (`.github/workflows/deploy.yml`) runs on **push to `main`** or via
  **Actions → Deploy → Run workflow**: builds 5 images → GHCR → SSH deploy with
  `docker-compose.deploy.yml`.

### One-time setup

**1. Launch the EC2 instance**
- Ubuntu 22.04+, **≥ 4 GB RAM** (8 GB recommended — the chat image bundles
  faster-whisper). A `t3.large` is comfortable.
- Security group inbound: **22** (your IP only), **80**, **443**.
- Point your domain's **A record** at the instance's public IP.

**2. Install Docker on the instance**
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

**3. Create the deploy dir + `.env` on the instance** (holds the real secrets;
never committed). e.g. `/home/ubuntu/ai-olive/.env`:
```bash
mkdir -p ~/ai-olive && cd ~/ai-olive
cat > .env <<'EOF'
# --- domain / TLS ---
OLIVE_DOMAIN=your-domain.com
# --- auth (production) ---
DISABLE_AUTH=false
JWT_SECRET=<a-random-32+-byte-string>
JWT_ALGORITHM=HS256
# --- secrets ---
POSTGRES_USER=olive
POSTGRES_PASSWORD=<strong>
POSTGRES_DB=olive
MINIO_ROOT_USER=olive
MINIO_ROOT_PASSWORD=<strong>
S3_BUCKET=olive-attachments
S3_REGION=us-east-1
S3_ACCESS_KEY=olive
S3_SECRET_KEY=<same as MINIO_ROOT_PASSWORD>
CLICKHOUSE_USER=olive
CLICKHOUSE_PASSWORD=<strong>
CLICKHOUSE_DB=olive
INGESTION_API_KEY=<strong>
INGESTION_API_KEYS=<strong>
# --- providers ---
ANTHROPIC_API_KEY=sk-ant-...
# IMAGE_PREFIX and TAG are written/refreshed by the deploy workflow.
EOF
```

**4. Add GitHub repo secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `SSH_HOST` | EC2 public IP or DNS |
| `SSH_USER` | `ubuntu` (or `ec2-user`) |
| `SSH_KEY` | the **private** key (full PEM) for that instance |
| `SSH_PORT` | `22` (optional) |
| `DEPLOY_DIR` | `/home/ubuntu/ai-olive` |

GHCR needs no secret — the workflow authenticates with the built-in
`GITHUB_TOKEN` (push in CI, pull on the box). Images are private under your
account.

### Deploy

Push to `main`, or run **Actions → Deploy → Run workflow**. The pipeline:
builds + pushes the 5 images, `scp`s `docker-compose.deploy.yml` + `Caddyfile`
to `DEPLOY_DIR`, then SSHes in to `docker compose pull && up -d`. On first run
Caddy provisions a Let's Encrypt cert for `OLIVE_DOMAIN`.

→ Your app is live at **https://your-domain.com**.

Check it:
```bash
ssh ubuntu@<ip> 'cd ~/ai-olive && docker compose -f docker-compose.deploy.yml ps'
curl https://your-domain.com/api/chat/health
```

That's the entire deployment. The app, the API, the logging pipeline, and the
dashboard all run behind that one domain.

---

## 3. Production hardening (when you go past a demo)

- **Auth:** the UI has no login screen yet, so keep `DISABLE_AUTH=true`. To
  turn on JWT (`DISABLE_AUTH=false` + a 32-byte `JWT_SECRET`) you first need a
  login flow in the UI — ask and I'll add it.
- **Secrets:** use strong values in `.env` (never commit it — it's gitignored)
  or a secrets manager. Rotate the Anthropic key if it's ever shared.
- **Cost:** every chat reply is a real provider API call ($). The stack is
  always-on.
- **Scale / Kubernetes:** for multi-node, the `k8s/` manifests +
  `scripts/k3s-rollout.sh` deploy the same images to a cluster (see that
  folder's README).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `up` fails on a missing var | `.env` is missing `POSTGRES_PASSWORD` / `MINIO_ROOT_PASSWORD` / `CLICKHOUSE_PASSWORD`. Set all three. |
| Chat replies error | `ANTHROPIC_API_KEY` not set in `.env`, or the provider picked in the UI has no key. |
| Uploads fail | The `createbuckets` init didn't run — `docker compose -f docker-compose.prod.yml logs createbuckets`. |
| Dashboard 500s | Send a few messages first (the worker flushes metrics to ClickHouse every few seconds), then refresh. |
| A service is unhealthy | `docker compose -f docker-compose.prod.yml logs <service>`. |
