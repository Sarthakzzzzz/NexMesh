#!/usr/bin/env bash
# commands/5_start_remote_client.sh — Run Remote NVFlare Client Agent
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COORDINATOR="${1:-http://127.0.0.1:8000}"
CLIENT_ID="${2:-}"
DATA_PATH="${3:-$REPO_ROOT/workspace/fedlearn/datasets/site-1/mnist.pt}"

if [ -z "$CLIENT_ID" ]; then
  echo -n "Enter your Client ID (from portal, e.g. remote-xxx or site-alpha): "
  read -r CLIENT_ID
fi

if [ -z "$CLIENT_ID" ]; then
  echo "Error: Client ID is required."
  exit 1
fi

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

echo "=========================================================="
echo " Connecting Client: $CLIENT_ID"
echo " Coordinator:       $COORDINATOR"
echo " Dataset Path:      $DATA_PATH"
echo "=========================================================="

exec "$PYTHON_BIN" platform/agent/remote_onboard.py \
  --coordinator "$COORDINATOR" \
  --client-id "$CLIENT_ID" \
  --data-path "$DATA_PATH" \
  --mode direct

