#!/usr/bin/env bash
# commands/2_start_backend.sh — Start NexMesh Coordinator Backend (Port 8000)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ -f .env ]; then
  set -a
  . .env
  set +a
fi

export NEXMESH_HOST_TOKEN="${NEXMESH_HOST_TOKEN:-${VITE_HOST_TOKEN:-changeme}}"
export NEXMESH_AGENT_TOKEN="${NEXMESH_AGENT_TOKEN:-agent-test}"
export NEXMESH_SERVER_NAME="${NEXMESH_SERVER_NAME:-192.168.1.43}"
export NEXMESH_COORDINATOR_URL="${NEXMESH_COORDINATOR_URL:-http://$NEXMESH_SERVER_NAME:8000}"
export NEXMESH_DATABASE_PATH="$REPO_ROOT/platform/nexmesh.db"

VENV_UVICORN="$REPO_ROOT/.venv/bin/uvicorn"
if [ ! -f "$VENV_UVICORN" ]; then
  VENV_UVICORN="uvicorn"
fi

echo "=========================================================="
echo " Starting NexMesh Coordinator API on http://127.0.0.1:8000"
echo " Docs:       http://127.0.0.1:8000/docs"
echo " Dashboard:  http://127.0.0.1:8000/dashboard"
echo " Host Token: $NEXMESH_HOST_TOKEN"
echo "=========================================================="

exec "$VENV_UVICORN" backend.main:app \
  --app-dir "$REPO_ROOT/platform" \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
