#!/usr/bin/env python3
"""Prove a workflow WORKS: the named seats actually answered.

Not the honesty contract -- that one passes when a seat names a blocker. This
one only passes when the work got done, because that is what "works as
expected" means.
"""
from __future__ import annotations

import argparse, json, re, subprocess, sys, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(mode: str, handlers: list[str], timeout: int) -> dict:
    token = f"OK-{uuid.uuid4().hex[:6].upper()}"
    ask = f"Reply with exactly: {token}"
    if mode == "webgpt":
        # Single-call path. The roundtable template needs two seats and returns
        # NEEDS_INTERVIEW for one, which is the harness misusing Ask, not Ask
        # failing.
        cmd = [str(ROOT / "run.sh"), "webgpt", ask, "--json"]
    elif mode == "compete":
        cmd = [str(ROOT / "run.sh"), "compete", ask,
               "--repo", "local/agent-skills", "--target", "prove-compete",
               "--immutable-goal", "Return the token.",
               "--criterion", "returns-the-token"]
    else:
        cmd = [str(ROOT / "run.sh"), "tau-dag", ask,
               "--repo", "local/agent-skills", "--target", f"prove-{mode}",
               "--immutable-goal", "Return the token.",
               "--dag-template", "roundtable", "--topology", "concurrent"]
    for h in handlers:
        cmd += ["--handler", h]
    cmd += ["--execute", "--json"]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
    m = re.search(r"^\{", proc.stdout, re.M)
    if not m:
        return {"ok": False, "reason": "no JSON result", "stderr": proc.stderr[-500:]}
    payload = json.loads(proc.stdout[m.start():])
    run_dir = Path(str((payload.get("execution") or {}).get("receipt_dir") or "").replace("/tau-receipts", ""))

    seats = []
    if run_dir and run_dir.is_dir():
        for lane in sorted(run_dir.glob("node-artifacts/handler-*")):
            resp = lane / "response.md"
            body = resp.read_text(encoding="utf-8", errors="replace") if resp.is_file() else ""
            rc = {}
            if (lane / "node-receipt.json").is_file():
                try: rc = json.loads((lane / "node-receipt.json").read_text(encoding="utf-8"))
                except ValueError: pass
            seats.append({"seat": lane.name, "status": rc.get("status"),
                          "failure_code": rc.get("failure_code"),
                          "answered": token in body, "bytes": len(body)})
    answered = [s for s in seats if s["answered"]]
    need = 2 if mode in {"roundtable", "compete"} else 1
    return {
        "ok": len(answered) >= need,
        "mode": mode, "handlers": handlers, "token": token,
        "run_status": payload.get("status"), "run_dir": str(run_dir),
        "seats": seats, "answered": len(answered), "required": need,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["webgpt", "roundtable", "compete"])
    ap.add_argument("--handler", action="append", default=[])
    ap.add_argument("--timeout", type=int, default=1500)
    args = ap.parse_args(argv)
    handlers = args.handler or {"webgpt": ["webgpt"],
                                "roundtable": ["webgpt", "webkimi"],
                                "compete": ["webgpt", "webkimi"]}[args.mode]
    try:
        r = run(args.mode, handlers, args.timeout)
    except subprocess.TimeoutExpired:
        r = {"ok": False, "mode": args.mode, "reason": f"timed out after {args.timeout}s", "seats": []}
    print(json.dumps(r, indent=2))
    print(("WORKS: " if r["ok"] else "DOES_NOT_WORK: ") +
          f"{r.get('answered',0)}/{r.get('required','?')} seat(s) returned the token")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
