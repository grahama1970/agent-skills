"""NDJSON event emitter for evidence case pipeline.

The pipeline writes structured events here. The QML app tails the file.
Each line is a self-contained JSON object with a `type` field.

Usage:
    emitter = EventEmitter("/tmp/evidence-case-events.jsonl")
    emitter.emit("question_received", question="How does X23-MUSTARD...")
    emitter.emit("gate_fired", gate="topic", passed=True, reason="on-topic")
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_LOG = "/tmp/evidence-case-events.jsonl"


class EventEmitter:
    """Write NDJSON events that the QML viewer tails."""

    def __init__(self, path: str = DEFAULT_LOG):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._start = time.monotonic()

    def clear(self) -> None:
        """Truncate the event log for a new question."""
        self.path.write_text("")
        self._start = time.monotonic()

    def emit(self, event_type: str, **data: Any) -> None:
        """Append one NDJSON line."""
        record = {
            "type": event_type,
            "ts": round(time.monotonic() - self._start, 3),
            **data,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")


def run_evidence_pipeline(question: str, emitter: EventEmitter | None = None) -> dict:
    """Run the full evidence case pipeline with event emission.

    Wraps collect.py functions and emits events at each step so the QML
    viewer can show progress live.

    After entity extraction, recall + lean4 classifier run CONCURRENTLY
    since they're independent.
    """
    import sys
    from concurrent.futures import ThreadPoolExecutor, as_completed

    _skills_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_skills_dir / "create-evidence-case"))
    sys.path.insert(0, str(Path.home() / "workspace" / "experiments" / "memory" / "src"))
    os.environ.setdefault("ARANGO_DB", "memory")

    from collect import (
        collect_entities, collect_recall, group_by_technique, collect_topic,
        collect_lean4_provable, collect_clarify,
    )
    from plausibility import check_plausibility

    if emitter is None:
        emitter = EventEmitter()

    emitter.clear()

    # Step 0: Question received
    emitter.emit("question_received", question=question)

    # Step 1: Topic classification
    emitter.emit("gate_start", gate="topic", label="Topic Classification")
    try:
        topic_result = collect_topic(question)
        on_topic = topic_result.get("on_topic", True) if topic_result else True
        emitter.emit("gate_result", gate="topic", passed=on_topic,
                     reason=topic_result.get("category", "unknown") if topic_result else "no classifier")
    except Exception as e:
        emitter.emit("gate_result", gate="topic", passed=True, reason=f"error: {e}")

    # Step 2: Entity extraction + sentence markup
    emitter.emit("gate_start", gate="entities", label="Entity Extraction")
    try:
        entities = collect_entities(question)
    except Exception as e:
        emitter.emit("gate_result", gate="entities", passed=True, reason=f"error: {e}")
        entities = {"warnings": [], "resolution_map": {}, "control_ids": []}

    resolution_map = entities.get("resolution_map", {})
    warnings = entities.get("warnings", [])
    control_ids = entities.get("control_ids", [])

    # Emit per-term NVIS annotations
    annotations = []
    for term, info in resolution_map.items():
        if isinstance(info, dict):
            if info.get("exists"):
                level = "GREEN"
                label = f"Confirmed: {info.get('name', term)}"
            elif info.get("closest_match"):
                dist = info.get("distance", 0)
                if dist < 0.3:
                    level = "AMBER"
                    label = f"Fuzzy match → {info['closest_match']} (dist={dist:.2f})"
                else:
                    level = "RED"
                    label = f"Fabricated — closest: {info['closest_match']} (dist={dist:.2f})"
            else:
                level = "YELLOW"
                label = "Not found in corpus"
            annotations.append({"term": term, "level": level, "label": label})

    for w in warnings:
        if w.get("category") == "not_in_corpus":
            term = w.get("term", "?")
            if not any(a["term"] == term for a in annotations):
                annotations.append({"term": term, "level": "YELLOW",
                                    "label": f"Not in corpus ({w.get('type', 'phrase')})"})

    emitter.emit("sentence_markup", annotations=annotations)

    # Check for fabricated IDs
    fabricated_ids = [w for w in warnings if w.get("category") == "fabricated_id"]
    resolved_count = sum(
        1 for v in resolution_map.values()
        if isinstance(v, dict) and v.get("exists")
    )
    emitter.emit("gate_result", gate="entities",
                 passed=not fabricated_ids,
                 reason=f"{resolved_count} resolved, {len(fabricated_ids)} fabricated, {len(warnings)} warnings",
                 resolved_count=resolved_count,
                 fabricated_count=len(fabricated_ids))

    if fabricated_ids:
        fab_terms = [w["term"] for w in fabricated_ids]
        emitter.emit("verdict", verdict="not_satisfied", grade="F",
                     reason=f"Fabricated ID(s): {', '.join(fab_terms)}")
        return {"verdict": "not_satisfied", "gate_failed": "fabricated_id"}

    # ── Step 3: CONCURRENT — recall + lean4 classifier + clarify ──────
    # These are independent after entity extraction. Run them in parallel.
    emitter.emit("gate_start", gate="recall", label="QRA Recall (/memory)")
    emitter.emit("gate_start", gate="lean4", label="Lean4 Provability Classifier")
    emitter.emit("gate_start", gate="clarify", label="Memory Clarify")

    qras = []
    lean4_result = None
    clarify_result = None

    def _do_recall():
        return collect_recall(question)

    def _do_lean4():
        return collect_lean4_provable(question, control_ids)

    def _do_clarify():
        return collect_clarify(question)

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_recall = pool.submit(_do_recall)
        fut_lean4 = pool.submit(_do_lean4)
        fut_clarify = pool.submit(_do_clarify)

        for fut in as_completed([fut_recall, fut_lean4, fut_clarify]):
            try:
                result = fut.result(timeout=30)
                if fut is fut_recall:
                    qras = result or []
                    top_qras = [{"control_id": q.get("control_id", "?"),
                                 "question": q.get("question", "")[:80],
                                 "score": round(q.get("score", 0), 3)}
                                for q in qras[:8]]
                    emitter.emit("qra_recall", count=len(qras), top_qras=top_qras)
                    emitter.emit("gate_result", gate="recall",
                                 passed=bool(qras),
                                 reason=f"{len(qras)} QRAs found" if qras else "No QRAs found")
                elif fut is fut_lean4:
                    lean4_result = result
                    if lean4_result:
                        pred = lean4_result.get("prediction", "unknown")
                        conf = lean4_result.get("confidence", 0)
                        emitter.emit("gate_result", gate="lean4", passed=True,
                                     reason=f"{pred} (confidence={conf:.2f})",
                                     prediction=pred, confidence=conf)
                    else:
                        emitter.emit("gate_result", gate="lean4", passed=True,
                                     reason="classifier unavailable — skipped")
                elif fut is fut_clarify:
                    clarify_result = result
                    if clarify_result:
                        emitter.emit("clarify_result",
                                     suggestions=clarify_result.get("suggestions", []),
                                     related=clarify_result.get("related", []))
                    emitter.emit("gate_result", gate="clarify", passed=True,
                                 reason="done" if clarify_result else "unavailable")
            except Exception as e:
                if fut is fut_recall:
                    emitter.emit("gate_result", gate="recall", passed=False,
                                 reason=f"error: {e}")
                elif fut is fut_lean4:
                    emitter.emit("gate_result", gate="lean4", passed=True,
                                 reason=f"error: {e}")
                elif fut is fut_clarify:
                    emitter.emit("gate_result", gate="clarify", passed=True,
                                 reason=f"error: {e}")

    if not qras:
        emitter.emit("verdict", verdict="not_satisfied", grade="F",
                     reason="No QRAs found via recall")
        return {"verdict": "not_satisfied", "gate_failed": "recall"}

    # Step 4: Plausibility check (conditional)
    not_in_corpus = [w for w in warnings if w.get("category") == "not_in_corpus"]
    id_like_unresolved = [w for w in not_in_corpus if w.get("type") == "id_like"]
    needs_plausibility = not_in_corpus and (
        id_like_unresolved or resolved_count < 5 or len(qras) < 10
    )

    if needs_plausibility:
        emitter.emit("gate_start", gate="plausibility",
                     label="Answerability Check (LLM)")
        plaus_result = check_plausibility(question, warnings, resolution_map)
        backend = plaus_result.get("backend", "none")
        answerable = plaus_result.get("answerable", plaus_result.get("plausible", True))

        emitter.emit("plausibility_detail",
                     backend=backend, answerable=answerable,
                     reason=plaus_result.get("reason", ""),
                     clarifying_questions=plaus_result.get("clarifying_questions", []))

        if plaus_result.get("checked") and not answerable:
            emitter.emit("gate_result", gate="plausibility", passed=False,
                         reason=plaus_result.get("reason", "not answerable"))
            clarify_qs = plaus_result.get("clarifying_questions", [])
            if clarify_qs:
                emitter.emit("clarify_suggestions", questions=clarify_qs,
                             reason=plaus_result.get("reason", ""))
            emitter.emit("verdict", verdict="not_satisfied", grade="F",
                         reason=f"Not answerable: {plaus_result.get('reason', '')}")
            return {"verdict": "not_satisfied", "gate_failed": "plausibility",
                    "clarifying_questions": clarify_qs}

        emitter.emit("gate_result", gate="plausibility", passed=True,
                     reason=f"Answerable ({backend})")
    else:
        emitter.emit("gate_start", gate="plausibility",
                     label="Answerability Check (LLM)")
        emitter.emit("gate_result", gate="plausibility", passed=True,
                     reason=f"Skipped — strong evidence ({resolved_count} resolved, {len(qras)} QRAs)")

    # Step 5: Technique coherence
    emitter.emit("gate_start", gate="technique", label="Technique Coherence")
    techniques = group_by_technique(qras) if qras else {}
    real_techs = {k: v for k, v in techniques.items() if k != "UNTAGGED"}
    total_tagged = sum(len(v) for v in real_techs.values())

    tech_summary = {k: len(v) for k, v in techniques.items()}
    emitter.emit("technique_groups", groups=tech_summary, total_tagged=total_tagged)

    if real_techs:
        dominant_name, dominant_list = max(real_techs.items(), key=lambda x: len(x[1]))
        coherence = len(dominant_list) / max(total_tagged, 1)
    else:
        dominant_name = "UNTAGGED"
        coherence = 0.0

    resolved_controls = [
        term for term, info in resolution_map.items()
        if isinstance(info, dict) and info.get("exists") and
        info.get("match_type") in ("exact", "domain_term")
    ]

    # Determine grade — lean4 proof strengthens confidence
    lean4_proved = (lean4_result or {}).get("prediction") == "provable"
    if total_tagged > 0 and coherence >= 0.25 and len(resolved_controls) >= 2:
        grade = "A+" if (coherence >= 0.6 and total_tagged >= 10) or lean4_proved else "A" if coherence >= 0.4 else "B+"
        verdict = "satisfied"
    elif len(qras) > 5 and len(resolved_controls) >= 1:
        grade = "B"
        verdict = "satisfied"
    elif total_tagged == 0 and len(qras) > 0:
        grade = "C"
        verdict = "inconclusive"
    else:
        grade = "C"
        verdict = "inconclusive"

    emitter.emit("gate_result", gate="technique", passed=(verdict == "satisfied"),
                 reason=f"{total_tagged} tagged, dominant '{dominant_name}' ({coherence:.0%}), {len(resolved_controls)} resolved")

    reason_parts = [f"{total_tagged} tagged", f"dominant '{dominant_name}' ({coherence:.0%})",
                    f"{len(resolved_controls)} resolved controls"]
    if lean4_proved:
        reason_parts.append("lean4 proved")
    reason = ", ".join(reason_parts)
    emitter.emit("verdict", verdict=verdict, grade=grade, reason=reason)

    return {"verdict": verdict, "grade": grade, "reason": reason,
            "lean4": lean4_result, "clarify": clarify_result}
