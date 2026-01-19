#!/usr/bin/env python3
"""
Interview Skill - Structured human-agent Q&A via HTML or TUI forms.

Agent provides recommendations, human validates or overrides.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

SCRIPT_DIR = Path(__file__).parent
SESSIONS_DIR = SCRIPT_DIR / "sessions"
TEMPLATES_DIR = SCRIPT_DIR / "templates"

# Question types
QuestionType = Literal["yes_no", "yes_no_refine", "select", "multi", "text", "confirm"]
DecisionType = Literal["accept", "override", "skip"]


@dataclass
class Question:
    """A single interview question with optional agent recommendation."""
    id: str
    text: str
    type: QuestionType = "yes_no_refine"
    recommendation: str | None = None
    reason: str | None = None
    options: list[str] | None = None
    required: bool = True

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Response:
    """User's response to a question."""
    decision: DecisionType  # accept, override, skip
    value: str | list[str]  # The actual answer
    note: str | None = None  # Optional refinement/comment

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Session:
    """Interview session with persistence."""
    id: str
    title: str
    context: str
    questions: list[Question]
    responses: dict[str, Response] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    mode: str = "auto"

    @classmethod
    def load(cls, session_id: str) -> "Session":
        """Load session from disk."""
        path = SESSIONS_DIR / f"{session_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        data = json.loads(path.read_text())
        questions = [Question(**q) for q in data.pop("questions")]
        responses = {k: Response(**v) for k, v in data.pop("responses", {}).items()}
        return cls(questions=questions, responses=responses, **data)

    def save(self) -> Path:
        """Save session to disk."""
        SESSIONS_DIR.mkdir(exist_ok=True)
        path = SESSIONS_DIR / f"{self.id}.json"
        data = {
            "id": self.id,
            "title": self.title,
            "context": self.context,
            "questions": [q.to_dict() for q in self.questions],
            "responses": {k: v.to_dict() for k, v in self.responses.items()},
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "mode": self.mode,
        }
        path.write_text(json.dumps(data, indent=2))
        return path

    def is_complete(self) -> bool:
        """Check if all required questions are answered."""
        for q in self.questions:
            if q.required and q.id not in self.responses:
                return False
        return True

    def to_result(self) -> dict:
        """Convert to result format."""
        return {
            "session_id": self.id,
            "completed": self.is_complete(),
            "duration_seconds": (self.completed_at or time.time()) - self.started_at,
            "responses": {k: v.to_dict() for k, v in self.responses.items()},
        }


def can_open_browser() -> bool:
    """Check if we can open a browser."""
    # Check for display
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return True
    # Check for macOS
    if sys.platform == "darwin":
        return True
    # Check for WSL with browser
    if "microsoft" in os.uname().release.lower():
        return shutil.which("wslview") is not None or shutil.which("explorer.exe") is not None
    return False


def detect_mode() -> str:
    """Auto-detect best mode."""
    env_mode = os.environ.get("INTERVIEW_MODE", "").lower()
    if env_mode in ("html", "tui"):
        return env_mode
    return "html" if can_open_browser() else "tui"


class Interview:
    """Main interview controller."""

    def __init__(
        self,
        title: str = "Interview",
        context: str = "",
        session_id: str | None = None,
    ):
        self.title = title
        self.context = context
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.session: Session | None = None

    def run(
        self,
        questions: list[dict | Question],
        mode: str = "auto",
        timeout: int | None = None,
    ) -> dict:
        """
        Run the interview.

        Args:
            questions: List of questions (dicts or Question objects)
            mode: "html", "tui", or "auto"
            timeout: Seconds before auto-save and exit

        Returns:
            Result dict with responses
        """
        # Normalize questions
        qs = []
        for q in questions:
            if isinstance(q, Question):
                qs.append(q)
            else:
                qs.append(Question(**q))

        # Create session
        self.session = Session(
            id=self.session_id,
            title=self.title,
            context=self.context,
            questions=qs,
            mode=mode if mode != "auto" else detect_mode(),
        )
        self.session.save()

        # Resolve mode
        actual_mode = mode if mode != "auto" else detect_mode()
        self.session.mode = actual_mode

        # Run appropriate interface
        timeout = timeout or int(os.environ.get("INTERVIEW_TIMEOUT", 600))

        if actual_mode == "html":
            self._run_html(timeout)
        else:
            self._run_tui(timeout)

        # Mark complete and save
        self.session.completed_at = time.time()
        self.session.save()

        return self.session.to_result()

    def _run_html(self, timeout: int):
        """Run HTML-based interview."""
        from .server import run_html_interview
        responses = run_html_interview(self.session, timeout)
        for qid, resp in responses.items():
            self.session.responses[qid] = Response(**resp)

    def _run_tui(self, timeout: int):
        """Run TUI-based interview."""
        from .tui import run_tui_interview
        responses = run_tui_interview(self.session, timeout)
        for qid, resp in responses.items():
            self.session.responses[qid] = Response(**resp)

    @classmethod
    def resume(cls, session_id: str) -> "Interview":
        """Resume an existing session."""
        session = Session.load(session_id)
        interview = cls(
            title=session.title,
            context=session.context,
            session_id=session.id,
        )
        interview.session = session
        return interview


def load_questions_file(path: str | Path) -> tuple[str, str, list[dict]]:
    """Load questions from JSON file."""
    data = json.loads(Path(path).read_text())
    title = data.get("title", "Interview")
    context = data.get("context", "")
    questions = data.get("questions", [])
    return title, context, questions


# CLI entry point
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Structured human-agent Q&A")
    parser.add_argument("--file", "-f", help="Questions JSON file")
    parser.add_argument("--mode", "-m", choices=["auto", "html", "tui"], default="auto")
    parser.add_argument("--timeout", "-t", type=int, default=600)
    parser.add_argument("--resume", "-r", nargs="?", const="latest", help="Resume session")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.resume:
        if args.resume == "latest":
            # Find most recent session
            sessions = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
            if not sessions:
                print("No sessions to resume", file=sys.stderr)
                sys.exit(1)
            session_id = sessions[-1].stem
        else:
            session_id = args.resume

        interview = Interview.resume(session_id)
        result = interview.run(
            interview.session.questions,
            mode=args.mode,
            timeout=args.timeout,
        )
    elif args.file:
        title, context, questions = load_questions_file(args.file)
        interview = Interview(title=title, context=context)
        result = interview.run(questions, mode=args.mode, timeout=args.timeout)
    else:
        parser.print_help()
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nInterview complete: {result['session_id']}")
        print(f"Duration: {result['duration_seconds']:.1f}s")
        print(f"Responses: {len(result['responses'])}")
        for qid, resp in result["responses"].items():
            status = "accepted" if resp["decision"] == "accept" else resp["decision"]
            print(f"  {qid}: {resp['value']} ({status})")


if __name__ == "__main__":
    main()
