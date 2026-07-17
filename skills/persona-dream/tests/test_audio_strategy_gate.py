from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audio_strategy_gate as gate  # noqa: E402
import phase11_payload_binding as binding_module  # noqa: E402
from phase11_fixture_helpers import make_compilation_inputs, write_json  # noqa: E402


LINE = "If we paddle now, we're cutting across the lineup."


def file_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def make_voiced_revision(tmp_path: Path, strategy: str = "post_mux") -> Path:
    revision_root = tmp_path / "rev_test"
    transcript_path = revision_root / "phase_06_script/timed_transcript.json"
    dna_path = revision_root / "phase_03_crew/script_dna_selection.json"
    receipt_path = revision_root / "phase_05_voices/kai_voice_audition.json"
    write_json(
        transcript_path,
        [{"start_s": 0.0, "end_s": 10.0, "speaker": "Kai", "text": LINE}],
    )
    write_json(dna_path, {"dialogue_style": "near-silent; at most one quiet practical line from Kai"})
    write_json(receipt_path, {"schema": "persona_dream.voice_audition_receipt.v1"})
    reference = tmp_path / "kai-reference.wav"
    ambience = tmp_path / "ocean.wav"
    reference.write_bytes(b"RIFF-reference")
    ambience.write_bytes(b"RIFF-ambience")
    write_json(
        revision_root / gate.VOICE_HANDOFF_RELATIVE,
        {
            "schema": gate.VOICE_HANDOFF_SCHEMA,
            "revision_id": "rev_test",
            "strategy": strategy,
            "provider_request": {
                "request_body_sha256": f"sha256:{'a' * 64}",
                "generate_audio": strategy != "post_mux",
            },
            "timed_transcript": {
                "revision_relative_path": "phase_06_script/timed_transcript.json",
                "sha256": file_sha(transcript_path),
            },
            "lines": [{"speaker": "Kai", "text": LINE, "start_s": 0.0, "end_s": 10.0}],
            "voice_bindings": {
                "Kai": {
                    "source_receipt_relative_path": "phase_05_voices/kai_voice_audition.json",
                    "source_receipt_sha256": file_sha(receipt_path),
                    "conditioning_reference": {"path": str(reference), "sha256": file_sha(reference)},
                }
            },
            "ambient_beds": [{"path": str(ambience), "sha256": file_sha(ambience)}],
        },
    )
    return revision_root


def test_classifies_near_silent_voiced_run_with_one_spoken_line():
    transcript = [
        {
            "start_s": 0.0,
            "end_s": 10.0,
            "speaker": None,
            "text": "Embry carries the autonomy pivot.",
            "voice_direction": "action description",
        },
        {
            "start_s": 0.0,
            "end_s": 10.0,
            "speaker": "Kai",
            "text": LINE,
            "voice_direction": "quiet, practical restraint",
        },
    ]
    script_dna = {"dialogue_style": "near-silent; at most one quiet practical line from Kai"}
    assert gate.classify_audio_strategy(timed_transcript=transcript, script_dna=script_dna) == (
        "NEAR_SILENT_VOICED"
    )


def test_post_mux_accepts_silent_provider_prompts_when_handoff_is_valid(tmp_path: Path):
    revision_root = make_voiced_revision(tmp_path)
    assessment = gate.assess_and_block_kling_request(
        revision_root,
        generate_audio=False,
        multi_prompt=[{"prompt": "SB_003. Silent shot: No spoken dialogue. No lip movement."}],
    )
    assert assessment.voice_handoff_valid is True
    assert assessment.delivery_mode == "post_mux"
    assert assessment.blockers == ()


def test_post_mux_fails_closed_when_reference_file_disappears(tmp_path: Path):
    revision_root = make_voiced_revision(tmp_path)
    plan_path = revision_root / gate.VOICE_HANDOFF_RELATIVE
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    Path(plan["voice_bindings"]["Kai"]["conditioning_reference"]["path"]).unlink()
    assessment = gate.assess_and_block_kling_request(revision_root, generate_audio=False)
    assert assessment.voice_handoff_valid is False
    assert "BLOCKED_VOICED_RUN_HANDOFF_INVALID" in assessment.blockers
    assert "VOICE_HANDOFF_REFERENCE:Kai_MISSING" in assessment.validation_errors


def test_post_mux_fails_closed_when_planned_words_differ(tmp_path: Path):
    revision_root = make_voiced_revision(tmp_path)
    plan_path = revision_root / gate.VOICE_HANDOFF_RELATIVE
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["lines"][0]["text"] = "Different words."
    write_json(plan_path, plan)
    assessment = gate.assess_and_block_kling_request(revision_root, generate_audio=False)
    assert "VOICE_HANDOFF_LINES_DO_NOT_MATCH_TRANSCRIPT" in assessment.validation_errors


def test_native_audio_requires_dialogue_and_generate_audio(tmp_path: Path):
    revision_root = make_voiced_revision(tmp_path, strategy="kling_native")
    assessment = gate.assess_and_block_kling_request(
        revision_root,
        generate_audio=False,
        multi_prompt=[{"prompt": "No spoken dialogue."}],
    )
    assert assessment.blockers == (
        "BLOCKED_KLING_NATIVE_REQUIRES_GENERATE_AUDIO",
        "BLOCKED_VOICED_RUN_DIALOGUE_STRIPPED",
    )


def test_custom_voice_requires_voice_id_and_prompt_token(tmp_path: Path):
    revision_root = make_voiced_revision(tmp_path, strategy="kling_custom_voice")
    assessment = gate.assess_and_block_kling_request(
        revision_root,
        generate_audio=True,
        multi_prompt=[{"prompt": f"Kai says: {LINE}"}],
    )
    assert assessment.blockers == (
        "BLOCKED_KLING_CUSTOM_VOICE_ID_MISSING",
        "BLOCKED_KLING_CUSTOM_VOICE_TOKEN_MISSING",
    )


def test_post_mux_return_requires_audio_stream_and_mux_receipt(tmp_path: Path):
    assessment = gate.assess_revision_audio_strategy(make_voiced_revision(tmp_path))
    assert gate.blockers_for_provider_return(
        assessment, mp4_has_audio_stream=True, mux_receipt_present=False
    ) == ["BLOCKED_VOICED_RUN_AWAITING_AUDIO_MUX"]
    assert gate.blockers_for_provider_return(
        assessment, mp4_has_audio_stream=True, mux_receipt_present=True
    ) == []


def test_silent_fixture_still_passes_phase11_bootstrap(tmp_path: Path):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    binding = json.loads(inputs.candidate_binding_path.read_text(encoding="utf-8"))
    binding_module.validate_payload_binding(
        binding,
        context=inputs.context,
        phase10_payload_path=inputs.phase10_payload_path,
        media_lock_path=inputs.media_lock_path,
    )


def test_active_revision_has_hash_bound_post_mux_handoff():
    revision_root = Path(
        "/home/graham/workspace/experiments/agent-skills-main/skills/persona-dream/"
        "reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8"
    )
    if not revision_root.is_dir() or not (revision_root / gate.VOICE_HANDOFF_RELATIVE).is_file():
        pytest.skip("active pipeline-complete handoff not installed")
    assessment = gate.assess_revision_audio_strategy(revision_root)
    assert assessment.classification == "NEAR_SILENT_VOICED"
    assert assessment.delivery_mode == "post_mux"
    assert assessment.voice_handoff_valid is True
    assert gate.blockers_for_kling_request(
        assessment,
        generate_audio=False,
        multi_prompt=[{"prompt": "SB_003. Silent shot: No spoken dialogue. No lip movement."}],
    ) == []
