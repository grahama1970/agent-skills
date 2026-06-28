"""Deferred question book for pdf-lab batch mode.

When running in batch mode (non-interactive), the convergence loop cannot
block waiting for human input. Instead, questions are written to a JSONL
"question book" and the PDF is skipped. The human reviews the book later
via ``pdf-lab answer``, producing an "answer book" that the next batch
run replays.

Flow:
1. Batch run hits a stuck PDF -> ``defer_question()`` appends to question_book.jsonl
2. Human runs ``pdf-lab answer`` -> ``run_batch_interview()`` presents all questions
3. Answers saved via ``save_answer_book()`` -> answer_book.jsonl
4. Next batch run calls ``lookup_guidance()`` to replay cached answers
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

from .delta import ExtractionDelta, Diagnosis
from .human_escalation import (
    HumanGuidance,
    INTERVIEW_SKILL,
    PDF_SCREENSHOT_SKILL,
    build_questions,
    capture_screenshots,
    parse_responses,
    _count_lines,
)


DEFAULT_BOOK_DIR = Path(os.environ.get(
    "PDF_LAB_DATA", str(Path.home() / ".pi" / "pdf-lab"),
))


@dataclass
class DeferredQuestion:
    """A single question deferred for later human review."""

    pdf_path: str
    pdf_name: str
    delta_summary: Dict[str, Any]
    diagnosis_summary: Dict[str, Any]
    patterns: List[str]
    iteration: int
    max_iterations: int
    best_delta: float
    reason: str  # Why we're asking (stalled, errors, ambiguous)
    screenshots: List[str] = field(default_factory=list)
    questions: Dict[str, Any] = field(default_factory=dict)  # Full interview JSON
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        import time
        return {
            "pdf_path": self.pdf_path,
            "pdf_name": self.pdf_name,
            "delta_summary": self.delta_summary,
            "diagnosis_summary": self.diagnosis_summary,
            "patterns": self.patterns,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "best_delta": self.best_delta,
            "reason": self.reason,
            "screenshots": self.screenshots,
            "questions": self.questions,
            "timestamp": self.timestamp or time.time(),
        }


def defer_question(
    pdf_path: Path,
    delta: ExtractionDelta,
    diagnosis: Diagnosis,
    trials_so_far: List[Dict[str, Any]],
    iteration: int,
    max_iterations: int,
    consecutive_errors: int,
    book_path: Optional[Path] = None,
) -> DeferredQuestion:
    """Write a question to the deferred book (JSONL) instead of blocking.

    Returns the DeferredQuestion that was written. The convergence loop
    should skip this PDF and move on.
    """
    import time

    book = book_path or (DEFAULT_BOOK_DIR / "question_book.jsonl")
    book.parent.mkdir(parents=True, exist_ok=True)

    # Capture screenshots (non-blocking, best-effort)
    screenshot_run = PDF_SCREENSHOT_SKILL / "run.sh"
    screenshots = capture_screenshots(pdf_path, screenshot_run)

    # Determine reason for escalation
    if consecutive_errors >= 2:
        reason = f"repeated_errors ({consecutive_errors} consecutive)"
    elif not diagnosis.patterns:
        reason = "ambiguous_diagnosis (no patterns detected)"
    else:
        reason = "stalled (no improvement)"

    # Build the full interview questions (for later presentation)
    questions = build_questions(
        pdf_path=pdf_path,
        delta=delta,
        diagnosis=diagnosis,
        trials_so_far=trials_so_far,
        iteration=iteration,
        max_iterations=max_iterations,
        consecutive_errors=consecutive_errors,
        screenshots=screenshots,
    )

    best_delta = 0.0
    if trials_so_far:
        best_delta = max(
            (t.get("delta", {}).get("overall_delta", 0) for t in trials_so_far),
            default=0.0,
        )

    dq = DeferredQuestion(
        pdf_path=str(pdf_path),
        pdf_name=pdf_path.name,
        delta_summary=delta.to_dict(),
        diagnosis_summary=diagnosis.to_dict(),
        patterns=list(diagnosis.patterns),
        iteration=iteration,
        max_iterations=max_iterations,
        best_delta=best_delta,
        reason=reason,
        screenshots=screenshots,
        questions=questions,
        timestamp=time.time(),
    )

    # Append to JSONL book
    with open(book, "a") as f:
        f.write(json.dumps(dq.to_dict()) + "\n")

    logger.info(
        f"Deferred question for {pdf_path.name} -> {book} "
        f"(reason: {reason}, total questions: {_count_lines(book)})"
    )

    return dq


def load_question_book(book_path: Optional[Path] = None) -> List[DeferredQuestion]:
    """Load all deferred questions from the book."""
    book = book_path or (DEFAULT_BOOK_DIR / "question_book.jsonl")
    if not book.exists():
        return []

    questions: List[DeferredQuestion] = []
    for line in book.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            questions.append(DeferredQuestion(**{
                k: v for k, v in data.items()
                if k in DeferredQuestion.__dataclass_fields__
            }))
        except Exception as e:
            logger.debug(f"Skipping malformed book entry: {e}")
    return questions


def build_batch_interview(
    book_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build a single /interview session from all deferred questions.

    Groups questions by PDF so the human sees one "tab" per stuck PDF.
    Sorted worst-first (lowest best_delta) so the human triages the most
    broken PDFs before the almost-good ones.
    Returns the interview JSON ready for /interview --file.
    """
    questions_list = load_question_book(book_path)
    if not questions_list:
        return {"title": "pdf-lab: No Questions", "questions": []}

    # Severity triage: worst delta first so human sees the most broken PDFs first
    questions_list.sort(key=lambda dq: dq.best_delta)

    all_questions: List[Dict[str, Any]] = []

    for i, dq in enumerate(questions_list):
        # Summary question for this PDF
        context_lines = [
            f"PDF: {dq.pdf_name}",
            f"Reason: {dq.reason}",
            f"Delta: {dq.delta_summary.get('overall_delta', '?')}",
            f"Best trial delta: {dq.best_delta:.2f}",
            f"Patterns: {', '.join(dq.patterns) or 'none'}",
            f"Iteration: {dq.iteration}/{dq.max_iterations}",
        ]

        # Pull the inner questions from the deferred entry
        inner_qs = dq.questions.get("questions", [])
        for q in inner_qs:
            # Prefix IDs with PDF index to avoid collisions
            q["id"] = f"pdf_{i}_{q['id']}"
            q["header"] = f"[{i+1}] d={dq.best_delta:.2f} {q.get('header', dq.pdf_name[:8])}"
            # Prepend context to the question text
            q["text"] = f"**{dq.pdf_name}** -- {q['text']}"
            all_questions.append(q)

    return {
        "title": f"pdf-lab: {len(questions_list)} PDFs Need Human Guidance",
        "context": (
            f"{len(questions_list)} PDFs got stuck during overnight convergence. "
            "Review each one and provide guidance."
        ),
        "questions": all_questions,
        "progress": {
            "total_pdfs": len(questions_list),
            "total_questions": len(all_questions),
            "show_counter": True,
        },
    }


