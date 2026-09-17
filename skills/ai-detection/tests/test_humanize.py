"""Red-team humanizer transforms and detector feature-fragility probe (mechanism-only)."""
import pytest

from ai_detection.errors import DetectionError
from ai_detection.humanize import Evasion, Transform, humanize, probe_evasion, probe_fragility
from ai_detection.model import train
from tests.helpers import corpus

SAMPLE = '''# a greeting helper
def greet(name):
    # say hello
    message = "hello, " + name


    return message
'''


def test_transforms_preserve_parseability_and_strip_comments():
    reformatted = humanize(SAMPLE, Transform.AST_REFORMAT)
    assert "greeting helper" not in reformatted  # ast.unparse drops comments
    assert "def greet" in reformatted
    stripped = humanize(SAMPLE, Transform.STRIP_COMMENTS)
    assert "say hello" not in stripped and "greet" in stripped


def test_invalid_python_fails_closed():
    with pytest.raises(DetectionError):
        humanize("def (:", Transform.AST_REFORMAT)


def test_style_normalization_moves_raw_view_but_not_structure():
    # The load-bearing R&D claim: formatting attacks perturb the raw-token view
    # while the AST/structure view and the normalized digest stay invariant.
    by_transform = {f.transform: f for f in probe_fragility(SAMPLE)}
    strip = by_transform[Transform.STRIP_COMMENTS.value]
    assert strip.raw_view_distance > strip.struct_view_distance
    assert strip.normalized_digest_changed is False
    assert strip.struct_view_distance == pytest.approx(0.0, abs=1e-9)


def test_docstring_removal_is_semantic_content_edit_that_moves_structure():
    # Content-level attack (unlike whitespace): removing a docstring changes the
    # normalized digest and perturbs the structural view — the evasion-vs-
    # preservation tradeoff. Output must still parse.
    doc = 'def f(x):\n    """add one."""\n    return x + 1\n'
    out = humanize(doc, Transform.STRIP_DOCSTRINGS)
    assert "add one" not in out and "return x + 1" in out
    frag = {f.transform: f for f in probe_fragility(doc)}[Transform.STRIP_DOCSTRINGS.value]
    assert frag.normalized_digest_changed is True


def test_evasion_probe_closes_the_loop_on_a_trained_synthetic_model():
    # Detect -> humanize -> re-detect against a trained detector's threshold.
    # Synthetic model: mechanism-only (analyze() still abstains); this measures
    # score movement across the calibrated boundary, not real evasion/efficacy.
    model, _report = train(corpus())
    machine_sources = [r.source for r in corpus() if r.label == "machine"]
    results = probe_evasion(model, machine_sources)
    assert {r.transform for r in results} == {t.value for t in Transform}
    for r in results:
        assert isinstance(r, Evasion)
        assert r.samples > 0
        assert r.dropped_below_after <= r.flagged_before
