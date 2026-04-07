"""Tests for review-conversation skill: models.py loaders/filters and renderers.py outputs.

All fixtures are inline -- no external files required.
Run:  pytest test_review_conversation.py -v
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

# Ensure the skill directory is importable.
_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from models import (
    filter_sessions,
    load_delta_index,
    load_sessions,
    load_shadow_index,
)
from renderers import (
    brief_session,
    build_heatmap_json,
    build_metrics_json,
    build_radar_json,
)

# ---------------------------------------------------------------------------
# Helpers: realistic session / shadow / delta builders
# ---------------------------------------------------------------------------

_COUNTER = 0


def _make_session(
    *,
    session_id: str | None = None,
    persona: str = "brandon",
    difficulty: str = "medium",
    resolution: str = "resolved",
    grade: str = "A",
    composite: float = 0.88,
    scores: dict | None = None,
    turns: list[dict] | None = None,
    rationale: str = "Solid answer.",
) -> dict:
    """Build a realistic session dict with sensible defaults."""
    global _COUNTER
    _COUNTER += 1
    sid = session_id or f"sess-{_COUNTER:04d}"

    if scores is None:
        scores = {
            "accuracy": composite,
            "relevance": composite + 0.02,
            "completeness": composite - 0.03,
        }

    if turns is None:
        turns = [
            {
                "turn_number": 1,
                "speaker": "persona",
                "role": "persona",
                "action": "QUERY",
                "content": "What is SV-SP-1?",
                "timestamp": "2026-02-20T10:00:00",
                "metadata": {},
            },
            {
                "turn_number": 2,
                "speaker": "assistant",
                "role": "assistant",
                "action": "ANSWER",
                "content": "SV-SP-1 is a security control for system protection.",
                "timestamp": "2026-02-20T10:00:05",
                "metadata": {
                    "self_grade_final": {
                        "grade": grade,
                        "composite": composite,
                        "iteration": 1,
                        "qra_count": 3,
                        "rationale": rationale,
                        "issues": [],
                    },
                },
            },
            {
                "turn_number": 3,
                "speaker": "persona",
                "role": "persona",
                "action": "FOLLOW_UP",
                "content": "That covers it.",
                "timestamp": "2026-02-20T10:00:10",
                "metadata": {
                    "evaluation": "satisfactory",
                    "reasoning": "The answer addressed the control accurately.",
                },
            },
        ]

    return {
        "session_id": sid,
        "persona": persona,
        "status": "completed",
        "resolution": resolution,
        "adversarial": False,
        "seed_question": {
            "difficulty": difficulty,
            "expected_action": "ANSWER",
            "target_control": "SV-SP-1",
            "grading_notes": "Standard lookup question.",
        },
        "turns": turns,
        "grade": {
            "grade": grade,
            "composite": composite,
            "scores": scores,
            "rationale": rationale,
            "tier": "gold",
            "source": "self",
        },
    }


def _make_shadow(session_id: str, *, agreed: bool = True, teacher_grade: str = "A") -> dict:
    return {
        "input_data": {"session_id": session_id},
        "session_id": session_id,
        "local_grade": "A",
        "teacher_grade": teacher_grade,
        "local_confidence": 0.85,
        "teacher_confidence": 0.90,
        "agreed": agreed,
        "student_model": "qwen3-1.7b",
        "teacher_model": "gpt-4o",
        "qra_citation_count": 3,
        "qra_citations_verified": 2,
        "qra_grounding_avg": 0.78,
    }


def _make_delta(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "first_composite": 0.65,
        "final_composite": 0.92,
        "delta": 0.27,
        "outer_rounds": 2,
        "inner_iterations": 4,
        "persona_evaluation": "satisfactory",
        "target_met": True,
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


# ===================================================================
# 1. Data loaders
# ===================================================================


class TestLoadSessions:
    def test_valid_jsonl(self, tmp_path: Path) -> None:
        f = tmp_path / "sessions.jsonl"
        s1 = _make_session(session_id="s1")
        s2 = _make_session(session_id="s2")
        _write_jsonl(f, [s1, s2])

        result = load_sessions(f)
        assert len(result) == 2
        assert result[0]["session_id"] == "s1"
        assert result[1]["session_id"] == "s2"

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert load_sessions(f) == []

    def test_missing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "does_not_exist.jsonl"
        assert load_sessions(f) == []

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        good = json.dumps(_make_session(session_id="good"))
        f = tmp_path / "mixed.jsonl"
        f.write_text(f"{good}\n{{bad json\n\n{good}\n")

        result = load_sessions(f)
        assert len(result) == 2
        assert all(r["session_id"] == "good" for r in result)

    def test_blank_lines_ignored(self, tmp_path: Path) -> None:
        rec = json.dumps(_make_session(session_id="only"))
        f = tmp_path / "blanks.jsonl"
        f.write_text(f"\n\n{rec}\n\n\n")
        assert len(load_sessions(f)) == 1


class TestLoadShadowIndex:
    def test_indexes_by_session_id(self, tmp_path: Path) -> None:
        f = tmp_path / "shadow.jsonl"
        _write_jsonl(f, [_make_shadow("s1"), _make_shadow("s2", agreed=False)])

        idx = load_shadow_index(f)
        assert "s1" in idx
        assert "s2" in idx
        assert idx["s1"]["agreed"] is True
        assert idx["s2"]["agreed"] is False

    def test_uses_input_data_session_id(self, tmp_path: Path) -> None:
        """Prefers input_data.session_id over top-level session_id."""
        entry = {"input_data": {"session_id": "from_input"}, "session_id": "from_top"}
        f = tmp_path / "shadow.jsonl"
        _write_jsonl(f, [entry])

        idx = load_shadow_index(f)
        assert "from_input" in idx
        assert "from_top" not in idx

    def test_missing_file(self, tmp_path: Path) -> None:
        assert load_shadow_index(tmp_path / "nope.jsonl") == {}

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "shadow.jsonl"
        good = json.dumps(_make_shadow("s1"))
        f.write_text(f"{good}\n{{broken\n")
        idx = load_shadow_index(f)
        assert len(idx) == 1


class TestLoadDeltaIndex:
    def test_indexes_by_session_id(self, tmp_path: Path) -> None:
        f = tmp_path / "deltas.jsonl"
        _write_jsonl(f, [_make_delta("s1"), _make_delta("s2")])

        idx = load_delta_index(f)
        assert "s1" in idx
        assert idx["s1"]["delta"] == 0.27

    def test_missing_file(self, tmp_path: Path) -> None:
        assert load_delta_index(tmp_path / "nope.jsonl") == {}


# ===================================================================
# 2. filter_sessions
# ===================================================================


def _default_indices():
    """Empty shadow/delta indices for tests that don't need them."""
    return {}, {}


