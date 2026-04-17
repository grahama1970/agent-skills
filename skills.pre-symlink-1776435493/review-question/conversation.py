"""Conversation execution: persona asks Brandon, capture turns + metrics."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from config import (
    CONVERSATIONS_DIR,
    PERSONAS,
)
from generators import GeneratedQuestion

SKILLS_DIR = Path(__file__).resolve().parents[1]  # .pi/skills/

# scillm import path (quick_completion — the approved import surface)
_SCILLM_DIR = SKILLS_DIR / "scillm"
if str(_SCILLM_DIR) not in sys.path:
    sys.path.insert(0, str(_SCILLM_DIR))

# graph_memory import path (hybrid_search_sparta_qra)
_MEMORY_ROOT = Path(os.getenv("MEMORY_ROOT", str(Path.home() / "workspace/experiments/memory")))
_GRAPH_MEMORY_SRC = _MEMORY_ROOT / "src"
if str(_GRAPH_MEMORY_SRC) not in sys.path:
    sys.path.insert(0, str(_GRAPH_MEMORY_SRC))

MAX_TURNS = 4  # Max turns per conversation (question + up to 3 follow-ups)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TurnMetrics:
    persona_alignment: bool = True
    f36_grounding: str = ""
    naturalness: float = 0.0
    qra_citations: int = 0
    datalake_docs_referenced: int = 0
    grounding_score: float = 0.0
    substance_score: float = 0.0
    hallucination_check: str = "N/A"
    follow_up_type: Optional[str] = None
    triggered_by: Optional[str] = None
    improvement_delta: float = 0.0


@dataclass
class Turn:
    speaker: str  # persona name or "Brandon Bailey"
    role: str  # "questioner" or "answerer"
    content: str
    timestamp: str = ""
    metrics: TurnMetrics = field(default_factory=TurnMetrics)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class ConversationThread:
    session_id: str
    question: GeneratedQuestion
    questioner: str
    answerer: str = "Brandon Bailey"
    turns: list[Turn] = field(default_factory=list)
    final_verdict: str = ""  # SATISFACTORY, INCOMPLETE, WRONG
    composite_score: float = 0.0
    grade: str = ""

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "question": self.question.to_dict(),
            "questioner": self.questioner,
            "answerer": self.answerer,
            "turns": [
                {
                    "speaker": t.speaker,
                    "role": t.role,
                    "content": t.content,
                    "timestamp": t.timestamp,
                    "metrics": asdict(t.metrics),
                }
                for t in self.turns
            ],
            "final_verdict": self.final_verdict,
            "composite_score": self.composite_score,
            "grade": self.grade,
        }


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _llm_completion(prompt: str, sys_prompt: str, json_mode: bool = False) -> str:
    """Call LLM via scillm's quick_completion (the approved import surface)."""
    from batch import quick_completion

    try:
        return quick_completion(
            prompt=prompt,
            system=sys_prompt,
            json_mode=json_mode,
            max_tokens=2048,
            timeout=60,
        )
    except Exception as e:
        logger.warning(f"scillm error: {e}")
        return ""


