# Deploying AI-OLive to the cloud (Railway + Vercel)

This is the **step-by-step** guide to put the whole project online:

- **UI → Vercel** (static React build; the only part that fits Vercel).
- **Backend (chat / ingestion / worker / dashboard) → Railway** as containers.
- **Data (Postgres / Redis / ClickHouse / MinIO) → Railway** services/plugins.

The UI talks to the backend through **same-origin rewrites** in
[`ui/vercel.json`](ui/vercel.json), so there is **no CORS** to configure.

> Reality check: this app is 4 services + a worker + 4 data stores. That is a
> real distributed system, not a one-click deploy. Budget ~45–60 min the first
> time. If you'd rather not wire 8 Railway services, the single-VM path in
> [DEPLOY.md](DEPLOY.md) (`docker-compose.prod.yml` on one server) is simpler —
> see "Alternative" at the bottom.

---

## Part 0 — Prerequisites

- A **GitHub repo** with this code pushed (Railway + Vercel deploy from GitHub).
- A **Railway** account (railway.app) and a **Vercel** account (vercel.com).
- Your **Anthropic API key** (already in your local `.env`).
  - ⚠️ The key you pasted is now in your shell history / this session. If this
    is ever shared, **rotate it** at console.anthropic.com. Never commit `.env`
    (it is gitignored).
- Optional but handy: the Railway CLI (`npm i -g @railway/cli`).

Decide one thing up front — **auth**:
- For a **demo**, keep `DISABLE_AUTH=true`. The chat works with a fixed dev
  user; anyone with the URL can use it. Simplest.
- For **real auth**, set `DISABLE_AUTH=false` + a 32-byte `JWT_SECRET`. ⚠️ The
  UI has **no login screen yet**, so it would not be able to obtain a token —
  you'd need to add a login flow first. For now, **keep `DISABLE_AUTH=true`**.

---

## Part 1 — Backend on Railway

### 1.1 Create the project + data plugins

