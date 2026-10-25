#!/usr/bin/env bash
# commands/1_start_k8s.sh — Start Kind cluster & deploy NVFlare server + admin
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Loading environment from .env"
if [ -f .env ]; then
  set -a
  . .env
  set +a
fi

KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-fedlearn-cluster}"
KIND_TMPDIR="${KIND_TMPDIR:-$REPO_ROOT/.kind_tmp}"
NVFLARE_IMAGE="${NVFLARE_IMAGE:-fedlearn/nvflare:local}"
FEDLEARN_ROOT="${FEDLEARN_ROOT:-$REPO_ROOT}"

echo "==> Rendering Kind configuration"
mkdir -p "$KIND_TMPDIR"
envsubst '${FEDLEARN_ROOT}' < kind-config.yaml > "$KIND_TMPDIR/kind-config.yaml"

echo "==> Re-creating Kind cluster: $KIND_CLUSTER_NAME"
kind delete cluster --name "$KIND_CLUSTER_NAME" 2>/dev/null || true
TMPDIR="$KIND_TMPDIR" kind create cluster --config "$KIND_TMPDIR/kind-config.yaml"

echo "==> Loading Docker image: $NVFLARE_IMAGE"
TMPDIR="$KIND_TMPDIR" kind load docker-image "$NVFLARE_IMAGE" --name "$KIND_CLUSTER_NAME"

echo "==> Deploying NVFlare server and admin pods"
kubectl apply -f k8s/nvflare-server.yaml

echo "==> Waiting for NVFlare server pod to be Ready"
kubectl rollout status deployment/nvflare-server --timeout=120s
kubectl rollout status deployment/nvflare-admin --timeout=120s

echo ""
echo "NVFlare Kubernetes deployment is READY!"
kubectl get pods -o wide

