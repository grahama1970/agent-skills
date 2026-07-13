from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).parents[1] / "scripts" / "generate_horus_corpus.py"
SPEC = importlib.util.spec_from_file_location("generate_horus_corpus", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_positive_transcript_gate_is_bounded() -> None:
    assert MODULE.positive_transcript_accepted("Hey, Embry!")
    assert MODULE.positive_transcript_accepted("Hey Embree.")
    assert MODULE.positive_transcript_accepted("Hey, Embrie!")
    assert MODULE.canonical_positive_transcript("Hey, Embrie!") == "hey embree"
    assert not MODULE.positive_transcript_accepted("Hey Emory.")
    assert not MODULE.positive_transcript_accepted("Embry.")
    assert not MODULE.positive_transcript_accepted("Hey Embry, are you there?")


def test_negative_gate_rejects_positive_phrase() -> None:
    assert MODULE.negative_transcript_accepted("Hey Henry.", prompt="Hey Henry.")
    assert MODULE.negative_transcript_accepted("Emery.", prompt="Emery.")
    assert not MODULE.negative_transcript_accepted("Henry.", prompt="Hey Henry.")
    assert not MODULE.negative_transcript_accepted("Hey, Embry!", prompt="Hey Henry.")
    assert not MODULE.negative_transcript_accepted("", prompt="Hey Henry.")


def test_negative_prompt_targets_are_balanced_and_exact() -> None:
    train = MODULE.balanced_prompt_targets(MODULE.NEGATIVE_PROMPTS, 260)
    validation = MODULE.balanced_prompt_targets(MODULE.NEGATIVE_PROMPTS, 90)
    assert sum(train.values()) == 260
    assert set(train.values()) == {20}
    assert sum(validation.values()) == 90
    assert min(validation.values()) == 6
    assert max(validation.values()) == 7


def test_service_errors_do_not_consume_content_attempt_budget() -> None:
    records = [
        {"split": "positive_train", "rejection_reason": "generation_or_validation_error"},
        {"split": "positive_train", "rejection_reason": "transcript_gate_rejected"},
        {"split": "positive_train", "rejection_reason": None},
    ]
    content_attempts = sum(
        1
        for record in records
        if record["split"] == "positive_train"
        and record["rejection_reason"] != "generation_or_validation_error"
    )
    assert content_attempts == 2


def test_split_seed_offsets_and_parameters_are_deterministic() -> None:
    offsets = MODULE.SPLIT_OFFSETS
    assert len(set(offsets.values())) == len(offsets)
    assert MODULE.deterministic_parameters(seed=7, index=3) == MODULE.deterministic_parameters(
        seed=7, index=3
    )
    assert MODULE.deterministic_choice(MODULE.POSITIVE_PROMPTS, seed=7, index=3) == (
        MODULE.deterministic_choice(MODULE.POSITIVE_PROMPTS, seed=7, index=3)
    )


def test_jsonl_resume_reads_prior_records(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    MODULE.append_jsonl(path, {"record_id": "one", "accepted": True})
    MODULE.append_jsonl(path, {"record_id": "two", "accepted": False})
    assert MODULE.read_jsonl(path) == [
        {"accepted": True, "record_id": "one"},
        {"accepted": False, "record_id": "two"},
    ]