1. Railway → **New Project** → **Deploy from GitHub repo** → pick this repo.
   (We'll add several services into this one project.)
2. **Add Postgres:** project → **New** → **Database** → **Add PostgreSQL**.
3. **Add Redis:** project → **New** → **Database** → **Add Redis**.

Railway now exposes these as referenceable variables, e.g.
`${{Postgres.PGHOST}}`, `${{Redis.REDISHOST}}` (used below).

### 1.2 Add ClickHouse + MinIO (as Docker image services)

ClickHouse and MinIO aren't Railway plugins, so add them as image services:

**ClickHouse** — project → **New** → **Empty Service** → Settings → **Source →
Docker Image** → `clickhouse/clickhouse-server:24.10-alpine`. Then:
- **Variables:** `CLICKHOUSE_DB=olive`, `CLICKHOUSE_USER=olive`,
  `CLICKHOUSE_PASSWORD=<pick-a-strong-one>`,
  `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1`.
- **Settings → Networking:** note its private name (e.g. `clickhouse.railway.internal`).
- **Settings → Volumes:** mount a volume at `/var/lib/clickhouse`.

**MinIO** — project → **New** → **Empty Service** → **Docker Image** →
`minio/minio:RELEASE.2025-04-22T22-12-26Z`. Then:
- **Start command:** `server /data --console-address :9001`
- **Variables:** `MINIO_ROOT_USER=olive`, `MINIO_ROOT_PASSWORD=<strong>`
- **Volume:** mount at `/data`
- After it boots, create the bucket once (Railway shell or `mc`):
  `mc alias set m http://localhost:9000 olive <pw> && mc mb -p m/olive-attachments`.

> Quicker alternative for object storage: use **Cloudflare R2** or **AWS S3**
> instead of MinIO, and point `S3_ENDPOINT_URL`/keys at it.

### 1.3 Add the four app services (from the Dockerfiles)

For **each** of `chat-service`, `ingestion-service`, `worker-service`,
`dashboard-service`: project → **New** → **GitHub Repo** (same repo) → then in
that service's **Settings**:

- **Build → Builder:** Dockerfile.
- **Build → Dockerfile Path:** `docker/<service>.Dockerfile`
  (e.g. `docker/chat-service.Dockerfile`).
- **Build → Root Directory:** `/` (repo root — the Dockerfiles `COPY . .`).
- **Deploy → Start Command:** override per service (binds Railway's `$PORT` and
  runs migrations on boot — see table).
- **Settings → Networking → Generate Domain:** for **chat-service** and
  **dashboard-service** only (these are public). Leave **ingestion** and
  **worker** private (no domain).

**Start commands** (paste into Deploy → Custom Start Command):

| Service | Start command |
|---|---|
| chat-service | `sh -c "cd /app/chat-service && alembic upgrade head && cd /app && uvicorn chat_service.interfaces.http.app:app --host 0.0.0.0 --port $PORT"` |
| ingestion-service | `sh -c "uvicorn ingestion_service.interfaces.http.app:app --host 0.0.0.0 --port $PORT"` |
| dashboard-service | `sh -c "uvicorn dashboard_service.interfaces.http.app:app --host 0.0.0.0 --port $PORT"` |
| worker-service | `sh -c "cd /app/worker-service && alembic upgrade head && cd /app && python -m worker_service.interfaces.cli.run_worker"` |

### 1.4 Environment variables (per service)

Set these under each service's **Variables**. Use Railway **variable
references** (`${{Postgres.PGHOST}}`, …) so they auto-resolve. `*.railway.internal`
hostnames are the private service-to-service addresses.

**Shared (all four app services):**

```
POSTGRES_HOST=${{Postgres.PGHOST}}
POSTGRES_PORT=${{Postgres.PGPORT}}
POSTGRES_USER=${{Postgres.PGUSER}}
POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}
POSTGRES_DB=${{Postgres.PGDATABASE}}
REDIS_HOST=${{Redis.REDISHOST}}
REDIS_PORT=${{Redis.REDISPORT}}
```

**chat-service** (also):
```
DISABLE_AUTH=true
ANTHROPIC_API_KEY=sk-ant-...          # your key
OPENAI_API_KEY=                        # optional
GEMINI_API_KEY=                        # optional
DEEPSEEK_API_KEY=                      # optional
S3_ENDPOINT_URL=http://minio.railway.internal:9000
S3_BUCKET=olive-attachments
S3_REGION=us-east-1
S3_ACCESS_KEY=olive
S3_SECRET_KEY=<minio password from 1.2>
INGESTION_URL=http://ingestion-service.railway.internal:8001/v1/logs
INGESTION_API_KEY=<shared-secret>
WHISPER_MODEL_SIZE=tiny
```

**ingestion-service** (also):
```
INGESTION_API_KEYS=<shared-secret>     # same value chat uses above
```

**worker-service** (also):
```
CLICKHOUSE_URL=http://clickhouse.railway.internal:8123
CLICKHOUSE_USER=olive
CLICKHOUSE_PASSWORD=<clickhouse password from 1.2>
CLICKHOUSE_DB=olive
```

**dashboard-service** (also):
```
CLICKHOUSE_URL=http://clickhouse.railway.internal:8123
CLICKHOUSE_USER=olive
CLICKHOUSE_PASSWORD=<clickhouse password>
CLICKHOUSE_DB=olive
```

> Ports: the chat/ingestion/dashboard internal hostnames above assume the
> default app ports (8000/8001/8004) for service-to-service calls. If Railway's
> private networking requires the assigned `$PORT`, use the service's
> `${{ingestion-service.PORT}}` reference in `INGESTION_URL` instead.

### 1.5 Deploy + apply the ClickHouse schema

1. Trigger a deploy of all four services (Railway auto-deploys on push, or hit
   **Deploy**). The chat/worker start commands apply Alembic migrations on boot.
2. Apply the ClickHouse analytics table **once** (Railway → ClickHouse service →
   **Shell**, or from your laptop against its public proxy):
   ```
   curl --fail --user "olive:<clickhouse-pw>" --data-binary @clickhouse/migrations/0001_inference_metrics.sql \
     "http://<clickhouse-host>:8123/?database=olive"
   ```
3. Confirm health: open `https://<chat-service>.up.railway.app/health` and
   `https://<dashboard-service>.up.railway.app/health` → both `{"status":"ok"}`.
   Check `/health/ready` too (verifies DB/Redis/ClickHouse connectivity).

**Copy the two public URLs** (chat-service and dashboard-service) — you need them
for Vercel next.

---

## Part 2 — UI on Vercel

### 2.1 Point the rewrites at your backend

Edit [`ui/vercel.json`](ui/vercel.json) and replace the two placeholder hosts
with your Railway public URLs:

```json
{ "source": "/api/chat/:path*",      "destination": "https://<chat-service>.up.railway.app/:path*" }
{ "source": "/api/dashboard/:path*", "destination": "https://<dashboard-service>.up.railway.app/:path*" }
```

Commit + push.

### 2.2 Create the Vercel project

1. Vercel → **Add New… → Project** → import this GitHub repo.
2. **Root Directory:** `ui`  ← important (the app lives in `ui/`).
3. Framework preset: **Vite** (auto-detected). Build `npm run build`, output
   `dist` (already in `vercel.json`).
4. **Deploy.** Vercel builds the static bundle and serves it; `/api/chat/*` and
   `/api/dashboard/*` are proxied to Railway by the rewrites.

Open the Vercel URL — you should get the ChatGPT-style UI, and sending a message
should stream a reply from your Railway chat-service.

---

## Part 3 — Verify the deployment

1. **UI loads** at the Vercel URL.
2. **New chat → send a message →** tokens stream back (chat-service + Anthropic).
3. **Upload a PDF** (the `+` in the composer) → it parses and is referenced next
   turn.
4. **Dashboard** → after a few messages, latency/throughput/cost render (proves
   the ingestion → worker → ClickHouse → dashboard pipeline end-to-end).
5. If a metric endpoint 500s, the worker hasn't flushed yet — send a couple more
   messages and refresh.

---

## Part 4 — Notes, gotchas, hardening

- **SSE streaming through Vercel:** rewrites to an external origin generally
  stream fine. If replies arrive all-at-once instead of token-by-token, switch
  to **direct mode**: set `import.meta.env.VITE_CHAT_BASE` to the Railway chat
  URL, make `CHAT_BASE`/`DASHBOARD_BASE` in `ui/src/api/client.ts` read it, and
  add FastAPI **CORS** middleware allowing the Vercel origin. (Ask me and I'll
  wire this.)
- **Worker has no public URL** — it's a background consumer. Railway shows it
  "Active" with logs; it has no HTTP healthcheck (k8s used an exec probe).
- **Costs:** every chat reply is a real Anthropic call (real $). The four
  always-on services + 4 data stores also consume Railway hours/credits.
- **Migrations on boot:** chat/worker run `alembic upgrade head` at startup
  (idempotent). With >1 replica there's a harmless race; keep replicas at 1 for
  the demo.
- **Secrets:** set them only in the Railway/Vercel dashboards, never in git.

---

## Alternative — one VM (simpler than 8 Railway services)

If the multi-service setup is more than you want, deploy the whole backend on a
single server with the compose stack you already have, and still host the UI on
Vercel:

```bash
# on a VM (Ubuntu + Docker):
git clone <repo> && cd AI-OLive
cp .env.example .env          # set DISABLE_AUTH, secrets, ANTHROPIC_API_KEY
docker compose -f docker-compose.prod.yml up -d --build
make migrate-clickhouse CLICKHOUSE_HTTP=http://127.0.0.1:8123
```

Put the VM behind a domain + TLS (Caddy/nginx), then point `ui/vercel.json`
rewrites at `https://<your-domain>/...` (chat on :8000, dashboard on :8004), and
deploy the UI to Vercel as in Part 2. See [DEPLOY.md](DEPLOY.md) for the
Kubernetes/k3s path.
