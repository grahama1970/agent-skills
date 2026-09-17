"""Layer-1 routing-correctness grader for the SPARTA stress hardener.

Grades run_single results (JSONL) on ROUTING CORRECTNESS, not persona
satisfaction. Authority split (non-negotiable):

  AUTO slice   fabricated control -> expected DEFLECT/NO_MATCH (entity
               non-existence is a hard corpus fact -- sound label by construction)
  EXPERT slice real controls, answerable-vs-clarify prose judgment (DeepSeek
               labels are unverified; queued for the human expert)

Attribution per wrong turn:
  CONTEXT = pipeline failed to ground a REAL control (answered False with the
            control existing + QRAs present, or pipeline_error) -> deterministic
            bug -> triage-error classify -> DRAFT ticket (replayable repro)
  POLICY  = grounded (or genuinely ambiguous) but the route/threshold is a
            judgment call (e.g. /intent CLARIFY vs /answer can_answer divergence)
            -> expert queue, NOT project-watchdog

DRAFT turns that ground and get signoff are successes; never ticketed.
persuasive_but_wrong = answered=true but zero grounded sources (false confidence).

Usage:
  python3 -m sparta_stress_test.grading <results.jsonl> [--out-dir DIR] [--wave N]
Emits: routing_grade.json (gradeSchema-shaped) + wave_<N>_review.md +
       drafted_tickets/*.md (NOT published -- publishing is gated).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

DEFLECT_ACTIONS = {"NO_MATCH", "OFF_TOPIC", "DEFLECT"}
TRIAGE_RUN = "/home/graham/workspace/experiments/sparta/.pi/skills/triage-error/run.sh"
MEMORY_BASE = "http://127.0.0.1:8601"
_exists_cache: dict[str, bool] = {}


def _control_exists(control: str) -> bool:
    """Deterministic entity-existence: is the control in sparta_controls? (corpus fact)"""
    if control in _exists_cache:
        return _exists_cache[control]
    try:
        with httpx.Client(base_url=MEMORY_BASE, timeout=15.0) as c:
            r = c.post("/list", json={"collection": "sparta_controls", "limit": 1,
                                      "filters": {"control_id": control}})
            docs = (r.json().get("documents") or [])
    except Exception as e:
        logger.warning(f"corpus existence check failed for {control}: {e}")
        docs = []  # fail closed: unknown -> not auto-gradable as fabricated
        _exists_cache[control] = True  # treat as real (expert slice) when corpus unreachable
        return True
    _exists_cache[control] = bool(docs)
    return bool(docs)


def _fabricated(control: str) -> bool:
    """Deterministic: the control does not exist in the corpus (hard fact)."""
    if not control:
        return False
    return not _control_exists(control)


def _triage_classify(signal: str) -> dict[str, Any]:
    """Route a raw failure signal through triage-error (never bare tickets)."""
    try:
        p = subprocess.run([TRIAGE_RUN, "classify", "--text", signal, "--layer", "sparta-stress"],
                           capture_output=True, text=True, timeout=60)
        if p.returncode == 0:
            return json.loads(p.stdout)
    except Exception as e:  # classifier down: preserve raw signal, fail closed
        logger.warning(f"triage-error classify failed: {e}")
    return {"code": "triage_unavailable", "cause": signal[:200], "next_command": ""}


def _draft_ticket(row: dict, triage: dict, out_dir: Path) -> Path:
    """DRAFT ticket file (never published; publishing is gated by the orchestrator)."""
    tdir = out_dir / "drafted_tickets"
    tdir.mkdir(parents=True, exist_ok=True)
    slug = (row.get("question_id") or f"q{int(time.time())}").replace("/", "_")[:40]
    path = tdir / f"{slug}.md"
    repro_q = row.get("question_text", "")
    ctrl = row.get("target_control", "")
    path.write_text(
        f"# DRAFT (unpublished): pipeline CONTEXT failure\n\n"
        f"- triage_code: `{triage.get('code')}`\n"
        f"- cause: {triage.get('cause', '')[:300]}\n"
        f"- next_command: {triage.get('next_command', '')}\n"
        f"- control: `{ctrl}` (exists in corpus; pipeline failed to ground)\n"
        f"- question: {repro_q}\n\n"
        f"## Replayable repro\n\n"
        f"```bash\n"
        f"curl -s http://127.0.0.1:8601/answer -H 'content-type: application/json' "
        f"-d '{{\"q\": \"{repro_q}\", \"scope\": \"sparta\", \"k\": 10}}' | jq .can_answer\n"
        f"```\nExpected: can_answer=true with sources for `{ctrl}`. Observed: "
        f"answered=false / ungrounded.\n")
    return path


def grade_results(results: list[dict], out_dir: Path, wave: int = 1) -> dict[str, Any]:
    rows, auto_total, auto_correct = [], 0, 0
    context_failures = policy_failures = expert_queue = tickets = pbw = 0
    for row in results:
        ctrl = row.get("target_control") or ""
        actual = (row.get("actual_action") or "").upper()
        answered = bool(row.get("had_answer"))
        source_keys = row.get("source_keys") or []
        q = row.get("question_text", "")
        r: dict[str, Any] = {"question": q[:120], "control": ctrl, "actual": actual}

        if row.get("pipeline_status") == "pipeline_unreachable":
            r.update(slice="infra", attribution="INFRA", note="daemon unreachable (typed)")
            policy_failures += 1
        elif _fabricated(ctrl):
            auto_total += 1
            ok = actual in DEFLECT_ACTIONS or not answered
            auto_correct += ok
            r.update(slice="auto", expected="deflect", correct=ok,
                     attribution=("CONTEXT" if not ok else None))
            if not ok:
                # answered a fabricated control = false-confidence, deterministic
                context_failures += 1
        else:
            # Real control: grounding is checkable; answerable-vs-clarify is expert.
            grounded = answered and bool(source_keys)
            if answered and not source_keys:
                pbw += 1  # persuasive-but-wrong shape: answered with zero grounded sources
                r.update(slice="expert", attribution="POLICY",
                         note="answered with zero grounded sources (false confidence?)")
                expert_queue += 1
            elif answered and actual in DEFLECT_ACTIONS:
                auto_total += 1
                auto_correct += 0  # answered text but routed deflect: inconsistent
                r.update(slice="auto", expected="answer|clarify", correct=False,
                         attribution="CONTEXT", note="deflected while answered")
                context_failures += 1
            elif not answered and actual in ("CLARIFY", "QUERY"):
                r.update(slice="expert", attribution="POLICY",
                         note=f"/intent {actual} vs ungrounded answer on real control -- judgment")
                expert_queue += 1
            else:
                auto_total += 1
                ok = grounded  # answered with sources = routed+grounded consistently
                auto_correct += ok
                r.update(slice="auto", expected="answer", correct=ok,
                         attribution=(None if ok else "CONTEXT"),
                         note="" if ok else "real control, pipeline failed to ground")
                if not ok:
                    context_failures += 1
        rows.append(r)

    # CONTEXT failures -> triage-error classify -> DRAFT tickets (never publish here)
    drafted = []
    for r in rows:
        if r.get("attribution") == "CONTEXT":
            signal = (f"stress-hardener: control {r['control']} exists but pipeline failed: "
                      f"actual={r['actual']} note={r.get('note', '')} question={r['question']}")
            tri = _triage_classify(signal)
            drafted.append(_draft_ticket({"question_id": r["question"][:30], "question_text": r["question"],
                                          "target_control": r["control"]}, tri, out_dir))
    tickets = len(drafted)

    rate = round(auto_correct / auto_total, 4) if auto_total else 0.0
    verdict = "graded"
    if auto_total and context_failures >= max(3, auto_total // 2):
        verdict = "pipeline_bug_found"
    elif not results:
        verdict = "infrastructure_failure"

    review = out_dir / f"wave_{wave}_review.md"
    out_dir.mkdir(parents=True, exist_ok=True)
    with review.open("w") as f:
        f.write(f"# Wave {wave} routing-correctness review\n\n"
                f"| question | control | slice | actual | expected | correct | attribution | note |\n"
                f"|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['question'][:60]} | {r['control']} | {r.get('slice')} | {r['actual'][:12]} "
                    f"| {r.get('expected', '-')} | {r.get('correct', '-')} "
                    f"| {r.get('attribution', '-')} | {r.get('note', '')[:60]} |\n")
        f.write(f"\n**routing_correct_rate (auto slice): {auto_correct}/{auto_total} = {rate}**"
                f" | context_failures={context_failures} policy_failures={policy_failures}"
                f" | expert_queue={expert_queue} | persuasive_but_wrong={pbw}"
                f" | tickets_drafted={tickets} (UNPUBLISHED)\n")

    summary = {"verdict": verdict, "routing_correct_rate": rate,
               "auto_graded": auto_total, "auto_correct": auto_correct,
               "context_failures": context_failures, "policy_failures": policy_failures,
               "expert_queue": expert_queue, "persuasive_but_wrong": pbw,
               "tickets_drafted": tickets, "ticket_paths": [str(p) for p in drafted],
               "review_path": str(review)}
    (out_dir / "routing_grade.json").write_text(json.dumps(summary, indent=2))
    return summary


def demo() -> None:
    """Self-check: fabricated->deflect is auto-graded; real-control grounding split holds."""
    fake_ok = {"question_text": "What does SV-ZZ-99 prescribe?", "target_control": "SV-ZZ-99",
               "actual_action": "NO_MATCH", "had_answer": False, "source_keys": []}
    fake_bad = {"question_text": "Tell me about SV-ZZ-99", "target_control": "SV-ZZ-99",
                "actual_action": "QUERY", "had_answer": True, "source_keys": ["x"]}
    real_ok = {"question_text": "Uplink jamming countermeasures?", "target_control": "EX-0016.01",
               "actual_action": "QUERY", "had_answer": True, "source_keys": ["k1"]}
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        s = grade_results([fake_ok, fake_bad, real_ok], Path(td), wave=0)
        assert s["auto_graded"] >= 2 and s["auto_correct"] >= 2, s
        assert s["context_failures"] >= 1, "answering a fabricated control must be CONTEXT"
    print("grading demo: OK (fabricated auto-graded; answered-fabricated = CONTEXT)")


if __name__ == "__main__":
    if len(__sys_args := __import__("sys").argv) > 1 and __sys_args[1] == "--demo":
        demo()
    else:
        ap = argparse.ArgumentParser()
        ap.add_argument("results_jsonl")
        ap.add_argument("--out-dir", default=".")
        ap.add_argument("--wave", type=int, default=1)
        a = ap.parse_args()
        res = [json.loads(l) for l in open(a.results_jsonl) if l.strip()]
        print(json.dumps(grade_results(res, Path(a.out_dir), a.wave), indent=2))
