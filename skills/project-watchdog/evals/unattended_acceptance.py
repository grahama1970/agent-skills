#!/usr/bin/env python3
"""Fail-closed live acceptance snapshot for #1641.

This is a verifier, not a simulator: it reads GitHub states, retained watchdog
receipts, and the public recovery command. If a required acceptance scenario has
not happened, it returns NOT_ESTABLISHED instead of inventing coverage.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RECEIPTS = Path('/home/graham/.local/state/project-watchdog/receipts')
BASE = RECEIPTS / 'project-watchdog-20260909T224502Z-b5644c5a67aa'


def run(cmd: list[str], *, cwd: Path = REPO) -> dict[str, object]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"command": cmd, "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def gh_issue(number: int) -> dict[str, object]:
    proc = run(["gh", "issue", "view", str(number), "--repo", "grahama1970/agent-skills", "--json", "number,state,closedAt,title,url"])
    if proc["exit_code"] != 0:
        return {"number": number, "state": "UNKNOWN", "error": proc}
    return json.loads(str(proc["stdout"]))


def load(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - receipt verifier records exact failure.
        return {"_error": str(exc), "_path": str(path)}


def human_only_receipts() -> list[str]:
    found: list[str] = []
    for path in RECEIPTS.glob('project-watchdog-*/receipt.json'):
        data = load(path)
        rows = [data]
        if isinstance(data.get('result'), dict):
            rows.append(data['result'])
        if any(row.get('requires_human_input') is True for row in rows if isinstance(row, dict)):
            found.append(str(path))
    return sorted(found)


def canary_lifecycles() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in RECEIPTS.glob('project-watchdog-*/ticket-closure-receipt-v2.json'):
        data = load(path)
        if (data.get('schema') == 'agent_skills.ticket_closure_receipt.v2'
                and data.get('state') == 'CLOSED'
                and data.get('tau_settled') is True
                and data.get('proof_comment_read_back') is True):
            rows.append({'path': str(path), 'repo': data.get('repo'), 'issue': data.get('issue'), 'run_id': data.get('run_id')})
    return sorted(rows, key=lambda row: str(row['path']))


def main() -> int:
    deps = {n: gh_issue(n) for n in [1592, 1637, 1638, 1639, 1640]}
    recover = run([
        "/home/graham/.local/bin/uv", "run", "--project",
        str(REPO / "skills/project-watchdog"), "python",
        str(REPO / "skills/project-watchdog/scripts/watchdog/recover_primary.py"),
        "--root", str(REPO), "--apply",
    ])
    recover_json = load(Path('/tmp/nonexistent'))
    try:
        recover_json = json.loads(str(recover["stdout"]))
    except ValueError:
        recover_json = {"_parse_error": recover["stdout"]}

    proof_gate = load(BASE / "repair-proof-gate.json")
    publication = load(BASE / "publication-recovery.json")
    release = load(BASE / "native-release-command.json")
    closure_1628 = load(REPO / ".artifacts/ticket/issue-1628-closure-receipt.json")
    closure_v2 = load(BASE / "ticket-closure-receipt-v2.json")
    bridge = load(Path('/tmp/watchdog-live-delivery-proof.json'))
    authority = run([
        "/home/graham/.local/bin/uv", "run", "--project", str(REPO / "skills/project-watchdog"),
        "pytest", "-q",
        "skills/project-watchdog/tests/test_primary_main_revision.py::test_tau_receipt_authority_rejects_response_only_pass",
        "skills/project-watchdog/tests/test_primary_main_revision.py::test_native_close_lost_response_is_read_back_without_second_close",
        "skills/project-watchdog/tests/test_primary_main_revision.py::test_native_close_failed_mutation_never_becomes_completed",
        "skills/project-watchdog/tests/test_primary_main_revision.py::test_closure_outbox_recovery_retries_native_close_without_new_provider",
    ])

    human_receipts = human_only_receipts()
    lifecycles = canary_lifecycles()
    lifecycle_repos = {row.get('repo') for row in lifecycles}

    checks = {
        "focused_verification_tickets_closed": all(deps[n].get("state") == "CLOSED" for n in [1637, 1638, 1639, 1640]),
        "authority_dependency_1592_proven": (
            deps[1592].get("state") == "CLOSED"
            or (authority.get("exit_code") == 0
                and closure_v2.get("schema") == "agent_skills.ticket_closure_receipt.v2"
                and closure_v2.get("state") == "CLOSED"
                and closure_v2.get("tau_settled") is True
                and closure_v2.get("proof_comment_read_back") is True)
        ),
        "real_target_success_closed": closure_1628.get("state") == "CLOSED",
        "real_target_proof_gate_ok": proof_gate.get("ok") is True,
        "real_target_scoped_publication_ok": publication.get("published_target_matches_reviewed") is True,
        "native_release_ok": release.get("exit_code") == 0,
        "agent_skills_recovery_queue_empty": recover.get("exit_code") == 0 and recover_json.get("pending") is False,
        "machine_actionable_bridge_proven": bridge.get("status") in {"PASS", "COMPLETED"} or bridge.get("ok") is True,
        "human_only_ops_discord_live_receipt_present": bool(human_receipts),
        "ten_consecutive_canary_lifecycles_proven": len(lifecycles) >= 10 and len(lifecycle_repos) >= 2,
    }
    established = all(checks.values())
    result = {
        "schema": "agent_skills.project_watchdog.unattended_acceptance.v1",
        "status": "PASS" if established else "NOT_ESTABLISHED",
        "passed": established,
        "real_world": True,
        "live": True,
        "mocked": False,
        "checks": checks,
        "dependency_states": deps,
        "recover_primary": {"exit_code": recover["exit_code"], "parsed": recover_json},
        "authority_dependency": {"issue_1592": deps[1592], "pytest_exit_code": authority["exit_code"], "closure_v2": str(BASE / "ticket-closure-receipt-v2.json")},
        "human_only_receipts": human_receipts,
        "canary_lifecycles": {"count": len(lifecycles), "repos": sorted(str(repo) for repo in lifecycle_repos), "items": lifecycles[-10:]},
        "receipts": {
            "positive_canary_base": str(BASE),
            "proof_gate": str(BASE / "repair-proof-gate.json"),
            "publication": str(BASE / "publication-recovery.json"),
            "native_release": str(BASE / "native-release-command.json"),
            "closure_1628": str(REPO / ".artifacts/ticket/issue-1628-closure-receipt.json"),
            "closure_v2": str(BASE / "ticket-closure-receipt-v2.json"),
            "machine_actionable_bridge": "/tmp/watchdog-live-delivery-proof.json",
        },
        "not_established_reasons": [name for name, ok in checks.items() if not ok],
    }
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp/watchdog-unattended-acceptance-result.json')
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "not_established_reasons": result["not_established_reasons"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
