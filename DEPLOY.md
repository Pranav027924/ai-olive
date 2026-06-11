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

## 2. Put it on the internet (a public URL)

Run the exact same one command on a cloud VM, then point a domain at it.

1. **Provision a VM** (DigitalOcean / Hetzner / EC2 — 4 GB RAM minimum,
   8 GB recommended; the ClickHouse + chat images are the heavy parts).
2. **Install Docker**, `git clone` the repo, do the **Section 1** steps.
3. **Front it with TLS.** Put Caddy in front of `:8080` for automatic HTTPS:

   ```bash
   # /etc/caddy/Caddyfile
   your-domain.com {
       reverse_proxy 127.0.0.1:8080
   }
   ```
   `sudo apt install caddy` → `sudo systemctl restart caddy`. Point your
   domain's A record at the VM's IP. Done — `https://your-domain.com` serves
   the whole app.
4. **Open the firewall** for 80/443 only (keep 8080 and the data ports
   internal).

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
