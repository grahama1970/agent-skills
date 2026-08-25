import asyncio

from live_evidence.fast_path import stream_fast_answer
from live_evidence.models import CardStatus, EvidenceCard
from live_evidence.solver import SolverChunk, SolverOutcome


class Journal:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, object, str | None]] = []

    async def append(self, session_id, kind, payload, *, policy_digest=None):
        self.rows.append((session_id, kind, payload, policy_digest))


class State:
    def __init__(self) -> None:
        self.decision = None

    async def publish_card_fenced(self, card):
        self.card = card
        return object()

    async def latest_card_publication_decision(self):
        return self.decision

    def session_id(self):
        return "wrong-live-session"

    def session_policy_digest(self):
        return "wrong-live-policy"


class Solver:
    def stream(self, query, evidence_excerpts):
        yield SolverChunk("answer", 0.01)
        yield SolverOutcome(
            ok=True,
            answer="answer",
            model="fixture",
            effort="fixture",
            first_content_s=0.01,
            total_s=0.02,
            response_sha256="a" * 64,
            chunk_count=1,
        )


def test_fast_solver_journals_captured_session_context() -> None:
    asyncio.run(_assert_fast_solver_journals_captured_session_context())


async def _assert_fast_solver_journals_captured_session_context() -> None:
    state = State()
    journal = Journal()
    card = EvidenceCard(
        query="How do we cache user profiles?",
        thread="cache",
        talking_point="pending",
        proof="pending",
        qualifier="bounded",
        confidence=0.5,
        status=CardStatus.INSUFFICIENT,
        question_id="question-context",
        question_revision=1,
    )

    await stream_fast_answer(
        state=state,
        journal=journal,
        solver=Solver(),
        card=card,
        query=card.query,
        evidence_excerpts=[],
        question_id="question-context",
        question_revision=1,
        session_id="captured-session",
        policy_digest="b" * 64,
    )

    assert journal.rows
    assert {row[0] for row in journal.rows} == {"captured-session"}
    assert {row[3] for row in journal.rows} == {"b" * 64}