class TestFilterByGrade:
    def test_matches_grade(self) -> None:
        s = [_make_session(grade="A"), _make_session(grade="F")]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, grade="A")
        assert len(result) == 1
        assert result[0]["grade"]["grade"] == "A"

    def test_case_insensitive(self) -> None:
        s = [_make_session(grade="B")]
        shadow, delta = _default_indices()
        assert len(filter_sessions(s, shadow, delta, grade="b")) == 1

    def test_no_match(self) -> None:
        s = [_make_session(grade="A")]
        shadow, delta = _default_indices()
        assert filter_sessions(s, shadow, delta, grade="F") == []


class TestFilterByResolution:
    def test_matches_resolution(self) -> None:
        s = [
            _make_session(resolution="resolved"),
            _make_session(resolution="no_coverage"),
        ]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, resolution="no_coverage")
        assert len(result) == 1
        assert result[0]["resolution"] == "no_coverage"

    def test_case_insensitive(self) -> None:
        s = [_make_session(resolution="Resolved")]
        shadow, delta = _default_indices()
        assert len(filter_sessions(s, shadow, delta, resolution="resolved")) == 1


class TestFilterByEvaluation:
    def _session_with_eval(self, evaluation: str, session_id: str | None = None) -> dict:
        turns = [
            {
                "turn_number": 1, "speaker": "persona", "role": "persona",
                "action": "QUERY", "content": "Question?", "metadata": {},
            },
            {
                "turn_number": 2, "speaker": "assistant", "role": "assistant",
                "action": "ANSWER", "content": "Answer.",
                "metadata": {
                    "self_grade_final": {
                        "grade": "A", "composite": 0.9, "iteration": 0,
                        "qra_count": 2, "rationale": "Good.", "issues": [],
                    },
                },
            },
            {
                "turn_number": 3, "speaker": "persona", "role": "persona",
                "action": "FOLLOW_UP", "content": "Thanks.",
                "metadata": {
                    "evaluation": evaluation,
                    "reasoning": f"Marked as {evaluation}.",
                },
            },
        ]
        return _make_session(turns=turns, session_id=session_id)

    def test_positive_match(self) -> None:
        s = [
            self._session_with_eval("satisfactory"),
            self._session_with_eval("wrong"),
        ]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, evaluation="wrong")
        assert len(result) == 1

    def test_negation(self) -> None:
        s = [
            self._session_with_eval("satisfactory", session_id="sat"),
            self._session_with_eval("wrong", session_id="wrn"),
        ]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, evaluation="!satisfactory")
        assert len(result) == 1
        assert result[0]["session_id"] == "wrn"

    def test_no_eval_turns_excluded(self) -> None:
        """Session with no evaluation metadata should not match positive filter."""
        turns = [
            {"turn_number": 1, "speaker": "persona", "action": "QUERY",
             "content": "Hi", "metadata": {}},
        ]
        s = [_make_session(turns=turns)]
        shadow, delta = _default_indices()
        assert filter_sessions(s, shadow, delta, evaluation="satisfactory") == []


