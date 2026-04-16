"""Nightly QRA promotion pipeline for conversation-lab.

Scans session files for satisfactory turns with synthesized answers,
deduplicates against existing QRAs, runs quality assessment (Brandon
inline assess_qra), optional Lean4 compiler verification, and promotes
passing candidates into the SPARTA QRA graph.

Pipeline stages:
  1. HARVEST -- Find satisfactory turns with synthesized answers
  2. DEDUPLICATE -- Check if promoted QRA already exists (query hash match)
  3. ENRICH -- /taxonomy extract bridge tags
  4. ASSESS -- Brandon inline assess_qra() on each candidate
  5. PROMOTE -- PASS candidates via QRABridge.upsert_qra()
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console

console = Console()

SKILLS_DIR = Path(__file__).parent.parent


def _harvest_candidates(sessions: list[dict]) -> list[dict]:
    """HARVEST: Find satisfactory turns with synthesized answers."""
    candidates = []
    for session in sessions:
        turns = session.get("turns", [])
        for i, turn in enumerate(turns):
            meta = turn.get("metadata", {})
            if meta.get("evaluation") not in ("satisfactory", "flaw_caught"):
                continue
            # Find the preceding SPARTA answer
            answer_turn = None
            for j in range(i - 1, -1, -1):
                if turns[j].get("role") == "system":
                    answer_turn = turns[j]
                    break
            if not answer_turn:
                continue
            answer_text = answer_turn.get("content", "")
            # Only promote synthesized answers (steering or graph-inferred)
            is_synthesis = (
                "[GRAPH-INFERRED]" in answer_text
                or answer_turn.get("metadata", {}).get("steering")
                or "[CONTROL-CONTEXT]" in answer_text
            )
            if not is_synthesis:
                continue
            # Find the original question
            question_turn = None
            for t in turns:
                if t.get("role") == "persona" and t.get("action") in ("QUERY", "FOLLOW_UP"):
                    question_turn = t
                    break
            if not question_turn:
                continue

            composite = meta.get("self_grade_final", {}).get("composite", 0)
            if composite < 0.85:
                composite_from_grade = session.get("grade", {}).get("composite", 0)
                if composite_from_grade < 0.85:
                    continue
                composite = composite_from_grade

            candidates.append({
                "question": question_turn["content"],
                "answer": answer_text,
                "session_id": session.get("session_id", "unknown"),
                "persona": session.get("persona", "unknown"),
                "composite": composite,
                "control_id": answer_turn.get("metadata", {}).get("target_control", ""),
            })
    return candidates


def _deduplicate(candidates: list[dict], db) -> list[dict]:
    """DEDUPLICATE: Filter out candidates that already exist in sparta_qra."""
    deduped = []
    for c in candidates:
        query_hash = hashlib.md5(c["question"].encode()).hexdigest()[:12]
        synth_hash = hashlib.md5(f"{c['question']}{c['answer']}".encode()).hexdigest()[:12]
        qra_key = f"qra__persona-conv__{synth_hash}"
        try:
            existing = db.collection("sparta_qra").get(qra_key)
            if existing:
                continue  # Already promoted
        except Exception:
            pass
        c["_key"] = qra_key
        c["query_hash"] = query_hash
        deduped.append(c)
    return deduped


def _load_lean4_verifier() -> Optional[callable]:
    """Try to load the Lean4 QRA reasoning verifier. Returns None if unavailable."""
    try:
        lean4_skill = Path(__file__).parent.parent / "lean4-prove"
        if not lean4_skill.exists():
            return None
        spec = importlib.util.spec_from_file_location(
            "qra_consistency", lean4_skill / "qra_consistency.py",
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, "verify_qra_reasoning", None)
            if fn:
                console.print("[green]Lean4 reasoning verification available[/green]")
                return fn
    except Exception as e:
        logger.debug(f"Lean4 verification not available: {e}")
    return None


def _assess_and_promote(
    deduped: list[dict], bridge, db, *, has_lean4: bool, verify_fn
) -> dict[str, int]:
    """ASSESS + PROMOTE: 3-way routing via assess_qra() + optional Lean4 verification.

    Returns counts dict with keys: promoted, staged, rejected, failed,
    lean4_verified, lean4_failed.
    """
    # Try to load assess infrastructure
    try:
        from graph_memory.quality.assess import assess_qra
        from graph_memory.candidate_bridge import CandidateBridge
        candidate_bridge = CandidateBridge(db)
        has_assess = True
    except ImportError:
        has_assess = False
        assess_qra = None
        candidate_bridge = None
        console.print("[yellow]assess_qra not available -- promoting without quality gate[/yellow]")

    counts = {
        "promoted": 0, "staged": 0, "rejected": 0, "failed": 0,
        "lean4_verified": 0, "lean4_failed": 0,
    }

    for c in deduped:
        try:
            qra_doc = {
                "_key": c["_key"],
                "qra_id": f"synth_persona_{c['query_hash']}",
                "run_id": "persona-conversation",
                "control_id": c.get("control_id", ""),
                "question": c["question"],
                "answer": c["answer"],
                "reasoning": (
                    f"Nightly promotion from session {c['session_id']}. "
                    f"Persona '{c['persona']}' evaluated 'satisfactory' "
                    f"(composite={c['composite']:.2f})."
                ),
                "grounding_score": c["composite"],
                "_source": "persona_conversation_promotion",
                "_scope": "sparta",
                "created_at": time.time(),
            }

            if has_assess:
                assessment = assess_qra(qra_doc)
                if assessment["grade"] == "FAIL":
                    candidate_bridge.log_rejected(qra_doc, assessment)
                    counts["rejected"] += 1
                    continue
                elif assessment["grade"] == "WARN":
                    candidate_bridge.stage(qra_doc, assessment)
                    counts["staged"] += 1
                    continue

            # Lean4 compiler gate: 3-way routing
            if has_lean4 and verify_fn:
                try:
                    lean4_result = verify_fn(qra_doc)
                    qra_doc["lean4_verified"] = lean4_result.get("verified", False)
                    qra_doc["lean4_error_taxonomy"] = lean4_result.get("error_taxonomy", {})
                    if lean4_result.get("verified"):
                        counts["lean4_verified"] += 1
                    elif lean4_result.get("steps_total", 0) > 0:
                        # Had formalizable claims but some failed -- stage for correction
                        counts["lean4_failed"] += 1
                        if has_assess:
                            candidate_bridge.stage(qra_doc, {
                                "grade": "WARN",
                                "reason": "Lean4 reasoning verification failed",
                                "error_taxonomy": lean4_result.get("error_taxonomy", {}),
                            })
                            counts["staged"] += 1
                            continue
                    else:
                        # steps_total == 0: couldn't formalize at all
                        control_id = qra_doc.get("control_id", "")
                        if control_id:
                            counts["lean4_failed"] += 1
                            logger.info(
                                f"  Cannot formalize {control_id} -- "
                                f"requirement may be ambiguous, flagging for clarify"
                            )
                            if has_assess:
                                candidate_bridge.stage(qra_doc, {
                                    "grade": "WARN",
                                    "reason": "Cannot formalize structured requirement -- ambiguous?",
                                    "needs_clarify": True,
                                    "control_id": control_id,
                                })
                                counts["staged"] += 1
                                continue
                except Exception as e:
                    logger.debug(f"Lean4 verification error (non-fatal): {e}")

            bridge.upsert_qra(qra_doc)
            counts["promoted"] += 1
        except Exception as e:
            logger.warning(f"Promotion failed for {c['_key']}: {e}")
            counts["failed"] += 1

    return counts


def promote_nightly_command(
    sessions: list[dict],
    dry_run: bool = False,
) -> None:
    """Execute the full promote-nightly pipeline.

    Called from the CLI command in conversation_lab.py.
    """
    # Ensure graph_memory is importable
    _src_path = str(Path(__file__).parent.parent.parent.parent / "memory" / "src")
    if _src_path not in sys.path:
        sys.path.insert(0, _src_path)

    try:
        from graph_memory.arango_client import get_db
        from graph_memory.qra_bridge import QRABridge
        db = get_db()
        bridge = QRABridge(db)
    except Exception as e:
        console.print(f"[red]Cannot connect to ArangoDB: {e}[/red]")
        raise typer.Exit(1)

    # HARVEST
    candidates = _harvest_candidates(sessions)
    console.print(
        f"[cyan]Harvested {len(candidates)} promotion candidates "
        f"from {len(sessions)} sessions[/cyan]"
    )

    # DEDUPLICATE
    deduped = _deduplicate(candidates, db)
    console.print(f"[cyan]After dedup: {len(deduped)} new candidates[/cyan]")

    if dry_run:
        for c in deduped[:10]:
            console.print(f"  [dim]{c['_key']}[/dim] {c['question'][:80]}...")
        if len(deduped) > 10:
            console.print(f"  ... and {len(deduped) - 10} more")
        raise typer.Exit(0)

    # Load optional Lean4 verifier
    verify_fn = _load_lean4_verifier()
    has_lean4 = verify_fn is not None

    # ASSESS + PROMOTE
    counts = _assess_and_promote(deduped, bridge, db, has_lean4=has_lean4, verify_fn=verify_fn)

    lean4_msg = ""
    if has_lean4:
        lean4_msg = (
            f" | [cyan]Lean4 verified: {counts['lean4_verified']}, "
            f"failed: {counts['lean4_failed']}[/cyan]"
        )
    console.print(
        f"[green]Promoted (PASS): {counts['promoted']}[/green] | "
        f"[yellow]Staged (WARN): {counts['staged']}[/yellow] | "
        f"[red]Rejected (FAIL): {counts['rejected']}[/red] | "
        f"[dim]Errors: {counts['failed']} | "
        f"Skipped (dedup): {len(candidates) - len(deduped)}[/dim]"
        f"{lean4_msg}"
    )
