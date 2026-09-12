from __future__ import annotations

import json
from pathlib import Path

from battle_skill.invariant_campaign import run_campaign


HERE = Path(__file__).resolve().parent
GEN_EXP = str(HERE / "fixtures/mini_expectation_generator.py")
JUDGE = str(HERE.parent / "fixtures/reference-judges/no_data_leak_judge.py")
FUNC = str(HERE.parent / "fixtures/reference-judges/functional_anonymize_judge.py")


def test_campaign_emits_typed_case_receipts_and_aggregate_gate() -> None:
    r = run_campaign(
        GEN_EXP,
        "mkdir -p {output}/corpus && for f in {input}/corpus/*; do sed 's/5551234567/Person-A/g' \"$f\" > {output}/corpus/$(basename \"$f\"); done && printf '{{\"status\":\"ready\"}}' > {output}/report.json",
        JUDGE,
        output_subdir="corpus",
        functional_judge=FUNC,
    )

    assert r.case_receipts
    receipt = next(c for c in r.case_receipts if c["case_id"] == "must-accept-case")
    assert receipt["schema"] == "battle.case_receipt.v1"
    assert receipt["fixture_precheck"]["status"] == "PASS"
    assert receipt["execution"]["kind"] == "ACCEPT"
    assert receipt["security_judge"]["status"] == "PASS"
    assert receipt["functional_judge"]["status"] == "PASS"
    assert r.aggregation["schema"] == "battle.campaign_aggregate.v1"
    assert r.aggregation["executed_count"] == len(r.case_receipts)


def test_delete_everything_target_fails_must_accept_functionality() -> None:
    r = run_campaign(
        GEN_EXP,
        "mkdir -p {output}/corpus && echo '{{}}' > {output}/report.json",
        JUDGE,
        output_subdir="corpus",
        functional_judge=FUNC,
    )

    assert r.passed is False
    assert r.aggregation["unexpected_rejected_count"] >= 1
    assert any("required-accept-case-rejected" in v for f in r.failures for v in f["violations"])


def test_fixture_without_policy_witness_fails_before_target_execution(tmp_path: Path) -> None:
    gen = tmp_path / "gen.py"
    gen.write_text(
        "import json\nfrom pathlib import Path\n"
        "def generate(work_dir, params):\n"
        "    d = Path(work_dir) / 'case'; (d / 'corpus').mkdir(parents=True)\n"
        "    (d / 'policy.json').write_text(json.dumps({'sensitive_values': [{'value': 'Alice'}]}))\n"
        "    (d / 'corpus' / 'd.txt').write_text('only Bob here')\n"
        "    yield 'missing-witness', str(d), 'MUST_ACCEPT'\n",
        encoding="utf-8",
    )

    r = run_campaign(str(gen), "echo should-not-run >&2; exit 1", JUDGE, output_subdir="corpus")

    receipt = r.case_receipts[0]
    assert r.passed is False
    assert receipt["schema"] == "battle.case_receipt.v1"
    assert receipt["fixture_precheck"]["status"] == "FAIL"
    assert receipt["execution"]["kind"] == "NOT_RUN"
    assert receipt["capture_complete"] is False
    assert "fixture_precheck:no_policy_value_witness" in receipt["violations"]
