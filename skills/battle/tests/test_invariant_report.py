from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from rich.console import Console


BATTLE = Path(__file__).resolve().parents[1]
REPO = BATTLE.parents[1]


def _report_module():
    path = BATTLE / "scripts" / "render_invariant_campaign_report.py"
    spec = importlib.util.spec_from_file_location("battle_invariant_report_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _campaign(path: Path, *, passed: bool, case_log: list[dict] | None = None) -> None:
    case_log = case_log or []
    failures = [case for case in case_log if case.get("passed") is not True]
    path.write_text(json.dumps({
        "schema": "battle.invariant_campaign_result.v1",
        "passed": passed,
        "cases_total": len(case_log),
        "cases_passed": len(case_log) - len(failures),
        "case_log": case_log,
        "failures": failures,
    }), encoding="utf-8")


def test_invariant_report_requires_project_state_and_renders_contractual_exploit_rows(tmp_path: Path) -> None:
    campaign = tmp_path / "brief-fuzz-campaign.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=True, case_log=[{
        "case": "contractual-email-json",
        "expectation": "MUST_ACCEPT",
        "passed": True,
        "execution": {"exit_code": 0},
    }])
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
    assert "exploits_table_rows=1" in json.dumps(report)
    text = out_md.read_text(encoding="utf-8")
    assert "## Exploits Table" in text
    assert "contractual rows are the frozen acceptance-contract floor" in text
    assert "| Scope | Contractual? | Adaptive lineage? | Case | Exploit / attack | Why chosen | Expectation | Result | Judge evidence |" in text
    assert "| contractual | yes | no | contractual-email-json | attack case: contractual email json | required by frozen acceptance contract | MUST_ACCEPT | ACCEPTED_CLEAN | Judge passed; no policy value survived. |" in text


def test_invariant_report_lists_judge_confirmed_red_wins(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=False, case_log=[{
        "case": "evil.csv",
        "expectation": "MUST_ACCEPT",
        "passed": False,
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
    assert "| campaign | no | no | evil.csv | attack case: evil.csv | chosen to search beyond the written contract for realistic release-boundary leaks | MUST_ACCEPT | RED_WIN | policy value survives in output: 'Alice' |" in text
    assert "skills/create-report/run.sh validate" in json.dumps(report)


def test_invariant_report_prefers_typed_case_receipts(tmp_path: Path) -> None:
    campaign = tmp_path / "brief-cases.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    campaign.write_text(json.dumps({
        "schema": "battle.invariant_campaign_result.v1",
        "passed": True,
        "cases_total": 1,
        "cases_passed": 1,
        "case_log": [],
        "case_receipts": [{
            "schema": "battle.case_receipt.v1",
            "case_id": "json-string",
            "expectation": "MUST_ACCEPT",
            "verdict": "PASS",
            "execution": {"kind": "ACCEPT", "exit_code": 0},
            "violations": [],
        }],
    }), encoding="utf-8")
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
    assert "| contractual | yes | no | json-string | policy value in a JSON string field" in out_md.read_text(encoding="utf-8")


def test_invariant_report_marks_adaptive_lineage_rows(tmp_path: Path) -> None:
    campaign = tmp_path / "brief-fuzz-campaign.json"
    lineage = tmp_path / "lineage.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=True, case_log=[{
        "case": "adv-formatted-phone-json-integer",
        "expectation": "MUST_ACCEPT",
        "passed": True,
        "execution": {"exit_code": 0},
    }])
    lineage.write_text(json.dumps({
        "schema": "battle.invariant_adaptive_lineage.v1",
        "status": "PASS",
        "target": "oai-trial",
        "red_wins": [{"case": "adv-formatted-phone-json-integer", "violations": ["old leak"]}],
        "fixed_cases": ["adv-formatted-phone-json-integer"],
        "replay_passed": True,
    }), encoding="utf-8")
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(campaign),
        "--adaptive-lineage", str(lineage),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert "adaptive_lineage_rows=1" in json.dumps(report)
    assert any(item["kind"] == "battle-adaptive-lineage" and item["path"] == str(lineage) for item in report["source_of_truth_inventory"])
    assert "yes: adaptive Red win fixed/replayed for oai-trial" in out_md.read_text(encoding="utf-8")


