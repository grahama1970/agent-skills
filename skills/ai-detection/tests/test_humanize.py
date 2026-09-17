"""Red-team humanizer transforms and detector feature-fragility probe (mechanism-only)."""
import pytest

from ai_detection.errors import DetectionError
from ai_detection.humanize import Transform, humanize, probe_fragility

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
