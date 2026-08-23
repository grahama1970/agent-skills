"""Regression guard for relationship-signal prospect queue accounting.

Inputs: a completed live monitor-opportunities nightly run selected from
MONITOR_OPPORTUNITIES_LIVE_RUN, the checkout's local/latest run, or the
operator's canonical nightly directory. Outputs: stdout summary and a rewritten
prospect-queue.json in a temporary copy. Failure modes are explicit nonzero
exits; no external effects are performed.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from monitor_opportunities.nightly_digest import run_digest_phase


def _skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_runs() -> list[Path]:
    configured = os.environ.get("MONITOR_OPPORTUNITIES_LIVE_RUN")
    if configured:
        return [Path(configured)]
    skill_dir = _skill_dir()
    canonical = Path("/home/graham/workspace/experiments/agent-skills/skills/monitor-opportunities")
    candidates = [skill_dir / "local" / "nightly" / "latest"]
    candidates.extend(sorted((skill_dir / "local" / "nightly").glob("run-*"), reverse=True))
    if canonical != skill_dir:
        candidates.append(canonical / "local" / "nightly" / "latest")
        candidates.extend(sorted((canonical / "local" / "nightly").glob("run-*"), reverse=True))
    return candidates


def _select_live_run() -> Path:
    for run in _candidate_runs():
        manifest = run / "report-manifest.json"
        receipt_path = run / "nightly-receipt.json"
        if not manifest.is_file():
            continue
        if receipt_path.is_file():
            receipt = _read_json(receipt_path)
            if receipt.get("status") != "PASS":
                continue
            if receipt.get("mocked") is True or receipt.get("live") is not True:
                continue
        return run
    raise SystemExit("RELATIONSHIP_PROSPECT_QUEUE_NO_LIVE_RUN")


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = _select_live_run()
    with tempfile.TemporaryDirectory(prefix="monitor-opportunities-relationship-queue-") as tmp:
        copied = Path(tmp) / "run"
        shutil.copytree(source, copied, symlinks=True)
        steps: dict[str, Any] = {}
        memory_url = os.environ.get("MONITOR_OPPORTUNITIES_EVAL_MEMORY_URL", "http://127.0.0.1:1")
        run_digest_phase(
            copied,
            _skill_dir(),
            copied / "browser-capture",
            memory_url,
            steps,
            degrade_digest_contract=True,
        )
        queue = _read_json(copied / "prospect-queue.json")
        manifest = _read_json(copied / "report-manifest.json")
        relationship = queue.get("relationship_signals") or {}
        included = int(relationship.get("included") or 0)
        excluded = int(relationship.get("excluded") or 0)
        input_count = int(relationship.get("input") or 0)
        unaccounted = int(relationship.get("unaccounted") or 0)
        relationship_count = int((queue.get("counts") or {}).get("relationship") or 0)
        if input_count <= 0:
            raise SystemExit("RELATIONSHIP_PROSPECT_QUEUE_NO_INPUT")
        if included + excluded != input_count or unaccounted != 0:
            raise SystemExit("RELATIONSHIP_PROSPECT_QUEUE_UNACCOUNTED")
        if relationship_count != included:
            raise SystemExit("RELATIONSHIP_PROSPECT_QUEUE_COUNT_MISMATCH")
        summary = {
            "schema": "monitor_opportunities.relationship_prospect_queue_eval.v1",
            "source_run": str(source),
            "mocked": False,
            "live": True,
            "manifest_relationship_signals": len(manifest.get("relationship_signals") or []),
            "input": input_count,
            "included": included,
            "excluded": excluded,
            "unaccounted": unaccounted,
            "relationship": relationship_count,
            "invariant_pass": True,
            "relationship_count_matches_included": relationship_count == included,
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(
            "RELATIONSHIP_PROSPECT_QUEUE_OK "
            f"source={source} "
            f"manifest_relationship_signals={len(manifest.get('relationship_signals') or [])} "
            f"input={input_count} included={included} excluded={excluded} "
            f"relationship={relationship_count}"
        )


if __name__ == "__main__":
    main()
