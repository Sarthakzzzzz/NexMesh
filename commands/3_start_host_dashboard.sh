#!/usr/bin/env bash
# commands/3_start_host_dashboard.sh — Start Host Coordinator UI (Port 5173)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/platform/frontend"

echo "=========================================================="
echo " Starting Host Coordinator Dashboard on http://127.0.0.1:5173"
echo "=========================================================="

if [ ! -d "node_modules" ]; then
  echo "==> Installing frontend dependencies..."
  npm install
fi

exec npm run dev -- --host 0.0.0.0 --port 5173

