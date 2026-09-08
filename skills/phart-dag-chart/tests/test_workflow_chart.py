from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "watchdog-ticket-repair"


def run_chart(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROOT / "run.sh"), "chart", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_watchdog_receipt_defaults_to_workflow_view() -> None:
    result = run_chart(
        str(FIXTURE / "receipt.json"),
        "--evidence",
        str(FIXTURE / "issue.json"),
        "--evidence",
        str(FIXTURE / "repair-proof.json"),
        "--evidence",
        str(FIXTURE / "agentic-eval.json"),
        "--plain",
    )

    assert result.returncode == 0, result.stderr
    out = result.stdout
    for expected in [
        "ticket #1627",
        "issue_observed",
        "route_classified",
        "ticket_repair",
        "fixer: codex",
        "gpt-5.5-high",
        "reviewer: claude-fable-low",
        "ops_discord_alert",
        "READY",
        "PASS",
        "2/2",
        "ticket_closed=true",
        "COMPLETED",
        "ok=true",
    ]:
        assert expected in out
    assert "join" not in out
    assert "human" not in out


def test_issue_evidence_must_match_receipt_issue(tmp_path: Path) -> None:
    issue = json.loads((FIXTURE / "issue.json").read_text())
    issue["number"] = 1628
    bad_issue = tmp_path / "issue-1628.json"
    bad_issue.write_text(json.dumps(issue))

    result = run_chart(str(FIXTURE / "receipt.json"), "--evidence", str(bad_issue), "--plain")

    assert result.returncode == 1
    assert "evidence_mismatch" in result.stderr


def test_ticket_closed_false_does_not_render_close_success(tmp_path: Path) -> None:
    receipt = json.loads((FIXTURE / "receipt.json").read_text())
    receipt["handled_issues"][0]["ticket_closed"] = False
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))

    result = run_chart(str(path), "--plain")

    assert result.returncode == 0, result.stderr
    assert "native_close" not in result.stdout
    assert "ticket_closed=false" in result.stdout
