"""#1381: archetype-conditioned structure catches what pixel marginals cannot.

The adversary benchmark proved layout-mirror and typography-swap pass the
pixel channels; these tests pin that check_structure rejects exactly those
mutations and stays silent on the honest deck."""

import json
from pathlib import Path

import pytest

pptx = pytest.importorskip("pptx")

from pitchdeck.house_structure import check_structure  # noqa: E402

GOOD = Path("/tmp/pd-1379c/deck.pptx")
DOC = Path("/tmp/pd-1379c/deck.document.json")


def _skip_unless_artifacts():
    if not (GOOD.exists() and DOC.exists()):
        pytest.skip("live eval artifacts absent (run scripts/eval_readme_to_deck.sh /tmp/pd-1379c)")


def test_honest_deck_is_clean():
    _skip_unless_artifacts()
    assert check_structure(GOOD, DOC) == []


def test_layout_mirror_is_rejected(tmp_path):
    _skip_unless_artifacts()
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from build_house_gate_adversaries import layout_mirror
    mutant = tmp_path / "mirror.pptx"
    layout_mirror(GOOD, mutant)
    codes = {f.code for f in check_structure(mutant, DOC)}
    assert "ROLE_REGION_VIOLATION" in codes


def test_typography_swap_is_rejected(tmp_path):
    _skip_unless_artifacts()
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from build_house_gate_adversaries import typography_swap
    mutant = tmp_path / "ransom.pptx"
    typography_swap(GOOD, mutant)
    codes = {f.code for f in check_structure(mutant, DOC)}
    assert "TYPOGRAPHY_VIOLATION" in codes


def test_two_tiny_visuals_is_rejected(tmp_path):
    _skip_unless_artifacts()
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from build_house_gate_adversaries import two_tiny_visuals
    mutant = tmp_path / "tiny.pptx"
    two_tiny_visuals(GOOD, mutant)
    codes = {f.code for f in check_structure(mutant, DOC)}
    assert "VISUAL_SUBSTANCE_VIOLATION" in codes


def test_unknown_archetype_fails_not_skips():
    _skip_unless_artifacts()
    doc = json.loads(DOC.read_text())
    doc["slides"][2]["intent"]["recipe"] = "statement-thesis"
    doc["slides"][2]["notes"] = "something unrecognizable"
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        # break EVERY slide's archetype markers
        for sl in doc["slides"]:
            if sl.get("intent"):
                sl["intent"]["recipe"] = sl["intent"]["recipe"]
            sl["notes"] = "unclassifiable"
            if sl.get("intent"):
                sl["intent"] = None
        json.dump(doc, fh)
        path = Path(fh.name)
    codes = {f.code for f in check_structure(GOOD, path)}
    assert "UNKNOWN_ARCHETYPE" in codes
