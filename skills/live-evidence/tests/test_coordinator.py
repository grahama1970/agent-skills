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
from live_evidence.retrieval import LeetCodeGateResult
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

        class ReadyGate:
            async def analyze(self, question_candidate, *, answers=None) -> LeetCodeGateResult:
                return LeetCodeGateResult(
                    status="ready_for_solution",
                    solution_allowed=True,
                    solver_prompt="Solve clarified prompt.",
                    transcript_sha256="abc123",
                    payload={
                        "status": "ready_for_solution",
                        "solution_allowed": True,
                        "transcript_sha256": "abc123",
                    },
                    latency_ms=3,
                    ok=True,
                    detail="ready",
                )

        slow_memory = SlowMemory()
        fast_ask = FastAsk()
        coordinator._memory = slow_memory
        coordinator._ripgrep = FastRipgrep()
        coordinator._ask = fast_ask
        coordinator._leetcode = ReadyGate()
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
        assert snapshot.cards[0].sources[0].metadata["leetcode_gate_status"] == "ready_for_solution"
        lane_states = {lane.lane: lane.state for lane in snapshot.lanes}
        assert lane_states[RetrievalLane.MEMORY] is LaneState.RUNNING
        assert lane_states[RetrievalLane.CODE] is LaneState.RUNNING

    asyncio.run(scenario())


def test_automatic_code_question_needs_clarification_blocks_ask(tmp_path: Path) -> None:
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
            label="youtube-eval/two_sum.py",
            excerpt="def two_sum(nums, target): pass",
            score=0.7,
            freshness=Freshness.CURRENT,
            repository="youtube-eval",
            path="/repo/two_sum.py",
            line_start=1,
        )

        class EmptyMemory:
            async def retrieve(self, query: str) -> SimpleNamespace:
                return SimpleNamespace(sources=[], latency_ms=2, detail="No results", ok=False)

        class FastRipgrep:
            async def retrieve(self, query: str) -> SimpleNamespace:
                return SimpleNamespace(sources=[current_source], latency_ms=5, detail="Current source", ok=True)

        class AskMustNotRun:
            called = False

            async def solve(self, query: str, evidence: list[EvidenceSource]) -> SimpleNamespace:
                self.called = True
                raise AssertionError("Ask must not run before clarification")

        class NeedsClarificationGate:
            async def analyze(self, question_candidate, *, answers=None) -> LeetCodeGateResult:
                return LeetCodeGateResult(
                    status="needs_clarification",
                    solution_allowed=False,
                    transcript_sha256="sha-two-sum",
                    clarifying_questions=[
                        {
                            "id": "return-contract",
                            "question": "Should the function return indices or values?",
                            "why_blocking": "Different outputs.",
                        }
                    ],
                    payload={
                        "status": "needs_clarification",
                        "solution_allowed": False,
                        "transcript_sha256": "sha-two-sum",
                    },
                    latency_ms=4,
                    ok=True,
                    detail="needs clarification",
                )

        ask = AskMustNotRun()
        coordinator._memory = EmptyMemory()
        coordinator._ripgrep = FastRipgrep()
        coordinator._ask = ask
        coordinator._leetcode = NeedsClarificationGate()
        await coordinator._retrieve(
            TriggerDecision(
                event_id="turn-clarify",
                query="Given an array and a target, find two numbers that sum to the target.",
                thread="youtube-eval",
                reason="code-question",
                code_related=True,
                question_payload={
                    "schema": "live_evidence.question_candidate.v1",
                    "question_id": "question-clarify",
                    "normalized_question": "Given an array and a target, find two numbers that sum to the target.",
                    "start_sequence": 1,
                    "end_sequence": 1,
                    "source_event_ids": ["event-clarify"],
                    "source_spans": [
                        {
                            "event_id": "event-clarify",
                            "sequence": 1,
                            "start_offset": 0,
                            "end_offset": 72,
                        }
                    ],
                    "trigger_reason": "code-question",
                    "fingerprint": "fingerprint-clarify",
                },
            )
        )

        snapshot = await state.snapshot()
        assert ask.called is False
        assert snapshot.cards[0].status.value == "insufficient"
        assert snapshot.cards[0].sources[0].metadata["gate_status"] == "needs_clarification"
        assert snapshot.cards[0].sources[0].metadata["transcript_sha256"] == "sha-two-sum"
        lane_states = {lane.lane: lane.state for lane in snapshot.lanes}
        assert lane_states[RetrievalLane.ASK] is LaneState.BLOCKED

    asyncio.run(scenario())