def test_invariant_report_terminal_summary_is_plain_battle_story(tmp_path: Path) -> None:
    contract = tmp_path / "contract-floor-campaign.json"
    beyond = tmp_path / "beyond-contract-campaign.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(contract, passed=True, case_log=[
        {
            "case": "adv-formatted-phone-json-integer",
            "expectation": "MUST_ACCEPT",
            "passed": True,
            "execution": {"kind": "ACCEPT", "exit_code": 0},
        },
        {
            "case": "adv-leading-zero-json-integer",
            "expectation": "MUST_REJECT",
            "passed": True,
            "execution": {"kind": "REJECT", "exit_code": 1},
        },
    ])
    _campaign(beyond, passed=False, case_log=[
        {
            "case": "bb-json-object-key",
            "expectation": "MUST_REJECT",
            "passed": True,
            "execution": {"kind": "REJECT", "exit_code": 1},
        },
        {
            "case": "bb-filename-value",
            "expectation": "MUST_REJECT",
            "passed": False,
            "violations": ["policy value survives in filename: Alice"],
        },
    ])
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(contract),
        "--campaign", str(beyond),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--terminal-summary",
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    json.loads(proc.stdout)
    terminal = proc.stderr
    assert "Battle report: oai-trial" in terminal
    assert "Contract floor:" in terminal
    assert "2 acceptance-floor cases: 1 accepted clean, 1 fail-closed, 0 RED_WIN." in terminal
    assert "Red pressure:" in terminal
    assert "2 beyond-contract probes: 0 accepted clean, 1 fail-closed, 1 RED_WIN." in terminal
    assert "Scorekeeper call:" in terminal
    assert "4 total cases; 1 accepted clean; 2 stopped fail-closed; 1 RED_WIN." in terminal
    assert "RED_WIN blocks release until Blue patches and Judge replay passes." in terminal
    assert "Case table:" in terminal
    assert "Scope" in terminal and "Case" in terminal and "Expect" in terminal and "Result" in terminal and "Attack" in terminal and "Evidence" in terminal
    assert "contractual     adv-formatted-phone-json-integer" in terminal
    assert "MUST_ACCEPT" in terminal and "ACCEPTED_CLEAN" in terminal
    assert "beyond-contract bb-json-object-key" in terminal
    assert "BLOCKED_FAIL_CLOSED" in terminal
    assert "beyond-contract bb-filename-value" in terminal
    assert "MUST_REJECT" in terminal and "RED_WIN" in terminal and "policy value survives in filename: Alice" in terminal
    assert "Highlight plays:" in terminal
    assert "bb-filename-value: Red tried policy value hidden in the released filename; result RED_WIN" in terminal
    assert "Next playbook:" in terminal
    assert "research similar exploit families, freeze deterministic variants, patch, and replay" in terminal
    assert "Caveats:" in terminal
    assert "This is bounded Battle evidence, not proof that every possible exploit is absent." in terminal
    assert "project-state JSON artifact" not in terminal
    assert "Judge passed; no policy value survived." not in terminal


def test_invariant_report_typer_terminal_table_alias_keeps_stdout_json(tmp_path: Path) -> None:
    campaign = tmp_path / "contract-floor-campaign.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=True, case_log=[{
        "case": "json-string",
        "expectation": "MUST_ACCEPT",
        "passed": True,
        "execution": {"kind": "ACCEPT", "exit_code": 0},
    }])
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(campaign),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--terminal-table",
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["schema"] == "battle.invariant_report_result.v1"
    assert "Case table:" in proc.stderr
    assert "json-string" in proc.stderr
    assert "ACCEPTED_CLEAN" in proc.stderr
    assert "\u001b[" not in proc.stderr


