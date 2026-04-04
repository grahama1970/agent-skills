#!/usr/bin/env python3
"""Regenerate full-fidelity viewer evidence cases.

Reads viewer `public/data.jsonl`, runs `/create-evidence-case` for each question,
and writes full result payloads keyed by `review_id` into `public/evidence_cases_full.json`.

This preserves `gate_trace`, `lean4_result`, decomposition, evidence, and other
fields the reduced sidecar dropped.
"""

from __future__ import annotations
import os

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer


VIEWER_DIR = Path(__file__).resolve().parent
SKILL_DIR = VIEWER_DIR.parent
RUN_SH = SKILL_DIR / "run.sh"
DEFAULT_DATA = VIEWER_DIR / "public" / "data.jsonl"
DEFAULT_OUT = VIEWER_DIR / "public" / "evidence_cases_full.json"


app = typer.Typer()


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data if isinstance(data, dict) else {}


def extract_json_blob(text: str) -> dict:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON object found in command output")


def run_case(question: str, timeout_s: int) -> dict:
    proc = subprocess.run(
        [str(RUN_SH), "create", "--json", "--quiet", question],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    return extract_json_blob(proc.stdout)


def persist(path: Path, payload: dict[str, dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


@app.command()
def main(
    input_path: Path = typer.Option(DEFAULT_DATA, "--input", help="Input JSONL data file"),
    output: Path = typer.Option(DEFAULT_OUT, "--output", help="Output JSON file"),
    limit: int = typer.Option(0, "--limit", help="Max items to process (0=all)"),
    only_review_id: Optional[list[int]] = typer.Option(None, "--only-review-id", help="Process only these review IDs"),
    force: bool = typer.Option(False, "--force", help="Reprocess even if already cached"),
    timeout: int = typer.Option(180, "--timeout", help="Timeout per case in seconds"),
) -> int:
    rows = load_rows(input_path)
    existing = load_existing(output)

    targets = rows
    if only_review_id:
        wanted = {int(v) for v in only_review_id}
        targets = [row for row in rows if int(row["review_id"]) in wanted]

    if limit > 0:
        targets = targets[: limit]

    total = len(targets)
    completed = 0
    started_at = time.monotonic()

    for row in targets:
        review_id = str(row["review_id"])
        if not force and review_id in existing:
            completed += 1
            continue

        question = row["question"]
        print(f"[{completed + 1}/{total}] review_id={review_id} running", flush=True)
        try:
            result = run_case(question, timeout)
        except subprocess.TimeoutExpired:
            print(f"[{completed + 1}/{total}] review_id={review_id} timeout", file=sys.stderr, flush=True)
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"[{completed + 1}/{total}] review_id={review_id} failed: {exc}", file=sys.stderr, flush=True)
            continue

        existing[review_id] = result
        persist(output, existing)
        completed += 1
        elapsed = time.monotonic() - started_at
        print(
            f"[{completed}/{total}] review_id={review_id} stored "
            f"(elapsed={elapsed:.1f}s, verdict={result.get('claim', {}).get('verdict', 'unknown')})",
            flush=True,
        )

    print(f"done: wrote {len(existing)} cases to {output}", flush=True)
    return 0


if __name__ == "__main__":
    app()
