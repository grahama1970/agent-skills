"""Regression fixtures for the SKILL.md contract checker (#1071).

The live proof is that the checker found real drift on the real file: two
revision-scoped snapshots carrying `actual_provider_call_attempts`, plus the
active revision id and two provider canary request ids. These pin each drift
class so it cannot return silently.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load("check_skill_contract")
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
RUN_SH = (ROOT / "run.sh").read_text(encoding="utf-8")


def _rules(text: str, run_text: str = RUN_SH) -> set[str]:
    return {p["rule"] for p in checker.check(text, run_text)}


def test_real_skill_md_passes():
    assert checker.check(SKILL, RUN_SH) == []


def test_advertised_commands_all_resolve_in_run_sh():
    known = checker.run_sh_commands(RUN_SH)
    advertised = checker.advertised_commands(SKILL)
    assert advertised, "canonical surface advertises no commands"
    assert set(advertised) <= known, set(advertised) - known


def test_phantom_command_blocks():
    bad = SKILL.replace("| `./run.sh read` |", "| `./run.sh totally-not-a-command` |", 1)
    assert "advertised_command_not_in_run_sh" in _rules(bad)


def test_mutable_revision_id_blocks():
    bad = SKILL.replace(
        "The active qualified revision is a mutable fact",
        "The currently active qualified revision is rev_x99. Also",
        1,
    )
    assert "mutable_status_in_contract" in _rules(bad)


def test_provider_request_id_blocks():
    assert "mutable_status_in_contract" in _rules(SKILL + "\nrequest_id: 019f-abc\n")


def test_canary_attempt_history_blocks():
    assert "mutable_status_in_contract" in _rules(
        SKILL + "\nactual_provider_call_attempts: 1\nattempt_ledger_state: FAILED\n"
    )


def test_missing_status_pointer_blocks():
    assert "no_status_pointer" in _rules(SKILL.replace("CURRENT_STATUS.json", "ELSEWHERE"))


def test_broken_relative_link_blocks():
    bad = SKILL.replace("](CURRENT_STATUS.json)", "](NO_SUCH_FILE.json)", 1)
    assert "broken_relative_link" in _rules(bad)


def test_unbalanced_code_fence_blocks():
    assert "unbalanced_code_fences" in _rules(SKILL + "\n```\n")


def test_missing_frontmatter_key_blocks():
    assert "frontmatter_key_missing" in _rules(SKILL.replace("\nprovides:", "\nremoved_provides:", 1))


def test_both_lanes_are_represented():
    low = SKILL.lower()
    assert any(t in low for t in checker.GENERIC_LANE_TOKENS)
    assert any(t in low for t in checker.CONTINUITY_LANE_TOKENS)


def test_continuity_lane_may_not_be_claimed_complete():
    bad = SKILL.replace("continuity lane is under active development and is not complete", "x", 1)
    bad = bad.replace("not complete", "x")
    assert "continuity_lane_overclaimed" in _rules(bad)


def test_speaker_scoring_ownership_is_external_and_consumed():
    low = SKILL.lower()
    assert any(t in low for t in checker.EXTERNAL_EVAL_TOKENS)
    assert "consumes" in low
