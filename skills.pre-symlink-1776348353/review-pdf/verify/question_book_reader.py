"""Question book reader — surfaces deferred items for human resolution via /interview.

When /review-pdf or /pdf-lab can't resolve an extraction issue automatically,
items are deferred to the question book or deferred_review queue. This module:

1. Reads both queues (question_book.jsonl + deferred_review.jsonl)
2. Groups items by type (hard_tail, html_block_page, non_auto_remediation)
3. Presents them via /interview for human resolution
4. Applies human decisions (blacklist, retry, skip, correct)

Items are NOT retried until the human answers — no error cascades from repeated
failed retries when /pdf-lab is blocked.

Usage:
    python question_book_reader.py status           # Show pending counts
    python question_book_reader.py review [--limit N]  # Present via /interview
    python question_book_reader.py apply <session>  # Apply /interview responses
    python question_book_reader.py clear            # Archive processed entries
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger

# Paths — resolve from env or defaults
_SKILLS_DIR = Path(os.environ.get(
    "PI_SKILLS_DIR",
    Path(__file__).resolve().parents[4],  # pi-mono/.pi/skills
))
_INTERVIEW_DIR = _SKILLS_DIR / "interview"
_MEMORY_DIR = _SKILLS_DIR / "memory"

# Queue files
_QUESTION_BOOK = Path(os.environ.get(
    "PDF_LAB_QUESTION_BOOK",
    _SKILLS_DIR / "learn-datalake" / "state" / "question_book.jsonl",
))
_DEFERRED_REVIEW = Path(os.environ.get(
    "DEFERRED_REVIEW_PATH",
    _SKILLS_DIR / "learn-datalake" / "state" / "deferred_review.jsonl",
))
_SESSIONS_DIR = Path(__file__).resolve().parent / "interview_sessions"


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file, skip malformed lines."""
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def _group_by_reason(entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group entries by reason code."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in entries:
        groups[e.get("reason", "unknown")].append(e)
    return dict(groups)


# ---------------------------------------------------------------------------
# status: Show what's pending for human review
# ---------------------------------------------------------------------------

def status() -> Dict[str, Any]:
    """Return summary of items awaiting human review."""
    qbook = _load_jsonl(_QUESTION_BOOK)
    deferred = _load_jsonl(_DEFERRED_REVIEW)
    all_items = qbook + deferred

    groups = _group_by_reason(all_items)
    summary = {
        "total_pending": len(all_items),
        "question_book_entries": len(qbook),
        "deferred_review_entries": len(deferred),
        "by_reason": {k: len(v) for k, v in groups.items()},
    }

    # Top worst-scoring hard_tail PDFs
    hard_tails = groups.get("hard_tail", [])
    if hard_tails:
        hard_tails.sort(key=lambda x: x.get("best_delta", 0))
        summary["worst_hard_tails"] = [
            {
                "pdf": e.get("pdf_name", "?"),
                "score": e.get("best_delta", 0),
                "iterations": e.get("iterations", 0),
                "worst_dims": e.get("worst_dimensions", []),
            }
            for e in hard_tails[:5]
        ]

    return summary


def print_status() -> None:
    """Print human-readable status to stdout."""
    s = status()
    print(f"\n=== Question Book Status ===")
    print(f"Total pending:     {s['total_pending']}")
    print(f"  Question book:   {s['question_book_entries']}")
    print(f"  Deferred review: {s['deferred_review_entries']}")
    print(f"\nBy reason:")
    for reason, count in sorted(s.get("by_reason", {}).items()):
        print(f"  {reason}: {count}")
    if "worst_hard_tails" in s:
        print(f"\nWorst hard-tail PDFs:")
        for ht in s["worst_hard_tails"]:
            print(f"  {ht['pdf']}: score={ht['score']:.3f} "
                  f"iters={ht['iterations']} worst={','.join(ht['worst_dims'][:2])}")
    print()


# ---------------------------------------------------------------------------
# review: Present items to human via /interview
# ---------------------------------------------------------------------------

def _build_interview_questions(
    items: List[Dict[str, Any]],
    reason: str,
) -> List[Dict[str, Any]]:
    """Build /interview questions from queue items."""
    questions = []

    for i, item in enumerate(items):
        pdf_name = item.get("pdf_name", item.get("stem", f"item_{i}"))

        if reason == "html_block_page":
            questions.append({
                "id": f"resolve_{i}",
                "header": f"HTML Block ({i+1}/{len(items)})",
                "text": (
                    f"'{pdf_name}' is not a real PDF — it's an HTML page "
                    f"(likely paywalled or access-denied).\n"
                    f"Path: {item.get('path', 'unknown')}\n"
                    f"Detail: {item.get('detail', '')}\n\n"
                    "What should we do?"
                ),
                "options": [
                    {"label": "Blacklist permanently", "description": "Never retry this file"},
                    {"label": "Re-download from alternate source", "description": "Flag for re-fetch with different credentials or URL"},
                    {"label": "Replace with correct PDF", "description": "You'll provide the correct file manually"},
                    {"label": "Skip for now", "description": "Leave in deferred queue, review later"},
                ],
            })

        elif reason == "hard_tail":
            score = item.get("best_delta", 0)
            trajectory = item.get("score_trajectory", [])
            worst = item.get("worst_dimensions", [])
            margaret = item.get("margaret_verdict", "?")
            jennifer = item.get("jennifer_verdict", "?")
            iters = item.get("iterations", 0)

            traj_str = " → ".join(f"{s:.3f}" for s in trajectory) if trajectory else "no data"
            questions.append({
                "id": f"resolve_{i}",
                "header": f"Hard Tail ({i+1}/{len(items)})",
                "text": (
                    f"'{pdf_name}' scored {score:.3f} after {iters} iterations.\n"
                    f"Score trajectory: {traj_str}\n"
                    f"Worst dimensions: {', '.join(worst[:3])}\n"
                    f"Margaret: {margaret} | Jennifer: {jennifer}\n\n"
                    "What should we do?"
                ),
                "options": [
                    {"label": "Skip — not worth fixing", "description": "Blacklist permanently, not valuable enough"},
                    {"label": "Retry with different strategy", "description": "Re-extract with different pipeline settings"},
                    {"label": "Needs manual correction", "description": "Open for bbox annotation of tables/figures"},
                    {"label": "Re-scan source document", "description": "Source PDF may be corrupt, get a better copy"},
                ],
            })
            # Follow-up text question for strategy hint
            questions.append({
                "id": f"hint_{i}",
                "header": "Strategy",
                "text": f"Any guidance for re-extracting '{pdf_name}'?",
                "type": "text",
            })

        elif reason == "non_auto_remediation":
            skill = item.get("skill", "unknown")
            detail = item.get("detail", "")
            verdict = item.get("verdict", "")
            questions.append({
                "id": f"resolve_{i}",
                "header": f"Remediation ({i+1}/{len(items)})",
                "text": (
                    f"'{pdf_name}' needs /{skill} but it's not auto-executable.\n"
                    f"Verdict: {verdict}\n"
                    f"Detail: {detail}\n\n"
                    "How should we proceed?"
                ),
                "options": [
                    {"label": f"Run /{skill} now", "description": "Approve auto-execution of this skill"},
                    {"label": "Skip — not worth fixing", "description": "Blacklist permanently"},
                    {"label": "Retry with different strategy", "description": "Re-extract with different settings"},
                    {"label": "Needs manual correction", "description": "Open for human annotation"},
                ],
            })

        else:
            questions.append({
                "id": f"resolve_{i}",
                "header": f"Review ({i+1}/{len(items)})",
                "text": (
                    f"'{pdf_name}' failed with reason: {reason}\n"
                    f"Detail: {item.get('detail', 'no detail')}\n\n"
                    "What should we do?"
                ),
                "options": [
                    {"label": "Blacklist permanently", "description": "Never retry"},
                    {"label": "Retry", "description": "Remove from deferred queue and re-extract"},
                    {"label": "Skip for now", "description": "Leave in queue"},
                ],
            })

    return questions


def review(limit: int = 10, mode: str = "html") -> Optional[Path]:
    """Present pending items to human via /interview.

    Returns the session file path for later `apply()`, or None if nothing to review.
    """
    qbook = _load_jsonl(_QUESTION_BOOK)
    deferred = _load_jsonl(_DEFERRED_REVIEW)
    all_items = qbook + deferred

    if not all_items:
        print("No items pending human review.")
        return None

    groups = _group_by_reason(all_items)

    # Build interview session — group by reason for efficiency
    all_questions: List[Dict[str, Any]] = []
    item_manifest: List[Dict[str, Any]] = []  # track which item maps to which question

    for reason, items in sorted(groups.items()):
        batch = items[:limit]
        questions = _build_interview_questions(batch, reason)
        for q, item in zip(questions, batch):
            all_questions.append(q)
            item_manifest.append({
                "reason": reason,
                "pdf_path": item.get("pdf_path", item.get("path", "")),
                "pdf_name": item.get("pdf_name", item.get("stem", "")),
                "source": "question_book" if item in qbook else "deferred_review",
                "original_entry": item,
            })

    session_data = {
        "title": f"Extraction Review — {len(all_items)} items pending",
        "context": (
            f"Items awaiting your decision. "
            f"By reason: {', '.join(f'{k}={len(v)}' for k, v in groups.items())}"
        ),
        "questions": all_questions[:limit * 2],  # cap total questions
    }

    # Write session request + manifest
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    session_file = _SESSIONS_DIR / f"review_{ts}.json"
    manifest_file = _SESSIONS_DIR / f"manifest_{ts}.json"

    session_file.write_text(json.dumps(session_data, indent=2, default=str))
    manifest_file.write_text(json.dumps(item_manifest, indent=2, default=str))

    print(f"Created interview session: {session_file}")
    print(f"Item manifest: {manifest_file}")
    print(f"Presenting {len(all_questions)} questions for {len(item_manifest)} items...")

    # Run /interview
    run_sh = _INTERVIEW_DIR / "run.sh"
    if not run_sh.exists():
        print(f"ERROR: /interview skill not found at {_INTERVIEW_DIR}")
        return session_file

    try:
        result = subprocess.run(
            [str(run_sh), "--mode", mode, "--file", str(session_file)],
            timeout=1800,  # 30 min max
            cwd=str(_INTERVIEW_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            print(f"WARNING: /interview exited with code {result.returncode}")
    except subprocess.TimeoutExpired:
        print("WARNING: /interview timed out after 30 minutes")
    except OSError as exc:
        print(f"ERROR: Failed to run /interview: {exc}")

    return session_file


# ---------------------------------------------------------------------------
# apply: Process /interview responses
# ---------------------------------------------------------------------------

def apply(session_dir: Optional[Path] = None) -> Dict[str, int]:
    """Apply human decisions from the most recent /interview session.

    Returns counts of actions taken.
    """
    if session_dir is None:
        session_dir = _SESSIONS_DIR

    # Find latest session response
    interview_sessions = _INTERVIEW_DIR / "sessions"
    if not interview_sessions.exists():
        print("No /interview sessions found")
        return {}

    session_files = sorted(
        interview_sessions.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not session_files:
        print("No /interview session responses found")
        return {}

    response_file = session_files[0]
    print(f"Applying decisions from: {response_file}")

    try:
        response = json.loads(response_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Failed to read session: {exc}")
        return {}

    # Find matching manifest
    manifest_files = sorted(
        _SESSIONS_DIR.glob("manifest_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not manifest_files:
        print("No manifest found — can't map responses to items")
        return {}

    try:
        manifest = json.loads(manifest_files[0].read_text())
    except (json.JSONDecodeError, OSError):
        manifest = []

    responses = response.get("responses", {})
    counts = {"blacklisted": 0, "retried": 0, "skipped": 0, "corrected": 0, "learned": 0}

    for i, item_info in enumerate(manifest):
        key = f"resolve_{i}"
        resp = responses.get(key, {})
        decision = resp.get("value", "").lower() if isinstance(resp, dict) else ""
        if not decision:
            continue

        pdf_path = Path(item_info.get("pdf_path", ""))
        pdf_name = item_info.get("pdf_name", "")
        reason = item_info.get("reason", "")

        if "blacklist" in decision or "skip" in decision and "not worth" in decision:
            _action_blacklist(pdf_path, reason)
            counts["blacklisted"] += 1

        elif "retry" in decision or "re-extract" in decision:
            hint_key = f"hint_{i}"
            hint = responses.get(hint_key, {})
            strategy_hint = hint.get("value", "") if isinstance(hint, dict) else ""
            _action_retry(pdf_path, strategy_hint)
            counts["retried"] += 1

        elif "manual correction" in decision:
            _action_flag_for_correction(pdf_path, reason)
            counts["corrected"] += 1

        elif "re-scan" in decision or "re-download" in decision:
            _action_flag_redownload(pdf_path)
            counts["retried"] += 1

        elif "skip for now" in decision:
            counts["skipped"] += 1
            continue  # leave in queue

        elif "run /" in decision:
            skill = item_info.get("original_entry", {}).get("skill", "")
            _action_run_skill(pdf_path, skill)
            counts["learned"] += 1

        # Remove from deferred queue (unless "skip for now")
        if "skip for now" not in decision:
            _remove_from_queues(pdf_path, pdf_name)

    print(f"\nApplied decisions: {counts}")
    return counts


def _action_blacklist(pdf_path: Path, reason: str) -> None:
    """Permanently blacklist a PDF."""
    try:
        # Import from learn-datalake if available
        sys.path.insert(0, str(_SKILLS_DIR / "learn-datalake"))
        from pdf_discovery import blacklist_pdf
        blacklist_pdf(pdf_path, reason=f"human_decision_{reason}")
        print(f"  BLACKLISTED: {pdf_path.name}")
    except ImportError:
        logger.warning("Could not import blacklist_pdf — manual blacklist needed")

    # Store decision as /memory lesson
    _learn_decision(pdf_path, "blacklist", reason)


def _action_retry(pdf_path: Path, strategy_hint: str = "") -> None:
    """Remove stale extraction and queue for retry."""
    # Remove from extracted_runs to force re-extraction
    from .triage import _slug_for_doc
    slug = _slug_for_doc(pdf_path)

    extracted_runs = Path(__file__).resolve().parent.parent / "extracted_runs"
    stale_run = extracted_runs / slug
    if stale_run.exists():
        try:
            if stale_run.is_symlink():
                target = stale_run.resolve()
                stale_run.unlink()
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
            else:
                shutil.rmtree(stale_run, ignore_errors=True)
            print(f"  RETRY: Removed stale run for {pdf_path.name}")
        except OSError as exc:
            logger.warning(f"Failed to remove stale run: {exc}")

    # Store strategy hint as /memory lesson for next extraction
    if strategy_hint:
        _learn_decision(pdf_path, "retry", f"strategy_hint: {strategy_hint}")
    print(f"  RETRY: {pdf_path.name} queued for re-extraction")


def _action_flag_for_correction(pdf_path: Path, reason: str) -> None:
    """Flag for human bbox annotation on next extraction attempt."""
    # Set env flag so human_feedback.py activates for this PDF
    _learn_decision(pdf_path, "needs_correction", reason)
    print(f"  CORRECTION: {pdf_path.name} flagged for bbox annotation")


def _action_flag_redownload(pdf_path: Path) -> None:
    """Flag for re-download from alternate source."""
    _learn_decision(pdf_path, "redownload", "Human requested re-scan of source document")
    print(f"  REDOWNLOAD: {pdf_path.name} flagged for re-fetch")


def _action_run_skill(pdf_path: Path, skill: str) -> None:
    """Execute a previously non-auto-executable skill."""
    if not skill:
        print(f"  SKILL: No skill specified for {pdf_path.name}")
        return
    skill_dir = _SKILLS_DIR / skill
    run_sh = skill_dir / "run.sh"
    if run_sh.exists():
        print(f"  SKILL: Running /{skill} for {pdf_path.name}...")
        try:
            subprocess.run(
                [str(run_sh), str(pdf_path)],
                timeout=600,
                cwd=str(skill_dir),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"  WARNING: /{skill} failed: {exc}")
    else:
        print(f"  WARNING: Skill /{skill} not found at {skill_dir}")
    _learn_decision(pdf_path, "skill_executed", skill)


def _learn_decision(pdf_path: Path, action: str, detail: str = "") -> None:
    """Store human decision in /memory as a lesson for future reference."""
    run_sh = _MEMORY_DIR / "run.sh"
    if not run_sh.exists():
        return
    import hashlib
    pdf_hash = hashlib.md5(str(pdf_path).encode()).hexdigest()[:10]
    text = (
        f"Human reviewed {pdf_path.name} and decided: {action}. "
        f"{detail}"
    )
    try:
        subprocess.run(
            [
                str(run_sh), "learn",
                "--text", text,
                "--tag", "human_decision",
                "--tag", f"pdf_{pdf_hash}",
                "--tag", action,
            ],
            timeout=30,
            capture_output=True,
            cwd=str(_MEMORY_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except (subprocess.TimeoutExpired, OSError):
        pass  # non-critical


def _remove_from_queues(pdf_path: Path, pdf_name: str) -> None:
    """Remove a resolved item from both queues."""
    stem = pdf_path.stem if pdf_path.name else pdf_name.replace(".pdf", "")

    for queue_path in (_QUESTION_BOOK, _DEFERRED_REVIEW):
        if not queue_path.exists():
            continue
        lines = queue_path.read_text().strip().split("\n")
        kept = []
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                entry_stem = entry.get("stem", entry.get("pdf_name", "").replace(".pdf", ""))
                entry_path = entry.get("pdf_path", entry.get("path", ""))
                # Match by stem or full path
                if entry_stem == stem or str(pdf_path) == entry_path:
                    continue  # remove
                kept.append(line)
            except json.JSONDecodeError:
                kept.append(line)
        queue_path.write_text("\n".join(kept) + "\n" if kept else "")


# ---------------------------------------------------------------------------
# clear: Archive processed entries
# ---------------------------------------------------------------------------

def clear() -> None:
    """Archive both queues to timestamped backup files."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    for path in (_QUESTION_BOOK, _DEFERRED_REVIEW):
        if path.exists() and path.stat().st_size > 0:
            backup = path.with_suffix(f".jsonl.bak.{ts}")
            shutil.copy2(path, backup)
            path.write_text("")
            print(f"Archived {path.name} → {backup.name}")
        else:
            print(f"Nothing to archive in {path.name}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_cli_app = typer.Typer(
    name="question-book-reader",
    help="Question book reader — surfaces deferred extraction items for human review",
    no_args_is_help=True,
)


@_cli_app.command("status")
def _cmd_status() -> None:
    """Show pending counts and worst items."""
    print_status()


@_cli_app.command("review")
def _cmd_review(
    limit: int = typer.Option(10, "--limit", help="Max items per reason group"),
    mode: str = typer.Option("html", "--mode", help="Interview display mode (html/tui)"),
) -> None:
    """Present items via /interview."""
    if mode not in ("html", "tui"):
        raise typer.BadParameter(f"Invalid mode: {mode}. Choose html or tui")
    review(limit=limit, mode=mode)


@_cli_app.command("apply")
def _cmd_apply() -> None:
    """Apply decisions from latest /interview session."""
    apply()


@_cli_app.command("clear")
def _cmd_clear() -> None:
    """Archive processed entries."""
    clear()


if __name__ == "__main__":
    _cli_app()
