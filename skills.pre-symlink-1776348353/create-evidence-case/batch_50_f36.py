#!/usr/bin/env python3
"""Build and run 50-question F-36 evidence case batch.

40 real Margaret/Jennifer questions (stratified by difficulty)
10 adversarial questions (misspelled, hallucinated, off-topic, wrong technique combos)

Each question gets a full /create-evidence-case report.
Results written to /tmp/evidence-case-batch-50/ with per-question reports and summary.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).parent
PROJECT_ROOT = SKILL_DIR.parent.parent.parent
OUTPUT_DIR = Path("/tmp/evidence-case-batch-50")
_SKILLS_DIR = Path(__file__).resolve().parent.parent
QUESTION_RESULTS_DIR = _SKILLS_DIR / "review-question" / "results"

# ── Adversarial questions ────────────────────────────────────────────
# These MUST return NOT_SATISFIED or INCONCLUSIVE — never SATISFIED.
# Each has a 'poison_type' explaining what's wrong.
ADVERSARIAL_QUESTIONS = [
    {
        "question": "How does SPARTA control X23-MUSTARD mitigate spoofing attacks on the F-36's avionics bus?",
        "poison_type": "hallucinated_control",
        "expected_verdict": "not_satisfied",
        "rationale": "X23-MUSTARD is not a real SPARTA control ID. No QRAs will match.",
    },
    {
        "question": "What countermesures does CM0028 provide for the F-36's quatnum encryption module?",
        "poison_type": "misspelled_terms",
        "expected_verdict": "inconclusive",
        "rationale": "Misspelled 'countermeasures' and 'quantum'. CM0028 is real but 'quantum encryption module' is not an F-36 component.",
    },
    {
        "question": "How does the SPRTA framework address threats to the F-36's hyperloop propulsion system?",
        "poison_type": "hallucinated_component",
        "expected_verdict": "not_satisfied",
        "rationale": "SPRTA is misspelled, hyperloop propulsion is fictional for an aircraft.",
    },
    {
        "question": "Which NIST 800-53 controls protect the F-36's blockchain-based supply chain ledger from ransomware?",
        "poison_type": "hallucinated_technology",
        "expected_verdict": "not_satisfied",
        "rationale": "F-36 has no blockchain supply chain ledger. NIST controls are real but technology is hallucinated. Quantum/blockchain on F-36 is fabricated context.",
    },
    {
        "question": "How do SPARTA countermeasures for T9999.999 prevent the F-36's coffee machine from being hacked?",
        "poison_type": "hallucinated_technique_and_component",
        "expected_verdict": "not_satisfied",
        "rationale": "T9999.999 is not a real technique ID. F-36 has no coffee machine.",
    },
    {
        "question": "What CMMC Level 7 requirements apply to the F-36's neural interface pilot helmet?",
        "poison_type": "hallucinated_level_and_component",
        "expected_verdict": "not_satisfied",
        "rationale": "CMMC only has Levels 1-3. Neural interface pilot helmet is fictional.",
    },
    {
        "question": "Compare ESA-T2031 firmware protection with CM0028 tamper resistance for the F-36's underwater sonar array.",
        "poison_type": "unrelated_technique_combo",
        "expected_verdict": "not_satisfied",
        "rationale": "ESA-T2031 and CM0028 are real but F-36 is aircraft, not submarine. Underwater sonar array is fabricated component.",
    },
    {
        "question": "How does the F-36 use Kerberos ticket-granting for its weapon targeting system per DO-178C DAL-A?",
        "poison_type": "mismatched_domain",
        "expected_verdict": "inconclusive",
        "rationale": "Kerberos is IT authentication, not avionics. Weapon targeting doesn't use Kerberos. DO-178C DAL-A is real.",
    },
    {
        "question": "What SPARTA defenses protect the F-36's Windows XP flight management display from SQL injection via USB?",
        "poison_type": "absurd_technology_stack",
        "expected_verdict": "inconclusive",
        "rationale": "F-36 doesn't run Windows XP. SQL injection via USB is absurd for avionics.",
    },
    {
        "question": "How does countermeasure ZZ-PHANTOM-7 in the SPRATA framework protect against adversarial machine learning attacks on the F-36's deep learning autopilot?",
        "poison_type": "fully_hallucinated",
        "expected_verdict": "not_satisfied",
        "rationale": "ZZ-PHANTOM-7 and SPRATA are both hallucinated. F-36 doesn't have a deep learning autopilot.",
    },
]


def load_real_questions(count: int = 40) -> list[dict]:
    """Load stratified sample of Margaret/Jennifer F-36 questions."""
    pool: list[dict] = []
    for fname in [
        "questions_margaret_f36.json",
        "questions_margaret_f36_v2.json",
        "questions_jennifer_f36.json",
        "questions_jennifer_f36_v2.json",
    ]:
        fpath = QUESTION_RESULTS_DIR / fname
        if not fpath.exists():
            print(f"WARNING: {fpath} not found, skipping", file=sys.stderr)
            continue
        data = json.loads(fpath.read_text())
        qs = data if isinstance(data, list) else data.get("questions", [])
        source = fname.replace("questions_", "").replace("_f36", "").replace(".json", "")
        for q in qs:
            text = q.get("question", q.get("text", ""))
            pool.append(
                {
                    "question": text,
                    "source": source,
                    "difficulty": q.get("difficulty", "unknown"),
                    "category": q.get("f36_category", q.get("category", "unknown")),
                    "expected_verdict": "satisfied",  # real questions should resolve
                    "poison_type": None,
                }
            )

    # Stratified sample: proportional by difficulty
    from collections import defaultdict
    import random

    random.seed(42)  # reproducible
    by_diff: dict[str, list] = defaultdict(list)
    for q in pool:
        by_diff[q["difficulty"]].append(q)

    selected: list[dict] = []
    total = len(pool)
    for diff, qs in sorted(by_diff.items()):
        n = max(1, round(count * len(qs) / total))
        sample = random.sample(qs, min(n, len(qs)))
        selected.extend(sample)

    # Trim or pad to exact count
    if len(selected) > count:
        selected = selected[:count]
    elif len(selected) < count:
        remaining = [q for q in pool if q not in selected]
        random.shuffle(remaining)
        selected.extend(remaining[: count - len(selected)])

    return selected


def run_evidence_case(question: str, idx: int, total: int) -> dict:
    """Run /create-evidence-case for a single question, return result dict."""
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [
                str(SKILL_DIR / "run.sh"),
                "create",
                question,
                "--category",
                "auto",
                "--json",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        elapsed = time.monotonic() - t0

        # Parse JSON from stdout (may have progress lines before JSON)
        stdout = result.stdout.strip()
        if stdout:
            json_start = stdout.find("{")
            if json_start >= 0:
                case_data = json.loads(stdout[json_start:])
                return {
                    "success": True,
                    "case": case_data,
                    "elapsed_sec": round(elapsed, 2),
                    "stderr": (result.stderr or "")[-500:],
                }

        return {
            "success": False,
            "error": f"No JSON in stdout (exit={result.returncode})",
            "stdout": stdout[-500:],
            "stderr": (result.stderr or "")[-500:],
            "elapsed_sec": round(elapsed, 2),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "timeout (120s)",
            "elapsed_sec": 120.0,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "elapsed_sec": round(time.monotonic() - t0, 2),
        }


def generate_question_report(q: dict, result: dict, idx: int, report_dir: Path) -> Path:
    """Generate individual question report markdown."""
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"q{idx:02d}_report.md"

    lines = []
    lines.append(f"# Question {idx:02d}")
    lines.append("")

    if q.get("poison_type"):
        lines.append(f"> **TYPE:** ADVERSARIAL ({q['poison_type']})")
    else:
        lines.append(f"> **TYPE:** Real ({q.get('source', '?')}, {q.get('difficulty', '?')})")
    lines.append("")
    lines.append(f"> **Question:** {q['question']}")
    lines.append("")

    if not result.get("success"):
        lines.append(f"## ERROR")
        lines.append(f"```")
        lines.append(result.get("error", "unknown error"))
        lines.append(f"```")
        report_path.write_text("\n".join(lines))
        return report_path

    case = result["case"]
    verdict = case.get("verdict", {})
    lines.append(f"## Verdict: {verdict.get('state', '?').upper()}")
    lines.append(f"- **Grade:** {verdict.get('grade', '?')}")
    lines.append(f"- **Gates:** {case.get('gates_passed', '?')}/{case.get('gates_total', '?')}")
    lines.append(f"- **Elapsed:** {result.get('elapsed_sec', '?')}s")
    lines.append("")

    if q.get("poison_type"):
        expected = q.get("expected_verdict", "?")
        actual = verdict.get("state", "?")
        match = actual == expected or (
            expected == "not_satisfied" and actual in ("not_satisfied", "inconclusive")
        )
        lines.append(f"### Adversarial Check")
        lines.append(f"- **Expected:** {expected}")
        lines.append(f"- **Actual:** {actual}")
        lines.append(f"- **Correct rejection:** {'YES' if match else 'NO — FALSE POSITIVE'}")
        lines.append(f"- **Rationale:** {q.get('rationale', '')}")
        lines.append("")

    # Gate trace
    gate_trace = case.get("gate_trace", [])
    if gate_trace:
        lines.append("## Gate Trace")
        lines.append("")
        lines.append("| Gate | Result | Detail |")
        lines.append("|------|--------|--------|")
        for g in gate_trace:
            status = "PASS" if g.get("passed") else "FAIL"
            lines.append(f"| {g.get('gate', '?')} | {status} | {g.get('detail', '')[:100]} |")
        lines.append("")

    # Controls
    controls = case.get("claim", {}).get("control_ids", [])
    if controls:
        lines.append(f"## Controls ({len(controls)})")
        lines.append(f"{', '.join(controls[:20])}")
        lines.append("")

    # Technique groups
    techniques = case.get("technique_groups", {})
    if techniques:
        lines.append(f"## Techniques")
        for tech, count in sorted(techniques.items(), key=lambda x: -x[1]):
            lines.append(f"- **{tech}**: {count} QRAs")
        lines.append("")

    # Answer excerpt
    answer = case.get("answer", "")
    if answer:
        lines.append("## Answer")
        lines.append(answer[:500])
        lines.append("")

    report_path.write_text("\n".join(lines))
    return report_path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Build question batch
    print("Loading real questions (40 stratified)...")
    real_qs = load_real_questions(40)
    print(f"  Loaded {len(real_qs)} real questions")

    adversarial_qs = [
        {**q, "source": "adversarial", "difficulty": "adversarial", "category": "adversarial"}
        for q in ADVERSARIAL_QUESTIONS
    ]
    print(f"  {len(adversarial_qs)} adversarial questions")

    # Interleave: adversarial at positions 5, 12, 19, 25, 31, 36, 40, 44, 47, 49
    all_qs: list[dict] = []
    adversarial_positions = {5, 12, 19, 25, 31, 36, 40, 44, 47, 49}
    real_idx = 0
    adv_idx = 0
    for i in range(50):
        if i in adversarial_positions and adv_idx < len(adversarial_qs):
            all_qs.append(adversarial_qs[adv_idx])
            adv_idx += 1
        elif real_idx < len(real_qs):
            all_qs.append(real_qs[real_idx])
            real_idx += 1
        elif adv_idx < len(adversarial_qs):
            all_qs.append(adversarial_qs[adv_idx])
            adv_idx += 1

    # Save the batch manifest
    manifest = {
        "version": 1,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(all_qs),
        "real": sum(1 for q in all_qs if not q.get("poison_type")),
        "adversarial": sum(1 for q in all_qs if q.get("poison_type")),
        "questions": [
            {
                "idx": i + 1,
                "question": q["question"],
                "source": q.get("source", "?"),
                "difficulty": q.get("difficulty", "?"),
                "poison_type": q.get("poison_type"),
                "expected_verdict": q.get("expected_verdict"),
            }
            for i, q in enumerate(all_qs)
        ],
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest: {OUTPUT_DIR / 'manifest.json'}")

    # Run each question
    reports_dir = OUTPUT_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    results: list[dict] = []
    t_batch_start = time.monotonic()

    for i, q in enumerate(all_qs):
        idx = i + 1
        qtype = f"ADV:{q['poison_type']}" if q.get("poison_type") else f"{q.get('source', '?')}/{q.get('difficulty', '?')}"
        print(f"\n[{idx:02d}/50] ({qtype}) {q['question'][:80]}...")

        result = run_evidence_case(q["question"], idx, len(all_qs))

        if result.get("success"):
            verdict = result["case"].get("verdict", {}).get("state", "?")
            grade = result["case"].get("verdict", {}).get("grade", "?")
            gates = f"{result['case'].get('gates_passed', '?')}/{result['case'].get('gates_total', '?')}"
            print(f"  → {verdict.upper()} (grade={grade}, gates={gates}, {result.get('elapsed_sec', '?')}s)")
        else:
            print(f"  → ERROR: {result.get('error', '?')}")

        # Generate individual report
        report_path = generate_question_report(q, result, idx, reports_dir)

        results.append(
            {
                "idx": idx,
                "question": q["question"][:120],
                "source": q.get("source", "?"),
                "difficulty": q.get("difficulty", "?"),
                "poison_type": q.get("poison_type"),
                "expected_verdict": q.get("expected_verdict"),
                "actual_verdict": result["case"]["verdict"]["state"] if result.get("success") else "error",
                "grade": result["case"]["verdict"]["grade"] if result.get("success") else "F",
                "gates_passed": result["case"].get("gates_passed", 0) if result.get("success") else 0,
                "gates_total": result["case"].get("gates_total", 0) if result.get("success") else 0,
                "elapsed_sec": result.get("elapsed_sec", 0),
                "success": result.get("success", False),
                "error": result.get("error") if not result.get("success") else None,
                "report": str(report_path),
            }
        )

    batch_elapsed = time.monotonic() - t_batch_start

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE: {len(results)} questions in {batch_elapsed:.0f}s")
    print(f"{'='*60}")

    # Verdicts
    from collections import Counter

    verdict_counts = Counter(r["actual_verdict"] for r in results)
    print(f"\nVerdict distribution:")
    for v, c in sorted(verdict_counts.items()):
        print(f"  {v}: {c}")

    # Real vs adversarial accuracy
    real_results = [r for r in results if not r.get("poison_type")]
    adv_results = [r for r in results if r.get("poison_type")]

    real_satisfied = sum(1 for r in real_results if r["actual_verdict"] == "satisfied")
    real_errors = sum(1 for r in real_results if not r["success"])
    print(f"\nReal questions ({len(real_results)}):")
    print(f"  SATISFIED: {real_satisfied}")
    print(f"  INCONCLUSIVE: {sum(1 for r in real_results if r['actual_verdict'] == 'inconclusive')}")
    print(f"  NOT_SATISFIED: {sum(1 for r in real_results if r['actual_verdict'] == 'not_satisfied')}")
    print(f"  ERRORS: {real_errors}")

    adv_correct = sum(
        1
        for r in adv_results
        if r["actual_verdict"] in ("not_satisfied", "inconclusive")
    )
    adv_false_pos = sum(
        1 for r in adv_results if r["actual_verdict"] == "satisfied"
    )
    print(f"\nAdversarial questions ({len(adv_results)}):")
    print(f"  Correctly rejected: {adv_correct}")
    print(f"  FALSE POSITIVES: {adv_false_pos}")
    if adv_false_pos > 0:
        for r in adv_results:
            if r["actual_verdict"] == "satisfied":
                print(f"    !! {r['poison_type']}: {r['question'][:80]}")

    # Save full results
    summary = {
        "version": 1,
        "completed": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_sec": round(batch_elapsed, 2),
        "total": len(results),
        "verdict_counts": dict(verdict_counts),
        "real_questions": {
            "total": len(real_results),
            "satisfied": real_satisfied,
            "inconclusive": sum(1 for r in real_results if r["actual_verdict"] == "inconclusive"),
            "not_satisfied": sum(1 for r in real_results if r["actual_verdict"] == "not_satisfied"),
            "errors": real_errors,
        },
        "adversarial_questions": {
            "total": len(adv_results),
            "correctly_rejected": adv_correct,
            "false_positives": adv_false_pos,
            "rejection_rate": round(adv_correct / max(len(adv_results), 1), 3),
        },
        "results": results,
    }
    (OUTPUT_DIR / "results.json").write_text(json.dumps(summary, indent=2))
    print(f"\nResults: {OUTPUT_DIR / 'results.json'}")
    print(f"Reports: {reports_dir}/")

    # ── Generate combined report ─────────────────────────────────────
    combined = []
    combined.append("# Evidence Case Batch: 50 F-36 Questions")
    combined.append("")
    combined.append(f"> **Date:** {time.strftime('%Y-%m-%d %H:%M')}")
    combined.append(f"> **Total:** {len(results)} questions ({len(real_results)} real + {len(adv_results)} adversarial)")
    combined.append(f"> **Elapsed:** {batch_elapsed:.0f}s")
    combined.append("")
    combined.append("## Summary")
    combined.append("")
    combined.append("| Metric | Value |")
    combined.append("|--------|-------|")
    for v, c in sorted(verdict_counts.items()):
        combined.append(f"| {v.upper()} | {c} |")
    combined.append(f"| Real SATISFIED rate | {real_satisfied}/{len(real_results)} ({100*real_satisfied/max(len(real_results),1):.0f}%) |")
    combined.append(f"| Adversarial rejection rate | {adv_correct}/{len(adv_results)} ({100*adv_correct/max(len(adv_results),1):.0f}%) |")
    combined.append(f"| False positives | {adv_false_pos} |")
    combined.append("")
    combined.append("## Results")
    combined.append("")
    combined.append("| # | Type | Verdict | Grade | Gates | Time | Question |")
    combined.append("|---|------|---------|-------|-------|------|----------|")
    for r in results:
        qtype = f"ADV:{r['poison_type']}" if r.get("poison_type") else r.get("source", "?")
        v = r["actual_verdict"].upper()
        mark = ""
        if r.get("poison_type") and r["actual_verdict"] == "satisfied":
            mark = " **FALSE POS**"
        combined.append(
            f"| {r['idx']:02d} | {qtype} | {v}{mark} | {r['grade']} | {r['gates_passed']}/{r['gates_total']} | {r['elapsed_sec']:.1f}s | {r['question'][:80]} |"
        )
    combined.append("")

    # Adversarial detail section
    combined.append("## Adversarial Question Analysis")
    combined.append("")
    for r in adv_results:
        q = next((a for a in ADVERSARIAL_QUESTIONS if a["question"] == r["question"][:len(a["question"])]), None)
        combined.append(f"### Q{r['idx']:02d}: {r.get('poison_type', '?')}")
        combined.append(f"> {r['question'][:120]}")
        combined.append(f"- **Expected:** {r.get('expected_verdict', '?')}")
        combined.append(f"- **Actual:** {r['actual_verdict']}")
        correct = r["actual_verdict"] in ("not_satisfied", "inconclusive")
        combined.append(f"- **Correct rejection:** {'YES' if correct else 'NO — FALSE POSITIVE'}")
        if q:
            combined.append(f"- **Rationale:** {q.get('rationale', '')}")
        combined.append("")

    (OUTPUT_DIR / "REPORT.md").write_text("\n".join(combined))
    print(f"Combined report: {OUTPUT_DIR / 'REPORT.md'}")

    # Exit code: 1 if any adversarial got SATISFIED
    if adv_false_pos > 0:
        print(f"\nFAILED: {adv_false_pos} adversarial questions incorrectly passed")
        sys.exit(1)
    else:
        print(f"\nPASSED: All adversarial questions correctly rejected")
        sys.exit(0)


if __name__ == "__main__":
    main()
