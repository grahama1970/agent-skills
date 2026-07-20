"""Unit tests for per-tone emotional prosody injection in the synthesized path.

Covers the deterministic tone -> Orpheus emotion-tag mapping, tag injection into
the spoken query, WER-normalization tag stripping, turn-script wiring for all 9
matrix tone families, and the compile -> validate round trip. The synthetic
provenance of assets must never be disturbed by tone metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from embry_voice_control.audio_e2e.asr_comparison import (
    EMOTION_TAG_RE,
    ORPHEUS_EMOTION_TAGS,
    compare_asr_text,
    normalized_tokens,
)
from embry_voice_control.audio_e2e.case_compiler import (
    PROSODY_FEATURE_FAMILIES,
    TONE_PROSODY_MAP,
    TONE_PROSODY_MAP_SHA256,
    apply_tone_tags,
    build_turn_script,
    case_family_uses_prosody_feature,
    compile_campaign,
    sha256_value,
    spoken_text,
    synthesis_text_for_family,
    tone_family_for_case,
)
from embry_voice_control.audio_e2e.prepare_clone_assets import (
    strip_leading_wake_phrase,
    validate_campaign_manifest,
)


MATRIX_PATH = Path(
    "/home/graham/workspace/experiments/chatterbox/docs/EMBRY_STRESS_SESSION_MATRIX.json"
)
EXPECTED_FAMILIES = {
    "calm_precise",
    "curious_searching",
    "firm_boundary",
    "memory_confident",
    "careful_concerned",
    "dynamic_intent_selected",
    "identity_clarification",
    "memory_uncertain",
    "serious_low_energy",
}


def _case(
    tone_family: str,
    *,
    minimum_tags: int = 1,
    difficulty: str = "simple",
    folder_id: str = "tone_emotion",
) -> dict:
    return {
        "id": f"{folder_id}-{tone_family}-01",
        "difficulty": difficulty,
        "folder_id": folder_id,
        "question": "What evidence supports that answer?",
        "oracle": {"kind": "synthetic"},
        "expected_route": "answer",
        "conversation_requirements": {
            "required_tone_family": tone_family,
            "minimum_inline_emotion_tag_count": minimum_tags,
        },
    }


# --- Mapping table integrity ------------------------------------------------


def test_all_nine_families_present():
    assert set(TONE_PROSODY_MAP["families"]) == EXPECTED_FAMILIES


@pytest.mark.parametrize("family", sorted(EXPECTED_FAMILIES))
def test_family_tags_are_trained_vocabulary(family):
    entry = TONE_PROSODY_MAP["families"][family]
    assert entry["orpheus_tags"], f"{family} has no tags"
    assert entry["placement"] in {"leading", "trailing"}
    allowed = {f"<{tag}>" for tag in ORPHEUS_EMOTION_TAGS}
    for tag in entry["orpheus_tags"]:
        assert tag in allowed, f"{family} uses untrained tag {tag}"


def test_delivery_is_distinct_per_family():
    # 8 tags for 9 families: distinctness is guaranteed by (tag, placement).
    combos = {
        (tuple(entry["orpheus_tags"]), entry["placement"])
        for entry in TONE_PROSODY_MAP["families"].values()
    }
    assert len(combos) == len(EXPECTED_FAMILIES)


def test_map_sha256_is_stable():
    assert TONE_PROSODY_MAP_SHA256 == sha256_value(TONE_PROSODY_MAP)


# --- apply_tone_tags --------------------------------------------------------


def test_leading_tag_injected_after_wake_phrase():
    out = apply_tone_tags("Hey Embry, why did the review fail?", "calm_precise")
    assert out == "Hey Embry, <sigh> why did the review fail?"
    # wake phrase preserved verbatim for wakeword detection
    assert out.startswith("Hey Embry, ")


def test_trailing_tag_injected_at_end():
    out = apply_tone_tags(
        "Hey Embry, who am I?", "identity_clarification"
    )
    assert out == "Hey Embry, who am I? <sigh>"


def test_missing_wake_phrase_rejected():
    with pytest.raises(ValueError, match="wake_phrase"):
        apply_tone_tags("why did the review fail?", "calm_precise")


def test_unknown_family_rejected():
    with pytest.raises(ValueError, match="tone_family_unsupported"):
        apply_tone_tags("Hey Embry, hi?", "nonexistent_family")


def test_tag_count_minimum_enforced():
    # calm_precise supplies a single tag; demanding two must fail loudly.
    with pytest.raises(ValueError, match="tag_count_below_minimum"):
        apply_tone_tags("Hey Embry, hi?", "calm_precise", minimum_tag_count=2)


@pytest.mark.parametrize("family", sorted(EXPECTED_FAMILIES))
def test_every_family_meets_minimum_one_tag(family):
    out = apply_tone_tags("Hey Embry, ready?", family, minimum_tag_count=1)
    tag_count = len(EMOTION_TAG_RE.findall(out))
    assert tag_count >= 1


# --- WER normalization strips tags ------------------------------------------


def test_normalized_tokens_strips_emotion_tags():
    assert normalized_tokens("<sigh> why did the review fail?") == [
        "why",
        "did",
        "the",
        "review",
        "fail",
    ]
    # the tag's inner word must never survive as a token
    assert "sigh" not in normalized_tokens("<sigh> hello")


@pytest.mark.parametrize("family", sorted(EXPECTED_FAMILIES))
def test_wer_zero_between_tagged_expected_and_plain_transcript(family):
    plain = "Hey Embry, what evidence supports that answer?"
    tagged = apply_tone_tags(plain, family)
    expected_query = strip_leading_wake_phrase(tagged)
    plain_query = strip_leading_wake_phrase(plain)
    comparison = compare_asr_text(
        expected_query, plain_query, strip_expected_wake=False
    )
    assert comparison["comparison_wer"] == 0.0
    assert comparison["raw_wer"] == 0.0


def test_plain_text_normalization_unchanged():
    # Regression guard: text with no tags tokenizes exactly as before.
    assert normalized_tokens("Hey Embry, ground your claim in SPARTA") == [
        "hey",
        "embry",
        "ground",
        "your",
        "claim",
        "in",
        "sparta",
    ]


# --- build_turn_script wiring -----------------------------------------------


@pytest.mark.parametrize("family", sorted(EXPECTED_FAMILIES))
def test_turn_script_carries_tone_and_synthesis_text(family):
    turns = build_turn_script(_case(family))
    assert turns
    for turn in turns:
        assert turn["tone_family"] == family
        assert turn["tone_prosody_map_sha256"] == TONE_PROSODY_MAP_SHA256
        assert turn["inline_emotion_tags"] == list(
            TONE_PROSODY_MAP["families"][family]["orpheus_tags"]
        )
        # plain utterance/spoken kept intact for WER (no tags leak in)
        assert not EMOTION_TAG_RE.search(turn["spoken_text"])
        assert not EMOTION_TAG_RE.search(turn["utterance"])
        # synthesis text carries the tags and derives from the plain spoken text
        assert EMOTION_TAG_RE.search(turn["synthesis_spoken_text"])
        assert turn["synthesis_spoken_text"] == apply_tone_tags(
            turn["spoken_text"], family
        )
        assert turn["synthesis_spoken_text_sha256"] == sha256_value(
            turn["synthesis_spoken_text"]
        )
        assert turn["inline_emotion_tag_count"] >= turn[
            "minimum_inline_emotion_tag_count"
        ]


@pytest.mark.parametrize("family", sorted(EXPECTED_FAMILIES))
def test_turn_script_drops_decorative_tags_for_non_feature_family(family):
    # Any family other than tone_emotion: prosody is decorative, so the synthesis
    # prompt is the plain lexical sentence with NO tags, but the tone metadata is
    # still recorded for provenance.
    turns = build_turn_script(_case(family, folder_id="persona_memory_miss"))
    assert turns
    for turn in turns:
        assert turn["tone_family"] == family
        assert turn["inline_emotion_tags"] == list(
            TONE_PROSODY_MAP["families"][family]["orpheus_tags"]
        )
        assert not EMOTION_TAG_RE.search(turn["synthesis_spoken_text"])
        assert turn["synthesis_spoken_text"] == turn["spoken_text"]
        assert turn["synthesis_spoken_text_sha256"] == sha256_value(
            turn["synthesis_spoken_text"]
        )


def test_prosody_feature_families_membership():
    assert "tone_emotion" in PROSODY_FEATURE_FAMILIES
    assert case_family_uses_prosody_feature("tone_emotion")
    assert not case_family_uses_prosody_feature("persona_memory_miss")


def test_synthesis_text_for_family_rule():
    plain = "Hey Embry, why did the review fail?"
    # feature family injects the tag
    feature = synthesis_text_for_family(plain, "calm_precise", "tone_emotion")
    assert feature == apply_tone_tags(plain, "calm_precise")
    assert EMOTION_TAG_RE.search(feature)
    # decorative family returns the plain sentence unchanged
    decorative = synthesis_text_for_family(plain, "calm_precise", "skill_analytics")
    assert decorative == plain
    assert not EMOTION_TAG_RE.search(decorative)
    # the tag-count invariant is still enforced for decorative families
    with pytest.raises(ValueError, match="tag_count_below_minimum"):
        synthesis_text_for_family(
            plain, "calm_precise", "skill_analytics", minimum_tag_count=2
        )


def test_unknown_tone_family_in_case_rejected():
    with pytest.raises(ValueError, match="tone_family_unsupported"):
        build_turn_script(_case("no_such_family"))


def test_tone_family_for_case():
    assert tone_family_for_case(_case("firm_boundary")) == "firm_boundary"


# --- compile -> validate round trip and provenance --------------------------


def _first_compilable_case_id(folder_id: str | None = None) -> str:
    matrix = json.loads(MATRIX_PATH.read_text())
    for case in matrix["sessions"]:
        if folder_id is not None and case.get("folder_id") != folder_id:
            continue
        try:
            spoken_text("Hey Embry, " + case["question"][0].lower() + case["question"][1:])
        except ValueError:
            continue
        return case["id"]
    raise AssertionError(f"no compilable matrix case found for folder_id={folder_id}")


def test_compile_validate_round_trip_carries_tags_for_prosody_feature(tmp_path):
    # tone_emotion cases exercise prosody AS the feature: tags are retained in the
    # synthesized/ASR-compared query.
    source_policy = tmp_path / "source_policy.json"
    source_policy.write_text(
        json.dumps({"schema": "embry.audio_e2e.clone_source_contract.v1"})
    )
    manifest = compile_campaign(
        matrix_path=MATRIX_PATH,
        source_policy_path=source_policy,
        case_id=_first_compilable_case_id("tone_emotion"),
        source_mode="qualified_horus_clone",
    )
    # manifest carries the tone map for auditability
    assert manifest["tone_prosody_map"]["sha256"] == TONE_PROSODY_MAP_SHA256
    normalized = validate_campaign_manifest(manifest)
    query = normalized[0]["turns"][0]["query"]
    # the synthesized/ASR-compared query carries the emotion tag
    assert EMOTION_TAG_RE.search(query)


def test_compile_validate_round_trip_drops_decorative_tags(tmp_path):
    # A non-tone_emotion family: the emotion tags are decorative and must NOT
    # appear in the synthesized prompt, while the tone metadata is retained for
    # provenance and the manifest still validates.
    source_policy = tmp_path / "source_policy.json"
    source_policy.write_text(
        json.dumps({"schema": "embry.audio_e2e.clone_source_contract.v1"})
    )
    case_id = _first_compilable_case_id("skill_create_evidence_case")
    manifest = compile_campaign(
        matrix_path=MATRIX_PATH,
        source_policy_path=source_policy,
        case_id=case_id,
        source_mode="qualified_horus_clone",
    )
    case = manifest["cases"][0]
    assert case["folder_id"] != "tone_emotion"
    for turn in case["turn_script"]:
        # decorative tags stripped from synthesis prompt...
        assert not EMOTION_TAG_RE.search(turn["synthesis_spoken_text"])
        assert turn["synthesis_spoken_text"] == turn["spoken_text"]
        # ...but tone metadata retained in the manifest for provenance
        assert turn["tone_family"]
        assert turn["inline_emotion_tags"]
        assert turn["tone_prosody_map_sha256"] == TONE_PROSODY_MAP_SHA256
    # round-trips through the strict validator
    normalized = validate_campaign_manifest(manifest)
    query = normalized[0]["turns"][0]["query"]
    assert not EMOTION_TAG_RE.search(query)


def test_tone_metadata_never_flips_synthetic_provenance(tmp_path):
    source_policy = tmp_path / "source_policy.json"
    source_policy.write_text(
        json.dumps({"schema": "embry.audio_e2e.clone_source_contract.v1"})
    )
    manifest = compile_campaign(
        matrix_path=MATRIX_PATH,
        source_policy_path=source_policy,
        case_id=_first_compilable_case_id(),
        source_mode="qualified_horus_clone",
    )
    for case in manifest["cases"]:
        # source_mode is the synthetic clone mode and tone metadata leaves it alone
        assert case["source_mode"] == "qualified_horus_clone"
        for turn in case["turn_script"]:
            assert turn["speaker"] == "horus_lupercal"
            # no physical/synthetic flags are introduced by tone injection
            assert "fresh_physical_human_speech" not in turn
            assert "speaker_identity_proven" not in turn


# --- matrix coverage --------------------------------------------------------


def test_every_matrix_tone_family_is_mapped():
    matrix = json.loads(MATRIX_PATH.read_text())
    families = {
        session["conversation_requirements"]["required_tone_family"]
        for session in matrix["sessions"]
    }
    assert families <= set(TONE_PROSODY_MAP["families"])
    assert families == EXPECTED_FAMILIES