def test_invariant_report_terminal_cards_render_long_case_blocks(tmp_path: Path) -> None:
    campaign = tmp_path / "beyond-contract-campaign.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=False, case_log=[{
        "case": "bb-filename-value",
        "expectation": "MUST_REJECT",
        "passed": False,
        "violations": ["policy value survives in filename: Alice"],
    }])
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(campaign),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--terminal-cards",
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["schema"] == "battle.invariant_report_result.v1"
    terminal = proc.stderr
    assert "==============" in terminal
    assert "Scope: beyond-contract" in terminal
    assert "Case: bb-filename-value" in terminal
    assert "Expect: MUST_REJECT" in terminal
    assert "Result: RED_WIN" in terminal
    assert "Example: bb-filename-value: policy value hidden in the released filename" in terminal
    assert "Why Battle checks this: release artifacts can leak through encoding or path surfaces" in terminal
    assert "Related research: not recorded in case receipt" in terminal
    assert "Judge evidence: policy value survives in filename: Alice" in terminal


def test_invariant_report_terminal_cards_preserve_typed_receipt_fields(tmp_path: Path) -> None:
    campaign = tmp_path / "brief-cases.json"
    project_state = tmp_path / "project-state.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    campaign.write_text(json.dumps({
        "schema": "battle.invariant_campaign_result.v1",
        "passed": True,
        "cases_total": 1,
        "cases_passed": 1,
        "case_receipts": [{
            "schema": "battle.case_receipt.v1",
            "case_id": "typed-case",
            "description": "typed description",
            "example": "typed example from receipt",
            "why_chosen": "typed rationale from receipt",
            "research_refs": [{"title": "Brave result", "url": "https://example.test/research"}],
            "expectation": "MUST_ACCEPT",
            "verdict": "PASS",
            "execution": {"kind": "ACCEPT", "exit_code": 0},
            "violations": [],
        }],
    }), encoding="utf-8")
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(campaign),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--terminal-cards",
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    terminal = proc.stderr
    assert "Example: typed example from receipt" in terminal
    assert "Why Battle checks this: typed rationale from receipt" in terminal
    assert "Related research: Brave result (https://example.test/research)" in terminal
    assert "Judge evidence: target processed the case; Judge found no released policy value" in terminal


def test_invariant_report_terminal_cards_accept_live_receipt_shapes(tmp_path: Path) -> None:
    contract = tmp_path / "acceptance-floor-latest" / "production-adapter-receipt.json"
    beyond = tmp_path / "runs" / "latest" / "beyond-contract-receipt.json"
    project_state = tmp_path / "project-state.md"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    contract.parent.mkdir(parents=True)
    beyond.parent.mkdir(parents=True)
    contract_campaign = {
        "schema": "battle.campaign_contract_receipt.v1",
        "verdict": "PASS",
        "aggregation": {"cases_total": 1, "cases_passed": 1},
        "case_receipts": [{
            "schema": "battle.case_receipt.v1",
            "case_id": "json-string",
            "expectation": "MUST_ACCEPT",
            "verdict": "PASS",
            "execution": {"kind": "ACCEPT", "exit_code": 0},
            "violations": [],
        }],
    }
    beyond_campaign = {
        "schema": "battle.campaign_contract_receipt.v1",
        "verdict": "PASS",
        "request": {"generator": "anon_beyond_brief_matrix.py"},
        "aggregation": {"cases_total": 1, "cases_passed": 1},
        "case_receipts": [{
            "schema": "battle.case_receipt.v1",
            "case_id": "bb-json-object-key",
            "expectation": "MUST_REJECT",
            "verdict": "PASS",
            "execution": {"kind": "REJECT", "exit_code": 1},
            "violations": [],
        }],
    }
    contract.write_text(json.dumps({
        "schema": "battle.production_adapter_round.v1",
        "status": "PASS",
        "acceptance_floor": {"case_map": {"AC-001": ["json-string"]}},
        "campaign": contract_campaign,
    }), encoding="utf-8")
    beyond.write_text(json.dumps(beyond_campaign), encoding="utf-8")
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(contract),
        "--campaign", str(beyond),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--terminal-cards",
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["status"] == "PASS"
    assert "## Acceptance contract floor" in proc.stderr
    assert "Scope: contractual" in proc.stderr
    assert "Case: json-string" in proc.stderr
    assert "Acceptance parent: AC-001" in proc.stderr
    assert "## Beyond-contract exploits" in proc.stderr
    assert "Scope: beyond-contract" in proc.stderr
    assert "Case: bb-json-object-key" in proc.stderr
    assert "Acceptance parent: not recorded in case receipt" in proc.stderr
    assert "Related research: not recorded in case receipt" in proc.stderr


