#!/usr/bin/env bash
# commands/6_test_workflow.sh — Run smoke & workflow test suite
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

echo "==> Running coordinator smoke test"
"$PYTHON_BIN" platform/backend/smoke_test.py

echo "==> Running full end-to-end workflow test"
"$PYTHON_BIN" platform/backend/test_workflow.py

echo ""
echo "All tests passed successfully!"

