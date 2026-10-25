#!/usr/bin/env bash
# commands/stop_all.sh — Stop background processes and clean up
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Stopping uvicorn and vite processes (if running)..."
pkill -f "backend.main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true

echo "==> Done. (To delete the Kind cluster as well, run: kind delete cluster --name fedlearn-cluster)"

