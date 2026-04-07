"""Evidence gate for QRA validation — thin wrapper over /create-evidence-case.

Imports directly from /create-evidence-case (collect.py, plausibility.py)
and /evidence-case-lab (agent_verdict from run_stress_test.py).

This is NOT a reimplementation. It calls the proven gate chain that was
validated at 269/269 in evidence-case-lab run 30.

ALL daemon calls go through the embry-memory Unix socket.
ALL LLM calls go through scillm HTTP proxy.
NO python-arango — entity extraction uses /extract-entities/run.sh subprocess.
NO fallbacks — if a step fails, it fails LOUDLY.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer

# ---------------------------------------------------------------------------
# Import from existing skills — NOT reimplementing
# ---------------------------------------------------------------------------

_SKILLS_DIR = Path(__file__).resolve().parent.parent
_CREATE_EVIDENCE_CASE = str(_SKILLS_DIR / "create-evidence-case")
_EVIDENCE_CASE_LAB = str(_SKILLS_DIR / "evidence-case-lab")

for _p in (_CREATE_EVIDENCE_CASE, _EVIDENCE_CASE_LAB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# NOTE: We do NOT add memory/src to sys.path. This forces collect.py to use
# the /extract-entities/run.sh subprocess path (daemon-compliant) instead of
# importing graph_memory directly (which would need python-arango).
#
# HOWEVER: run_stress_test.py line 32 does sys.path.insert(0, ".../memory/src")
# at module level. Importing agent_verdict triggers that, polluting sys.path
# and making graph_memory importable (but non-functional without arango pkg).
# We MUST remove that path after import so collect_entities() falls through
# to the /extract-entities/run.sh subprocess (daemon-compliant).

_MEMORY_SRC = str(Path.home() / "workspace" / "experiments" / "memory" / "src")

from collect import (  # noqa: E402
    collect_entities,
    collect_recall_with_confidence,
    collect_topic,
    group_by_technique,
)
from run_stress_test import agent_verdict  # noqa: E402

# Clean up: remove memory/src from sys.path so collect_entities() uses
# the subprocess path (/extract-entities/run.sh) instead of direct import.
while _MEMORY_SRC in sys.path:
    sys.path.remove(_MEMORY_SRC)

# ---------------------------------------------------------------------------
# Thread-local daemon client (reuse pattern from run_stress_test.py)
# ---------------------------------------------------------------------------

DAEMON_SOCKET = "/run/user/1000/embry/memory.sock"
MEMORY_SERVICE_URL = "http://127.0.0.1:8601"
_local = threading.local()


def _thread_daemon() -> httpx.Client:
    """Get or create a thread-local httpx client for the daemon."""
    if not hasattr(_local, "daemon"):
        transport = httpx.HTTPTransport(uds=DAEMON_SOCKET)
        _local.daemon = httpx.Client(
            transport=transport, base_url="http://localhost", timeout=30.0,
        )
    return _local.daemon


def _thread_memory_service() -> httpx.Client:
    """Get or create a thread-local httpx client for the memory service.

    The SPARTA QRA endpoints (/sparta/qra/*) are on the memory service
    (port 8601), NOT proxied by the daemon. Use this for backfill reads/writes.
    """
    if not hasattr(_local, "memory_svc"):
        _local.memory_svc = httpx.Client(
            base_url=MEMORY_SERVICE_URL, timeout=30.0,
        )
    return _local.memory_svc


# ---------------------------------------------------------------------------
# Core functions — NO fallbacks, fail loudly
# ---------------------------------------------------------------------------

_EVIDENCE_FIELDS = (
    "evidence_verdict", "evidence_score", "evidence_grade",
    "evidence_gates_passed", "evidence_gates_total",
    "evidence_correction_rounds", "evidence_gate_trace",
    "evidence_validated_at",
)


def _deterministic_verdict(question, entities, qras, techniques, topic_result=None):
    """Fast deterministic-only verdict — NO LLM calls.

    Runs gates 0-2 and technique coherence. Skips plausibility LLM entirely.
    For backfill of known-good production QRAs where the LLM gate adds cost
    but no value (these already passed quality gates during generation).
    """
    # Gate 0: Off-topic
    if topic_result and not topic_result.get("on_topic", True):
        return {
            "verdict": "not_satisfied", "grade": "F", "score": 0.0,
            "reason": "Off-topic: outside SPARTA space vehicle cybersecurity domain.",
            "gate_failed": "step_0_topic",
        }

    # Gate 0b: Naval/maritime
    q_lower = question.lower()
    naval_terms = ["naval deployment", "naval variant", "naval aviation",
                   "carrier operations", "submarine", "maritime"]
    naval_hits = [t for t in naval_terms if t in q_lower]
    if naval_hits:
        return {
            "verdict": "not_satisfied", "grade": "F", "score": 0.0,
            "reason": f"Off-topic: naval/maritime context ({', '.join(naval_hits)}).",
            "gate_failed": "step_0_naval",
        }

    warnings = entities.get("warnings", [])
    fabricated_ids = [w for w in warnings if w.get("category") == "fabricated_id"]

    # Gate 1: Fabricated IDs — hard block
    if fabricated_ids:
        fab_terms = [w["term"] for w in fabricated_ids]
        return {
            "verdict": "not_satisfied", "grade": "F", "score": 0.0,
            "reason": f"Fabricated IDs: {', '.join(fab_terms)}",
            "gate_failed": "step_1_fabricated_id",
        }

    # Gate 2: No QRAs
    if not qras:
        return {
            "verdict": "not_satisfied", "grade": "F", "score": 0.0,
            "reason": "No QRAs found for this question.",
            "gate_failed": "step_2_no_qras",
        }

    # Gate 4: Technique coherence for grading
    real_techs = {k: v for k, v in techniques.items() if k != "UNTAGGED"}
    total_tagged = sum(len(v) for v in real_techs.values())

    if total_tagged == 0:
        return {"verdict": "satisfied", "grade": "B", "score": 0.7,
                "reason": "Deterministic gates passed (no technique bridge)."}

    if len(real_techs) == 1:
        return {"verdict": "satisfied", "grade": "A", "score": 0.95,
                "reason": "Deterministic gates passed, single technique."}

    return {"verdict": "satisfied", "grade": "A-", "score": 0.85,
            "reason": "Deterministic gates passed, multiple techniques."}


def evidence_validate_qra(question: str, control_id: str = "",
                          deterministic_only: bool = False) -> dict:
    """Validate a QRA question using the evidence gate chain.

    Calls the same functions as evidence-case-lab's process_question():
      1. collect_topic() — off-topic classifier
      2. collect_recall_with_confidence() — QRA recall
      3. collect_entities() — entity extraction + grounding
      4. group_by_technique() — technique coherence
      5. agent_verdict() — the proven gate chain (skipped if deterministic_only)

    When deterministic_only=True, skips the plausibility LLM call. Use this
    for backfill of known-good production QRAs where deterministic gates
    are sufficient and the LLM adds ~1s/QRA of unnecessary cost.

    Returns dict with evidence_* fields ready for stamping onto QRA docs.
    Raises on any step failure — NO silent degradation.
    """
    t0 = time.monotonic()

    # Gate 0: Topic classifier — MUST succeed
    topic_result = collect_topic(question)

    # QRA recall — MUST succeed
    recall_result = collect_recall_with_confidence(question)
    qras = recall_result["items"]
    recall_confidence = recall_result.get("confidence", 0.0)

    # Entity extraction — MUST succeed (uses /extract-entities/run.sh subprocess)
    entities = collect_entities(question)

    # Technique grouping — pure Python, no IO
    techniques = group_by_technique(qras) if qras else {}

    if deterministic_only:
        vd = _deterministic_verdict(
            question, entities, qras, techniques,
            topic_result=topic_result,
        )
    else:
        # The proven verdict chain (includes plausibility LLM)
        vd = agent_verdict(
            question, entities, qras, techniques,
            topic_result=topic_result, recall_confidence=recall_confidence,
        )

    elapsed_ms = round((time.monotonic() - t0) * 1000)

    # Build gate trace from verdict
    gates_total = 4 if deterministic_only else 5  # skip plausibility count
    gates_passed = gates_total
    gate_trace = []

    if vd.get("gate_failed"):
        gates_passed = max(0, gates_total - 1)
        gate_trace.append({
            "gate": vd["gate_failed"], "passed": False,
            "detail": vd.get("reason", ""),
        })

    return {
        "verdict": vd["verdict"],
        "evidence_verdict": vd["verdict"],
        "evidence_score": vd.get("score", 0.0),
        "evidence_grade": vd.get("grade", "?"),
        "evidence_gates_passed": gates_passed,
        "evidence_gates_total": gates_total,
        "evidence_correction_rounds": 0,
        "evidence_gate_trace": gate_trace or vd.get("gate_trace", []),
        "evidence_validated_at": datetime.now(timezone.utc).isoformat(),
        "reason": vd.get("reason", ""),
        "grade": vd.get("grade", "?"),
        "score": vd.get("score", 0.0),
        "elapsed_ms": elapsed_ms,
        "gate_trace": gate_trace,
        "plausibility": vd.get("plausibility"),
    }


def evidence_correct_qra(
    question: str,
    control_id: str,
    gate_trace: list[dict],
    max_retries: int = 3,
) -> dict:
    """Self-correction loop: ask scillm to fix the question, re-validate.

    Sends structured JSON gate trace to scillm so the LLM knows exactly
    what failed and can propose a corrected question.

    Prompt validated via /prompt-lab: evidence_qra_correction_v3 (10/10, 100%).
    """
    SCILLM_BASE = "http://localhost:4001"
    SCILLM_KEY = "sk-dev-proxy-123"

    # System prompt validated via /prompt-lab (evidence_qra_correction_v3)
    system_prompt = (
        "You are a SPARTA QRA question correction specialist. Your job is "
        "to fix QRA (Question-Response-Anchor) questions that failed "
        "evidence validation against the SPARTA controls corpus (8,979 "
        "controls covering space vehicle cybersecurity: NIST 800-53, CWE, "
        "ATT&CK, SPARTA, D3FEND, ISO 27001).\n\n"
        "You receive:\n"
        "1. The original question that failed validation\n"
        "2. The control_id it claimed to reference\n"
        "3. A structured gate_failures array showing exactly what went "
        "wrong\n\n"
        "CORRECTION RULES BY GATE TYPE:\n\n"
        "fabricated_id gate:\n"
        "- If closest match distance < 0.30: Replace the control ID with "
        "the closest match. Pick the match whose topic best fits the "
        "question.\n"
        "- If closest match distance > 0.70 or \"No close matches\": "
        'Return "UNFIXABLE"\n'
        "- Two close matches at same distance? Pick the one whose topic "
        "matches the question subject.\n\n"
        "technique_coherence gate:\n"
        "- The control ID is valid but covers the WRONG topic. The detail "
        "field names the correct control.\n"
        "- SWAP the control_id to the one mentioned in the detail that "
        "matches the question's actual topic.\n\n"
        "no_qras gate:\n"
        "- The control ID is valid but the question's TOPIC doesn't match "
        "what the control covers.\n"
        "- The detail field lists what the control actually covers.\n"
        "- KEEP the control_id, REWRITE the question topic to match the "
        "control's actual coverage.\n\n"
        "plausibility gate:\n"
        '- If the question is too vague: Return "UNFIXABLE"\n\n'
        "Multiple gate failures (fabricated_id + plausibility, or 2+ "
        'failures): Return "UNFIXABLE"\n\n'
        "GENERAL:\n"
        "- PRESERVE the original question structure and security domain "
        "language where possible\n"
        "- Use the gate_failures detail field — it contains the closest "
        "matches, distances, and actual QRA topics\n\n"
        "Return ONLY valid JSON:\n"
        '{"corrected_question": "the fixed question text"}\n\n'
        "Or if unfixable:\n"
        '{"corrected_question": "UNFIXABLE"}'
    )

    all_traces = [gate_trace]
    current_question = question

    for attempt in range(max_retries):
        # User prompt with structured gate trace
        user_prompt = (
            f"Original question: {current_question}\n"
            f"Control ID: {control_id}\n"
            f"Gate failures:\n{json.dumps(gate_trace, indent=2)}"
        )

        # scillm call — let connection errors propagate (fail loudly)
        resp = httpx.post(
            f"{SCILLM_BASE}/v1/chat/completions",
            headers={"Authorization": f"Bearer {SCILLM_KEY}"},
            json={
                "model": "text",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 256,
                "temperature": 0.2,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        corrected = parsed.get("corrected_question", current_question)

        if corrected == current_question:
            continue

        current_question = corrected
        result = evidence_validate_qra(current_question, control_id)
        result["evidence_correction_rounds"] = attempt + 1
        all_traces.append(result.get("gate_trace", []))

        if result["verdict"] == "satisfied":
            result["final_question"] = current_question
            result["original_question"] = question
            result["correction_rounds"] = attempt + 1
            result["gate_traces"] = all_traces
            return result

        gate_trace = result.get("gate_trace", [])

    # Exhausted retries — return last result
    result = evidence_validate_qra(current_question, control_id)
    result["evidence_correction_rounds"] = max_retries
    result["final_question"] = current_question
    result["original_question"] = question
    result["correction_rounds"] = max_retries
    result["gate_traces"] = all_traces
    return result


# ---------------------------------------------------------------------------
# CLI commands — registered into the main app via register_commands()
# ---------------------------------------------------------------------------

def register_commands(app: typer.Typer) -> None:
    """Register evidence gate CLI commands on the main typer app."""

    @app.command()
    def validate_qra(
        question: str = typer.Argument(..., help="QRA question to validate"),
        control_id: str = typer.Option("", help="Control ID (optional)"),
        correct: bool = typer.Option(False, help="Attempt correction"),
        max_retries: int = typer.Option(3, help="Max correction retries"),
        json_output: bool = typer.Option(False, "--json", help="JSON output"),
    ) -> None:
        """Validate a single QRA question via evidence gate chain."""
        result = evidence_validate_qra(question, control_id)
        if correct and result["verdict"] != "satisfied":
            result = evidence_correct_qra(
                question, control_id, result["gate_trace"], max_retries,
            )
        if json_output:
            typer.echo(json.dumps(result, indent=2, default=str))
        else:
            v = result["verdict"]
            g = result.get("evidence_grade", "?")
            s = result.get("evidence_score", 0)
            ms = result.get("elapsed_ms", 0)
            typer.echo(f"Verdict: {v}  Grade: {g}  Score: {s:.2f}  ({ms}ms)")
            if result.get("reason"):
                typer.echo(f"Reason: {result['reason']}")

    @app.command()
    def validate_batch(
        input_file: Path = typer.Argument(
            ..., help="JSONL file with {question, control_id} per line",
        ),
        workers: int = typer.Option(15, help="Parallel workers"),
        correct: bool = typer.Option(False, help="Attempt correction"),
        max_retries: int = typer.Option(3, help="Max retries"),
        json_stream: bool = typer.Option(
            False, "--json-stream", help="NDJSON streaming",
        ),
    ) -> None:
        """Batch-validate QRA questions via evidence gate chain."""
        if not input_file.exists():
            typer.echo(f"Error: {input_file} not found", err=True)
            raise typer.Exit(1)

        questions = []
        for line in input_file.read_text().strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                questions.append(json.loads(line))
            except json.JSONDecodeError:
                questions.append({"question": line, "control_id": ""})

        if not questions:
            typer.echo("No questions found", err=True)
            raise typer.Exit(1)

        typer.echo(f"Validating {len(questions)} QRAs with {workers} workers...")
        t0 = time.time()
        stats = {
            "satisfied": 0, "not_satisfied": 0,
            "inconclusive": 0, "error": 0,
        }

        def _process(q: dict) -> dict:
            r = evidence_validate_qra(
                q["question"], q.get("control_id", ""),
            )
            if correct and r["verdict"] != "satisfied":
                r = evidence_correct_qra(
                    q["question"], q.get("control_id", ""),
                    r["gate_trace"], max_retries,
                )
            r["input_question"] = q["question"]
            return r

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_process, q): q for q in questions}
            for i, fut in enumerate(as_completed(futs), 1):
                r = fut.result()
                v = r.get("verdict", "error")
                stats[v if v in stats else "error"] += 1
                if json_stream:
                    typer.echo(json.dumps(r, default=str))
                elif i % 10 == 0 or i == len(questions):
                    typer.echo(f"  Progress: {i}/{len(questions)} — {stats}")

        elapsed = round(time.time() - t0, 1)
        typer.echo(
            f"\nBatch complete: {len(questions)} QRAs in {elapsed}s — {stats}",
        )

    @app.command()
    def backfill_evidence(
        limit: int = typer.Option(0, help="Max QRAs (0=all)"),
        workers: int = typer.Option(15, help="Parallel workers"),
        batch_size: int = typer.Option(10000, help="Batch size per fetch"),
        skip_validated: bool = typer.Option(True, help="Skip already validated"),
        json_stream: bool = typer.Option(
            False, "--json-stream", help="NDJSON streaming",
        ),
    ) -> None:
        """Backfill evidence metadata for existing QRAs (no correction).

        Fetches batches of unvalidated QRAs and processes them. Since stamped
        QRAs get evidence_validated_at set, each subsequent fetch naturally
        returns the next batch. Loops until all are done or limit is reached.
        """
        t0 = time.time()
        total_processed = 0
        stats = {
            "satisfied": 0, "not_satisfied": 0,
            "inconclusive": 0, "error": 0,
        }

        def _validate_and_stamp(qra: dict) -> str:
            qra_key = qra.get("_key", "?")
            qra_id = qra.get("qra_id", qra_key)
            try:
                result = evidence_validate_qra(
                    qra["question"], qra.get("control_id", ""),
                    deterministic_only=True,  # Skip plausibility LLM for backfill
                )
            except httpx.ConnectError as e:
                raise RuntimeError(
                    f"QRA {qra_id}: daemon connection failed "
                    f"(is embry-memory running?): {e}"
                ) from e
            except httpx.TimeoutException as e:
                raise RuntimeError(
                    f"QRA {qra_id}: daemon timeout after 30s "
                    f"(recall or entity extraction too slow): {e}"
                ) from e
            except Exception as e:
                raise RuntimeError(
                    f"QRA {qra_id}: validation failed at "
                    f"{type(e).__name__}: {e}"
                ) from e

            patch = {
                f: result[f] for f in _EVIDENCE_FIELDS if f in result
            }
            patch["evidence_correction_rounds"] = 0
            stamp_resp = _thread_memory_service().post(
                "/sparta/qra/stamp-evidence",
                json={"key": qra_key, "patch": patch},
            )
            if stamp_resp.status_code != 200:
                raise RuntimeError(
                    f"QRA {qra_id}: stamp-evidence returned "
                    f"{stamp_resp.status_code}: {stamp_resp.text[:200]}"
                )
            if json_stream:
                typer.echo(json.dumps({
                    "qra_id": qra_id,
                    "verdict": result["evidence_verdict"],
                }, default=str))
            return result["evidence_verdict"]

        batch_num = 0
        while True:
            batch_num += 1
            # Determine how many to fetch this batch
            if limit > 0:
                remaining = limit - total_processed
                if remaining <= 0:
                    break
                fetch_size = min(batch_size, remaining)
            else:
                fetch_size = batch_size

            typer.echo(
                f"\n--- Batch {batch_num}: fetching up to {fetch_size} "
                f"unvalidated QRAs..."
            )
            svc = _thread_memory_service()
            resp = svc.post(
                "/sparta/qra/unvalidated",
                params={"limit": fetch_size},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"/sparta/qra/unvalidated returned {resp.status_code}: "
                    f"{resp.text}"
                )

            qras = resp.json().get("items", [])
            if not qras:
                typer.echo("No more QRAs need evidence validation.")
                break

            typer.echo(
                f"  Processing {len(qras)} QRAs with {workers} workers..."
            )

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(_validate_and_stamp, q): q for q in qras}
                for i, fut in enumerate(as_completed(futs), 1):
                    try:
                        v = fut.result()
                    except RuntimeError as e:
                        v = "error"
                        typer.echo(f"  ERROR: {e}", err=True)
                    except Exception as e:
                        v = "error"
                        typer.echo(
                            f"  UNEXPECTED {type(e).__name__}: {e}",
                            err=True,
                        )
                    stats[v if v in stats else "error"] += 1
                    total_processed += 1
                    if i % 50 == 0 or i == len(qras):
                        elapsed = time.time() - t0
                        rate = total_processed / max(elapsed, 1)
                        typer.echo(
                            f"  Progress: {total_processed} total "
                            f"({rate:.1f}/s) — {stats}",
                        )

        elapsed = round(time.time() - t0, 1)
        typer.echo(
            f"\nBackfill complete: {total_processed} QRAs in {elapsed}s "
            f"— {stats}",
        )
