from __future__ import annotations

import json
import subprocess
from pathlib import Path


BATTLE = Path(__file__).resolve().parents[1]
REPO = BATTLE.parents[1]


def _campaign(path: Path, *, passed: bool, failures: list[dict] | None = None) -> None:
    failures = failures or []
    path.write_text(json.dumps({
        "schema": "battle.invariant_campaign_result.v1",
        "passed": passed,
        "cases_total": 2,
        "cases_passed": 2 - len(failures),
        "failures": failures,
    }), encoding="utf-8")


def test_invariant_report_requires_project_state_and_renders_exploits_table(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=True)
    project_state.write_text(json.dumps({"schema": "project_state.report.v1", "status": "TEST", "goals": ["keep PII out"]}), encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(campaign),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["schema"] == "create_report.report.v1"
    assert any(item["kind"] == "project-state" and item["path"] == str(project_state) for item in report["source_of_truth_inventory"])
    assert "## Exploits Table" in out_md.read_text(encoding="utf-8")
    assert "NO_JUDGE_CONFIRMED_EXPLOIT" in out_md.read_text(encoding="utf-8")


def test_invariant_report_lists_judge_confirmed_red_wins(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=False, failures=[{
        "case": "evil.csv",
        "expectation": "MUST_ACCEPT",
        "violations": ["policy value survives in output: 'Alice'"],
    }])
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(campaign),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["overall_finding"] == "Needs Changes"
    text = out_md.read_text(encoding="utf-8")
    assert "| campaign.json | evil.csv | MUST_ACCEPT | RED_WIN | policy value survives in output: 'Alice' |" in text
    assert "skills/create-report/run.sh validate" in json.dumps(report)
