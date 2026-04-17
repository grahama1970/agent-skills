#!/bin/bash
set -eo pipefail
# Lean4 Compilation Service launcher
# Starts the FastAPI service wrapping ParallelCompiler.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${LEAN4_SERVICE_PORT:-8604}"
WORKERS="${LEAN4_WORKERS:-20}"

echo "[lean4-prove] Starting compilation service on :${PORT} with ${WORKERS} workers..."
exec uv run --project "$SCRIPT_DIR" uvicorn service:app --host 127.0.0.1 --port "$PORT"
