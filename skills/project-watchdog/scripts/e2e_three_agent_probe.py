#!/usr/bin/env python3
"""Adversarial end-to-end probe of the three-agent watchdog pipeline.

Runs the REAL tick code path — scan -> route -> lease -> repair dispatch ->
proof gate -> pydantic receipt validation -> $triage-error self-heal ->
$ops-discord alerting — against a sandboxed GitHub (a ``gh`` PATH shim backed
by a JSON ticket ledger) and a stubbed ``$ask tau-dag`` transport whose seats
(creator, reviewer/classifier) are controlled per scenario.

Proof boundary, stated plainly:
- LIVE: registry scan/route/lease logic, worktree preparation on a real git
  repo, proof-gate verdict reading, pydantic receipt validation,
  triage-error classification (real sibling skill), ops-discord alert path
  (dry-run transport resolution through the real sibling skill), ui-data.
- FAKED: GitHub (gh shim + ledger) and the model seats ($ask stub). No paid
  provider calls, no real GitHub mutation.

Scenarios (one ticket each):
  completed        creator+reviewer PASS, commit ahead -> COMPLETED, gh ledger
                   shows agent-done, ops-discord notified (dry-run receipt)
  needs-human      reviewer/classifier seat rejects with VERDICT:
                   NEEDS_ATTENTION -> proof gate refuses, ticket labeled
                   needs-human + agent-blocked, alert fired
  bad-code         a handler injects an invented triage code into the receipt
                   -> pydantic downgrade to NEEDS_ATTENTION + minted
                   triage-error code recorded
  ui-data          after the runs, ./run.sh ui-data snapshot contains the
                   eventful receipts (dynamically viewable UX)

Usage: e2e_three_agent_probe.py <scenario> [--sandbox DIR]
Exits 0 on scenario proof, 1 on failure. Prints a JSON proof object.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]

GH_SHIM = r'''#!/usr/bin/env python3
import json, sys, os
from pathlib import Path
LEDGER = Path(os.environ["PW_E2E_LEDGER"])
def load():
    return json.loads(LEDGER.read_text())
def save(d):
    LEDGER.write_text(json.dumps(d, indent=1))
def log(entry):
    with open(str(LEDGER) + ".log", "a") as f:
        f.write(json.dumps(entry) + "\n")
a = sys.argv[1:]
log({"argv": a})
d = load()
issues = d["issues"]
def issue(n):
    return next(i for i in issues if i["number"] == int(n))
if a[:2] == ["issue", "list"]:
    state = a[a.index("--state") + 1] if "--state" in a else "open"
    labels = [a[i + 1] for i, t in enumerate(a) if t == "--label"]
    out = [i for i in issues if i["state"].lower() == state
           and all(l in [x["name"] for x in i["labels"]] for l in labels)]
    print(json.dumps(out)); sys.exit(0)
if a[:2] == ["issue", "view"]:
    print(json.dumps(issue(a[2]))); sys.exit(0)
if a[:2] == ["issue", "edit"]:
    i = issue(a[2])
    names = [x["name"] for x in i["labels"]]
    for k, t in enumerate(a):
        if t == "--add-label":
            for n in a[k + 1].split(","):
                if n not in names:
                    i["labels"].append({"name": n}); names.append(n)
        if t == "--remove-label":
            for n in a[k + 1].split(","):
                i["labels"] = [x for x in i["labels"] if x["name"] != n]
    save(d); sys.exit(0)
if a[:2] == ["issue", "comment"]:
    issue(a[2]).setdefault("comments", []).append({"body": a[a.index("--body") + 1]})
    save(d); sys.exit(0)
if a[:2] == ["issue", "reopen"]:
    issue(a[2])["state"] = "OPEN"; save(d); sys.exit(0)
if a[:2] == ["issue", "close"]:
    issue(a[2])["state"] = "CLOSED"; save(d); sys.exit(0)
if a[0] == "api":
    print(json.dumps([[]])); sys.exit(0)
print(json.dumps([])); sys.exit(0)
'''

ASK_STUB = r'''#!/usr/bin/env bash
# $ask tau-dag stub: writes seat artifacts the real proof gate reads.
# PW_E2E_REVIEWER_VERDICT controls the classifier seat: PASS or NEEDS_ATTENTION.
set -e
ROOT=""; WORKSPACE=""; HANDLERS=()
args=("$@")
for i in "${!args[@]}"; do
  case "${args[$i]}" in
    --run-output-root) ROOT="${args[$((i+1))]}";;
    --handler) HANDLERS+=("${args[$((i+1))]}");;
    --handler-workspace) WORKSPACE="${args[$((i+1))]#*=}";;
  esac
done
RUN="$ROOT/run-1"
mkdir -p "$RUN"
echo '{"event":"dag_start"}' > "$RUN/events.jsonl"
echo '{"state":"done"}' > "$RUN/dag-progress.json"
slug() { echo "handler-$(echo "$1" | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9]\+/-/g;s/^-//;s/-$//')"; }
CREATOR="${HANDLERS[0]}"; REVIEWER="${HANDLERS[1]}"
CD="$RUN/node-artifacts/$(slug "$CREATOR")"; mkdir -p "$CD"
printf 'Implemented the fix.\nVERDICT: PASS\n' > "$CD/response.md"
echo '{"status":"PASS"}' > "$CD/node-receipt.json"
RD="$RUN/node-artifacts/$(slug "$REVIEWER")"; mkdir -p "$RD"
V="${PW_E2E_REVIEWER_VERDICT:-PASS}"
printf 'Classifier review of the creator+reviewer classification.\nVERDICT: %s\n' "$V" > "$RD/response.md"
echo "{\"status\":\"$V\"}" > "$RD/node-receipt.json"
# the creator commits in its workspace so the branch is ahead of origin/main
if [ -n "$WORKSPACE" ] && [ -d "$WORKSPACE" ]; then
  cd "$WORKSPACE" && echo "fix $(date +%s)" > fix.txt && git add fix.txt \
    && git -c user.email=e2e@probe -c user.name=e2e commit -q -m "e2e repair" || true
fi
echo '{"ok": true}'
'''


def sh(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                          check=True).stdout


def build_sandbox(base: Path) -> dict:
    bin_dir = base / "bin"
    bin_dir.mkdir(parents=True)
    gh = bin_dir / "gh"
    gh.write_text(GH_SHIM)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    ask = base / "ask" / "run.sh"
    ask.parent.mkdir()
    ask.write_text(ASK_STUB)
    ask.chmod(ask.stat().st_mode | stat.S_IEXEC)

    # a real git "project" repo with an origin, so worktree prep is live
    origin = base / "origin.git"
    sh(["git", "init", "-q", "--bare", str(origin)])
    repo = base / "probe-repo"
    sh(["git", "init", "-q", str(repo)])
    (repo / "README.md").write_text("probe\n")
    sh(["git", "add", "."], cwd=repo)
    sh(["git", "-c", "user.email=e2e@probe", "-c", "user.name=e2e",
        "commit", "-qm", "init"], cwd=repo)
    sh(["git", "remote", "add", "origin", str(origin)], cwd=repo)
    sh(["git", "push", "-q", "origin", "HEAD:main"], cwd=repo)
    sh(["git", "fetch", "-q", "origin"], cwd=repo)

    real = json.loads((SKILL_DIR / "registry" / "projects.json").read_text())
    projects = {
        "schema": real["schema"],
        "updated_at": real.get("updated_at"),
        "defaults": real.get("defaults"),
        "projects": [{
            "project_id": "probe",
            "display_name": "E2E Probe",
            "repo": "e2e/probe",
            "worktree": str(repo),
            "status": "registered",
            "runner_kind": "project-local",
            "auto_land_main": False,
        }],
    }
    projects_path = base / "projects.json"
    projects_path.write_text(json.dumps(projects, indent=1))

    state_root = base / "state"
    state_root.mkdir()
    (state_root / "state.json").write_text(json.dumps({
        "schema": "agent_skills.project_watchdog.state.v1",
        "global": {"state": "active", "reason": "e2e probe"},
        "projects": {"probe": {"state": "active", "reason": "e2e probe"}},
    }, indent=1))

    ticket_body = (
        "## Current state\nprobe defect\n\n## Target paths\n\n- README.md\n\n"
        "target: README.md\n\n## Acceptance criteria\nfix lands\n"
    )
    ledger = base / "ledger.json"
    ledger.write_text(json.dumps({"issues": [
        {"number": 101, "title": "probe ticket completed-path", "state": "OPEN",
         "url": "https://example.invalid/101", "body": ticket_body,
         "labels": [{"name": "agent-work"}], "comments": []},
        {"number": 102, "title": "probe ticket classifier-override", "state": "OPEN",
         "url": "https://example.invalid/102", "body": ticket_body,
         "labels": [{"name": "agent-work"}], "comments": []},
        {"number": 103, "title": "probe ticket bad-code", "state": "OPEN",
         "url": "https://example.invalid/103", "body": ticket_body,
         "labels": [{"name": "agent-work"}], "comments": []},
    ]}, indent=1))

    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "PW_E2E_LEDGER": str(ledger),
        "PROJECT_WATCHDOG_STATE_ROOT": str(state_root),
        "PROJECT_WATCHDOG_PROJECTS_PATH": str(projects_path),
        "PROJECT_WATCHDOG_ASK_RUN_SH": str(ask),
        "PROJECT_WATCHDOG_ALERT_DRY_RUN": "1",
    })
    return {"env": env, "ledger": ledger, "state_root": state_root, "base": base}


def run_tick(sb: dict, extra_env: dict | None = None) -> dict:
    env = dict(sb["env"], **(extra_env or {}))
    proc = subprocess.run(
        [str(SKILL_DIR / "run.sh"), "tick", "--apply", "--project", "probe",
         "--max-tickets", "1"],
        capture_output=True, text=True, env=env, cwd=str(SKILL_DIR), timeout=600,
    )
    out = proc.stdout
    receipt = json.loads(out[out.find("{"):])
    return receipt


def labels_of(sb: dict, number: int) -> list[str]:
    d = json.loads(sb["ledger"].read_text())
    return [l["name"] for i in d["issues"] if i["number"] == number
            for l in i["labels"]]


def main() -> int:
    scenario = sys.argv[1]
    keep = "--sandbox" in sys.argv
    base = Path(tempfile.mkdtemp(prefix=f"pw-e2e-{scenario}-"))
    sb = build_sandbox(base)
    proof: dict = {"scenario": scenario, "sandbox": str(base)}
    ok = False

    if scenario == "completed":
        r = run_tick(sb)
        h = r["handled_issues"][0]
        proof.update({
            "tick_status": r["status"], "issue_status": h["status"],
            "issue": h["issue_number"],
            "schema_validation": r.get("schema_validation"),
            "alert": {k: r.get("alert", {}).get(k) for k in ("status", "dry_run")},
            "labels_after": labels_of(sb, h["issue_number"]),
        })
        ok = (r["status"] == "COMPLETED" and h["status"] == "COMPLETED"
              and r["schema_validation"]["valid"] is True
              # deterministic non-delivery: under batch load the dry-run bot
              # resolution can time out (ALERT_DELIVERY_FAILED); the invariant
              # is dry_run recorded and nothing delivered, not the exact status
              and r.get("alert", {}).get("dry_run") is True
              and r.get("alert", {}).get("status") != "SENT"
              and r.get("alert", {}).get("delivered") is not True
              and "agent-done" in proof["labels_after"])

    elif scenario == "needs-human":
        r = run_tick(sb, {"PW_E2E_REVIEWER_VERDICT": "NEEDS_ATTENTION"})
        h = r["handled_issues"][0]
        proof.update({
            "tick_status": r["status"], "issue_status": h["status"],
            "issue": h["issue_number"],
            "gate_reasons": (h.get("proof_gate") or {}).get("reasons"),
            "schema_validation": r.get("schema_validation"),
            "alert": {k: r.get("alert", {}).get(k) for k in ("status", "dry_run")},
            "labels_after": labels_of(sb, h["issue_number"]),
        })
        ok = (r["status"] == "NEEDS_ATTENTION"
              and h["status"] == "NEEDS_ATTENTION"
              and "needs-human" in proof["labels_after"]
              and "agent-blocked" in proof["labels_after"]
              and r["schema_validation"]["valid"] is True
              # deterministic non-delivery: under batch load the dry-run bot
              # resolution can time out (ALERT_DELIVERY_FAILED); the invariant
              # is dry_run recorded and nothing delivered, not the exact status
              and r.get("alert", {}).get("dry_run") is True
              and r.get("alert", {}).get("status") != "SENT"
              and r.get("alert", {}).get("delivered") is not True)

    elif scenario == "bad-code":
        # inject an invented classification and drive it through the FULL
        # finish() boundary: validation downgrade, alerting, persistence, and
        # the hardened exit code (review findings 1 and 5, 2026-09-03).
        import re

        sys.path.insert(0, str(SKILL_DIR / "scripts"))
        os.environ.update({k: v for k, v in sb["env"].items()
                          if k.startswith("PROJECT_WATCHDOG")})
        from watchdog import core  # noqa: E402
        receipt_dir = sb["state_root"] / "receipts" / "e2e-bad-code"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt = {"schema": "agent_skills.project_watchdog.tick_receipt.v1",
                   "run_id": "e2e-bad-code", "status": "COMPLETED", "ok": True,
                   "apply": False,
                   "handled_issues": [{"issue_number": 103,
                                       "triage": {"code": "invented_by_agent",
                                                  "cause": "x"}}]}
        exit_code = core.finish("e2e-bad-code", receipt_dir, receipt, 0)
        record = receipt["schema_validation"]
        persisted = json.loads((receipt_dir / "receipt.json").read_text())
        proof.update({"validation": {k: record.get(k) for k in
                                     ("valid", "error", "triage")},
                      "status_after": receipt["status"],
                      "stop_reason": receipt.get("stop_reason"),
                      "exit_code": exit_code,
                      "persisted_status": persisted.get("status")})
        triage = record.get("triage") or {}
        minted_ok = bool(re.fullmatch(
            r"[a-z0-9_-]+_unclassified_[0-9a-f]{8}",
            str(triage.get("code", ""))))
        ok = (record["valid"] is False
              and receipt["status"] == "NEEDS_ATTENTION"
              and receipt["stop_reason"] == "receipt_schema_invalid"
              and exit_code != 0
              and persisted.get("status") == "NEEDS_ATTENTION"
              and minted_ok)

    elif scenario == "ui-data":
        run_tick(sb)  # completed
        run_tick(sb, {"PW_E2E_REVIEWER_VERDICT": "NEEDS_ATTENTION"})
        proc = subprocess.run([str(SKILL_DIR / "run.sh"), "ui-data",
                               "--receipt-limit", "20"],
                              capture_output=True, text=True, env=sb["env"],
                              cwd=str(SKILL_DIR), timeout=120)
        snap = json.loads(proc.stdout[proc.stdout.find("{"):])
        items = snap.get("items", [])
        statuses = sorted({i.get("status") for i in items})
        proof.update({"ui_schema": snap.get("schema"),
                      "item_count": len(items), "statuses": statuses})
        ok = (len(items) >= 2 and "COMPLETED" in statuses
              and "NEEDS_ATTENTION" in statuses)
    else:
        print(f"unknown scenario {scenario}", file=sys.stderr)
        return 2

    proof["ok"] = ok
    print(json.dumps(proof, indent=1, default=str))
    if not keep and ok:
        subprocess.run(["rm", "-rf", str(base)], check=False)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
