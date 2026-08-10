from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "skills/monitor-website/scripts/design_world_check.py"


def load_module():
    spec = importlib.util.spec_from_file_location("design_world_check_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_current_g11_passes_with_current_section_crop_rater_packet():
    module = load_module()

    gate = module.distinctiveness_blind_gate()

    assert gate["status"] == "PASS"
    assert gate["design_outcome_status"] == "PASS"
    assert gate["subgates"]["corpus_current"]["status"] == "PASS"
    assert gate["subgates"]["section_crop_review_units"]["status"] == "PASS"
    assert gate["subgates"]["contact_sheet_current"]["status"] == "PASS"
    assert gate["subgates"]["fresh_rater_set_complete"]["status"] == "PASS"
    assert gate["subgates"]["fresh_rater_set_complete"]["usable"] >= 5
    assert gate["subgates"]["fresh_rater_set_complete"]["required"] == 5
    assert gate["subgates"]["thresholds_met"]["status"] == "PASS"


def write_distinctiveness_fixture(tmp_path: Path, aggregate: dict, raters: list[dict]) -> Path:
    roundtable = tmp_path / "site/design-roundtable"
    corpus_dir = roundtable / "rendered-screens/g11-fixture"
    output_dir = roundtable / "rater-outputs"
    corpus_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    screenshot = corpus_dir / "desktop-1440-00-top.png"
    screenshot.write_bytes(b"not a real png; fixture only")
    contact_sheet = corpus_dir / "contact-sheet.png"
    contact_sheet.write_bytes(b"contact sheet fixture")
    manifest = corpus_dir / "manifest.json"
    manifest_data = {
        "schema": "grahama.responsive_section_corpus.v1",
        "review_note": "Review units are section/page-state crops. Full-page screenshots are not primary evidence.",
        "counts": {"viewports": 1, "sections": 1, "screenshots": 1, "failures": 0},
        "screenshots": [
            {
                "status": "PASS",
                "id": "top",
                "route": "/#top",
                "viewport_id": "desktop-1440",
                "path": str(screenshot.relative_to(tmp_path)),
                "dimensions": {"width": 1440, "height": 600},
                "intended_proof": "Section/page-state crop; not a full-page or whole-site screenshot.",
            }
        ],
    }
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

    for index, rater in enumerate(raters, start=1):
        output = output_dir / f"rater-{index}.md"
        raw = output_dir / f"rater-{index}.raw.md"
        output.write_text("usable rater output", encoding="utf-8")
        raw.write_text("raw usable rater output", encoding="utf-8")
        rater["output_path"] = str(output.relative_to(tmp_path))
        rater["raw_output_path"] = str(raw.relative_to(tmp_path))

    receipt = {
        "schema": "grahama.distinctiveness_blind.v1",
        "status": "NOT_TESTED",
        "thresholds": {
            "min_raters": 5,
            "min_positive_classification": 4,
            "min_competitor_swap_tension": 4,
            "min_cross_screen_family": 4,
            "max_generic_ai_template_primary": 1,
        },
        "aggregate": aggregate,
        "raters": raters,
        "section_corpus_manifest": {
            "path": str(manifest.relative_to(tmp_path)),
            "sha256": sha256(manifest),
            "schema": "grahama.responsive_section_corpus.v1",
        },
        "contact_sheet": {
            "path": str(contact_sheet.relative_to(tmp_path)),
            "sha256": sha256(contact_sheet),
            "crop_count": 1,
        },
    }
    receipt_path = roundtable / "distinctiveness-blind.r1.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return roundtable


def test_completed_g11_rater_set_below_competitor_swap_threshold_fails(tmp_path, monkeypatch):
    module = load_module()
    raters = [{"usable": True, "rater_id": f"rater-{i}"} for i in range(1, 6)]
    roundtable = write_distinctiveness_fixture(
        tmp_path,
        aggregate={
            "usable": 5,
            "positive_classification": 5,
            "competitor_swap_tension": 1,
            "cross_screen_family": 5,
            "generic_ai_template_primary": 0,
        },
        raters=raters,
    )
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "DESIGN_ROUNDTABLE", roundtable)

    gate = module.distinctiveness_blind_gate()

    assert gate["status"] == "FAIL"
    assert gate["reason_code"] == "blind_distinctiveness_thresholds_not_met"
    assert gate["subgates"]["fresh_rater_set_complete"]["status"] == "PASS"
    assert gate["subgates"]["raw_outputs_preserved"]["status"] == "PASS"
    assert gate["subgates"]["thresholds_met"]["status"] == "FAIL"
    assert "competitor_swap_tension 1 does not satisfy >= 4" in gate["subgates"]["thresholds_met"]["errors"]


def test_g11_with_current_corpus_but_missing_fresh_raters_stays_not_tested(tmp_path, monkeypatch):
    module = load_module()
    roundtable = write_distinctiveness_fixture(
        tmp_path,
        aggregate={
            "usable": 0,
            "positive_classification": 0,
            "competitor_swap_tension": 0,
            "cross_screen_family": 0,
            "generic_ai_template_primary": 0,
        },
        raters=[],
    )
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "DESIGN_ROUNDTABLE", roundtable)

    gate = module.distinctiveness_blind_gate()

    assert gate["status"] == "NOT_TESTED"
    assert gate["reason_code"] == "fresh_blind_raters_not_run_for_current_segmented_corpus"
    assert gate["design_outcome_status"] == "NOT_TESTED"
    assert gate["next_action"]["lane"] == "rater_submission"
    assert gate["subgates"]["corpus_current"]["status"] == "PASS"
    assert gate["subgates"]["section_crop_review_units"]["status"] == "PASS"
    assert gate["subgates"]["fresh_rater_set_complete"]["status"] == "NOT_TESTED"
    assert gate["subgates"]["fresh_rater_set_complete"]["usable"] == 0
    assert gate["subgates"]["fresh_rater_set_complete"]["required"] == 5
