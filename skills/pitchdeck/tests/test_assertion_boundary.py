"""Atom authorization at the publication boundary (#1371).

The previous gate treated a compiler-emitted atom with any nonempty ``claim_id``
as authorization. That is an assertion BY the compiler, not evidence the
assertion was legally derived — and it was exploitable: inverting a diagram edge
label while preserving its claim_id and binding paths passed with zero findings.

These tests pin the distinction. A transform a machine can check (verbatim,
truncation, inflection) must actually hold against the cited claim text. One it
cannot check (aggregation, generalization) requires an exact named human
attestation. Chrome is a typed role, never a string-length heuristic.
"""

import pytest

from pitchdeck.publish_verify import (
    AssertionAtom,
    PublishApprovals,
    authorize_atom,
)

CLAIMS = {
    "c-relevance": (
        "Search, embeddings, and graph traversal can identify relevant material "
        "without establishing support, scope, currency, or approval."
    ),
    "c-boundary": "The model helps users navigate while governed evidence and authorized people decide.",
}


def _atom(text: str, *, claim_id="c-relevance", transform="truncation", role="diagram-node-label",
          slide_id="m-problem", element_id="diagram", binding_kind="claim_quote") -> AssertionAtom:
    return AssertionAtom(
        text=text, canonical_id=f"{slide_id}/{element_id}", role=role,
        claim_id=claim_id, transform_class=transform, binding_kind=binding_kind,
        slide_id=slide_id, element_id=element_id,
    )


def _authorize(atom, approved=()):
    return authorize_atom(
        atom, claims_by_id=CLAIMS,
        approved_texts={" ".join(t.split()).casefold() for t in approved},
    )


def test_true_truncation_is_authorized():
    assert _authorize(_atom("graph traversal can identify relevant material")) is None


def test_inverted_text_with_a_valid_claim_id_is_refused():
    """The reproduced bypass: keep the claim_id, invert the meaning."""
    refusal = _authorize(_atom("Relevance always establishes support"))
    assert refusal is not None
    assert refusal.code == "TRANSFORM_NOT_SATISFIED"


def test_claim_id_absent_from_the_ledger_is_refused():
    refusal = _authorize(_atom("graph traversal", claim_id="c-does-not-exist"))
    assert refusal is not None
    assert refusal.code == "CLAIM_NOT_IN_LEDGER"


def test_generalization_without_human_attestation_is_refused():
    """"Retrieval" is a legal generalization but not an excerpt — a machine
    cannot verify it, so it needs a named human receipt."""
    refusal = _authorize(_atom("Retrieval", transform="generalization"))
    assert refusal is not None
    assert refusal.code == "UNATTESTED_TRANSFORM"


def test_generalization_with_attestation_is_authorized():
    assert _authorize(_atom("Retrieval", transform="generalization"), approved=["Retrieval"]) is None


def test_mislabelled_transform_class_is_refused():
    """Declaring truncation does not make a paraphrase into an excerpt."""
    refusal = _authorize(_atom("Retrieval", transform="truncation"))
    assert refusal is not None
    assert refusal.code == "TRANSFORM_NOT_SATISFIED"


def test_unknown_transform_class_is_refused():
    refusal = _authorize(_atom("anything", transform="vibes"))
    assert refusal is not None
    assert refusal.code == "UNKNOWN_TRANSFORM_CLASS"


def test_typed_chrome_needs_no_claim():
    """Chrome is a ROLE, not a length. A footer asserts nothing about the product."""
    atom = _atom("Prepared-host capture", claim_id=None, transform=None, role="caption",
                 binding_kind="non_claim")
    assert _authorize(atom) is None


def test_short_strings_are_no_longer_chrome_by_length():
    """The old gate waved through anything <= 3 chars or all-digits."""
    refusal = _authorize(_atom("AI", claim_id=None, transform=None, role="diagram-edge-label",
                               binding_kind="claim_quote"))
    assert refusal is not None
    assert refusal.code == "CLAIM_NOT_IN_LEDGER"


def test_digits_are_no_longer_chrome_by_shape():
    refusal = _authorize(_atom("42", claim_id=None, transform=None, role="diagram-node-label",
                               binding_kind="claim_quote"))
    assert refusal is not None


@pytest.mark.parametrize("suffix", [
    " and therefore always establishes support",
    " which proves the conclusion",
])
def test_unsupported_suffix_after_a_legitimate_prefix_is_refused(suffix):
    """The old 60-character-prefix rule licensed exactly this."""
    legitimate = "Search, embeddings, and graph traversal can identify relevant material"
    refusal = _authorize(_atom(legitimate + suffix))
    assert refusal is not None
    assert refusal.code == "TRANSFORM_NOT_SATISFIED"
