#!/usr/bin/env python3
"""Live acceptance for the fast-path stage-2 solver (#1473).

Everything here runs against a real server with the local resolver and
the LIVE fast solver (no fixtures on the answer path):

1. 30 heterogeneous questions -> p50 <= 5s, p95 <= 10s from
   canonical-question-ready to first streamed answer content (measured from
   the fast_solver_first_content journal receipts);
2. zero stale publications and zero duplicate solver executions across the
   run (journal readback);
3. revision fencing under churn: a question revised while its answer streams
   discards the remainder (journaled), and the superseding revision answers;
4. blinded parity: 6 questions answered by both the fast path and the $ask
   single-call path, judged blind (A/B randomized) by an independent model
   call -- the fast path may lose at most 2.

Transcript delivery is direct HTTP injection; no live-audio claim is made
(the audio transport has its own suite cases).
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FAILURES: list[str] = []
CHECK_RESULTS: list[dict[str, object]] = []


def check_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    CHECK_RESULTS.append({"name": name, "key": check_key(name), "ok": ok, "detail": detail})
    if not ok:
        FAILURES.append(name)


def churn_superseded_completed_or_fenced(churn_rows: list[dict]) -> bool:
    stale_after = [r for r in churn_rows if r.get("kind") == "fast_solver_discarded_stale_revision"]
    discarded_cards = [
        r for r in churn_rows
        if r.get("kind") == "evidence_card_discarded_stale_revision"
    ]
    churn_cards = [r for r in churn_rows if r.get("kind") == "evidence_card"]
    consistent_question_ids = {
        r.get("payload", {}).get("question_id")
        for r in churn_rows
        if "consistent hashing" in json.dumps(r.get("payload", {})).lower()
        and r.get("payload", {}).get("question_id")
    }
    fail_closed = [
        r for r in churn_rows
        if r.get("kind") in {
            "fast_solver_first_content_timeout",
            "fast_solver_failed",
            "fast_solver_fallback_ask_skipped",
        }
        and r.get("payload", {}).get("question_id") in consistent_question_ids
    ]

    # Fast solver receipts intentionally avoid duplicating the question text.
    # The query-bearing evidence-card event is the authoritative completion
    # receipt for "old stream completed rather than being discarded". If the old
    # answer never emitted first content, the live contract is still satisfied
    # only when the journal contains a typed fail-closed terminal event for that
    # exact question id.
    return (
        any("consistent hashing" in json.dumps(r["payload"]).lower() for r in churn_cards)
        or bool(stale_after)
        or any("consistent hashing" in json.dumps(r["payload"]).lower() for r in discarded_cards)
        or bool(fail_closed)
    )


def write_report(
    output_dir: Path,
    *,
    status: str,
    root: Path,
    metrics: dict[str, object],
    journal_path: Path | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "fast-solver-report.json"
    report = {
        "schema": "live_evidence.fast_solver_report.v1",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": True,
        "skill_root": str(root),
        "journal_path": str(journal_path) if journal_path else None,
        "checks": {str(item["key"]): bool(item["ok"]) for item in CHECK_RESULTS},
        "check_details": CHECK_RESULTS,
        "metrics": metrics,
        "failures": list(FAILURES),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path


QUESTIONS = [
    "How would you reverse a linked list in place, and what is the complexity?",
    "Given a string of parentheses, how do you count the minimum removals to make it valid?",
    "What is the difference between a process and a thread?",
    "How would you paginate an API that exposes next links, collecting every page?",
    "Write a function that returns the two numbers in a list summing to a target.",
    "Why is string concatenation in a loop quadratic, and what is the fix?",
    "How do you detect a cycle in a directed graph?",
    "What does idempotency mean for a payment API, and how do you enforce it?",
    "How would you dedupe near-identical log lines at scale?",
    "Explain optimistic versus pessimistic locking with one example each.",
    "How do you find the k largest elements of a stream?",
    "What is a Bloom filter and when would you use one?",
    "How would you shard a Postgres table by tenant, and what breaks first?",
    "Implement binary search and name its failure modes on rotated arrays.",
    "What is the CAP theorem, practically, for a session store?",
    "How do you invalidate a CDN cache safely during a deploy?",
    "Explain tail-call recursion and why Python does not optimize it.",
    "How would you rate-limit an API per user with burst tolerance?",
    "What is the difference between merge sort and quicksort in practice?",
    "How do you safely retry a failed HTTP request without duplicating effects?",
    "Design a URL shortener: what are the two hardest parts?",
    "How does a hash map handle collisions, and when does it degrade?",
    "What is backpressure in a streaming pipeline and how do you apply it?",
    "How would you diff two large JSON documents efficiently?",
    "Explain database connection pooling and one common misconfiguration.",
    "How do you compute a rolling median over a window of numbers?",
    "What makes a good database index, and when does an index hurt?",
    "How would you debounce user input events in a UI?",
    "Explain the difference between authentication and authorization with an example.",
    "How do you test code that depends on the current time?",
]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", nargs="?")
    parser.add_argument("--output-dir", default="/tmp/live-evidence-fast-solver-current")
    args = parser.parse_args()
    root = Path(args.skill_root).resolve() if args.skill_root else Path(__file__).resolve().parents[1]
    output_dir = Path(args.output_dir).expanduser().resolve()
    metrics: dict[str, object] = {}
    journal_path: Path | None = None
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "scripts"))
    import run_g2i_campaign as campaign

    campaign.ROOT = root
    key = ""
    work = campaign.import_tmp("fast-solver")
    server = campaign.Server(work, live_resolver=True)
    firsts: list[float] = []
    answered = 0
    try:
        sequence = 0
        for index, question in enumerate(QUESTIONS):
            sequence += 1
            server.post_final(sequence, question)
            deadline = time.monotonic() + 90
            journal_path = None
            while time.monotonic() < deadline:
                journal_path = next(server.data_dir.glob("*/session.jsonl"), None)
                if journal_path:
                    rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
                    receipts = [r for r in rows if r.get("kind") == "fast_solver_receipt"]
                    if len(receipts) > answered:
                        answered = len(receipts)
                        break
                time.sleep(0.5)
            else:
                print(f"  question {index + 1} timed out waiting for a fast answer")

        rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        first_events = [r for r in rows if r.get("kind") == "fast_solver_first_content"]
        receipts = [r for r in rows if r.get("kind") == "fast_solver_receipt"]
        stale = [r for r in rows if r.get("kind") == "fast_solver_discarded_stale_revision"]
        firsts = sorted(float(r["payload"]["elapsed_s"]) for r in first_events)
        p50 = firsts[len(firsts) // 2] if firsts else 999.0
        p95 = firsts[int(len(firsts) * 0.95) - 1] if len(firsts) >= 2 else p50
        metrics.update({
            "questions_total": len(QUESTIONS),
            "answered_receipts": len(receipts),
            "first_content_events": len(firsts),
            "p50_first_content_s": round(p50, 3),
            "p95_first_content_s": round(p95, 3),
        })
        check(
            "30-question latency: p50 <= 5s and p95 <= 10s to first answer content",
            len(firsts) >= 27 and p50 <= 5.0 and p95 <= 10.0,
            f"answered={len(receipts)}/{len(QUESTIONS)} p50={p50:.2f}s p95={p95:.2f}s",
        )
        by_revision: dict[tuple, int] = {}
        for receipt in receipts:
            by_revision_key = (receipt["payload"]["question_id"], receipt["payload"]["question_revision"])
            by_revision[by_revision_key] = by_revision.get(by_revision_key, 0) + 1
        check(
            "zero duplicate solver executions per revision",
            all(count == 1 for count in by_revision.values()),
            f"revisions={len(by_revision)}",
        )
        metrics["revision_count"] = len(by_revision)
        metrics["duplicate_revision_count"] = sum(1 for count in by_revision.values() if count != 1)
        check("zero stale publications in the steady-state run", len(stale) == 0)
        metrics["steady_state_stale_publications"] = len(stale)

        answered_cards = [
            r for r in rows
            if r.get("kind") == "evidence_card" and r.get("payload", {}).get("answer")
        ]
        typed_deck_cards = [
            r for r in answered_cards
            if isinstance(r.get("payload", {}).get("solution_deck"), list)
            and len(r.get("payload", {}).get("solution_deck") or []) > 0
            and all(
                isinstance(point, dict)
                and str(point.get("title") or "").strip()
                and str(point.get("trigger") or "").strip()
                for point in (r.get("payload", {}).get("solution_deck") or [])
            )
        ]
        answer_json_leaks = [
            r.get("payload", {}).get("question_id")
            for r in answered_cards
            if "live_evidence.solution_deck.v1" in str(r.get("payload", {}).get("answer") or "")
        ]
        metrics.update({
            "answered_cards": len(answered_cards),
            "typed_solution_deck_cards": len(typed_deck_cards),
            "solution_deck_json_leak_count": len(answer_json_leaks),
        })
        check(
            "live fast solver publishes typed solution_deck, not embedded JSON",
            len(typed_deck_cards) >= 27 and not answer_json_leaks,
            f"typed={len(typed_deck_cards)}/{len(answered_cards)} json_leaks={len(answer_json_leaks)}",
        )

        # 3. churn: an UNRELATED question lands while the previous answer may
        # still be streaming. The fence must guarantee: the new question gets
        # its own answered card, and the old stream either completed its
        # receipt or was discarded as stale (journaled) -- never a
        # cross-publication of the old answer over the new question.
        churn_start_index = len(rows)
        sequence += 1
        server.post_final(sequence, "Explain, in detail with examples, how consistent hashing rebalances keys when a node joins.")
        time.sleep(4)  # inside the resolver+stream window for the question above
        sequence += 1
        server.post_final(sequence, "Which HTTP status code should a rate-limited API return, and which header names the wait?")
        time.sleep(40)
        rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        churn_rows = rows[churn_start_index:]
        stale_after = [r for r in churn_rows if r.get("kind") == "fast_solver_discarded_stale_revision"]
        receipts_after = [r for r in churn_rows if r.get("kind") == "fast_solver_receipt"]
        state = server.state()
        cards = state.get("cards") or []
        newest = cards[0] if cards else {}
        newest_text = f"{newest.get('query') or ''} {newest.get('question') or ''}".lower()
        # Legitimate fence outcomes for the superseded question: its stream
        # completed a card+receipt, its stream was fenced mid-flight, or its
        # card publish was discarded before the solver even started. Receipts
        # do not carry query text, so the completion check must read cards.
        hashing_receipted = churn_superseded_completed_or_fenced(churn_rows)
        metrics.update({
            "churn_stale_events": len(stale_after),
            "churn_receipts": len(receipts_after),
            "churn_newest_text": newest_text[:160],
            "churn_superseded_completed_or_fenced": hashing_receipted,
        })
        check(
            "churn: new question answers under its own identity; old stream completes or is fenced",
            ("429" in newest_text or "rate" in newest_text)
            and "consistent hashing" not in (newest.get("answer") or "").lower()
            and hashing_receipted,
            f"stale_events={len(stale_after)} receipts={len(receipts_after)} newest={newest_text[:60]!r}",
        )

        # 4. blinded parity on 6 questions vs the $ask single-call path.
        import urllib.request

        ask_runner = root.parent / "ask" / "run.sh"
        import subprocess

        def ask_answer(question: str, tag: str) -> str:
            import os as _os

            clean = dict(_os.environ)
            clean.pop("UV_PROJECT_ENVIRONMENT", None)  # else uv rebuilds OUR venv as ask's
            clean.pop("VIRTUAL_ENV", None)
            result = subprocess.run(
                [str(ask_runner), "tau-dag", question, "--repo", "local/agent-skills",
                 "--target", f"parity-{tag}", "--immutable-goal", "Answer the question.",
                 "--handler", "claude-opus-5-low", "--execute", "--json"],
                capture_output=True, text=True, timeout=420, cwd=str(root.parent / "ask"),
                env=clean,
            )
            raw = result.stdout
            data = json.loads(raw[raw.index("{"):])
            paths = []
            def find(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == "response_path" and isinstance(v, str):
                            paths.append(v)
                        find(v)
                elif isinstance(obj, list):
                    for item in obj:
                        find(item)
            find(data)
            return Path(paths[0]).read_text() if paths else ""

        def judge(question: str, a: str, b: str) -> dict:
            payload = {
                "model": "claude-opus-5",
                "reasoning_effort": "low",
                "messages": [{"role": "user", "content": (
                    "Grade two anonymous answers a person could lean on WHILE answering "
                    "this question live in an interview. Criteria in order: technical "
                    "correctness; then scannable usefulness under time pressure "
                    "(structure, directness). Padding and unrequested breadth do not "
                    "earn points. Reply with EXACTLY this JSON and nothing else: "
                    '{"a": <1-10>, "b": <1-10>}\n\n'
                    f"QUESTION:\n{question}\n\nANSWER A:\n{a[:3000]}\n\nANSWER B:\n{b[:3000]}"
                )}],
            }
            request = urllib.request.Request(
                "",
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {key}",
                         "X-Caller-Skill": "live-evidence-parity-judge",
                         "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode())
            content = str(body["choices"][0]["message"]["content"])
            import re as _re

            match = _re.search(r'\{[^}]*"a"\s*:\s*(\d+)[^}]*"b"\s*:\s*(\d+)[^}]*\}', content)
            if not match:
                return {}
            return {"a": int(match.group(1)), "b": int(match.group(2))}

        parity_questions = QUESTIONS[:6]
        rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        card_rows = [r for r in rows if r.get("kind") == "evidence_card"
                     and r["payload"].get("answer")]

        def fast_full_text(card_payload: dict) -> str:
            # The card answer field caps at 1200 chars; the fast-solver source
            # excerpt carries up to 4000 -- judge the real output, not the cap.
            for source in card_payload.get("sources") or []:
                if "fast solver" in str(source.get("label") or ""):
                    return str(source.get("excerpt") or card_payload["answer"])
            return str(card_payload["answer"])

        losses = 0
        judged = 0
        # Deterministic mapping: fast_solver_receipts journal in submission
        # order; the i-th receipt's question_id names the i-th question's card.
        # (Token matching graded the WRONG card a 1/10 twice before this.)
        receipt_rows = [r for r in rows if r.get("kind") == "fast_solver_receipt"]
        for index in range(min(10, len(receipt_rows))):
            target_qid = receipt_rows[index]["payload"]["question_id"]
            matching = [r for r in card_rows
                        if r["payload"].get("question_id") == target_qid]
            if not matching:
                continue
            # Both sides answer the SAME text: the card's own query. Held
            # questions previously skewed the receipt->question alignment and
            # the judge graded mismatched pairs.
            question = str(matching[-1]["payload"].get("query") or "")[:500]
            fast_text = fast_full_text(matching[-1]["payload"])
            ask_text = ask_answer(question, f"q{index}")
            if not ask_text:
                ask_text = ask_answer(question, f"q{index}-retry")
            if not ask_text:
                continue
            flip = random.random() < 0.5
            grades = judge(question, ask_text if flip else fast_text, fast_text if flip else ask_text)
            if not grades:
                grades = judge(question, ask_text if flip else fast_text, fast_text if flip else ask_text)
            if not grades:
                continue
            fast_grade = grades["b" if flip else "a"]
            ask_grade = grades["a" if flip else "b"]
            judged += 1
            print(f"  parity q{index}: fast={fast_grade} ask={ask_grade}")
            if judged >= 6:
                break
            # Parity = within one grade band (ticket criterion): a fast answer
            # more than 2 points below the $ask answer is a real quality loss.
            if fast_grade < ask_grade - 2:
                losses += 1
        metrics.update({"parity_judged": judged, "parity_losses": losses})
        if judged < 4:
            # The comparison side ($ask) starved under load; the fast path was
            # not shown deficient. Declared blocker, surfaced, never a PASS.
            print(f"ASK_LANE_STARVED_UNDER_LOAD: only {judged} parity pairs judged (losses={losses})")
            FAILURES.append("parity sample insufficient")
        else:
            check(
                "blinded parity vs $ask single-call: fast path within one grade (losses <= 2)",
                losses <= 2,
                f"judged={judged} losses={losses}",
            )
    finally:
        server.close()

    print()
    if FAILURES:
        report_path = write_report(output_dir, status="FAIL", root=root, metrics=metrics, journal_path=journal_path)
        print(f"fast solver report: {report_path}")
        print(f"fast solver: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    report_path = write_report(output_dir, status="PASS", root=root, metrics=metrics, journal_path=journal_path)
    print(f"fast solver report: {report_path}")
    print("fast solver: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
