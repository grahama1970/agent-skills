"""Contract tests for cleanup skill operating instructions."""

import json
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent
SKILL_TEXT = (SKILL_DIR / "SKILL.md").read_text()


def test_skill_uses_canonical_agent_skills_commands():
    assert "/home/graham/workspace/experiments/agent-skills/skills/cleanup/run.sh" in SKILL_TEXT
    assert "/home/graham/workspace/experiments/agent-skills/skills/ingest-code/run.sh" in SKILL_TEXT
    assert ".pi/skills/cleanup/run.sh" not in SKILL_TEXT
    assert ".pi/skills/ingest-code/run.sh" not in SKILL_TEXT


def test_deprecated_move_contract_is_explicit_and_preserving():
    required_phrases = [
        "Human-authorized deprecated move",
        "move to deprecated folder, do not delete",
        "deprecated/cleanup-<YYYYMMDD>/<class>/",
        "MOVE_RECEIPT.tsv",
        "old_paths_absent",
        "new_files_present",
        "receipt_records",
        "Do not run `rm`",
        "Do not stage unrelated dirty worktree entries",
    ]
    for phrase in required_phrases:
        assert phrase in SKILL_TEXT


def test_root_stray_and_artifact_mutation_require_owner_receipts():
    assert (
        "| `root_stray_mutation` | human owner decision + path-scoped deprecated move receipt |"
        in SKILL_TEXT
    )
    assert (
        "| `artifact_archive` | human owner decision + path-scoped deprecated move receipt |"
        in SKILL_TEXT
    )


def test_agentic_eval_covers_deprecated_move_regression():
    fixture = json.loads((SKILL_DIR / "fixtures" / "agentic_eval.json").read_text())
    case_names = {case["name"] for case in fixture["cases"]}
    assert "deprecated-move-contract" in case_names
