#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-${HOME}/workspace/experiments/extractor}"
FIXTURE_DIR="${EXTRACTOR_ROOT}/data/input/twins/preset_twin"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== Extractor skill sanity ===" >&2

if [[ ! -f "$FIXTURE_DIR/preset_twin.pdf" ]]; then
  echo "FAIL: missing PDF fixture at $FIXTURE_DIR/preset_twin.pdf" >&2
  exit 1
fi

if [[ ! -f "$FIXTURE_DIR/preset_twin.docx" ]]; then
  echo "FAIL: missing DOCX fixture at $FIXTURE_DIR/preset_twin.docx" >&2
  exit 1
fi

bash "$SCRIPT_DIR/run.sh" \
  "$FIXTURE_DIR/preset_twin.pdf" \
  --out "$TMPDIR/pdf" \
  --offline \
  --format json > "$TMPDIR/pdf.json"

bash "$SCRIPT_DIR/run.sh" \
  "$FIXTURE_DIR/preset_twin.docx" \
  --out "$TMPDIR/docx" \
  --offline \
  --format json > "$TMPDIR/docx.json"

uv run --project "$EXTRACTOR_ROOT" python - "$TMPDIR/pdf.json" "$TMPDIR/docx.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

for result_path in map(Path, sys.argv[1:]):
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "extractor.result.v1", result_path
    assert payload["status"] in {"complete", "degraded"}, payload["status"]
    assert payload["source_sha256"], result_path
    assert payload["artifacts"], result_path
PY

uv run --project "$EXTRACTOR_ROOT" python - "$SCRIPT_DIR" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

script_dir = Path(sys.argv[1])
forbidden = [
    "--" + "fast",
    "--" + "accurate",
    "--" + "preset",
    "CHUTES" + "_",
    "pdf_" + "oxide",
    "extract_pdf_" + "with",
]
violations: list[str] = []
for path in [script_dir / "SKILL.md", script_dir / "run.sh", script_dir / "extract.py"]:
    text = path.read_text(encoding="utf-8")
    for term in forbidden:
        if term in text:
            violations.append(f"{path.name}: {term}")
if violations:
    raise SystemExit("forbidden wrapper terms: " + ", ".join(violations))
PY

echo "OK: extractor.result.v1 emitted for PDF and DOCX" >&2
