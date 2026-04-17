#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEMORY_ROOT="${MEMORY_ROOT:-$HOME/workspace/experiments/memory}"
LOG_PATH="$ROOT_DIR/.artifacts/layout_pi.jsonl"

mkdir -p "$ROOT_DIR/.artifacts"

export MEMORY_LAYOUT=auto
export MEMORY_LAYOUT_THRESHOLD=6000

uv run --directory "$MEMORY_ROOT" --all-extras python - "$MEMORY_ROOT" "$LOG_PATH" <<'PY'
import importlib.util
from pathlib import Path
import sys

root = Path(sys.argv[1])
log_path = Path(sys.argv[2])
src = root / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

spec = importlib.util.spec_from_file_location(
    "eval_harness", root / "tests" / "retrieval" / "eval_harness.py"
)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

from scripts.retrieval import build_qra_bundle as bundle  # noqa: E402

fixture = module.Fixture("code_niah_repo", root / "tests" / "fixtures" / "code_niah_repo")
items = module._load_fixture_items(fixture)
bundle.layout_items(
    items,
    requested=bundle.LayoutStrategy.REPOSITIONED,
    token_threshold=0,
    layout_log_path=str(log_path),
    metadata={"fixture": fixture.name},
)
PY

if [[ ! -s "$LOG_PATH" ]]; then
  echo "layout log missing: $LOG_PATH" >&2
  exit 1
fi

echo "PASS: pi-mono layout flags"
