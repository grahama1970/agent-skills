"""Deterministic tests for the persona-dream cognitive loop (phases 13-15).

No live LLM or memory calls. Every test exercises the deterministic validation
and boundary logic that decides admissibility and canonical-write safety.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p13 = _load("phase13_self_interpretation")
p14 = _load("phase14_tom_validation")
p15 = _load("phase15_dream_persistence")

HISTORICAL_PACKET = (
    ROOT / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
    / "watch_gauntlet/991c311f365f/dream_observation_packet.v1.json"
)

_REV = (
    ROOT / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
)
ACCEPTED_PACKET = _REV / "watch_gauntlet/59b9ff3155d6/dream_observation_packet.v1.json"
ACCEPTANCE_RECEIPT_V2 = (
    _REV / "phase_11_submit_return/provider_return"
    / "97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4"
    / "post_return_acceptance_receipt.v2.json"
)
ACCEPTED_RETURN_ID = "97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4"


# --------------------------------------------------------------------------- #
# Phase 13 - observation index + citation gate                                #
# --------------------------------------------------------------------------- #
def test_observation_index_from_historical_packet():
    packet = p13.read_json(HISTORICAL_PACKET)
    index = p13.build_observation_index(packet)
    ids = {o["observation_id"] for o in index}
    assert "frame_0000" in ids
    assert "transcript_seg_000" in ids
    assert "identity_temporal_continuity_review" in ids
    assert "visible_speaker_lipsync_window" in ids
    # The identity review carries the DRIFT defect verdict.
    defect_ids = p13.renderer_defect_observation_ids(index)
    assert "identity_temporal_continuity_review" in defect_ids


def _obs_index():
    return [
        {"observation_id": "frame_0000", "observation_type": "frame", "summary": "x",
         "renderer_review": False, "renderer_defect_verdict": None},
        {"observation_id": "identity_temporal_continuity_review", "observation_type": "renderer_continuity_review",
         "summary": "DRIFT", "renderer_review": True, "renderer_defect_verdict": "DRIFT"},
    ]


def test_uncited_claim_is_rejected():
    obs = _obs_index()
    accepted, rejected = p13.validate_interpretations(
        [{
            "interpretation_id": "i-1", "tom_state_type": "trust", "subject": "embry", "target": "kai",
            "statement": "Embry trusts Kai.", "observation_refs": [], "source_memory_refs": [],
            "confidence": 0.5, "uncertainty": "x", "alternative_explanation": "renderer",
        }],
        obs, source_ids={"mem-1"},
    )
    assert accepted == []
    assert rejected[0]["interpretation_id"] == "i-1"
    assert "NO_OBSERVATION_CITATION" in rejected[0]["reasons"]
    assert "NO_SOURCE_MEMORY_CITATION" in rejected[0]["reasons"]


def test_unknown_refs_are_rejected():
    obs = _obs_index()
    _, rejected = p13.validate_interpretations(
        [{
            "interpretation_id": "i-1", "tom_state_type": "trust", "subject": "embry", "target": "kai",
            "statement": "s", "observation_refs": ["frame_9999"], "source_memory_refs": ["not-a-mem"],
            "confidence": 0.5, "uncertainty": "x", "alternative_explanation": "renderer",
        }],
        obs, source_ids={"mem-1"},
    )
    reasons = rejected[0]["reasons"]
    assert any(r.startswith("UNKNOWN_OBSERVATION_REFS") for r in reasons)
    assert any(r.startswith("UNKNOWN_SOURCE_MEMORY_REFS") for r in reasons)


def test_grounded_claim_is_accepted_and_stamped_synthetic():
    obs = _obs_index()
    accepted, rejected = p13.validate_interpretations(
        [{
            "interpretation_id": "i-1", "tom_state_type": "trust", "subject": "embry", "target": "kai",
            "statement": "Embry trusts Kai's warning.", "observation_refs": ["frame_0000"],
            "source_memory_refs": ["mem-1"], "confidence": 0.4, "uncertainty": "unclear",
            "emotional_intensity": 0.5, "alternative_explanation": "renderer dropped context",
        }],
        obs, source_ids={"mem-1"},
    )
    assert rejected == []
    assert accepted[0]["synthetic_origin"] is True
    assert accepted[0]["literal_historical_event"] is False


def test_honesty_rule_rejects_psychological_reading_of_renderer_defect():
    """A claim citing the DRIFT continuity review must FAVOR renderer defect."""
    obs = _obs_index()
    _, rejected = p13.validate_interpretations(
        [{
            "interpretation_id": "i-1", "tom_state_type": "belief", "subject": "embry", "target": "kai",
            "statement": "Embry's shifting face means her identity is dissolving.",
            "observation_refs": ["identity_temporal_continuity_review"], "source_memory_refs": ["mem-1"],
            "confidence": 0.6, "uncertainty": "x", "emotional_intensity": 0.7,
            "alternative_explanation": "renderer failed identity continuity",
            "favored_explanation": "psychological",
        }],
        obs, source_ids={"mem-1"},
    )
    assert "RENDERER_DEFECT_NOT_FAVORED_DESPITE_REVIEW" in rejected[0]["reasons"]


def test_honesty_rule_accepts_when_renderer_defect_favored():
    obs = _obs_index()
    accepted, rejected = p13.validate_interpretations(
        [{
            "interpretation_id": "i-1", "tom_state_type": "uncertainty", "subject": "embry", "target": "kai",
            "statement": "The instability could read as Embry's dream-uncertainty about being seen.",
            "observation_refs": ["identity_temporal_continuity_review"], "source_memory_refs": ["mem-1"],
            "confidence": 0.3, "uncertainty": "high", "emotional_intensity": 0.4,
            "alternative_explanation": "the renderer failed identity continuity (DRIFT verdict)",
            "favored_explanation": "renderer_defect",
        }],
        obs, source_ids={"mem-1"},
    )
    assert rejected == []
    assert accepted[0]["favored_explanation"] == "renderer_defect"


# --------------------------------------------------------------------------- #
# Phase 14 - ToM gate                                                          #
# --------------------------------------------------------------------------- #
def _parent():
    return {
        "interpretation_id": "i-1", "tom_state_type": "trust", "subject": "embry", "target": "kai",
        "statement": "s", "observation_refs": ["frame_0000", "visible_speaker_lipsync_window"],
        "source_memory_refs": ["mem-1", "mem-2"],
    }


def test_tom_candidate_rejected_when_refs_not_in_parent():
    parent = _parent()
    accepted, receipts = p14.validate_candidates(
        [{
            "candidate_id": "tom-1", "parent_interpretation_id": "i-1", "tom_state_type": "trust",
            "subject": "embry", "target": "kai", "statement": "s",
            "source_memory_refs": ["mem-99"], "watch_observation_refs": ["frame_0000"],
            "confidence": 0.5, "emotional_intensity": 0.5,
            "synthetic_origin": True, "literal_historical_event": False,
        }],
        [parent],
    )
    assert accepted == []
    assert receipts[0]["decision"] == "REJECT"
    assert any(r.startswith("SOURCE_REFS_NOT_IN_PARENT") for r in receipts[0]["reasons"])


def test_tom_candidate_rejected_when_missing_grounding_fields():
    parent = _parent()
    _, receipts = p14.validate_candidates(
        [{
            "candidate_id": "tom-1", "parent_interpretation_id": "i-1", "tom_state_type": "belief",
            "subject": "embry", "target": "kai", "statement": "s",
            "source_memory_refs": ["mem-1"], "watch_observation_refs": [],  # missing observation grounding
            "confidence": 0.5, "emotional_intensity": 0.5,
            "synthetic_origin": True, "literal_historical_event": False,
        }],
        [parent],
    )
    assert "NO_WATCH_OBSERVATION_CITATION" in receipts[0]["reasons"]


def test_tom_candidate_rejected_when_state_not_bounded():
    parent = _parent()
    _, receipts = p14.validate_candidates(
        [{
            "candidate_id": "tom-1", "parent_interpretation_id": "i-1", "tom_state_type": "world_domination",
            "subject": "embry", "target": "kai", "statement": "s",
            "source_memory_refs": ["mem-1"], "watch_observation_refs": ["frame_0000"],
            "confidence": 0.5, "emotional_intensity": 0.5,
            "synthetic_origin": True, "literal_historical_event": False,
        }],
        [parent],
    )
    assert any(r.startswith("TOM_STATE_TYPE_NOT_BOUNDED") for r in receipts[0]["reasons"])


def test_tom_candidate_accepted_when_grounded_in_parent():
    parent = _parent()
    accepted, receipts = p14.validate_candidates(
        [{
            "candidate_id": "tom-1", "parent_interpretation_id": "i-1", "tom_state_type": "trust",
            "subject": "embry", "target": "kai", "statement": "Embry trusts Kai's lineup warning.",
            "source_memory_refs": ["mem-1"], "watch_observation_refs": ["visible_speaker_lipsync_window"],
            "confidence": 0.4, "emotional_intensity": 0.5,
            "synthetic_origin": True, "literal_historical_event": False,
        }],
        [parent],
    )
    assert receipts[0]["decision"] == "ACCEPT"
    assert accepted[0]["schema"] == "persona_dream.tom_candidate.v1"


def test_deterministic_fallback_candidates_pass_gate():
    parent = _parent()
    parent["confidence"] = 0.4
    parent["emotional_intensity"] = 0.5
    derived = p14.derive_candidates_deterministic([parent])
    accepted, receipts = p14.validate_candidates(derived, [parent])
    assert len(accepted) == 1
    assert receipts[0]["decision"] == "ACCEPT"


# --------------------------------------------------------------------------- #
# Phase 15 - the non-negotiable canonical-write boundary                      #
# --------------------------------------------------------------------------- #
def test_superseded_historical_return_is_blocked_even_with_allow_flag():
    packet = p13.read_json(HISTORICAL_PACKET)
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id="rev_successor_943b01ecd9a3",
    )
    assert allowed is False
    assert "RETURN_IS_HISTORICAL_PROVIDER_RETURN" in blockers
    assert "OBSERVATION_STATUS_DEGRADED" in blockers
    assert any(b.startswith("IDENTITY_CONTINUITY_DEFECT") for b in blockers)


def test_canonical_write_blocked_without_flag():
    packet = {"evidence_origin": "live_provider_return", "status": "OK"}
    allowed, blockers = p15.canonical_write_decision(packet, allow_canonical_write=False, return_id="r-1")
    assert allowed is False
    assert "CANONICAL_WRITE_FLAG_NOT_SET" in blockers


def test_clean_nonsuperseded_return_is_allowed():
    """A clean, live, non-degraded return with the flag and a return id is the
    ONLY path to a canonical write."""
    packet = {
        "evidence_origin": "live_provider_return",
        "status": "OK_WATCH_GAUNTLET_OBSERVATION",
        "step_hooks": {"step_36_identity_temporal_continuity": {"vision_review": {"verdict": "MATCH"}}},
    }
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id="rev_clean_return",
    )
    assert allowed is True
    assert blockers == []


def test_clean_return_blocked_when_in_superseded_set():
    packet = {"evidence_origin": "live_provider_return", "status": "OK",
              "step_hooks": {"step_36_identity_temporal_continuity": {"vision_review": {"verdict": "MATCH"}}}}
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id="r-1", superseded_return_ids={"r-1"},
    )
    assert allowed is False
    assert "RETURN_ID_SUPERSEDED" in blockers


def test_dry_run_persistence_performs_zero_canonical_writes(tmp_path):
    interp = {
        "observation_packet_sha256": "sha256:abc",
        "accepted_interpretations": [{
            "interpretation_id": "i-1", "tom_state_type": "trust", "subject": "embry", "target": "kai",
            "statement": "s", "observation_refs": ["frame_0000"], "source_memory_refs": ["mem-1"],
        }],
        "source_memory_bindings": [{"source_id": "mem-1"}],
    }
    tom = {"accepted_tom_candidates": [{
        "candidate_id": "tom-1", "tom_state_type": "trust", "confidence": 0.4, "emotional_intensity": 0.5,
    }]}
    interp_path = tmp_path / "interp.json"
    tom_path = tmp_path / "tom.json"
    p13.write_json(interp_path, interp)
    p13.write_json(tom_path, tom)

    result = p15.run_phase15(
        HISTORICAL_PACKET, interp_path, tom_path, "dream-x", "rev-x", "run-x", "embry",
        allow_canonical_write=False, return_id=None, validation_collection=None,
    )
    assert result["canonical_write_allowed"] is False
    assert result["canonical_writes_performed"] == 0
    assert result["status"].startswith("DRY_RUN")
    # The plan still contains exact would-write payloads and hashes.
    assert result["canonical_plan"]["dream_memory_document"]["document"]["synthetic_origin"] is True
    assert result["canonical_plan"]["dream_memory_document"]["document"]["literal_historical_event"] is False
    assert result["canonical_plan"]["dream_memory_document"]["payload_sha256"].startswith("sha256:")
    # Edge vocabulary present.
    rels = {e["document"]["relationship_type"] for e in result["canonical_plan"]["graph_edges"]}
    assert "derived_from" in rels
    assert "observed_in_scene" in rels
    assert "supports_interpretation" in rels


# --------------------------------------------------------------------------- #
# Phase 15 - acceptance-receipt gating for the ACCEPTED successor return       #
# The accepted return's raw pre-mux packet is DEGRADED; only a binding          #
# agent-level acceptance receipt may override that, and never a hard block.     #
# --------------------------------------------------------------------------- #
def test_accepted_return_permitted_with_binding_acceptance_receipt():
    packet = p13.read_json(ACCEPTED_PACKET)
    receipt = p13.read_json(ACCEPTANCE_RECEIPT_V2)
    assert packet["status"].startswith("DEGRADED")  # the raw packet is degraded
    assert receipt["status"] == "ACCEPTED_AGENT_LEVEL"
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id=ACCEPTED_RETURN_ID,
        acceptance_receipt=receipt,
    )
    assert allowed is True, blockers
    assert blockers == []


def test_degraded_accepted_return_blocked_without_acceptance_receipt():
    packet = p13.read_json(ACCEPTED_PACKET)
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id=ACCEPTED_RETURN_ID,
        acceptance_receipt=None,
    )
    assert allowed is False
    assert "OBSERVATION_STATUS_DEGRADED" in blockers


def test_degraded_return_blocked_with_mismatched_return_id():
    packet = p13.read_json(ACCEPTED_PACKET)
    receipt = p13.read_json(ACCEPTANCE_RECEIPT_V2)
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id="some-other-return",
        acceptance_receipt=receipt,
    )
    assert allowed is False
    assert "OBSERVATION_STATUS_DEGRADED" in blockers


def test_degraded_return_blocked_with_wrong_video_sha_receipt():
    packet = p13.read_json(ACCEPTED_PACKET)
    receipt = dict(p13.read_json(ACCEPTANCE_RECEIPT_V2))
    receipt["return_video_sha256"] = "sha256:deadbeef"
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id=ACCEPTED_RETURN_ID,
        acceptance_receipt=receipt,
    )
    assert allowed is False
    assert "OBSERVATION_STATUS_DEGRADED" in blockers


def test_acceptance_receipt_never_overrides_hard_blocks():
    """A forged/valid acceptance receipt can override DEGRADED status but NEVER a
    historical origin, a renderer DEFECT verdict, or a superseded id."""
    packet = p13.read_json(HISTORICAL_PACKET)
    forged = {
        "schema": "persona_dream.post_return_acceptance_receipt.v2",
        "status": "ACCEPTED_AGENT_LEVEL",
        "return_video_sha256": packet.get("source_video_sha256"),
        "return_id": "rev_successor_943b01ecd9a3",
        "gate_summary": {"step_36": True, "step_38": True, "agent_level_gauntlet": "ACCEPTED"},
    }
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id="rev_successor_943b01ecd9a3",
        acceptance_receipt=forged,
    )
    assert allowed is False
    assert "RETURN_IS_HISTORICAL_PROVIDER_RETURN" in blockers
    assert any(b.startswith("IDENTITY_CONTINUITY_DEFECT") for b in blockers)
    # DEGRADED IS overridden by the receipt (it binds), proving overrides are scoped.
    assert "OBSERVATION_STATUS_DEGRADED" not in blockers


def test_accepted_return_blocked_when_in_superseded_set():
    packet = p13.read_json(ACCEPTED_PACKET)
    receipt = p13.read_json(ACCEPTANCE_RECEIPT_V2)
    allowed, blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id=ACCEPTED_RETURN_ID,
        acceptance_receipt=receipt, superseded_return_ids={ACCEPTED_RETURN_ID},
    )
    assert allowed is False
    assert "RETURN_ID_SUPERSEDED" in blockers


def test_acceptance_receipt_certifies_requires_both_gates():
    packet = p13.read_json(ACCEPTED_PACKET)
    receipt = dict(p13.read_json(ACCEPTANCE_RECEIPT_V2))
    receipt["gate_summary"] = {**receipt["gate_summary"], "step_38": False}
    certifies, reasons = p15.acceptance_receipt_certifies(receipt, packet, ACCEPTED_RETURN_ID)
    assert certifies is False
    assert "ACCEPTANCE_STEP_38_NOT_PASS" in reasons
