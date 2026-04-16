#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UV="${UV:-uv}"

# ---------------------------------------------------------------------------
# Gold-set: 20 compliance QRA test cases
# Each entry: QUESTION | EXPECTED_ANSWER_SUBSTRING
# ---------------------------------------------------------------------------
read -r -d '' GOLD_SET_PY << 'PYEOF' || true
import json, time, sys, os, statistics, random

GOLD_SET = [
    {
        "id": "NIST-AC-1",
        "question": "What controls satisfy NIST 800-171 AC-1 (Access Control Policy and Procedures)?",
        "expected": "AC-1 requires documented access control policy and procedures consistent with applicable laws, orders, directives, regulations, policies, standards, and guidelines",
        "domain": "NIST 800-171"
    },
    {
        "id": "AS9100D-VENDOR",
        "question": "Is vendor substitution of alloy 7075-T6 with 7050-T7451 compliant with AS9100D Section 8.4?",
        "expected": "Requires documented evaluation of externally provided processes, products, and services including material equivalency analysis",
        "domain": "AS9100D"
    },
    {
        "id": "CMMC-L2-SC",
        "question": "What are the CMMC Level 2 requirements for System and Communications Protection (SC)?",
        "expected": "CMMC Level 2 SC domain includes boundary protection, cryptographic key establishment, and CUI encryption at rest and in transit",
        "domain": "CMMC"
    },
    {
        "id": "ITAR-RETRANSFER",
        "question": "Under ITAR 22 CFR 120-130, what approval is required for re-transfer of defense articles to a third country?",
        "expected": "Prior written approval from DDTC is required for any re-transfer or re-export of defense articles",
        "domain": "ITAR"
    },
    {
        "id": "DFARS-7012",
        "question": "What are the incident reporting timelines under DFARS 252.204-7012?",
        "expected": "72-hour reporting requirement to DoD CIO via dibnet.dod.mil for cyber incidents on covered contractor information systems",
        "domain": "DFARS"
    },
    {
        "id": "DO178C-DAL",
        "question": "What is the relationship between Design Assurance Level (DAL) and software verification under DO-178C?",
        "expected": "DAL A requires 100% MC/DC coverage; DAL B requires decision coverage; DAL C requires statement coverage",
        "domain": "DO-178C"
    },
    {
        "id": "MILSTD-1553",
        "question": "What are the fault tolerance requirements for MIL-STD-1553B data bus redundancy?",
        "expected": "Dual redundant bus architecture with automatic bus controller switchover and remote terminal response time under 12 microseconds",
        "domain": "MIL-STD"
    },
    {
        "id": "NIST-IA-2",
        "question": "What multi-factor authentication requirements exist in NIST 800-171 IA-2 for privileged accounts?",
        "expected": "Multi-factor authentication for network access to privileged accounts using two or more different factors",
        "domain": "NIST 800-171"
    },
    {
        "id": "DRIFT-F16-F35",
        "question": "What compliance drift risks exist when migrating F-16 wire harness specifications to F-35 EMI shielding requirements?",
        "expected": "F-35 requires MIL-STD-461G EMI compliance versus F-16 MIL-STD-461E; wire harness shielding effectiveness must be re-validated",
        "domain": "Cross-Program Drift"
    },
    {
        "id": "AS9100D-NCR",
        "question": "What is the required nonconformance reporting process under AS9100D Section 10.2?",
        "expected": "Requires root cause analysis, containment actions, corrective action effectiveness verification, and impact assessment on delivered product",
        "domain": "AS9100D"
    },
    {
        "id": "CMMC-L3-IR",
        "question": "What incident response capabilities are required at CMMC Level 3?",
        "expected": "Establish incident handling capability including preparation, detection, analysis, containment, recovery, and user response activities",
        "domain": "CMMC"
    },
    {
        "id": "ITAR-BROKERING",
        "question": "What registration requirements exist for brokering activities under ITAR Part 129?",
        "expected": "Any person engaged in brokering activities must register with DDTC and obtain prior approval for each brokering transaction",
        "domain": "ITAR"
    },
    {
        "id": "NIST-MP-1",
        "question": "What media protection controls does NIST 800-171 require for CUI on removable media?",
        "expected": "Protect and control CUI on digital media during transport; implement cryptographic mechanisms to protect confidentiality",
        "domain": "NIST 800-171"
    },
    {
        "id": "MILSTD-882E",
        "question": "How does MIL-STD-882E classify risk for software-intensive systems?",
        "expected": "Risk matrix combining severity categories (catastrophic to negligible) with probability levels (frequent to improbable); software control categories SCI through SCIV",
        "domain": "MIL-STD"
    },
    {
        "id": "DO178C-TOOL",
        "question": "What qualification criteria apply to software development tools under DO-178C Section 12.2?",
        "expected": "Tool Qualification Level TQL-1 through TQL-5 based on criteria 1 (output is part of airborne software) and criteria 2 (tool automates verification)",
        "domain": "DO-178C"
    },
    {
        "id": "DRIFT-ALLOY",
        "question": "What traceability is required when a vendor substitutes Ti-6Al-4V with Ti-6Al-4V ELI in a flight-critical component?",
        "expected": "Material certification per AMS 4930/4931, mechanical property equivalency testing, fracture toughness requalification, and OEM design authority approval",
        "domain": "Cross-Program Drift"
    },
    {
        "id": "DFARS-7020",
        "question": "What self-assessment requirements does DFARS 252.204-7020 impose?",
        "expected": "Contractors must conduct NIST SP 800-171 DoD Assessment and report scores to SPRS; medium and high assessments conducted by DoD",
        "domain": "DFARS"
    },
    {
        "id": "AS9100D-FOD",
        "question": "What Foreign Object Debris/Damage (FOD) prevention requirements exist in AS9100D?",
        "expected": "Section 8.5.4 requires FOD prevention program including awareness training, contamination controls, tool accountability, and clean-as-you-go procedures",
        "domain": "AS9100D"
    },
    {
        "id": "NIST-AU-3",
        "question": "What audit event content does NIST 800-171 AU-3 require for CUI systems?",
        "expected": "Audit records must contain type of event, when it occurred, where it occurred, source of event, outcome, and identity of subjects/objects",
        "domain": "NIST 800-171"
    },
    {
        "id": "DRIFT-CNC",
        "question": "If a CNC machine producing F-35 bulkhead components shows 0.002 inch tolerance drift, what compliance actions are required?",
        "expected": "Machine recalibration per AS9100D 7.1.5, nonconformance review of in-process parts, retrospective lot sampling, customer notification per 8.7, and corrective action per 10.2",
        "domain": "Cross-Program Drift"
    }
]