class TestFilterByFirstEval:
    def _two_eval_session(self, first: str, second: str) -> dict:
        turns = [
            {"turn_number": 1, "speaker": "persona", "action": "QUERY",
             "content": "Q?", "metadata": {}},
            {"turn_number": 2, "speaker": "assistant", "action": "ANSWER",
             "content": "A.", "metadata": {"self_grade_final": {
                 "grade": "B", "composite": 0.7, "iteration": 0,
                 "qra_count": 1, "rationale": "OK", "issues": []}}},
            {"turn_number": 3, "speaker": "persona", "action": "FOLLOW_UP",
             "content": "Hmm.", "metadata": {"evaluation": first, "reasoning": "first"}},
            {"turn_number": 4, "speaker": "assistant", "action": "ANSWER",
             "content": "Better A.", "metadata": {"self_grade_final": {
                 "grade": "A", "composite": 0.9, "iteration": 1,
                 "qra_count": 2, "rationale": "Improved", "issues": []}}},
            {"turn_number": 5, "speaker": "persona", "action": "FOLLOW_UP",
             "content": "OK.", "metadata": {"evaluation": second, "reasoning": "second"}},
        ]
        return _make_session(turns=turns)

    def test_first_eval_positive(self) -> None:
        s = [self._two_eval_session("incomplete", "satisfactory")]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, first_eval="incomplete")
        assert len(result) == 1

    def test_first_eval_negative(self) -> None:
        s = [self._two_eval_session("incomplete", "satisfactory")]
        shadow, delta = _default_indices()
        # first eval IS incomplete, so !incomplete should exclude it
        assert filter_sessions(s, shadow, delta, first_eval="!incomplete") == []

    def test_first_eval_negation_passes(self) -> None:
        s = [self._two_eval_session("satisfactory", "wrong")]
        shadow, delta = _default_indices()
        # first eval is satisfactory, !wrong should pass since first != wrong
        result = filter_sessions(s, shadow, delta, first_eval="!wrong")
        assert len(result) == 1


class TestFilterByComposite:
    def test_min_composite(self) -> None:
        s = [_make_session(composite=0.5), _make_session(composite=0.9)]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, min_composite=0.8)
        assert len(result) == 1
        assert result[0]["grade"]["composite"] == 0.9

    def test_max_composite(self) -> None:
        s = [_make_session(composite=0.5), _make_session(composite=0.9)]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, max_composite=0.6)
        assert len(result) == 1
        assert result[0]["grade"]["composite"] == 0.5

    def test_min_and_max(self) -> None:
        s = [
            _make_session(composite=0.3),
            _make_session(composite=0.6),
            _make_session(composite=0.95),
        ]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, min_composite=0.5, max_composite=0.7)
        assert len(result) == 1


