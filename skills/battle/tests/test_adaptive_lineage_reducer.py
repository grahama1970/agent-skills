"""Deterministic, fixture-only contract tests for the adaptive-lineage reducer.

No live model, Docker, Tau, or network calls. Every specimen is a hand-built
fixture; the injected RecordedSpecimenProvider replays them in order.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battle_skill import adaptive_lineage as al  # noqa: E402

BATTLE_ID = "battle-adaptive-lineage"
RUN_ID = "run-adaptive-lineage-0001"


# --- exploit source fixtures (validated against technique_signature) ---------

G0_SOURCE = (
    "import tempfile\n"
    "from pathlib import Path\n"
    "from zipfile import ZipFile\n\n"
    "from app import import_zip\n\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    root = Path(tmp)\n"
    "    upload = root / 'evil.zip'\n"
    "    dest = root / 'imports'\n"
    "    with ZipFile(upload, 'w') as archive:\n"
    "        archive.writestr('../evil.txt', 'pwned')\n"
    "    written = import_zip(str(upload), str(dest))\n"
    "    escaped = Path(tmp) / 'evil.txt'\n"
    "    if escaped.exists():\n"
    "        print('ZIP_SLIP_CONFIRMED written=' + str(written))\n"
)

# method_replace: only app_load_mode + target_call_form move (import app; app.import_zip).
G1A_SOURCE = (
    "import tempfile\n"
    "from pathlib import Path\n"
    "from zipfile import ZipFile\n\n"
    "import app\n\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    root = Path(tmp)\n"
    "    upload = root / 'evil.zip'\n"
    "    dest = root / 'imports'\n"
    "    with ZipFile(upload, 'w') as archive:\n"
    "        archive.writestr('../evil.txt', 'pwned')\n"
    "    written = app.import_zip(str(upload), str(dest))\n"
    "    escaped = Path(tmp) / 'evil.txt'\n"
    "    if escaped.exists():\n"
    "        print('ZIP_SLIP_CONFIRMED written=' + str(written))\n"
)

# oracle_or_parameter_mutation: only traversal_representation moves (../ -> absolute).
G1B_SOURCE = G0_SOURCE.replace("'../evil.txt'", "'/tmp/evil.txt'")

# failure_guided_crossover of G1-A: app_load_mode + traversal + target move (novelty 3).
G2_SOURCE = (
    "import tempfile\n"
    "from pathlib import Path\n"
    "from zipfile import ZipFile\n\n"
    "import httpx\n\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    root = Path(tmp)\n"
    "    upload = root / 'evil.zip'\n"
    "    with ZipFile(upload, 'w') as archive:\n"
    "        archive.writestr('/tmp/evil.txt', 'pwned')\n"
    "    resp = httpx.post('http://localhost:8000/api/import', data={'p': str(upload)})\n"
    "    escaped = Path(tmp) / 'evil.txt'\n"
    "    if escaped.exists():\n"
    "        print('ZIP_SLIP_CONFIRMED status=' + str(resp))\n"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _specimen(
    specimen_id: str,
    source: str,
    operator: str | None,
    *,
    vuln: bool = True,
    bypass: bool = False,
    duration: float = 10.0,
    technique_delta: str = "mutated technique",
    parent_ref: str | None = "evidence-packet-parent",
    inputs: dict | None = None,
    judge_attempts: int | None = None,
) -> dict:
    spec: dict = {
        "specimen_id": specimen_id,
        "exploit_py": source,
        "source_sha256": _sha(source),
        "mutation_operator": operator,
        "technique_delta": technique_delta,
        "parent_evidence_packet_ref": parent_ref,
        "judge_outcome": {
            "vulnerable_original_confirmed": vuln,
            "patched_bypass": bypass,
            "duration_seconds": duration,
        },
    }
    if inputs is not None:
        spec["inputs"] = inputs
    if judge_attempts is not None:
        spec["judge_attempts"] = judge_attempts
    return spec


def _g2_bindings(selected_id: str = "G1-A") -> dict:
    return {
        "selected_g1_id": selected_id,
        "selected_g1_evidence_packet_ref": f"evidence-packet-{selected_id}",
        "g1a_outcome": {"vulnerable_original_confirmed": True},
        "g1b_outcome": {"vulnerable_original_confirmed": True},
        "selection_receipt_ref": f"{RUN_ID}-lineage-selection",
    }


def _happy_budget() -> al.AdaptiveLineageBudget:
    budget = al.AdaptiveLineageBudget()
    for _ in range(4):
        budget.record_red_specimen()
    budget.record_descendant_generation(2)
    budget.record_blue_artifact()
    budget.mark_g2_judge_complete()
    return budget


_AUTO = object()


def _valid_specimens() -> dict[str, dict]:
    return {
        "G0": _specimen("G0", G0_SOURCE, None, parent_ref=None),
        "G1-A": _specimen("G1-A", G1A_SOURCE, "method_replace", vuln=True, duration=20.0),
        "G1-B": _specimen("G1-B", G1B_SOURCE, "oracle_or_parameter_mutation", vuln=True, duration=10.0),
        "G2": _specimen(
            "G2",
            G2_SOURCE,
            "failure_guided_crossover",
            vuln=True,
            duration=15.0,
            parent_ref="evidence-packet-G1-A",
            inputs=_g2_bindings("G1-A"),
            judge_attempts=1,
        ),
    }


def _qualify(
    specimens_by_id: dict[str, dict],
    *,
    budget: al.AdaptiveLineageBudget | None = None,
    selection=_AUTO,
    extra_specimens: list[dict] | None = None,
) -> dict:
    """Rebuild fitness + selection from (possibly mutated) specimens, then qualify."""
    g0 = specimens_by_id.get("G0")
    g1a = specimens_by_id.get("G1-A")
    g1b = specimens_by_id.get("G1-B")
    g2 = specimens_by_id.get("G2")

    fitness: dict[str, dict] = {}
    if g1a is not None:
        fitness["G1-A"] = al.build_candidate_fitness_receipt(g0, g1a, battle_id=BATTLE_ID, run_id=RUN_ID)
    if g1b is not None:
        fitness["G1-B"] = al.build_candidate_fitness_receipt(g0, g1b, battle_id=BATTLE_ID, run_id=RUN_ID)

    if selection is _AUTO:
        sel = al.select_lineage(fitness["G1-A"], fitness["G1-B"], battle_id=BATTLE_ID, run_id=RUN_ID)
    else:
        sel = selection

    g2_outcome = None
    if g2 is not None and sel is not None:
        selected = specimens_by_id.get(sel["selected_id"])
        fitness["G2"] = al.build_candidate_fitness_receipt(selected, g2, battle_id=BATTLE_ID, run_id=RUN_ID)
        outcome = al._judge_outcome(g2)
        g2_outcome = {
            "judge_attempts": int(g2.get("judge_attempts", 1)),
            **outcome,
            "technique_signature": fitness["G2"]["technique_signature"],
        }

    ordered = [s for s in (g0, g1a, g1b, g2) if s is not None]
    if extra_specimens:
        ordered = ordered + extra_specimens

    return al.build_qualification_receipt(
        ordered,
        fitness,
        sel,
        g2_outcome,
        budget or _happy_budget(),
        battle_id=BATTLE_ID,
        run_id=RUN_ID,
    )


# --- selection tie-break determinism (a..e) ---------------------------------


def _fit(specimen_id: str, *, vuln: bool, bypass: bool, novelty: int, duration: float) -> dict:
    return {
        "specimen_id": specimen_id,
        "novelty_distance": novelty,
        "judge_outcome": {
            "vulnerable_original_confirmed": vuln,
            "patched_bypass": bypass,
            "duration_seconds": duration,
        },
    }


def test_selection_tiebreak_a_vulnerable_original() -> None:
    a = _fit("G1-A", vuln=True, bypass=False, novelty=1, duration=99.0)
    b = _fit("G1-B", vuln=False, bypass=True, novelty=9, duration=1.0)
    result = al.select_lineage(a, b, battle_id=BATTLE_ID, run_id=RUN_ID)
    assert result["selected_id"] == "G1-A"
    assert result["runner_up_id"] == "G1-B"
    assert result["deciding_criterion"] == "vulnerable_original_confirmed"
    decisive = [t for t in result["selection_trace"] if t["decisive"]]
    assert decisive[0]["criterion"] == "vulnerable_original_confirmed"


def test_selection_tiebreak_b_patched_bypass() -> None:
    a = _fit("G1-A", vuln=True, bypass=True, novelty=1, duration=99.0)
    b = _fit("G1-B", vuln=True, bypass=False, novelty=9, duration=1.0)
    result = al.select_lineage(a, b, battle_id=BATTLE_ID, run_id=RUN_ID)
    assert result["selected_id"] == "G1-A"
    assert result["deciding_criterion"] == "patched_bypass"


def test_selection_tiebreak_c_novelty_distance() -> None:
    a = _fit("G1-A", vuln=True, bypass=True, novelty=5, duration=99.0)
    b = _fit("G1-B", vuln=True, bypass=True, novelty=2, duration=1.0)
    result = al.select_lineage(a, b, battle_id=BATTLE_ID, run_id=RUN_ID)
    assert result["selected_id"] == "G1-A"
    assert result["deciding_criterion"] == "novelty_distance"


def test_selection_tiebreak_d_duration_seconds() -> None:
    a = _fit("G1-A", vuln=True, bypass=True, novelty=3, duration=5.0)
    b = _fit("G1-B", vuln=True, bypass=True, novelty=3, duration=9.0)
    result = al.select_lineage(a, b, battle_id=BATTLE_ID, run_id=RUN_ID)
    assert result["selected_id"] == "G1-A"
    assert result["deciding_criterion"] == "duration_seconds"


def test_selection_tiebreak_e_specimen_id() -> None:
    a = _fit("G1-A", vuln=True, bypass=True, novelty=3, duration=5.0)
    b = _fit("G1-B", vuln=True, bypass=True, novelty=3, duration=5.0)
    result = al.select_lineage(a, b, battle_id=BATTLE_ID, run_id=RUN_ID)
    assert result["selected_id"] == "G1-A"
    assert result["deciding_criterion"] == "specimen_id"


def test_selection_requires_both_g1_fitness() -> None:
    a = _fit("G1-A", vuln=True, bypass=True, novelty=3, duration=5.0)
    with pytest.raises(ValueError):
        al.select_lineage(a, None, battle_id=BATTLE_ID, run_id=RUN_ID)
    with pytest.raises(ValueError):
        al.select_lineage(None, a, battle_id=BATTLE_ID, run_id=RUN_ID)


# --- candidate fitness receipt ----------------------------------------------


def test_candidate_fitness_receipt_shape() -> None:
    specs = _valid_specimens()
    receipt = al.build_candidate_fitness_receipt(specs["G0"], specs["G1-A"], battle_id=BATTLE_ID, run_id=RUN_ID)
    assert receipt["schema"] == "battle.candidate_fitness_receipt.v1"
    assert receipt["status"] == "PASS"
    assert receipt["delta_status"] == "PASS"
    assert receipt["novelty_distance"] == 2
    assert receipt["delta_validation"]["schema"] == "battle.technique_delta_validation.v1"
    assert receipt["source_sha256_matches"] is True


# --- qualification PASS ------------------------------------------------------


def test_qualification_pass_on_valid_lineage() -> None:
    result = _qualify(_valid_specimens())
    assert result["schema"] == "battle.adaptive_lineage_qualification.v1"
    assert result["status"] == "PASS"
    assert result["stop_condition"] is None
    assert result["reasons"] == []
    assert result["selected_id"] == "G1-A"
    assert result["runner_up_id"] == "G1-B"
    assert all(c["ok"] for c in result["checks"])


# --- fail-closed stop conditions --------------------------------------------


def test_fail_red_3_present() -> None:
    specs = _valid_specimens()
    extra = _specimen("G3", G2_SOURCE, "failure_guided_crossover", parent_ref="evidence-packet-G2")
    result = _qualify(specs, extra_specimens=[extra])
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "red_3_present"


def test_fail_invalid_mutation_contract() -> None:
    specs = _valid_specimens()
    specs["G1-A"]["technique_delta"] = "   "  # empty delta => invalid contract
    result = _qualify(specs)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "invalid_mutation_contract"


def test_fail_duplicate_g1_signature() -> None:
    specs = _valid_specimens()
    specs["G1-B"]["exploit_py"] = G1A_SOURCE  # identical signature to G1-A
    specs["G1-B"]["source_sha256"] = _sha(G1A_SOURCE)
    result = _qualify(specs)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "duplicate_g1_signature"


def test_fail_g1_delta_validation_failed() -> None:
    specs = _valid_specimens()
    # G1-A is byte-identical to G0 => no dimension changed => delta FAIL, while the
    # mutation contract (operator/delta/parent-ref) stays structurally valid.
    specs["G1-A"]["exploit_py"] = G0_SOURCE
    specs["G1-A"]["source_sha256"] = _sha(G0_SOURCE)
    result = _qualify(specs)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "g1_delta_validation_failed"


def test_fail_both_g1_failed_vulnerable_original() -> None:
    specs = _valid_specimens()
    specs["G1-A"]["judge_outcome"]["vulnerable_original_confirmed"] = False
    specs["G1-B"]["judge_outcome"]["vulnerable_original_confirmed"] = False
    result = _qualify(specs)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "both_g1_failed_vulnerable_original"


def test_fail_selection_receipt_missing() -> None:
    specs = _valid_specimens()
    result = _qualify(specs, selection=None)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "selection_receipt_missing"


def test_fail_missing_g2_bindings() -> None:
    specs = _valid_specimens()
    del specs["G2"]["inputs"]["selection_receipt_ref"]  # drop a required binding
    result = _qualify(specs)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "g2_bindings_missing"


def test_fail_g2_judge_attempt_count() -> None:
    specs = _valid_specimens()
    specs["G2"]["judge_attempts"] = 2
    result = _qualify(specs)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "g2_judge_attempt_count_invalid"


def test_fail_g2_reproduced_rejected_signature() -> None:
    specs = _valid_specimens()
    # G2 reproduces the rejected runner-up (G1-B) signature exactly.
    specs["G2"]["exploit_py"] = G1B_SOURCE
    specs["G2"]["source_sha256"] = _sha(G1B_SOURCE)
    result = _qualify(specs)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "g2_reproduced_rejected_signature"


def test_fail_budget_overrun() -> None:
    specs = _valid_specimens()
    budget = _happy_budget()
    budget.record_red_specimen()  # 5 > 4 (red-3)
    result = _qualify(specs, budget=budget)
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "budget_overrun"


# --- budget accounting -------------------------------------------------------


def test_budget_within_envelope() -> None:
    budget = _happy_budget()
    over, reasons = budget.overrun()
    assert over is False
    assert reasons == []


def test_budget_overrun_detected_with_reasons() -> None:
    budget = al.AdaptiveLineageBudget()
    budget.record_primary_scillm_call(11)
    budget.record_http_completion(15)
    budget.record_red_specimen(5)
    budget.record_descendant_generation(3)
    budget.record_blue_artifact(2)
    budget.record_seconds(1500.0)
    over, reasons = budget.overrun()
    assert over is True
    assert len(reasons) == 6
    assert any("red-3" in r for r in reasons)


# --- orchestration seam ------------------------------------------------------


def test_orchestration_pass_and_stop_after_g2(tmp_path: Path) -> None:
    specs = _valid_specimens()
    provider = al.RecordedSpecimenProvider(
        {
            "G0": specs["G0"],
            "G1-A": specs["G1-A"],
            "G1-B": specs["G1-B"],
            "G2": specs["G2"],
        }
    )
    budget = al.AdaptiveLineageBudget()
    result = al.run_adaptive_lineage_qualification(
        provider,
        battle_id=BATTLE_ID,
        run_id=RUN_ID,
        out_dir=tmp_path,
        budget=budget,
    )
    assert result["status"] == "PASS"
    assert result["stop_condition"] is None
    # stop-after-G2: exactly four stages requested, never a fifth.
    assert provider.requested_stages == ["G0", "G1-A", "G1-B", "G2"]
    assert (tmp_path / "adaptive-lineage-qualification.json").exists()
    # Exactly two descendant generations (gen 1 = G1 pair, gen 2 = G2), owned
    # solely by the orchestrator. Regression guard against the provider also
    # counting per-descendant, which overran the budget (5 > 2) on a live run.
    assert budget.descendant_generations == 2


def test_orchestration_pass_g2_context_binds_selection(tmp_path: Path) -> None:
    specs = _valid_specimens()
    provider = al.RecordedSpecimenProvider(specs)
    al.run_adaptive_lineage_qualification(
        provider, battle_id=BATTLE_ID, run_id=RUN_ID, out_dir=tmp_path
    )
    g2_context = provider.request_contexts[-1]
    assert g2_context["selection_receipt"]["selected_id"] == "G1-A"
    assert "g1a_outcome" in g2_context and "g1b_outcome" in g2_context


def test_orchestration_pre_g2_stop_halts_provider(tmp_path: Path) -> None:
    specs = _valid_specimens()
    # Duplicate G1 signatures => pre-G2 fail-closed stop; G2 must never be requested.
    # Keep G1-B's delta valid (operator matches its actual change) so the duplicate
    # signature is the isolated stop rather than a delta failure.
    specs["G1-B"]["exploit_py"] = G1A_SOURCE
    specs["G1-B"]["source_sha256"] = _sha(G1A_SOURCE)
    specs["G1-B"]["mutation_operator"] = "method_replace"
    provider = al.RecordedSpecimenProvider(
        {"G0": specs["G0"], "G1-A": specs["G1-A"], "G1-B": specs["G1-B"]}
    )
    result = al.run_adaptive_lineage_qualification(
        provider, battle_id=BATTLE_ID, run_id=RUN_ID, out_dir=tmp_path
    )
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "duplicate_g1_signature"
    assert "G2" not in provider.requested_stages


def test_live_provider_fails_closed_without_live_config() -> None:
    # The LIVE provider is wired (see test_live_specimen_provider_wiring.py), but
    # it fails closed when the orchestrator has not supplied the live arena config,
    # so no caller can accidentally drive it without a real run set up.
    provider = al.LiveTauSpecimenProvider()
    with pytest.raises(ValueError):
        provider.request(stage="G0", context={})


def test_live_provider_rejects_unknown_stage() -> None:
    provider = al.LiveTauSpecimenProvider(out_dir="/tmp/x")
    with pytest.raises(ValueError):
        provider.request(stage="G3", context={})
