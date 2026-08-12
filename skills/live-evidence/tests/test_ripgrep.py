"""Tests for real fixed-string current-source retrieval."""

import asyncio
from pathlib import Path

from live_evidence.config import AppSettings, InterviewProfile
from live_evidence.models import Freshness, RetrievalLane
from live_evidence.retrieval.ripgrep import RipgrepEvidenceClient


def test_ripgrep_returns_current_source(tmp_path: Path) -> None:
    repo = tmp_path / "tau"
    repo.mkdir()
    source = repo / "README.md"
    source.write_text(
        "Tau uses receipt admission to keep agent work inspectable and bounded.\n",
        encoding="utf-8",
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: test\n", encoding="utf-8")
    settings = AppSettings(
        skill_root=tmp_path,
        data_dir=tmp_path / "data",
        profile_path=profile_path,
        repo_roots=[repo],
        memory_url="http://127.0.0.1:9",
        subprocess_timeout_s=3.0,
    )
    profile = InterviewProfile(
        name="test",
        watch_terms=["agent", "receipt"],
        project_aliases={"tau": ["receipt admission"]},
    )
    result = asyncio.run(
        RipgrepEvidenceClient(settings, profile).retrieve(
            "How does receipt admission constrain an agent?"
        )
    )
    assert result.ok is True
    assert result.sources
    assert result.sources[0].lane is RetrievalLane.RIPGREP
    assert result.sources[0].freshness is Freshness.CURRENT
    assert result.sources[0].path == str(source.resolve())


def test_ripgrep_bounds_high_frequency_matches(tmp_path: Path) -> None:
    repo = tmp_path / "agent-skills"
    repo.mkdir()
    for index in range(40):
        (repo / f"proof-{index:02d}.md").write_text(
            "Receipt admission keeps the workflow source-bound.\n",
            encoding="utf-8",
        )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: bounded\n", encoding="utf-8")
    settings = AppSettings(
        skill_root=tmp_path,
        data_dir=tmp_path / "data",
        profile_path=profile_path,
        repo_roots=[repo],
        memory_url="http://127.0.0.1:9",
        subprocess_timeout_s=3.0,
    )
    profile = InterviewProfile(
        name="bounded",
        project_aliases={"agent-skills": ["receipt admission"]},
    )
    result = asyncio.run(
        RipgrepEvidenceClient(settings, profile).retrieve(
            "How does receipt admission keep the workflow bounded?"
        )
    )
    assert result.ok is True
    assert 1 <= len(result.sources) <= 12
