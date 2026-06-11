#!/usr/bin/env bash
# k3s rollout for AI-OLive (PRD §9.11).
#
# Builds every service image, makes them available to the cluster, applies
# the manifests, runs the migration Jobs, and waits for the deployments to
# become available.
#
# Usage:
#   scripts/k3s-rollout.sh
#
# Env:
#   IMPORT_METHOD   how images reach the cluster (default: k3s)
#                     k3s       docker save | sudo k3s ctr images import -
#                     registry  push to $IMAGE_REGISTRY (set it + retag)
#                     none      skip (images already present)
#   IMAGE_REGISTRY  registry prefix when IMPORT_METHOD=registry
#                     (e.g. registry.example.com/ai-olive)
#   TAG             image tag (default: latest)
#   KUBECTL         kubectl binary (default: kubectl)
#
# Prereqs: docker, kubectl pointed at the k3s cluster, and either the
# `k3s` CLI on this host (IMPORT_METHOD=k3s) or a reachable registry.
set -euo pipefail

cd "$(dirname "$0")/.."

IMPORT_METHOD="${IMPORT_METHOD:-k3s}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-}"
TAG="${TAG:-latest}"
KUBECTL="${KUBECTL:-kubectl}"
NS=ai-olive

SERVICES=(chat-service ingestion-service worker-service dashboard-service ui)

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
command -v docker >/dev/null || die "docker not found"
command -v "$KUBECTL" >/dev/null || die "kubectl not found"
"$KUBECTL" cluster-info >/dev/null 2>&1 || die "kubectl can't reach a cluster"

if [[ ! -f k8s/11-secret.yaml ]]; then
  die "k8s/11-secret.yaml missing — copy k8s/11-secret.example.yaml, fill it, and retry"
fi

# ------------------------------------------------------------------- build
build_images() {
  for svc in "${SERVICES[@]}"; do
    log "Building ai-olive/${svc}:${TAG}"
    docker build -f "docker/${svc}.Dockerfile" -t "ai-olive/${svc}:${TAG}" .
  done
}

# ---------------------------------------------------------- ship to cluster
ship_images() {
  case "$IMPORT_METHOD" in
    k3s)
      for svc in "${SERVICES[@]}"; do
        log "Importing ai-olive/${svc}:${TAG} into k3s containerd"
        docker save "ai-olive/${svc}:${TAG}" | sudo k3s ctr images import -
      done
      ;;
    registry)
      [[ -n "$IMAGE_REGISTRY" ]] || die "IMAGE_REGISTRY must be set for IMPORT_METHOD=registry"
      for svc in "${SERVICES[@]}"; do
        local ref="${IMAGE_REGISTRY}/${svc}:${TAG}"
        log "Pushing ${ref}"
        docker tag "ai-olive/${svc}:${TAG}" "$ref"
        docker push "$ref"
      done
      log "NOTE: update k8s image refs to ${IMAGE_REGISTRY}/<svc>:${TAG} (kustomize images: or sed)"
      ;;
    none)
      log "IMPORT_METHOD=none — assuming images are already on the cluster"
      ;;
    *)
      die "unknown IMPORT_METHOD: $IMPORT_METHOD"
      ;;
  esac
}

# ------------------------------------------------------------------- apply
apply_manifests() {
  log "Applying Secret"
  "$KUBECTL" apply -f k8s/11-secret.yaml
  log "Applying manifests (kustomize)"
  "$KUBECTL" apply -k k8s/
}

wait_for_infra() {
  log "Waiting for infra StatefulSets to be ready"
  for sts in postgres redis minio clickhouse; do
    "$KUBECTL" -n "$NS" rollout status "statefulset/${sts}" --timeout=180s
  done
}

run_migrations() {
  log "Re-running migration Jobs"
  "$KUBECTL" -n "$NS" delete job chat-migrate worker-migrate clickhouse-migrate --ignore-not-found
  "$KUBECTL" apply -f k8s/30-migrations.yaml
  for job in chat-migrate worker-migrate clickhouse-migrate; do
    log "Waiting for job/${job}"
    "$KUBECTL" -n "$NS" wait --for=condition=complete "job/${job}" --timeout=180s
  done
}

wait_for_apps() {
  log "Waiting for app Deployments to be available"
  for dep in chat-service ingestion-service worker-service dashboard-service ui; do
    "$KUBECTL" -n "$NS" rollout status "deployment/${dep}" --timeout=180s
  done
}

# -------------------------------------------------------------------- main
build_images
ship_images
apply_manifests
wait_for_infra
run_migrations
wait_for_apps

log "Rollout complete. Pods:"
"$KUBECTL" -n "$NS" get pods
log "Next: scripts/verify-deployment.sh"