def test_invariant_report_terminal_cards_group_adaptive_lineage(tmp_path: Path) -> None:
    campaign = tmp_path / "beyond-contract-campaign.json"
    lineage = tmp_path / "lineage.json"
    project_state = tmp_path / "project-state.md"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=True, case_log=[{
        "case": "bb-filename-value",
        "expectation": "MUST_REJECT",
        "passed": True,
        "execution": {"kind": "REJECT", "exit_code": 1},
    }])
    lineage.write_text(json.dumps({
        "schema": "battle.invariant_adaptive_lineage.v1",
        "target": "oai-trial",
        "red_wins": [{"case": "bb-filename-value"}],
        "fixed_cases": ["bb-filename-value"],
    }), encoding="utf-8")
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(campaign),
        "--adaptive-lineage", str(lineage),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--terminal-cards",
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "## Adaptive lineage" in proc.stderr
    assert "Case: bb-filename-value" in proc.stderr
    assert "Adaptive lineage: yes: adaptive Red win fixed/replayed for oai-trial" in proc.stderr


def test_invariant_report_terminal_cards_render_lineage_only_receipt(tmp_path: Path) -> None:
    campaign = tmp_path / "beyond-contract-campaign.json"
    lineage = tmp_path / "lineage.json"
    project_state = tmp_path / "project-state.md"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    _campaign(campaign, passed=True, case_log=[{
        "case": "bb-filename-value",
        "expectation": "MUST_REJECT",
        "passed": True,
        "execution": {"kind": "REJECT", "exit_code": 1},
    }])
    lineage.write_text(json.dumps({
        "schema": "battle.invariant_adaptive_lineage.v1",
        "target": "battle-004",
        "red_wins": [{"case": "battle-004-adaptive-lineage"}],
        "fixed_cases": ["battle-004-adaptive-lineage"],
    }), encoding="utf-8")
    project_state.write_text("# Project State\ncurrent\n", encoding="utf-8")

    proc = subprocess.run([
        str(BATTLE / "run.sh"), "invariant-report",
        "--campaign", str(campaign),
        "--adaptive-lineage", str(lineage),
        "--project-state", str(project_state),
        "--target", "oai-trial",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--terminal-cards",
    ], cwd=REPO, capture_output=True, text=True, check=False)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "## Adaptive lineage" in proc.stderr
    assert "Scope: adaptive-lineage" in proc.stderr
    assert "Case: battle-004-adaptive-lineage" in proc.stderr
    assert "Why Battle checks this: adaptive lineage receipt supplied with live Red/Blue replay proof" in proc.stderr


def test_invariant_report_rich_terminal_table_path_renders_colored_rows(monkeypatch, capsys) -> None:
    module = _report_module()
    monkeypatch.setattr(
        module,
        "Console",
        lambda **kwargs: Console(force_terminal=True, color_system="standard", width=180, **kwargs),
    )
    module._print_rich_terminal_summary("oai-trial", [
        {
            "scope": "contractual",
            "case": "json-string",
            "expectation": "MUST_ACCEPT",
            "result": "ACCEPTED_CLEAN",
            "description": "policy value in a JSON string field",
            "evidence": "Judge passed; no policy value survived.",
        },
        {
            "scope": "beyond-contract",
            "case": "bb-filename-value",
            "expectation": "MUST_REJECT",
            "result": "RED_WIN",
            "description": "policy value hidden in the released filename",
            "evidence": "policy value survives in filename: Alice",
        },
    ])

    terminal = capsys.readouterr().err
    assert "\u001b[" in terminal
    assert "Battle report:" in terminal
    assert "Case table" in terminal
    assert "json-string" in terminal
    assert "ACCEPTED_CLEAN" in terminal
    assert "bb-filename-value" in terminal
    assert "RED_WIN" in terminal
    assert "policy value survives in filename: Alice" in terminal
