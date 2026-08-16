"""Tests for retrieval routing policy."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from live_evidence.config import AppSettings
from live_evidence.config import InterviewProfile
from live_evidence.coordinator import EvidenceCoordinator
from live_evidence.coordinator import _card_sources_for_decision, _code_problem_key
from live_evidence.models import EvidenceSource, Freshness, LaneState, RetrievalLane
from live_evidence.persistence import SessionJournal
from live_evidence.state import RuntimeState
from live_evidence.trigger import TriggerDecision


def test_code_problem_key_is_stable_for_growing_parentheses_prompt() -> None:
    first = (
        "Turn any valid string. Formally, a parenthesis string is valid. "
        "Does the order matter here? So to make it clear, paste in the sample "
        "in terms of looking for minimum number of parentheses."
    )
    grown = (
        "Turn any valid string. Formally, a parentheses string is valid. "
        "Does the order matter here? So to make it clear, paste in the sample "
        "in terms of looking for minimum number of parentheses to remove so the output is valid."
    )

    assert _code_problem_key(first) == _code_problem_key(grown)


def test_code_card_keeps_current_source_when_ask_degrades() -> None:
    profile = InterviewProfile(
        name="youtube",
        repo_priorities=["youtube-eval"],
    )
    decision = TriggerDecision(
        event_id="turn-1",
        query="Find the minimum number of parentheses to remove from the input.",
        thread="youtube-eval",
        reason="code-question",
        code_related=True,
    )
    current_source = EvidenceSource(
        lane=RetrievalLane.RIPGREP,
        label="youtube-eval/newly_written_solution.js",
        excerpt="function countMinimumInvalidParentheses(input) { return { left, right }; }",
        score=0.7,
        freshness=Freshness.CURRENT,
        repository="youtube-eval",
        path="/repo/newly_written_solution.js",
        line_start=33,
    )

    selected = _card_sources_for_decision(decision, [current_source], [], profile)

    assert selected == [current_source]


def test_code_question_card_surfaces_before_slow_optional_memory(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = AppSettings(
            skill_root=tmp_path,
            data_dir=tmp_path / "data",
            profile_path=tmp_path / "profile.yaml",
            repo_roots=[tmp_path],
            memory_url="http://127.0.0.1:8601",
            request_timeout_s=1.0,
            subprocess_timeout_s=1.0,
            ask_timeout_s=2.0,
        )
        profile = InterviewProfile(name="youtube-eval", repo_priorities=["youtube-eval"])
        state = RuntimeState(settings, profile)
        await state.start_session(consent_confirmed=True)
        coordinator = EvidenceCoordinator(settings, profile, state, SessionJournal(settings.data_dir))
        current_source = EvidenceSource(
            lane=RetrievalLane.RIPGREP,
            label="youtube-eval/remove_invalid_parentheses.js",
            excerpt="export function removeInvalidParentheses(input) { return input; }",
            score=0.7,
            freshness=Freshness.CURRENT,
            repository="youtube-eval",
            path="/repo/remove_invalid_parentheses.js",
            line_start=1,
        )
        ask_source = EvidenceSource(
            lane=RetrievalLane.ASK,
            label="Ask code solution",
            excerpt="Use a stack of open parenthesis indices and remove unmatched parentheses.",
            score=0.93,
            freshness=Freshness.UNKNOWN,
            repository="ask",
            path="/tmp/ask-run",
        )

        class SlowMemory:
            finished = False

            async def retrieve(self, query: str) -> SimpleNamespace:
                await asyncio.sleep(5)
                self.finished = True
                return SimpleNamespace(sources=[], latency_ms=5_000, detail="No results", ok=False)

        class FastRipgrep:
            async def retrieve(self, query: str) -> SimpleNamespace:
                return SimpleNamespace(
                    sources=[current_source],
                    latency_ms=5,
                    detail="Current source 1",
                    ok=True,
                )

        class FastAsk:
            seeded_lanes: list[RetrievalLane] = []

            async def solve(
                self,
                query: str,
                evidence: list[EvidenceSource],
            ) -> SimpleNamespace:
                self.seeded_lanes = [source.lane for source in evidence]
                return SimpleNamespace(
                    sources=[ask_source],
                    latency_ms=10,
                    detail="Ask solution",
                    ok=True,
                )

        slow_memory = SlowMemory()
        fast_ask = FastAsk()
        coordinator._memory = slow_memory
        coordinator._ripgrep = FastRipgrep()
        coordinator._ask = fast_ask
        decision = TriggerDecision(
            event_id="turn-1",
            query="Return a valid string after removing the minimum invalid parentheses.",
            thread="youtube-eval",
            reason="code-question",
            code_related=True,
        )

        task = asyncio.create_task(coordinator._retrieve(decision))
        try:
            snapshot = await asyncio.wait_for(_wait_for_card(state), timeout=1.5)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert slow_memory.finished is False
        assert fast_ask.seeded_lanes == [RetrievalLane.RIPGREP]
        assert snapshot.cards
        assert set(snapshot.cards[0].lanes) == {RetrievalLane.ASK, RetrievalLane.RIPGREP}
        assert snapshot.cards[0].status.value == "supported"
        lane_states = {lane.lane: lane.state for lane in snapshot.lanes}
        assert lane_states[RetrievalLane.MEMORY] is LaneState.RUNNING
        assert lane_states[RetrievalLane.CODE] is LaneState.RUNNING

    asyncio.run(scenario())


async def _wait_for_card(state: RuntimeState):
    for _ in range(40):
        snapshot = await state.snapshot()
        if snapshot.cards:
            return snapshot
        await asyncio.sleep(0.05)
    pytest.fail("evidence card was not surfaced")
