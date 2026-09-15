#!/usr/bin/env python3
"""Live-e2e validator for the composed ask pipeline (research -> verify -> packet -> lanes).

Grades ONLY what the run's artifacts show on disk. Nothing green is inferred
from exit codes or prose. Usage:

  python3 eval_pipeline_run.py <pipeline-root> [--nonce TOKEN]

Expects under <root>:
  one-shot-verdict.json        - the ask one-shot verdict
  lane-specs.json              - packet written by the verify gate
  synthesis.md                 - packet digest
  lanes-output.md              - parent-saved stage-3 lane outputs
  seat run dirs                - per <lane-specs.json>.source_run (receipts + responses)

Prints ask.pipeline_live_eval.v1; exit 0 PASS, 3 honest NOT_READY.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


def fail(problems: list[str]) -> int:
    print(json.dumps({"schema": "ask.pipeline_live_eval.v1", "status": "NOT_READY", "problems": problems}, indent=2))
    return 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--nonce")
    args = ap.parse_args()
    root = Path(args.root)
    problems: list[str] = []
    checks: list[str] = []

    verdict_p = root / "one-shot-verdict.json"
    if not verdict_p.is_file():
        return fail([f"missing {verdict_p}"])
    verdict = json.loads(verdict_p.read_text(encoding="utf-8"))
    answered = verdict.get("answered") if isinstance(verdict, dict) else None
    seats = verdict.get("seats") or verdict.get("lanes") or {}
    if not answered:
        problems.append("one-shot verdict records no answered seats")
    else:
        checks.append(f"one-shot answered seats: {answered}")

    specs_p = root / "lane-specs.json"
    if not specs_p.is_file():
        return fail(problems + [f"missing {specs_p}"])
    specs = json.loads(specs_p.read_text(encoding="utf-8"))
    lanes = specs.get("lanes") or []
    if not lanes:
        return fail(problems + ["lane-specs.json has no lanes"])
    for lane in lanes:
        if not lane.get("derived_from"):
            problems.append(f"lane {lane.get('key')} lacks derived_from")
    if not specs.get("verified_by"):
        problems.append("lane-specs.json lacks verified_by")
    checks.append(f"packet lanes with derived_from: {len(lanes)}")

    nonce = args.nonce or ""
    source = str(specs.get("source_run") or "")
    seat_dirs = sorted(glob.glob(source)) if "*" in source else ([source] if source and Path(source).is_dir() else [])
    if not seat_dirs:
        seat_dirs = sorted(p.parent.parent for p in root.glob("**/node-receipt.json"))
    if not seat_dirs:
        return fail(problems + ["no seat run dirs found on disk"])
    ok_seats = 0
    for d in seat_dirs:
        for receipt in Path(d).glob("node-artifacts/*/node-receipt.json"):
            node = receipt.parent.name
            if not node.startswith("handler-"):
                # join/adapter nodes aggregate seats; ok must be true but their
                # response is a synthesis, not a seat answer - nonce exempt.
                data = json.loads(receipt.read_text(encoding="utf-8"))
                if data.get("ok") is not True:
                    problems.append(f"non-handler node {node} ok!=true")
                continue
            data = json.loads(receipt.read_text(encoding="utf-8"))
            handler = node.replace("handler-", "")
            if data.get("ok") is not True:
                problems.append(f"seat {handler} receipt ok!=true ({data.get('failure_code')})")
                continue
            resp = receipt.parent / "response.md"
            text = resp.read_text(encoding="utf-8") if resp.is_file() else ""
            if nonce and nonce not in text:
                problems.append(f"seat {handler} response lacks nonce {nonce}")
                continue
            ok_seats += 1
    if ok_seats == 0:
        problems.append("no seat verified ok with nonce on disk")
    else:
        checks.append(f"seats verified ok+nonce on disk: {ok_seats}")

    synth_p = root / "synthesis.md"
    if not synth_p.is_file():
        problems.append("missing synthesis.md")
    else:
        checks.append("synthesis.md present")

    lanes_out = root / "lanes-output.md"
    if not lanes_out.is_file():
        problems.append("missing lanes-output.md (parent must save stage-3 output)")
    else:
        text = lanes_out.read_text(encoding="utf-8")
        cites = text.count("DERIVED_FROM")
        if cites < len(lanes):
            problems.append(f"lanes-output cites DERIVED_FROM {cites}x < {len(lanes)} lanes")
        else:
            checks.append(f"lane outputs citing DERIVED_FROM: {cites}")

    if problems:
        return fail(problems)
    print(json.dumps({"schema": "ask.pipeline_live_eval.v1", "status": "PASS", "checks": checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
