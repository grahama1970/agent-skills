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
    assert MODULE.negative_transcript_accepted("Hey Henry.")
    assert MODULE.negative_transcript_accepted("Emery.")
    assert not MODULE.negative_transcript_accepted("Hey, Embry!")
    assert not MODULE.negative_transcript_accepted("")


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
