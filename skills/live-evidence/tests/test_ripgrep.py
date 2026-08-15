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


def test_ripgrep_finds_youtube_parentheses_prompt_source(tmp_path: Path) -> None:
    repo = tmp_path / "youtube-eval"
    repo.mkdir()
    source = repo / "newly_written_solution.js"
    source.write_text(
        "\n".join(
            [
                "export function liveEvidenceNewlyWrittenRemoveInvalidParentheses(input) {",
                "  const removals = countMinimumInvalidParentheses(input);",
                "  return removals.left + removals.right;",
                "}",
                "",
                "function countMinimumInvalidParentheses(input) {",
                "  let left = 0;",
                "  let right = 0;",
                "  return { left, right };",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: youtube\n", encoding="utf-8")
    settings = AppSettings(
        skill_root=tmp_path,
        data_dir=tmp_path / "data",
        profile_path=profile_path,
        repo_roots=[repo],
        memory_url="http://127.0.0.1:9",
        subprocess_timeout_s=3.0,
    )
    profile = InterviewProfile(
        name="youtube",
        watch_terms=["valid parentheses", "minimum number of parentheses"],
        project_aliases={"youtube-eval": ["valid parentheses", "stack solution"]},
    )
    query = (
        "This is not valid, right? Even though it has the same opening and closing, "
        "they're in different orders. Let me paste in an example in terms of "
        "looking for minimum number of parentheses. Based on the input, think "
        "about a dangling parentheses necessary for the output. The actual "
        "English characters we mostly ignore and preserve."
    )

    result = asyncio.run(RipgrepEvidenceClient(settings, profile).retrieve(query))

    assert result.ok is True
    assert result.sources
    assert result.sources[0].path == str(source.resolve())
    matched_terms = {term.casefold() for term in result.sources[0].metadata["matched_terms"]}
    assert {"input", "minimum", "parentheses"} & matched_terms
