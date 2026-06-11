# syntax=docker/dockerfile:1.7
# Production image for the React UI (PRD §9.8).
#   docker build -f docker/ui.Dockerfile -t ai-olive/ui .
#
# Stage 1 builds the static bundle with Vite; stage 2 serves it from nginx.
# API routing (/api/chat, /api/dashboard) is handled by the cluster ingress,
# so nginx only serves static assets + the SPA fallback.

FROM node:22-bookworm-slim AS builder

WORKDIR /app
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
