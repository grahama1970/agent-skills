from __future__ import annotations

import json
from pathlib import Path

import pytest

from embry_voice_control.audio_e2e.case_compiler import compile_campaign


def write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    sessions = []
    for folder in ("memory", "research"):
        for difficulty in ("simple", "advanced"):
            for index in range(1, 3):
                sessions.append({
                    "id": f"{folder}-{difficulty}-{index:02d}", "folder_id": folder, "difficulty": difficulty,
                    "question": f"Question {folder} {difficulty} {index}?", "oracle": {"type": "grounded"},
                    "expected_route": {"first_authority": "memory"}, "conversation_requirements": {"flat_neutral_allowed": False},
                    "source_generation": {"template_index": index},
                })
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"schema": "embry.stress_session_matrix.v1", "sessions": sessions}))
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema": "embry.audio_e2e_source_policy.v1"}))
    return matrix, policy


def test_compile_one_case_is_deterministic_and_multiturn(tmp_path: Path) -> None:
    matrix, policy = write_inputs(tmp_path)
    first = compile_campaign(matrix_path=matrix, source_policy_path=policy, case_id="memory-simple-01")
    second = compile_campaign(matrix_path=matrix, source_policy_path=policy, case_id="memory-simple-01")
    assert first == second
    assert len(first["cases"]) == 1
    assert len(first["cases"][0]["turn_script"]) == 2
    assert first["execution"]["typed_transcript_allowed"] is False
    assert first["execution"]["browser_microphone_allowed"] is False


def test_stratified_selection_spans_buckets(tmp_path: Path) -> None:
    matrix, policy = write_inputs(tmp_path)
    manifest = compile_campaign(matrix_path=matrix, source_policy_path=policy, stratified_count=4)
    assert {(case["folder_id"], case["difficulty"]) for case in manifest["cases"]} == {
        ("memory", "simple"), ("memory", "advanced"), ("research", "simple"), ("research", "advanced")
    }


@pytest.mark.parametrize("source_mode", ["typed", "browser_microphone", "generic_tts"])
def test_non_countable_source_modes_fail_closed(tmp_path: Path, source_mode: str) -> None:
    matrix, policy = write_inputs(tmp_path)
    with pytest.raises(ValueError, match="source_mode_not_countable"):
        compile_campaign(matrix_path=matrix, source_policy_path=policy, case_id="memory-simple-01", source_mode=source_mode)