def mock_result(tc):
    """Generate deterministic mock result for dry-run mode."""
    random.seed(hash(tc["id"]))
    match = random.random() > 0.15  # ~85% accuracy in mock
    latency = random.randint(120, 2800)
    return {
        "id": tc["id"],
        "domain": tc["domain"],
        "question": tc["question"],
        "expected": tc["expected"],
        "actual": tc["expected"] if match else "Insufficient context to determine compliance requirement",
        "match": match,
        "latency_ms": latency
    }


def run_live(tc, model):
    """Run a single test case against the model via scillm."""
    import subprocess
    prompt = (
        f"You are a defense/aerospace compliance expert. Answer concisely.\n\n"
        f"Question: {tc['question']}\n\n"
        f"Provide a factual answer referencing specific standards and requirements."
    )
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["bash", "-c", f"cd {os.environ.get('SKILL_DIR', '.')}/../scillm && ./run.sh complete --model {model} --prompt {json.dumps(prompt)}"],
            capture_output=True, text=True, timeout=60
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        actual = result.stdout.strip() if result.returncode == 0 else f"ERROR: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        elapsed_ms = 60000
        actual = "ERROR: timeout"

    # Simple substring match for expected answer fragments
    exp_words = set(tc["expected"].lower().split())
    act_words = set(actual.lower().split())
    overlap = len(exp_words & act_words) / max(len(exp_words), 1)
    match = overlap > 0.40

    return {
        "id": tc["id"],
        "domain": tc["domain"],
        "question": tc["question"],
        "expected": tc["expected"],
        "actual": actual[:200],
        "match": match,
        "latency_ms": elapsed_ms
    }


def compute_stats(results):
    """Compute aggregate metrics from results list."""
    latencies = [r["latency_ms"] for r in results]
    matches = sum(1 for r in results if r["match"])
    total = len(results)
    return {
        "accuracy_pct": round(matches / total * 100, 1) if total else 0,
        "latency_p50": int(statistics.median(latencies)) if latencies else 0,
        "latency_p95": int(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0),
        "total": total,
        "passed": matches,
        "estimated_token_cost_usd": round(total * 0.003, 4)  # rough estimate per query
    }


def print_results_table(model, results, stats):
    """Print formatted results table."""
    print(f"\n{'='*100}")
    print(f"  BENCHMARK RESULTS: {model}")
    print(f"{'='*100}")
    print(f"{'TEST_CASE':<20} {'DOMAIN':<22} {'MATCH':<8} {'LATENCY_MS':<12} EXPECTED (truncated)")
    print(f"{'-'*100}")
    for r in results:
        match_str = "PASS" if r["match"] else "FAIL"
        print(f"{r['id']:<20} {r['domain']:<22} {match_str:<8} {r['latency_ms']:<12} {r['expected'][:40]}...")
    print(f"{'-'*100}")
    print(f"  accuracy: {stats['accuracy_pct']}%  |  passed: {stats['passed']}/{stats['total']}  |  "
          f"latency_p50: {stats['latency_p50']}ms  |  latency_p95: {stats['latency_p95']}ms  |  "
          f"est_cost: ${stats['estimated_token_cost_usd']}")
    print(f"{'='*100}\n")