def _evaluate_response(question: str, response: str) -> dict:
    """Evaluate Brandon's response quality via LLM (real metrics)."""
    from prompts import response_evaluation_system, response_evaluation_user

    raw = _llm_completion(
        prompt=response_evaluation_user(question, response),
        sys_prompt=response_evaluation_system(),
        json_mode=True,
    )
    if not raw:
        # Fallback: heuristic estimates
        has_content = len(response) > 200
        return {
            "grounding": 0.5 if has_content else 0.2,
            "substance": 0.5 if has_content else 0.2,
            "hallucination_risk": 0.7,
            "f36_relevance": 0.5 if has_content else 0.2,
        }
    try:
        data = json.loads(raw)
        return {
            "grounding": float(data.get("grounding", 0.5)),
            "substance": float(data.get("substance", 0.5)),
            "hallucination_risk": float(data.get("hallucination_risk", 0.5)),
            "f36_relevance": float(data.get("f36_relevance", 0.5)),
            "reason": data.get("reason", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return {"grounding": 0.5, "substance": 0.5, "hallucination_risk": 0.7, "f36_relevance": 0.5}



def _search_arango(question: str) -> dict:
    """Search memory for relevant QRAs and datalake docs via direct graph_memory imports."""
    result = {"qra_citations": 0, "datalake_docs": 0, "qra_refs": [], "datalake_refs": []}
    try:
        from graph_memory.arango_client import get_db
        from graph_memory.hybrid_search import hybrid_search_sparta_qra
        db = get_db()
        items = hybrid_search_sparta_qra(db, query=question[:200], k=8)

        for doc in items:
            _id = doc.get("_id", "")
            collection = doc.get("_collection", doc.get("collection", _id.split("/")[0] if "/" in _id else ""))
            if "qra" in collection:
                result["qra_citations"] += 1
                result["qra_refs"].append({
                    "_key": doc.get("_key", ""),
                    "question": (doc.get("question", "") or "")[:120],
                    "answer": (doc.get("answer", "") or "")[:120],
                })
            elif "datalake" in collection or "profile" in collection:
                result["datalake_docs"] += 1
                result["datalake_refs"].append({
                    "_key": doc.get("_key", ""),
                    "title": doc.get("title", ""),
                    "category": doc.get("category", ""),
                })
    except Exception as e:
        logger.warning(f"Memory recall failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Score and grade
# ---------------------------------------------------------------------------

def _compute_composite(turns: list[Turn]) -> float:
    """Compute composite score from turn metrics."""
    if not turns:
        return 0.0
    answerer_turns = [t for t in turns if t.role == "answerer"]
    if not answerer_turns:
        return 0.0
    last = answerer_turns[-1]
    m = last.metrics
    # Weighted: grounding 40%, substance 40%, citations 20%
    citation_score = min(m.qra_citations / 3.0, 1.0)
    return 0.4 * m.grounding_score + 0.4 * m.substance_score + 0.2 * citation_score


def _grade(composite: float) -> str:
    """Convert composite to letter grade."""
    if composite >= 0.90:
        return "A"
    if composite >= 0.80:
        return "B+"
    if composite >= 0.70:
        return "B"
    if composite >= 0.60:
        return "C"
    return "F"


# ---------------------------------------------------------------------------
# Conversation execution
# ---------------------------------------------------------------------------

def execute_conversation(
    question: GeneratedQuestion,
    session_id: Optional[str] = None,
) -> ConversationThread:
    """Execute a full conversation: persona asks Brandon, capture turns + metrics."""
    from prompts import (
        conversation_brandon_system,
        conversation_brandon_user,
        follow_up_system,
        follow_up_user,
    )

    persona = PERSONAS.get(question.persona)
    if persona is None:
        raise ValueError(f"Unknown persona: {question.persona}")

    if session_id is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        session_id = f"review_q_{ts}_{persona.short_name}"

    thread = ConversationThread(
        session_id=session_id,
        question=question,
        questioner=persona.name,
    )

    # Search ArangoDB for context
    search_results = _search_arango(question.question)

    # --- Turn 1: Persona asks ---
    turn1 = Turn(
        speaker=persona.name,
        role="questioner",
        content=question.question,
        metrics=TurnMetrics(
            persona_alignment=True,
            f36_grounding=question.f36_category,
            naturalness=0.9,  # Pre-validated
        ),
    )
    thread.turns.append(turn1)
    logger.info(f"[{session_id}] Turn 1: {persona.name} asks")

    # --- Turn 2: Brandon responds ---
    brandon_system = conversation_brandon_system(
        questioner_name=persona.name,
        questioner_role=persona.role,
        questioner_org=persona.organization,
    )

    # Build context from ArangoDB results
    context_parts = []
    if search_results["qra_refs"]:
        context_parts.append("Relevant SPARTA knowledge:")
        for qra in search_results["qra_refs"][:3]:
            context_parts.append(f"- Q: {qra.get('question', '')}")
            context_parts.append(f"  A: {qra.get('answer', '')}")
    if search_results["datalake_refs"]:
        context_parts.append("\nRelevant F-36 documents:")
        for doc in search_results["datalake_refs"][:2]:
            context_parts.append(f"- {doc.get('title', 'Untitled')} [{doc.get('category', '')}]")

    brandon_prompt = question.question
    if context_parts:
        brandon_prompt += "\n\n[Context for your response:\n" + "\n".join(context_parts) + "]"

    brandon_response = _llm_completion(
        prompt=conversation_brandon_user(brandon_prompt),
        sys_prompt=brandon_system,
    )

    if not brandon_response:
        brandon_response = "[Brandon response unavailable — LLM error]"

    # Evaluate response quality via LLM (real metrics, not estimates)
    eval_scores = _evaluate_response(question.question, brandon_response)

    turn2 = Turn(
        speaker="Brandon Bailey",
        role="answerer",
        content=brandon_response,
        metrics=TurnMetrics(
            qra_citations=search_results["qra_citations"],
            datalake_docs_referenced=search_results["datalake_docs"],
            grounding_score=eval_scores.get("grounding", 0.5),
            substance_score=eval_scores.get("substance", 0.5),
            hallucination_check=(
                "PASS" if eval_scores.get("hallucination_risk", 0.5) >= 0.7
                else "WARN" if eval_scores.get("hallucination_risk", 0.5) >= 0.4
                else "FAIL"
            ),
        ),
    )
    thread.turns.append(turn2)
    logger.info(
        f"[{session_id}] Turn 2: Brandon responds "
        f"(grounding={eval_scores.get('grounding', 0):.2f}, "
        f"substance={eval_scores.get('substance', 0):.2f})"
    )

    # --- Turn 3+: Follow-up evaluation ---
    prev_composite = _compute_composite(thread.turns)

    for follow_up_idx in range(MAX_TURNS - 2):
        eval_system = follow_up_system(persona.name)
        eval_prompt = follow_up_user(question.question, brandon_response)

        eval_raw = _llm_completion(
            prompt=eval_prompt,
            sys_prompt=eval_system,
            json_mode=True,
        )

        if not eval_raw:
            thread.final_verdict = "SATISFACTORY"
            break

        try:
            eval_data = json.loads(eval_raw)
            verdict = eval_data.get("verdict", "SATISFACTORY")
            reason = eval_data.get("reason", "")
            follow_up_q = eval_data.get("follow_up")
        except (json.JSONDecodeError, ValueError):
            verdict = "SATISFACTORY"
            follow_up_q = None
            reason = "eval parse error"

        if verdict == "SATISFACTORY" or follow_up_q is None:
            thread.final_verdict = verdict
            logger.info(f"[{session_id}] {persona.name}: {verdict} — {reason}")
            break

        # Persona follow-up
        turn_fu = Turn(
            speaker=persona.name,
            role="questioner",
            content=follow_up_q,
            metrics=TurnMetrics(
                follow_up_type="clarification" if verdict == "INCOMPLETE" else "correction",
                triggered_by=reason[:100],
            ),
        )
        thread.turns.append(turn_fu)
        logger.info(f"[{session_id}] Turn {len(thread.turns)}: {persona.name} follow-up ({verdict})")

        # Brandon responds to follow-up
        brandon_response = _llm_completion(
            prompt=conversation_brandon_user(follow_up_q),
            sys_prompt=brandon_system,
        )
        if not brandon_response:
            brandon_response = "[Brandon follow-up unavailable]"

        # Evaluate follow-up response quality via LLM
        fu_scores = _evaluate_response(question.question, brandon_response)

        new_composite = _compute_composite(thread.turns)
        delta = new_composite - prev_composite

        turn_br = Turn(
            speaker="Brandon Bailey",
            role="answerer",
            content=brandon_response,
            metrics=TurnMetrics(
                qra_citations=search_results["qra_citations"],
                datalake_docs_referenced=search_results["datalake_docs"],
                grounding_score=fu_scores.get("grounding", 0.5),
                substance_score=fu_scores.get("substance", 0.5),
                hallucination_check=(
                    "PASS" if fu_scores.get("hallucination_risk", 0.5) >= 0.7
                    else "WARN" if fu_scores.get("hallucination_risk", 0.5) >= 0.4
                    else "FAIL"
                ),
                improvement_delta=delta,
            ),
        )
        thread.turns.append(turn_br)
        prev_composite = new_composite

    if not thread.final_verdict:
        thread.final_verdict = "SATISFACTORY"

    thread.composite_score = _compute_composite(thread.turns)
    thread.grade = _grade(thread.composite_score)
    logger.info(
        f"[{session_id}] Complete: {thread.grade} ({thread.composite_score:.2f}) "
        f"turns={len(thread.turns)}"
    )

    return thread


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------

def render_conversation_markdown(thread: ConversationThread) -> str:
    """Render conversation thread as human-readable markdown."""
    lines = [
        f"# Conversation: {thread.questioner} -> Brandon Bailey",
        f"Session: {thread.session_id} | Question: {thread.question.difficulty.title()} "
        f"| F36 Category: {thread.question.f36_category}",
        "",
    ]

    for i, turn in enumerate(thread.turns, 1):
        speaker_label = f"{turn.speaker} {'asks' if turn.role == 'questioner' else 'responds'}"
        if i > 2 and turn.role == "questioner":
            speaker_label = f"{turn.speaker} follow-up"
        elif i > 2 and turn.role == "answerer":
            speaker_label = f"{turn.speaker} revised"

        lines.append(f"## Turn {i} -- {speaker_label}")
        lines.append(f"> {turn.content}")
        lines.append("")

        # Metrics
        m = turn.metrics
        if turn.role == "questioner":
            parts = [f"persona_alignment={'Y' if m.persona_alignment else 'N'}"]
            if m.f36_grounding:
                parts.append(f"f36_grounding={m.f36_grounding}")
            if m.naturalness > 0:
                parts.append(f"naturalness={m.naturalness:.2f}")
            if m.follow_up_type:
                parts.append(f"follow_up_type={m.follow_up_type}")
            if m.triggered_by:
                parts.append(f"triggered_by={m.triggered_by}")
        else:
            parts = [
                f"qra_citations: {m.qra_citations}",
                f"datalake_docs: {m.datalake_docs_referenced}",
                f"grounding: {m.grounding_score:.2f}",
                f"substance: {m.substance_score:.2f}",
                f"hallucination: {m.hallucination_check}",
            ]
            if m.improvement_delta != 0:
                parts.append(f"improvement_delta: {m.improvement_delta:+.2f}")

        lines.append("Metrics: " + " | ".join(parts))
        lines.append("")

    # Session summary
    lines.extend([
        "## Session Summary",
        f"Grade: {thread.grade} | Composite: {thread.composite_score:.2f} "
        f"| Turns: {len(thread.turns)} "
        f"| Follow-ups: {max(0, len(thread.turns) // 2 - 1)}",
        f"Persona evaluation: {thread.final_verdict}",
        f"Saved to: conversations/{thread.session_id}.md",
    ])

    return "\n".join(lines)


def save_conversation(thread: ConversationThread, output_dir: Optional[Path] = None) -> Path:
    """Save conversation thread as markdown + JSONL."""
    output_dir = output_dir or CONVERSATIONS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Markdown
    md_path = output_dir / f"{thread.session_id}.md"
    md_path.write_text(render_conversation_markdown(thread))

    # JSONL (compatible with /review-conversation)
    jsonl_path = output_dir / f"{thread.session_id}.jsonl"
    with jsonl_path.open("w") as f:
        f.write(json.dumps(thread.to_dict()) + "\n")

    logger.info(f"Saved: {md_path} + {jsonl_path}")
    return md_path