class TestFilterByDifficulty:
    def test_matches(self) -> None:
        s = [
            _make_session(difficulty="simple"),
            _make_session(difficulty="complex"),
        ]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, difficulty="complex")
        assert len(result) == 1

    def test_case_insensitive(self) -> None:
        s = [_make_session(difficulty="Complex")]
        shadow, delta = _default_indices()
        assert len(filter_sessions(s, shadow, delta, difficulty="complex")) == 1


class TestFilterByPersona:
    def test_substring_match(self) -> None:
        s = [
            _make_session(persona="brandon_skeptic"),
            _make_session(persona="margaret_thorough"),
        ]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, persona="brandon")
        assert len(result) == 1

    def test_case_insensitive(self) -> None:
        s = [_make_session(persona="Brandon")]
        shadow, delta = _default_indices()
        assert len(filter_sessions(s, shadow, delta, persona="brandon")) == 1


class TestFilterByMinTurns:
    def test_filters_short_sessions(self) -> None:
        short_turns = [
            {"turn_number": 1, "speaker": "persona", "action": "QUERY",
             "content": "Q", "metadata": {}},
        ]
        long = _make_session()  # default has 3 turns
        short = _make_session(turns=short_turns)
        shadow, delta = _default_indices()
        result = filter_sessions([short, long], shadow, delta, min_turns=3)
        assert len(result) == 1


class TestFilterByText:
    def test_finds_in_content(self) -> None:
        s = [_make_session()]  # default content mentions "SV-SP-1"
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, text="SV-SP-1")
        assert len(result) == 1

    def test_case_insensitive(self) -> None:
        s = [_make_session()]
        shadow, delta = _default_indices()
        assert len(filter_sessions(s, shadow, delta, text="sv-sp-1")) == 1

    def test_no_match(self) -> None:
        s = [_make_session()]
        shadow, delta = _default_indices()
        assert filter_sessions(s, shadow, delta, text="ZZZNONEXISTENT") == []

    def test_finds_in_rationale(self) -> None:
        s = [_make_session(rationale="The quantum flux capacitor was relevant.")]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, text="quantum flux")
        assert len(result) == 1


class TestFilterByAgreed:
    def test_agreed_true(self) -> None:
        s1 = _make_session(session_id="agreed-sess")
        s2 = _make_session(session_id="disagreed-sess")
        shadow = {
            "agreed-sess": _make_shadow("agreed-sess", agreed=True),
            "disagreed-sess": _make_shadow("disagreed-sess", agreed=False),
        }
        result = filter_sessions([s1, s2], shadow, {}, agreed=True)
        assert len(result) == 1
        assert result[0]["session_id"] == "agreed-sess"

    def test_agreed_false(self) -> None:
        s1 = _make_session(session_id="agreed-sess")
        s2 = _make_session(session_id="disagreed-sess")
        shadow = {
            "agreed-sess": _make_shadow("agreed-sess", agreed=True),
            "disagreed-sess": _make_shadow("disagreed-sess", agreed=False),
        }
        result = filter_sessions([s1, s2], shadow, {}, agreed=False)
        assert len(result) == 1
        assert result[0]["session_id"] == "disagreed-sess"

    def test_no_shadow_excluded(self) -> None:
        """Sessions without shadow data are excluded when agreed filter is set."""
        s = [_make_session(session_id="orphan")]
        result = filter_sessions([s[0]], {}, {}, agreed=True)
        assert result == []


class TestFilterCombined:
    """Multiple filters are AND-combined."""

    def test_grade_and_difficulty(self) -> None:
        s = [
            _make_session(grade="A", difficulty="simple"),
            _make_session(grade="A", difficulty="complex"),
            _make_session(grade="F", difficulty="complex"),
        ]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, grade="A", difficulty="complex")
        assert len(result) == 1
        assert result[0]["grade"]["grade"] == "A"
        assert result[0]["seed_question"]["difficulty"] == "complex"

    def test_persona_and_min_composite(self) -> None:
        s = [
            _make_session(persona="brandon", composite=0.3),
            _make_session(persona="brandon", composite=0.95),
            _make_session(persona="margaret", composite=0.95),
        ]
        shadow, delta = _default_indices()
        result = filter_sessions(s, shadow, delta, persona="brandon", min_composite=0.8)
        assert len(result) == 1
        assert result[0]["persona"] == "brandon"

    def test_all_filters_no_match_returns_empty(self) -> None:
        s = [_make_session()]
        shadow, delta = _default_indices()
        result = filter_sessions(
            s, shadow, delta,
            grade="F", resolution="no_coverage", difficulty="flawed",
            persona="nonexistent", min_turns=100,
        )
        assert result == []