def save_results(model, suite, results, stats):
    """Save results to ~/.embry/benchmark_results.json."""
    results_dir = os.path.expanduser("~/.embry")
    os.makedirs(results_dir, exist_ok=True)
    path = os.path.join(results_dir, "benchmark_results.json")

    existing = {}
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)

    key = f"{model}_{suite}_{time.strftime('%Y%m%dT%H%M%S')}"
    existing[key] = {
        "model": model,
        "suite": suite,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stats": stats,
        "results": results
    }
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"Results saved to {path}")


def cmd_run(model, suite, dry_run):
    """Run benchmark for a single model."""
    if suite != "compliance-basic":
        print(f"ERROR: Unknown suite '{suite}'. Available: compliance-basic", file=sys.stderr)
        sys.exit(1)

    print(f"Running suite '{suite}' against model '{model}' ({'DRY RUN' if dry_run else 'LIVE'})...")
    results = []
    for tc in GOLD_SET:
        if dry_run:
            results.append(mock_result(tc))
        else:
            results.append(run_live(tc, model))

    stats = compute_stats(results)
    print_results_table(model, results, stats)
    save_results(model, suite, results, stats)
    return results, stats


def cmd_compare(models_str, suite, dry_run):
    """Run benchmark for multiple models and compare."""
    models = [m.strip() for m in models_str.split(",") if m.strip()]
    if not models:
        print("ERROR: No models specified", file=sys.stderr)
        sys.exit(1)

    all_stats = {}
    for model in models:
        _, stats = cmd_run(model, suite, dry_run)
        all_stats[model] = stats

    # Print comparison table
    print(f"\n{'='*90}")
    print(f"  COMPARISON: {' vs '.join(models)}")
    print(f"{'='*90}")
    print(f"{'MODEL':<30} {'ACCURACY':<12} {'P50_MS':<10} {'P95_MS':<10} {'COST_USD':<12}")
    print(f"{'-'*90}")
    for model, stats in all_stats.items():
        print(f"{model:<30} {stats['accuracy_pct']:>6}%     {stats['latency_p50']:<10} {stats['latency_p95']:<10} ${stats['estimated_token_cost_usd']:<10}")
    print(f"{'='*90}\n")


def cmd_report():
    """Print last benchmark results."""
    path = os.path.expanduser("~/.embry/benchmark_results.json")
    if not os.path.exists(path):
        print("No benchmark results found. Run a benchmark first.", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    if not data:
        print("No benchmark results found.", file=sys.stderr)
        sys.exit(1)

    # Show most recent entries
    print(f"\n{'='*90}")
    print(f"  STORED BENCHMARK RESULTS ({path})")
    print(f"{'='*90}")
    print(f"{'KEY':<50} {'MODEL':<20} {'ACCURACY':<10} {'TIMESTAMP'}")
    print(f"{'-'*90}")
    for key in sorted(data.keys(), reverse=True)[:10]:
        entry = data[key]
        s = entry["stats"]
        print(f"{key:<50} {entry['model']:<20} {s['accuracy_pct']:>5}%    {entry['timestamp']}")
    print(f"{'='*90}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compliance QRA LLM Benchmark")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Run benchmark against a model")
    p_run.add_argument("--model", required=True, help="Model name")
    p_run.add_argument("--suite", default="compliance-basic", help="Test suite (default: compliance-basic)")
    p_run.add_argument("--dry-run", action="store_true", help="Mock results, no LLM calls")

    p_cmp = sub.add_parser("compare", help="Compare multiple models")
    p_cmp.add_argument("--models", required=True, help="Comma-separated model names")
    p_cmp.add_argument("--suite", default="compliance-basic", help="Test suite")
    p_cmp.add_argument("--dry-run", action="store_true", help="Mock results, no LLM calls")

    p_rpt = sub.add_parser("report", help="Show last benchmark results")

    args = parser.parse_args()
    if args.command == "run":
        cmd_run(args.model, args.suite, args.dry_run)
    elif args.command == "compare":
        cmd_compare(args.models, args.suite, args.dry_run)
    elif args.command == "report":
        cmd_report()
    else:
        parser.print_help()
        sys.exit(1)
PYEOF

# ---------------------------------------------------------------------------
# Dispatch subcommands
# ---------------------------------------------------------------------------
usage() {
    echo "Usage: $0 <run|compare|report> [OPTIONS]"
    echo ""
    echo "Subcommands:"
    echo "  run      --model MODEL --suite SUITE [--dry-run]"
    echo "  compare  --models 'model1,model2' [--suite SUITE] [--dry-run]"
    echo "  report"
    exit 1
}

[[ $# -lt 1 ]] && usage

SUBCMD="$1"
shift

export SKILL_DIR="$SCRIPT_DIR"

case "$SUBCMD" in
    run|compare|report)
        $UV run python3 -c "$GOLD_SET_PY" "$SUBCMD" "$@"
        ;;
    *)
        usage
        ;;
esac
