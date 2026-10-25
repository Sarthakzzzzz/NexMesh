#!/usr/bin/env bash
# commands/4_start_client_portal.sh — Start Remote Participant Client Portal (Port 5174)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/platform/client-frontend"

echo "=========================================================="
echo " Starting Participant Client Portal on http://127.0.0.1:5174"
echo "=========================================================="

if [ ! -d "node_modules" ]; then
  echo "==> Installing client portal dependencies..."
  npm install
fi

# Leave VITE_API_URL unset so the browser connects to window.location.hostname:8000
unset VITE_API_URL

exec npm run dev -- --host 0.0.0.0 --port 5174

