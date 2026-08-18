#!/usr/bin/env python3
"""Prove a workflow WORKS: the named seats actually answered.

Not the honesty contract -- that one passes when a seat names a blocker. This
one only passes when the work got done, because that is what "works as
expected" means.

For a panel, "the work got done" is a quorum of seats returning the token:
three for a roundtable, two for a competition. The bar is imported from
panel_compliance so this harness cannot certify a run the audit would reject.
"""
from __future__ import annotations

import argparse, json, os, re, signal, subprocess, sys, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ask.panel_compliance import (  # noqa: E402
    COMPETITION_MIN_ANSWERING,
    ROUNDTABLE_MIN_ANSWERING,
)

#: Seats that must return the token, by mode. Imported rather than restated so
#: the bar this harness proves is the same one panel_compliance enforces --
#: two copies of the number drift, and the harness would then certify runs the
#: audit rejects.
REQUIRED_SEATS = {
    "roundtable": ROUNDTABLE_MIN_ANSWERING,
    "compete": COMPETITION_MIN_ANSWERING,
}

#: A roundtable is proved against the full preferred roster, not against the
#: quorum. Dispatching exactly three and demanding three makes every trial a
#: perfect run; the roster is what Ask actually seats, so it is what gets
#: proved.
DEFAULT_HANDLERS = {
    "roundtable": ["webgpt", "webkimi", "webgemini", "webgrok", "webdeepseek"],
    "compete": ["webgpt", "webkimi", "webgemini"],
}


def _kill_group(proc: "subprocess.Popen") -> None:
    """TERM then KILL the child's whole process group.

    start_new_session=True made the child a group leader, so signalling -pgid
    reaches every descendant -- the browser submit and the node CLI holding the
    Surf lock included -- instead of only the shell we spawned.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError):
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def run(mode: str, handlers: list[str], timeout: int) -> dict:
    token = f"OK-{uuid.uuid4().hex[:6].upper()}"
    ask = f"Reply with exactly: {token}"
    if mode not in {"roundtable", "compete"}:
        # Single-call path. The roundtable template needs two seats and returns
        # NEEDS_INTERVIEW for one, which is the harness misusing Ask, not Ask
        # failing.
        # single-call template: one seat, no join, no interview. The
        # roundtable template demands two seats and returns NEEDS_INTERVIEW for
        # one, which is the harness misusing Ask rather than Ask failing.
        cmd = [str(ROOT / "run.sh"), "tau-dag", ask,
               "--repo", "local/agent-skills", "--target", f"prove-{mode}",
               "--immutable-goal", "Return the token.",
               "--dag-template", "single-call"]
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

    # Run the DAG in its own process group and kill the GROUP on timeout.
    #
    # subprocess.run(timeout=...) kills only the direct child. Observed
    # 2026-08-17: this harness timed out at 1500s, and the tree underneath it --
    # tau_dag_cli -> kimi-submit.sh -> timeout(4860s) -> node cli.cjs kimi_tab --
    # stayed alive holding the Surf browser lock, so every later probe failed
    # with surf_browser_lock_timeout against an owner whose parent was gone.
    # A stranded lease is worse than a failed run: it breaks the next run too.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, err = proc.communicate()
        raise
    proc = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
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
    need = REQUIRED_SEATS.get(mode, 1)
    return {
        "ok": len(answered) >= need,
        "mode": mode, "handlers": handlers, "token": token,
        "run_status": payload.get("status"), "run_dir": str(run_dir),
        "seats": seats, "answered": len(answered), "required": need,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # Any browser handler may be proved as a single seat: the question
    # "can Ask open a window and tab for THIS provider and get a response"
    # has to be answered per provider, not for webgpt and then assumed.
    ap.add_argument("mode")
    ap.add_argument("--handler", action="append", default=[])
    # A panel seats five providers against one browser and one surf lock, so it
    # cannot finish inside a single seat's budget.
    ap.add_argument("--timeout", type=int, default=None)
    args = ap.parse_args(argv)
    handlers = args.handler or DEFAULT_HANDLERS.get(args.mode, [args.mode])
    timeout = args.timeout if args.timeout is not None else (
        2400 if args.mode in REQUIRED_SEATS else 1500
    )
    try:
        r = run(args.mode, handlers, timeout)
    except subprocess.TimeoutExpired:
        r = {"ok": False, "mode": args.mode, "reason": f"timed out after {timeout}s", "seats": []}
    print(json.dumps(r, indent=2))
    print(("WORKS: " if r["ok"] else "DOES_NOT_WORK: ") +
          f"{r.get('answered',0)}/{r.get('required','?')} seat(s) returned the token")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
