"""An idea must steer the dream, or be refused.

The failure this guards against is silent substitution: an idea that matches no
residue quietly falling back to autonomous selection, so the run receipt claims
an idea the dream ignored. That is worse than refusing, because it is a receipt
that lies rather than a run that stops.

The second guard is that an idea never INVENTS residue. Selection is restricted
to memories she already has; steering changes which of them surface, never what
exists. A dream about material she was never given would be confabulation with a
provenance trail.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "adc_mod", ROOT / "scripts" / "autonomous_dream_cycle.py")
adc = importlib.util.module_from_spec(_spec)
sys.modules["adc_mod"] = adc
_spec.loader.exec_module(adc)


def _root(key: str, text: str) -> tuple[str, dict]:
    return key, {"_key": key, "claim": text, "claim_text": text,
                 "evidence_text": "", "retrieval_text": text}


ROOTS = dict([
    _root("m1", "Kai stood on the seawall and I said nothing at all."),
    _root("m2", "The succulent on my desk was already dying that first day."),
    _root("m3", "Moana played on a Sunday and I turned it off at the grandmother scene."),
])


def test_an_idea_restricts_selection_to_residue_it_touches():
    seeded, prov = adc.seed_roots_with_idea(ROOTS, "kai on the seawall")
    assert set(seeded) == {"m1"}
    assert prov["roots_before"] == 3 and prov["roots_after"] == 1


def test_a_different_idea_selects_different_residue():
    """Steering, not coincidence. Live: three ideas chose three clusters."""
    a, _ = adc.seed_roots_with_idea(ROOTS, "the dying succulent on my desk")
    b, _ = adc.seed_roots_with_idea(ROOTS, "moana grandmother scene")
    assert set(a) == {"m2"}
    assert set(b) == {"m3"}
    assert set(a) != set(b)


def test_an_idea_with_no_residue_is_refused_not_substituted():
    """The whole point. A silent fallback makes the receipt claim an idea the
    dream ignored."""
    with pytest.raises(SystemExit) as exc:
        adc.seed_roots_with_idea(ROOTS, "quantum chromodynamics in tungsten")
    message = str(exc.value)
    assert "BLOCKED_IDEA_NO_RESIDUE" in message
    # The refusal must name what it looked for, or it is unactionable.
    assert "chromodynamics" in message and "tungsten" in message


def test_an_idea_of_only_stopwords_is_refused():
    with pytest.raises(SystemExit) as exc:
        adc.seed_roots_with_idea(ROOTS, "the things that were about it")
    assert "BLOCKED_IDEA_EMPTY" in str(exc.value)


def test_every_matching_root_is_kept_not_just_the_best():
    """A top-1 filter would starve the cluster engine's conflict search."""
    roots = dict([
        _root("a", "Kai laughed."),
        _root("b", "Kai and the seawall and the silence."),
        _root("c", "Nothing relevant here."),
    ])
    seeded, prov = adc.seed_roots_with_idea(roots, "kai seawall")
    assert set(seeded) == {"a", "b"}
    assert prov["best_term_hits"] == 2


def test_stopword_list_stays_small():
    """Over-filtering an idea quietly changes what she dreams about. An idea is
    a sentence a human typed, not a query language."""
    assert len(adc._IDEA_STOPWORDS) < 60
