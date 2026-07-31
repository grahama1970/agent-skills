"""Battle source-bearing Dogpile research gate tests for #1114."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = SKILL_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import battle_skill.memory as battle_memory  # noqa: E402
from battle_skill.memory import BattleMemory, DOGPILE_EVENT_PREFIX  # noqa: E402


def _write_dogpile_script(tmp_path: Path, lines: list[dict[str, object]], *, sleep_s: float = 0) -> Path:
    run_sh = tmp_path / "run.sh"
    body = ["#!/usr/bin/env python3", "import json, sys, time"]
    for line in lines:
        body.append(
            f"print({DOGPILE_EVENT_PREFIX!r} + json.dumps(json.loads({json.dumps(json.dumps(line))})), "
            "file=sys.stderr, flush=True)"
        )
    if sleep_s:
        body.append(f"time.sleep({sleep_s})")
    body.append("print('# dogpile fixture stdout')")
    run_sh.write_text("\n".join(body) + "\n")
    run_sh.chmod(0o755)
    return run_sh


def test_battle_rejects_model_only_research(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_dogpile_script(
        tmp_path,
        [
            {
                "event": "partial_result",
                "provider": "codex_knowledge",
                "summary": {"ok": True, "source_bearing_evidence_count": 0, "model_synthesis_present": True},
            },
            {"event": "search_finished", "status": "completed"},
        ],
    )
    monkeypatch.setattr(battle_memory, "DOGPILE_SKILL", tmp_path)

    result = BattleMemory("fixture-battle", "red").research("fixture", force=True, deadline_s=5)

    assert result["success"] is False
    assert result["error"] == "research_degraded_no_sources"
    assert result["productive_provider_count"] == 1
    assert result["source_bearing_provider_count"] == 0
    assert result["source_bearing_evidence_count"] == 0
    assert result["model_synthesis_present"] is True
    assert result["research_evidence_sufficient"] is False


def test_battle_accepts_source_bearing_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_dogpile_script(
        tmp_path,
        [
            {
                "event": "partial_result",
                "provider": "brave",
                "summary": {"ok": True, "source_bearing_evidence_count": 2, "source_bearing": True},
            },
            {
                "event": "partial_result",
                "provider": "codex_knowledge",
                "summary": {"ok": True, "source_bearing_evidence_count": 0, "model_synthesis_present": True},
            },
            {"event": "search_finished", "status": "completed"},
        ],
    )
    monkeypatch.setattr(battle_memory, "DOGPILE_SKILL", tmp_path)

    result = BattleMemory("fixture-battle", "blue").research("fixture", force=True, deadline_s=5)

    assert result["success"] is True
    assert result["productive_provider_count"] == 2
    assert result["source_bearing_provider_count"] == 1
    assert result["source_bearing_evidence_count"] == 2
    assert result["source_bearing_providers"] == ["brave"]
    assert result["model_synthesis_present"] is True
    assert result["research_evidence_sufficient"] is True


def test_battle_timeout_before_sources_is_degraded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_dogpile_script(
        tmp_path,
        [
            {
                "event": "partial_result",
                "provider": "codex_knowledge",
                "summary": {"ok": True, "source_bearing_evidence_count": 0, "model_synthesis_present": True},
            }
        ],
        sleep_s=2,
    )
    monkeypatch.setattr(battle_memory, "DOGPILE_SKILL", tmp_path)

    result = BattleMemory("fixture-battle", "red").research("fixture", force=True, deadline_s=1)

    assert result["success"] is False
    assert result["timed_out"] is True
    assert "source-bearing provider" in result["error"]
    assert result["source_bearing_evidence_count"] == 0
