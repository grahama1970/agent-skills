"""Negative fixtures for the current-state consistency checker.

The live proof for this checker is that it caught real drift on the real
repository (a PASS speaker-recognition receipt alongside an
``active_blockers`` entry reading ``resemblyzer=false``, and a README paragraph
still instructing an already-receipted ledger hardening). These fixtures pin the
fail-closed behaviour so that drift cannot pass silently again.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load("check_current_state_consistency")


def _status_doc() -> dict:
    """A projection consistent with the real receipts on disk."""
    doc = json.loads((ROOT / "CURRENT_STATUS.json").read_text(encoding="utf-8"))
    return doc


def _run(tmp_path: Path, doc: dict):
    path = tmp_path / "CURRENT_STATUS.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    args = type("Args", (), {"current_status": path, "out": None})()
    return checker.run(args)


def _rules(receipt) -> set[str]:
    return {row["rule"] for row in receipt["mismatches"]}


def test_real_repository_state_is_consistent():
    args = type("Args", (), {"current_status": ROOT / "CURRENT_STATUS.json", "out": None})()
    got = checker.run(args)
    assert got["status"] == "PASS_CURRENT_STATE_CONSISTENT", got["mismatches"]


def test_pass_receipt_contradicted_by_active_blocker_blocks(tmp_path):
    doc = _status_doc()
    doc["active_blockers"].append(
        "P2.4 speaker-recognition preflight is blocked: resemblyzer=false."
    )

    got = _run(tmp_path, doc)

    assert got["status"] == "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS"
    assert "blocker_contradicts_accepted_receipt" in _rules(got)


def test_next_step_naming_accepted_stage_blocks(tmp_path):
    doc = _status_doc()
    doc["next_step"]["ordered_steps"].insert(
        0, "Resolve the P2.4 speaker-recognition backend blocker with resemblyzer."
    )

    got = _run(tmp_path, doc)

    assert got["status"] == "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS"
    assert "next_step_names_accepted_stage" in _rules(got)


def test_next_step_reopening_live_chain_receipt_blocks(tmp_path):
    doc = _status_doc()
    doc["next_step"]["ordered_steps"].insert(
        0, "Write reports/goal_v5/continuity/live_chain/RECEIPT.json with the positive chain."
    )

    got = _run(tmp_path, doc)

    assert got["status"] == "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS"
    assert "next_step_names_accepted_stage" in _rules(got)


def test_next_step_reopening_session_arc_bias_blocks(tmp_path):
    doc = _status_doc()
    doc["next_step"]["ordered_steps"].insert(
        0, "Publish the persona arc-bias artifact under session_arc_bias.v1."
    )

    got = _run(tmp_path, doc)

    assert got["status"] == "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS"
    assert "next_step_names_accepted_stage" in _rules(got)


def test_receipt_hash_mismatch_blocks(tmp_path):
    doc = _status_doc()
    doc["continuity_state"]["latest_voice_recognition_preflight_receipt_sha256"] = "sha256:" + "0" * 64

    got = _run(tmp_path, doc)

    assert got["status"] == "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS"
    assert "receipt_hash_mismatch" in _rules(got)


def test_retracted_pctom_result_as_current_positive_blocks(tmp_path):
    doc = _status_doc()
    doc["pctom_r_workstream"]["status"] = "CONFIDENCE_BOUNDED_BENEFIT_PROVEN"
    doc["pctom_r_workstream"]["unverified"] = [
        "confidence-bounded counterfactual-dreaming planning advantage"
    ]

    got = _run(tmp_path, doc)

    assert got["status"] == "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS"
    assert "retracted_result_presented_as_current" in _rules(got)


def test_wrapped_prose_contradiction_is_detected(tmp_path):
    """Markdown hard-wrapping must not hide a contradiction.

    The original per-line matcher missed the README's
    "harden the continuity\\nledger first" because the marker straddled a line
    break. Paragraph normalization is what makes this detectable.
    """
    paragraphs = checker.summary_paragraphs(ROOT / "README.md")
    joined = " ".join(text for _, text in paragraphs)
    assert "\n" not in joined
    wrapped = tmp_path / "WRAPPED.md"
    wrapped.write_text("build the receipt, but harden the continuity\nledger first.\n", encoding="utf-8")

    got = checker.summary_paragraphs(wrapped)

    assert any("harden the continuity ledger" in text for _, text in got)


def test_historical_marker_exempts_a_paragraph(tmp_path):
    marked = tmp_path / "LOG.md"
    marked.write_text(
        "Historical note: we once had to harden the continuity ledger first.\n",
        encoding="utf-8",
    )

    paragraphs = checker.summary_paragraphs(marked)

    assert paragraphs
    assert any(
        any(mark in text for mark in checker.HISTORICAL_MARKERS) for _, text in paragraphs
    )


def test_missing_current_status_blocks(tmp_path):
    args = type("Args", (), {"current_status": tmp_path / "absent.json", "out": None})()

    got = checker.run(args)

    assert got["status"] == "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS"
    assert "current_status_missing" in _rules(got)


def test_reintroducing_the_1069_stale_instruction_blocks(tmp_path, monkeypatch):
    """The exact wording that slipped past the first marker set must block.

    #1069: PROJECT_KNOWLEDGE's order said "Resolve the speaker-recognition
    backend blocker with an approved real backend" -- no "p2.4" token, so every
    marker in the original set missed it while the checker reported PASS.
    """
    stale = tmp_path / "PROJECT_KNOWLEDGE.md"
    stale.write_text(
        "# Project Knowledge: persona-dream\n\n"
        "## CURRENT NEXT STEP\n\n"
        "Next implementation order:\n\n"
        "1. Resolve the speaker-recognition backend blocker with an approved real\n"
        "   backend such as `resemblyzer` or `speechbrain_ecapa`.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "PROJECT_KNOWLEDGE", stale)

    args = type("Args", (), {"current_status": ROOT / "CURRENT_STATUS.json", "out": None})()
    got = checker.run(args)

    assert got["status"] == "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS"
    offenders = {r.get("offending") for r in got["mismatches"]}
    assert "resolve the speaker-recognition backend blocker" in offenders
    assert any(r["rule"] == "current_summary_contradicts_receipt" for r in got["mismatches"])


def test_superseded_marker_exempts_the_historical_p24_section(tmp_path, monkeypatch):
    """Marking the old section SUPERSEDED must keep its evidence readable."""
    marked = tmp_path / "PROJECT_KNOWLEDGE.md"
    marked.write_text(
        "# Project Knowledge: persona-dream\n\n"
        "## CURRENT NEXT STEP\n\n"
        "1. #1037 recognition gate.\n\n"
        "## SUPERSEDED - P2.4 voice-recognition preflight blocks on missing backend\n\n"
        "> SUPERSEDED 2026-07-28. Retained as the record of the failed attempts.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "PROJECT_KNOWLEDGE", marked)

    args = type("Args", (), {"current_status": ROOT / "CURRENT_STATUS.json", "out": None})()
    got = checker.run(args)

    assert got["status"] == "PASS_CURRENT_STATE_CONSISTENT", got["mismatches"]
