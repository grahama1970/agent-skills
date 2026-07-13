from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).parents[1] / "scripts" / "write_revision_artifact_index.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("write_revision_artifact_index", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_storyboard_frame_ids_are_stable_and_checkout_independent() -> None:
    assert module.canonical_artifact_id(
        Path("sb_001_start_frame.png"),
        "07",
        "phase_07/generated_storyboard_frames/sb_001_start_frame.png",
    ) == "sb_001.start_frame"
    assert module.canonical_artifact_id(
        Path("sb_004_END_frame.webp"),
        "07",
        "different/root/sb_004_END_frame.webp",
    ) == "sb_004.end_frame"


def test_non_storyboard_artifacts_keep_optional_ids() -> None:
    assert module.canonical_artifact_id(
        Path("notes.json"),
        "07",
        "phase_07/notes.json",
    ) == "phase07.phase.07.notes.json"