def test_clarification_resume_requires_all_answers_before_ask(tmp_path: Path) -> None:
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
        seed_source = EvidenceSource(
            lane=RetrievalLane.RIPGREP,
            label="youtube-eval/two_sum.py",
            excerpt="def two_sum(nums, target): pass",
            score=0.7,
            freshness=Freshness.CURRENT,
            repository="youtube-eval",
            path="/repo/two_sum.py",
            line_start=1,
        )

        class EmptyMemory:
            async def retrieve(self, query: str) -> SimpleNamespace:
                return SimpleNamespace(sources=[], latency_ms=2, detail="No results", ok=False)

        class FastRipgrep:
            async def retrieve(self, query: str) -> SimpleNamespace:
                return SimpleNamespace(sources=[seed_source], latency_ms=5, detail="Current source", ok=True)

        class CountingAsk:
            prompts: list[str] = []

            async def solve(self, query: str, evidence: list[EvidenceSource]) -> SimpleNamespace:
                self.prompts.append(query)
                return SimpleNamespace(
                    sources=[
                        EvidenceSource(
                            lane=RetrievalLane.ASK,
                            label="Ask code solution",
                            excerpt="Use a hash map and return the two indices.",
                            score=0.93,
                            freshness=Freshness.UNKNOWN,
                            repository="ask",
                            path="/tmp/ask-run",
                        )
                    ],
                    latency_ms=10,
                    detail="Ask solution",
                    ok=True,
                )

        class TwoPhaseGate:
            async def analyze(self, question_candidate, *, answers=None) -> LeetCodeGateResult:
                if answers and set(answers) >= {"return-contract", "element-reuse", "multiple-solutions"}:
                    return LeetCodeGateResult(
                        status="ready_for_solution",
                        solution_allowed=True,
                        solver_prompt="Solve Two Sum with distinct indices and one guaranteed answer.",
                        transcript_sha256="sha-two-sum",
                        payload={
                            "status": "ready_for_solution",
                            "solution_allowed": True,
                            "transcript_sha256": "sha-two-sum",
                            "solver_prompt": "Solve Two Sum with distinct indices and one guaranteed answer.",
                        },
                        latency_ms=4,
                        ok=True,
                        detail="ready",
                    )
                missing = [
                    item
                    for item in ("return-contract", "element-reuse", "multiple-solutions")
                    if not answers or item not in answers
                ]
                return LeetCodeGateResult(
                    status="needs_clarification",
                    solution_allowed=False,
                    transcript_sha256="sha-two-sum",
                    clarifying_questions=[
                        {
                            "id": item,
                            "question": f"Answer {item}",
                            "why_blocking": "Required.",
                        }
                        for item in missing[:3]
                    ],
                    payload={
                        "status": "needs_clarification",
                        "solution_allowed": False,
                        "transcript_sha256": "sha-two-sum",
                    },
                    latency_ms=4,
                    ok=True,
                    detail="needs clarification",
                )

        ask = CountingAsk()
        coordinator._memory = EmptyMemory()
        coordinator._ripgrep = FastRipgrep()
        coordinator._ask = ask
        coordinator._leetcode = TwoPhaseGate()
        decision = TriggerDecision(
            event_id="turn-two-sum",
            query="Given an array and a target, find two numbers that sum to the target.",
            thread="youtube-eval",
            reason="code-question",
            code_related=True,
        )
        await coordinator._retrieve(decision)
        blocked_card = (await state.snapshot()).cards[0]
        partial = await coordinator.submit_clarification(
            blocked_card.card_id,
            {"return-contract": "Return indices."},
        )
        assert partial.status.value == "insufficient"
        assert ask.prompts == []

        answer = await coordinator.submit_clarification(
            blocked_card.card_id,
            {
                "return-contract": "Return indices.",
                "element-reuse": "Indices must be distinct.",
                "multiple-solutions": "Exactly one answer exists.",
            },
        )

        assert ask.prompts == ["Solve Two Sum with distinct indices and one guaranteed answer."]
        assert answer.status.value == "supported"
        assert answer.sources[0].metadata["leetcode_gate_status"] == "ready_for_solution"
        assert answer.sources[0].metadata["transcript_sha256"] == "sha-two-sum"

    asyncio.run(scenario())


async def _wait_for_card(state: RuntimeState):
    for _ in range(40):
        snapshot = await state.snapshot()
        if snapshot.cards:
            return snapshot
        await asyncio.sleep(0.05)
    pytest.fail("evidence card was not surfaced")