def run_batch_interview(
    book_path: Optional[Path] = None,
    mode: str = "auto",
) -> Dict[str, HumanGuidance]:
    """Present all deferred questions to the human, return guidance keyed by pdf_path.

    This is the "morning review" -- the human answers all questions at once.
    Returns a dict mapping pdf_path -> HumanGuidance.
    """
    questions_list = load_question_book(book_path)
    if not questions_list:
        logger.info("No deferred questions to answer.")
        return {}

    interview_json = build_batch_interview(book_path)
    interview_run = INTERVIEW_SKILL / "run.sh"

    if not interview_run.exists():
        logger.error(f"Interview skill not found: {interview_run}")
        return {}

    # Write interview to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="pdf_lab_book_", delete=False,
    ) as f:
        json.dump(interview_json, f, indent=2)
        interview_path = f.name

    try:
        args = [str(interview_run), "--file", interview_path, "--json"]
        if mode != "auto":
            args.extend(["--mode", mode])
        # No tight timeout -- human takes their time
        args.extend(["--timeout", "3600"])

        result = subprocess.run(
            args, capture_output=True, text=True, timeout=3660,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode != 0:
            logger.warning(f"Batch interview exited with code {result.returncode}")
            return {}

        raw_responses = json.loads(result.stdout.strip()).get("responses", {})
    except Exception as e:
        logger.error(f"Batch interview failed: {e}")
        return {}
    finally:
        Path(interview_path).unlink(missing_ok=True)

    # Demux responses back to per-PDF guidance
    guidance_map: Dict[str, HumanGuidance] = {}

    for i, dq in enumerate(questions_list):
        # Collect responses for this PDF (prefixed with pdf_{i}_)
        prefix = f"pdf_{i}_"
        pdf_responses = {
            k.removeprefix(prefix): v
            for k, v in raw_responses.items()
            if k.startswith(prefix)
        }

        if pdf_responses:
            diagnosis = Diagnosis(
                patterns=dq.patterns,
                root_cause=dq.diagnosis_summary.get("root_cause", ""),
            )
            guidance = parse_responses(pdf_responses, diagnosis)
            guidance.escalated = True
            guidance_map[dq.pdf_path] = guidance
        else:
            # Human skipped this PDF -- no guidance
            guidance_map[dq.pdf_path] = HumanGuidance(escalated=False)

    return guidance_map


def save_answer_book(
    guidance_map: Dict[str, HumanGuidance],
    book_path: Optional[Path] = None,
) -> Path:
    """Save answered guidance to an answer book (JSONL) for replay."""
    import time

    book = book_path or (DEFAULT_BOOK_DIR / "answer_book.jsonl")
    book.parent.mkdir(parents=True, exist_ok=True)

    with open(book, "w") as f:
        for pdf_path, guidance in guidance_map.items():
            entry = {
                "pdf_path": pdf_path,
                "guidance": guidance.to_dict(),
                "timestamp": time.time(),
            }
            f.write(json.dumps(entry) + "\n")

    logger.info(f"Saved {len(guidance_map)} answers to {book}")
    return book


def load_answer_book(
    book_path: Optional[Path] = None,
) -> Dict[str, HumanGuidance]:
    """Load previously answered guidance for replay."""
    book = book_path or (DEFAULT_BOOK_DIR / "answer_book.jsonl")
    if not book.exists():
        return {}

    guidance_map: Dict[str, HumanGuidance] = {}
    for line in book.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            pdf_path = data["pdf_path"]
            g_data = data["guidance"]
            guidance_map[pdf_path] = HumanGuidance(**{
                k: v for k, v in g_data.items()
                if k in HumanGuidance.__dataclass_fields__
            })
        except Exception as e:
            logger.debug(f"Skipping malformed answer entry: {e}")

    return guidance_map


def lookup_guidance(
    pdf_path: Path,
    answer_book: Dict[str, HumanGuidance],
) -> Optional[HumanGuidance]:
    """Look up pre-answered guidance for a specific PDF."""
    # Try exact path match first, then filename match
    key = str(pdf_path)
    if key in answer_book:
        return answer_book[key]

    # Fallback: match by filename (PDFs might be in different dirs)
    name = pdf_path.name
    for k, v in answer_book.items():
        if Path(k).name == name:
            return v

    return None


def clear_question_book(book_path: Optional[Path] = None) -> None:
    """Clear the question book after answers have been collected."""
    book = book_path or (DEFAULT_BOOK_DIR / "question_book.jsonl")
    if book.exists():
        book.unlink()
        logger.info(f"Cleared question book: {book}")