# ===================================================================
# 3. brief_session output: no ANSI codes
# ===================================================================


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class TestBriefSession:
    def test_no_ansi_codes(self) -> None:
        session = _make_session()
        output = brief_session(session)
        assert not _ANSI_RE.search(output), f"ANSI codes found in brief output: {output!r}"

    def test_contains_session_id(self) -> None:
        session = _make_session(session_id="test-brief-id")
        output = brief_session(session)
        assert "test-brief-id" in output

    def test_contains_persona(self) -> None:
        session = _make_session(persona="margaret_thorough")
        output = brief_session(session)
        assert "margaret_thorough" in output

    def test_contains_grade(self) -> None:
        session = _make_session(grade="B", composite=0.72)
        output = brief_session(session)
        assert "B" in output
        assert "0.72" in output

    def test_with_shadow_no_ansi(self) -> None:
        session = _make_session(session_id="shadow-brief")
        shadow = _make_shadow("shadow-brief", teacher_grade="B")
        output = brief_session(session, shadow_entry=shadow)
        assert not _ANSI_RE.search(output)
        assert "DISAGREE" not in output  # agreed=True by default
        assert "AGREE" in output


# ===================================================================
# 4. JSON builders: schema validation
# ===================================================================


class TestBuildRadarJson:
    def test_schema(self) -> None:
        sessions = [
            _make_session(persona="alice", scores={"accuracy": 0.9, "relevance": 0.8}),
            _make_session(persona="bob", scores={"accuracy": 0.7, "relevance": 0.6}),
        ]
        result = build_radar_json(sessions)
        assert "series" in result
        assert isinstance(result["series"], dict)
        assert len(result["series"]) == 2
        for label, dims in result["series"].items():
            assert isinstance(dims, dict)
            for dim_name, val in dims.items():
                assert isinstance(val, float)

    def test_empty_sessions(self) -> None:
        result = build_radar_json([])
        assert result == {"series": {}}

    def test_session_without_scores_skipped(self) -> None:
        session = _make_session()
        session["grade"]["scores"] = {}
        result = build_radar_json([session])
        assert result["series"] == {}


class TestBuildHeatmapJson:
    def test_schema(self) -> None:
        sessions = [
            _make_session(difficulty="simple", grade="A"),
            _make_session(difficulty="simple", grade="A"),
            _make_session(difficulty="complex", grade="F"),
        ]
        result = build_heatmap_json(sessions)
        assert isinstance(result, dict)
        assert "simple" in result
        assert "complex" in result
        assert result["simple"]["A"] == 2
        assert result["complex"]["F"] == 1

    def test_empty(self) -> None:
        assert build_heatmap_json([]) == {}


class TestBuildMetricsJson:
    def test_schema(self) -> None:
        s1 = _make_session(session_id="m1", grade="A", resolution="resolved")
        s2 = _make_session(session_id="m2", grade="F", resolution="no_coverage")
        shadow = {"m1": _make_shadow("m1", agreed=True)}

        result = build_metrics_json([s1, s2], shadow)

        assert "grade_distribution" in result
        assert "resolution_distribution" in result
        assert "agreement" in result

        gd = result["grade_distribution"]["metrics"]
        assert gd["A"] == 1
        assert gd["F"] == 1

        rd = result["resolution_distribution"]["metrics"]
        assert rd["resolved"] == 1
        assert rd["no_coverage"] == 1

        ag = result["agreement"]["metrics"]
        assert ag["agreed"] == 1
        assert ag["disagreed"] == 0
        assert ag["no_teacher"] == 1  # s2 has no shadow

    def test_empty(self) -> None:
        result = build_metrics_json([], {})
        assert result["agreement"]["metrics"]["agreed"] == 0
        assert result["agreement"]["metrics"]["no_teacher"] == 0
