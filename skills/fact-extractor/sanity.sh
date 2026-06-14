#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

uv run --project "$SCRIPT_DIR" python -m fact_extractor.cli doctor --json >/tmp/fact-extractor-doctor.json
uv run --project "$SCRIPT_DIR" pytest -q

FIXTURE_ROOT="$(mktemp -d /tmp/fact-extractor-verify.XXXXXX)"
export FIXTURE_ROOT
uv run --project "$SCRIPT_DIR" python - <<'PY'
import json
import os
from pathlib import Path

from fact_extractor.cli import ChunkResult, enrich_records, write_aggregate, write_chunk_dicts_jsonl

root = Path(os.environ["FIXTURE_ROOT"])
good = root / "good"
broken = root / "broken"
good.mkdir(parents=True)
broken.mkdir(parents=True)

primary = "Alpha sentence. Beta sentence. Gamma sentence."
chunk = {
    "chunk_id": "c01",
    "document_id": "test_book_ch01",
    "source_path": str(root / "chapter_01.txt"),
    "source_sha256": "source-hash",
    "context_start_char": 0,
    "primary_start_char": 0,
    "primary_end_char": len(primary),
    "context_end_char": len(primary),
    "chunk_text": primary,
    "record_id_prefix": "test_book_ch01-c01-r",
}
record = {
    "question": "What sentence is beta?",
    "answer": "Beta sentence.",
    "claim": "The primary text contains beta sentence.",
    "evidence_quote": "Beta sentence.",
    "factuality": "narration_assertion",
    "tom": None,
}
meta = {"book": "Test Book", "chapter": "Chapter 01", "chapter_id": "test_book_ch01"}
chunk_dir = good / "chunks" / "c01"
chunk_dir.mkdir(parents=True)
(chunk_dir / "accepted_records.jsonl").write_text(
    json.dumps(enrich_records([record], chunk, meta)[0], ensure_ascii=False) + "\n",
    encoding="utf-8",
)
(chunk_dir / "accepted_attempt.txt").write_text("attempt_01\n", encoding="utf-8")
write_chunk_dicts_jsonl([chunk], good / "chunks.jsonl")
write_aggregate(
    good,
    [chunk],
    [
        ChunkResult(
            chunk_id="c01",
            accepted=True,
            record_count=1,
            elapsed_s=0.1,
            http_status=200,
            defects=[],
            chunk_dir=str(chunk_dir),
            accepted_attempt=1,
            attempts=1,
        )
    ],
)

(broken / "aggregate_report.json").write_text(
    json.dumps({"schema_version": "fact-extractor-result.v1", "accepted": False}, indent=2),
    encoding="utf-8",
)
PY

./run.sh verify --job-dir "$FIXTURE_ROOT/good" >/tmp/fact-extractor-verify-good.json
if ./run.sh verify --job-dir "$FIXTURE_ROOT/broken" >/tmp/fact-extractor-verify-broken.json 2>&1; then
  echo "broken fixture unexpectedly passed verify" >&2
  exit 1
fi
./run.sh file-maintainer-ticket --job-dir "$FIXTURE_ROOT/good" >/tmp/fact-extractor-maintainer-ticket.json

test -f "$FIXTURE_ROOT/good/verify-receipt.json"
test -f "$FIXTURE_ROOT/good/maintainer-ticket.json"
