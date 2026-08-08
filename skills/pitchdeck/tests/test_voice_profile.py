"""Mutation tests for the voice-profile and transform-policy compilers (#1311)."""

from pathlib import Path

from pitchdeck.voice_profile import (
    TransformMapping,
    check_rendering_policy,
    compile_voice_profile,
)

CORPUS = Path(__file__).resolve().parents[2] / "best-practices-slide-design"

CLAIM = (
    "Search, embeddings, and graph traversal can identify relevant material "
    "without establishing support, scope, currency, or approval."
)

RETRIEVAL = TransformMapping(
    id="methods-to-retrieval",
    kind="aggregation",
    source_terms=["search", "embeddings", "graph traversal"],
    target="retrieval",
    direction_note="exact set alias for the three named mechanisms; not all retrieval",
    status="approved",
    approved_by="graham (chat approval 2026-08-07)",
)


def test_profile_is_deterministic_and_content_addressed():
    a = compile_voice_profile(CORPUS)
    b = compile_voice_profile(CORPUS)
    assert a.content_sha256() == b.content_sha256()
    assert a.exemplars, "corpus must yield exemplars"
    ids = {e.id for e in a.exemplars}
    assert "statement-slide" in ids  # "Intelligent Automation Saves Time"
    for exemplar in a.exemplars:
        assert 2 <= exemplar.word_count <= 12, exemplar


def test_mutation_can_to_will_is_refused():
    bad = "Search, embeddings, and graph traversal will identify relevant material without establishing support, scope, currency, or approval."
    codes = {v.code for v in check_rendering_policy(CLAIM, bad)}
    assert "MODALITY_STRENGTHENED" in codes


def test_mutation_dropped_without_is_refused():
    bad = "Search, embeddings, and graph traversal can identify relevant material."
    codes = {v.code for v in check_rendering_policy(CLAIM, bad)}
    assert "GUARD_DROPPED" in codes


def test_mutation_added_only_today_is_refused():
    bad = "Only today can search identify relevant material without establishing support, scope, currency, or approval."
    codes = {v.code for v in check_rendering_policy(CLAIM, bad)}
    assert "GUARD_ADDED" in codes


def test_mutation_missing_list_member_is_refused():
    bad = "Relevant material can be identified without establishing support, scope, or approval."
    violations = check_rendering_policy(CLAIM, bad)
    assert any(v.code == "COORDINATED_SPAN_BROKEN" and "currency" in v.detail for v in violations)


def test_unregistered_exemplar_word_is_refused_and_approved_mapping_licenses():
    witty = "Retrieval can identify relevant material without establishing support, scope, currency, or approval."
    unlicensed = check_rendering_policy(CLAIM, witty)
    assert any(v.code == "UNREGISTERED_REWRITE_TERM" and "'retrieval'" in v.detail for v in unlicensed)
    licensed = check_rendering_policy(CLAIM, witty, mappings=[RETRIEVAL])
    assert not licensed, licensed
    # candidate (unapproved) mappings license nothing
    candidate = RETRIEVAL.model_copy(update={"status": "candidate", "approved_by": None})
    assert any(
        v.code == "UNREGISTERED_REWRITE_TERM"
        for v in check_rendering_policy(CLAIM, witty, mappings=[candidate])
    )


def test_horrible_style_word_never_sneaks_in():
    bad = "Hand retrieval is horrible without establishing support, scope, currency, or approval."
    codes = {v.code for v in check_rendering_policy(CLAIM, bad, mappings=[RETRIEVAL])}
    assert "UNREGISTERED_REWRITE_TERM" in codes
