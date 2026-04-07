"""CLI entrypoint for /create-evidence-case.

Build structured evidence cases using Claims-Arguments-Evidence (CAE) trees.
Exploit-first with MCTS escalation for verification strategy selection.

Inputs: Claim text via CLI args.
Outputs: Evidence case JSON to stdout, tree persisted in /memory.
Failures: Logs errors via loguru, exits with code 1 on fatal.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure skill-local modules are found before any PYTHONPATH pollution
_SKILL_DIR = str(Path(__file__).resolve().parent)
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

import typer
from loguru import logger
from rich.console import Console
from rich.tree import Tree

# Bust stale module cache if wrong models was imported by a dependency
if "models" in sys.modules and "create-evidence-case" not in (getattr(sys.modules["models"], "__file__", "") or ""):
    del sys.modules["models"]
from models import grade_from_score
from plausibility import check_plausibility
from runner import EvidenceCaseRunner
from storage import EvidenceCaseStore


def _apply_plausibility_gate(result: dict, claim: str, show_progress: bool = True) -> dict:
    """Post-run plausibility check for satisfied verdicts with not_in_corpus warnings.

    If the LLM determines the entity combination is implausible (e.g. "Kerberos
    for weapon targeting", "Windows XP flight management"), downgrade from
    satisfied to inconclusive and record the evidence.
    """
    verdict = result.get("verdict", {})
    if verdict.get("state") != "satisfied":
        return result

    # Extract entity warnings from gate trace
    gate_trace = result.get("gate_trace", [])
    recall_step = next((g for g in gate_trace if g.get("gate") == "step_2_recall"), None)
    if not recall_step:
        return result

    grounding = recall_step.get("data", {}).get("grounding_evidence", {})
    warnings = grounding.get("warnings", [])
    resolution_map = grounding.get("resolution_map", {})
    not_in_corpus = [w for w in warnings if w.get("category") == "not_in_corpus"]

    if not not_in_corpus:
        return result

    if show_progress:
        console = Console()
        console.print("[dim]Plausibility check: not_in_corpus terms detected...[/]")

    plaus = check_plausibility(claim, warnings, resolution_map)
    result["plausibility"] = plaus

    if plaus.get("checked") and not plaus.get("plausible"):
        # Downgrade verdict
        verdict["state"] = "inconclusive"
        verdict["grade"] = "B"
        verdict["score"] = max(verdict.get("score", 0) - 0.2, 0.0)
        verdict["reasoning"] = (
            f"Plausibility check failed: {plaus.get('reason', 'implausible entity combination')}. "
            f"Original verdict was satisfied but entity combination is not plausible "
            f"in the F-36/SPARTA domain."
        )
        # Add plausibility gate to trace
        gate_trace.append({
            "gate": "step_6_plausibility",
            "passed": False,
            "detail": f"IMPLAUSIBLE: {plaus.get('reason', '')}",
            "data": plaus,
        })
        if show_progress:
            Console().print(f"[bold red]IMPLAUSIBLE:[/] {plaus.get('reason', '')}")
            Console().print("[yellow]Verdict downgraded: satisfied → inconclusive[/]")
    else:
        gate_trace.append({
            "gate": "step_6_plausibility",
            "passed": True,
            "detail": f"Plausible: {plaus.get('reason', 'entity combination checks out')}",
            "data": plaus,
        })
        if show_progress and plaus.get("checked"):
            Console().print(f"[green]Plausible:[/] {plaus.get('reason', '')}")

    return result


app = typer.Typer(
    name="create-evidence-case",
    help="CAE evidence trees with exploit-first MCTS strategy selection.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def create(
    claim: str = typer.Argument(..., help="The claim or question to verify"),
    category: str = typer.Option("auto", "--category", "-c", help="Category: compliance|code|analytics|pipeline|auto"),
    strategies: int = typer.Option(0, "--strategies", "-s", help="Force N concurrent strategies (0=exploit-first)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress Rich TUI progress"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
    test_only: bool = typer.Option(False, "--test-only", "-t", help="Run deterministic gates only (no LLM). Fast preview."),
) -> None:
    """Build an evidence case for a claim."""
    if test_only:
        # Short-circuit: deterministic gates only, no LLM calls
        return test(claim=claim, quiet=quiet, json_output=json_output)

    runner = EvidenceCaseRunner()
    try:
        result = runner.run(
            claim_text=claim,
            category=category,
            force_strategies=strategies,
            show_progress=not quiet,
        )
        # Plausibility gate: if verdict is satisfied but not_in_corpus warnings
        # exist, ask LLM whether the entity combination is plausible.
        result = _apply_plausibility_gate(result, claim, show_progress=not quiet)
    except Exception as exc:
        logger.error("Evidence case runner failed: {}", exc)
        # Re-ensure skill dir is first on path (PYTHONPATH pollution from pi-mono)
        # Force reimport from skill dir (PYTHONPATH pollution may have cached wrong models)
        if "models" in sys.modules and "create-evidence-case" not in getattr(sys.modules["models"], "__file__", ""):
            del sys.modules["models"]
        sys.path.insert(0, _SKILL_DIR)
        from models import VerdictNode as _VN
        result = {
            "claim": {"text": claim, "category": category, "id": "error", "verdict": "NOT_SATISFIED"},
            "strategies": [],
            "evidence": [],
            "verdict": {"state": "not_satisfied", "grade": "F", "score": 0.0,
                        "strategy_id": "", "evidence_ids": [],
                        "reasoning": f"Runner error: {exc}"},
            "answer": f"Unable to process: {exc}",
            "needs_clarification": True,
            "clarify_questions": ["Could you rephrase the question?"],
        }

    if json_output:
        # Sanitize control chars that break JSON consumers
        import re
        raw = json.dumps(result, indent=2, default=str)
        clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', raw)
        print(clean)
        return

    # Pretty print — transparent output so humans can course-correct
    verdict = result.get("verdict", {})
    v_state = verdict.get("state", "unknown")
    v_grade = verdict.get("grade", "?")
    v_score = verdict.get("score", 0.0)
    gate_trace = result.get("gate_trace", [])

    style = "green" if v_state == "satisfied" else "red" if v_state == "not_satisfied" else "yellow"
    console.print(f"\n[bold {style}]{v_state.upper()}[/] — Grade: {v_grade} — Score: {v_score:.3f}")
    console.print(f"[dim]Question:[/] {result['claim']['text'][:120]}")
    console.print(f"[dim]Category:[/] {result['claim']['category']}  |  Case ID: {result['claim']['id']}")

    evidence_count = len(result.get("evidence", []))
    console.print(f"[dim]Evidence:[/] {evidence_count} items")
    console.print()

    # --- Decision rationale (the human must see WHY) ---
    console.print("[bold]Why this verdict:[/]")

    for step in gate_trace:
        gate = step.get("gate", "")
        passed = step.get("passed", False)
        detail = step.get("detail", "")
        icon = "[green]PASS[/]" if passed else "[red]FAIL[/]"
        # Short gate name for readability
        short_name = gate.replace("step_", "").replace("_", " ").title()
        console.print(f"  {icon} {short_name}: {detail[:120]}")

    # --- Grounding evidence warnings ---
    recall_step = next((g for g in gate_trace if g.get("gate") == "step_2_recall"), None)
    if recall_step:
        grounding = recall_step.get("data", {}).get("grounding_evidence", {})
        if isinstance(grounding, dict):
            unresolved_id = grounding.get("unresolved_id_like", 0)
            resolved = grounding.get("resolved", 0)
            if unresolved_id > 0:
                console.print()
                console.print(f"[bold red]WARNING: {unresolved_id} ID-like term(s) "
                              f"did not resolve against the corpus[/]")
                unresolved_terms = grounding.get("unresolved_terms", [])
                for t in unresolved_terms:
                    if isinstance(t, dict) and t.get("type") == "id_like":
                        term = t.get("term", "?")
                        closest = t.get("closest_match", "none")
                        console.print(f"  [red]UNRESOLVED:[/] {term} → closest match: {closest}")
                if v_state == "satisfied":
                    console.print(f"  [yellow]The question references entities that may not exist. "
                                  f"Verdict may be a false positive.[/]")
            elif resolved > 0:
                console.print(f"\n[dim]Grounding: {resolved} terms resolved, 0 unresolved[/]")

    # --- What to check ---
    console.print()
    if v_state == "satisfied":
        console.print("[dim]Check: Do the QRAs below actually answer the question, "
                      "or just share keywords?[/]")
    elif v_state == "inconclusive":
        console.print("[dim]Check: Is this a genuine corpus gap, or a question "
                      "spanning unrelated domains?[/]")
    elif v_state == "not_satisfied":
        console.print("[dim]Check: Is the question genuinely out of scope, "
                      "or using unfamiliar terminology?[/]")


@app.command()
def get(
    case_id: str = typer.Argument(..., help="Evidence case ID to retrieve"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Retrieve a stored evidence case."""
    store = EvidenceCaseStore()
    case = store.recall_case(case_id)
    if case is None:
        console.print(f"[red]Case {case_id} not found in /memory[/]")
        raise typer.Exit(code=1)
    if json_output:
        print(json.dumps(case, indent=2, default=str))
    else:
        console.print_json(json.dumps(case, default=str))


@app.command()
def validate(
    case_file: str = typer.Argument(..., help="Path to evidence case JSON file"),
) -> None:
    """Validate an evidence case for schema completeness."""
    path = Path(case_file)
    if not path.exists():
        console.print(f"[red]File not found: {case_file}[/]")
        raise typer.Exit(code=1)

    case = json.loads(path.read_text())
    issues: list[str] = []

    # Check required top-level keys
    for key in ("claim", "strategies", "evidence", "verdict"):
        if key not in case:
            issues.append(f"missing top-level key: {key}")

    # Check claim fields
    claim = case.get("claim", {})
    for field in ("id", "text", "category", "verdict"):
        if not claim.get(field):
            issues.append(f"claim missing: {field}")

    # Check verdict fields
    verdict = case.get("verdict", {})
    for field in ("state", "grade", "score", "strategy_id"):
        if field not in verdict:
            issues.append(f"verdict missing: {field}")

    # Check evidence chain
    strategies = case.get("strategies", [])
    evidence = case.get("evidence", [])
    if not strategies:
        issues.append("no strategies executed")
    if not evidence:
        issues.append("no evidence collected")

    selected = [s for s in strategies if s.get("selected")]
    if not selected:
        issues.append("no winning strategy marked")

    # Check evidence IDs referenced by verdict exist
    cited_ids = set(verdict.get("evidence_ids", []))
    actual_ids = {e.get("id") for e in evidence}
    missing = cited_ids - actual_ids
    if missing:
        issues.append(f"verdict cites missing evidence: {missing}")

    if issues:
        console.print("[yellow]Validation issues:[/]")
        for issue in issues:
            console.print(f"  - {issue}")
        raise typer.Exit(code=1)
    else:
        console.print("[green]Evidence case is valid[/]")


@app.command()
def history(
    category: str = typer.Option("", "--category", "-c", help="Filter by category"),
) -> None:
    """Show UCT strategy history."""
    store = EvidenceCaseStore()
    categories = [category] if category else ["compliance", "code", "analytics", "pipeline", "general"]

    for cat in categories:
        cached = store.load_uct_cache(cat)
        if not cached:
            continue
        parent_visits = sum(s.get("visits", 0) for s in cached)
        console.print(f"\n[bold cyan]{cat}[/] (total visits: {parent_visits})")
        from scoring import uct_score as _uct
        for s in sorted(cached, key=lambda x: _uct(x.get("wins", 0), x.get("visits", 0), max(parent_visits, 1)), reverse=True):
            wins = s.get("wins", 0)
            visits = s.get("visits", 0)
            uct = _uct(wins, visits, max(parent_visits, 1))
            win_rate = wins / visits if visits > 0 else 0
            console.print(f"  {s['name']:20s}  wins={wins:<4}  visits={visits:<4}  rate={win_rate:.2f}  uct={uct:.3f}")


@app.command()
def tree(
    case_id: str = typer.Argument(..., help="Evidence case ID to display"),
) -> None:
    """Print evidence tree (Rich tree display)."""
    store = EvidenceCaseStore()
    case = store.recall_case(case_id)
    if case is None:
        console.print(f"[red]Case {case_id} not found[/]")
        raise typer.Exit(code=1)

    claim = case if case.get("node_type") == "claim" else case.get("claim", case)
    rich_tree = Tree(f"[bold]{claim.get('text', case_id)[:80]}[/] [{claim.get('verdict', '?')}]")

    # If this is a full case dict with strategies/evidence
    for s in case.get("strategies", []):
        marker = "[green]*[/] " if s.get("selected") else "  "
        branch = rich_tree.add(f"{marker}[cyan]{s['name']}[/] score={s.get('score', 0):.3f} ({s.get('latency_ms', 0):.0f}ms)")
        for e in case.get("evidence", []):
            if e.get("layer") == s["name"]:
                branch.add(f"[dim]{e['method']}[/] conf={e.get('confidence', 0):.2f} — {e.get('collector', '')}")

    verdict = case.get("verdict", {})
    if verdict:
        if isinstance(verdict, str):
            rich_tree.add(f"[bold]{verdict}[/]")
        else:
            rich_tree.add(f"[bold {'green' if verdict.get('state') == 'satisfied' else 'red'}]Verdict: {verdict.get('state', '?')} ({verdict.get('grade', '?')})[/]")

    console.print(rich_tree)


@app.command()
def test(
    claim: str = typer.Argument(..., help="The claim or QRA text to test"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress Rich TUI progress"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Run deterministic gates only — no LLM calls.

    Tests a claim against the 6 deterministic gates:
      1. On-topic (keyword heuristic only)
      1b. Sentence decomposition (regex heuristic)
      2. /memory recall (daemon call)
      2_entities. Entity extraction (deterministic)
      2b. Grounding check (fabricated ID detection)
      3. Technique bridge (tag coherence + entity overlap)

    Returns SATISFIED (6/6), INCONCLUSIVE (2-5/6), or NOT_SATISFIED (<2/6).
    Target: <10s per claim. No subprocess calls, no LLM fallbacks.
    """
    from deterministic_test import run_deterministic_gates

    result = run_deterministic_gates(claim)

    if json_output:
        import re
        raw = json.dumps(result, indent=2, default=str)
        clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', raw)
        print(clean)
        return

    if not quiet:
        verdict = result["verdict"]
        style = (
            "green" if verdict == "SATISFIED"
            else "yellow" if verdict == "INCONCLUSIVE"
            else "red"
        )
        console.print(f"\n[bold {style}]{verdict}[/] — {result['gates_passed']}/{result['gates_total']} gates passed ({result['latency_ms']:.0f}ms)")
        for gate_name, passed in result["gates"].items():
            icon = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            short = gate_name.replace("step_", "").replace("_", " ").title()
            detail = result["gate_details"].get(gate_name, "")
            console.print(f"  {icon} {short}: {detail}")


@app.command("test-batch")
def test_batch(
    input_file: str = typer.Option("", "--input", "-i", help="Input JSONL with QRAs (question/answer fields)"),
    output_file: str = typer.Option("", "--output", "-o", help="Output JSONL with verdicts"),
    scope: str = typer.Option("", "--scope", help="Read directly from /memory daemon (e.g. sparta_qra)"),
    limit: int = typer.Option(0, "--limit", "-n", help="Max QRAs to process (0=all)"),
    workers: int = typer.Option(5, "--workers", "-w", help="Concurrent workers"),
    resume: bool = typer.Option(False, "--resume", help="Skip already-processed _keys in output file"),
    json_output: bool = typer.Option(False, "--json", help="Output summary as JSON"),
) -> None:
    """Batch deterministic gate audit on QRAs.

    Reads QRAs from JSONL file or /memory daemon, runs 6 deterministic gates
    on each, writes per-QRA verdicts to output JSONL.

    Modes:
      --input file.jsonl : Read QRAs from JSONL (must have question/answer fields)
      --scope sparta_qra : Read from /memory daemon via paginated recall
    """
    from deterministic_test import load_qras_from_scope, run_batch

    if not input_file and not scope:
        console.print("[red]Must specify --input or --scope[/]")
        raise typer.Exit(1)

    if not output_file:
        output_file = "/tmp/test_batch_results.jsonl"

    # Load already-processed keys for resume
    processed_keys: set[str] = set()
    out_path = Path(output_file)
    if resume and out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                rec = json.loads(line)
                if rec.get("_key"):
                    processed_keys.add(rec["_key"])
            except json.JSONDecodeError:
                continue
        if processed_keys:
            console.print(f"[dim]Resuming: {len(processed_keys)} already processed[/]")

    # Load QRAs
    qras: list[dict] = []
    if input_file:
        inp = Path(input_file)
        if not inp.exists():
            console.print(f"[red]Input file not found: {input_file}[/]")
            raise typer.Exit(1)
        for line in inp.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                qras.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    elif scope:
        qras = load_qras_from_scope(scope, limit=limit or 500)

    if limit > 0:
        qras = qras[:limit]

    if not qras:
        console.print("[yellow]No QRAs to process[/]")
        raise typer.Exit(0)

    console.print(f"Processing {len(qras)} QRAs with {workers} workers → {output_file}")

    summary = run_batch(qras, output_file, workers=workers, processed_keys=processed_keys or None)

    if json_output:
        print(json.dumps(summary, indent=2))
    else:
        total = summary["total"]
        verdicts = summary.get("verdicts", {})
        console.print(f"\n[bold]Batch Results ({total} QRAs, {summary.get('total_seconds', 0):.0f}s):[/]")
        for v, count in verdicts.items():
            pct = count / total * 100 if total else 0
            ci = summary.get("wilson_ci_95", {}).get(v, [0, 0])
            lo, hi = ci[0], ci[1]
            style = "green" if v == "SATISFIED" else "yellow" if v == "INCONCLUSIVE" else "red"
            console.print(f"  [{style}]{v}[/]: {count} ({pct:.1f}%) — 95% CI [{lo:.1%}, {hi:.1%}]")
        console.print(f"  Mean latency: {summary.get('mean_latency_ms', 0):.0f}ms")
        console.print(f"  Output: {output_file}")


@app.command("stress-test")
def stress_test(
    output: str = typer.Option("01_EVIDENCE_STRESS_TEST_TASKS.md", "--output", "-o",
                               help="Task file path for /orchestrate"),
    questions_file: str = typer.Option("", "--questions", "-q",
                                       help="Custom questions JSON (default: evidence-case-lab/state/questions.json)"),
    count: int = typer.Option(0, "--count", "-n", help="Limit to first N questions (0=all)"),
) -> None:
    """Generate an /orchestrate task file for agent-driven stress testing.

    Each question becomes a task where the AGENT (not EvidenceCaseRunner)
    follows the full 7-step SKILL.md flow:
      1. Decompose → 2. Per-component recall → 3. Entity extraction + grounding
      4. Same-technique check → 5. Clarify → 6. Lean4 → 7. Verdict

    The agent reads the evidence and decides. Deterministic code provides evidence only.
    """
    import time as _time

    # Load questions
    questions = _load_stress_test_questions(questions_file)
    if not questions:
        console.print("[red]No questions found. Provide --questions or ensure "
                      "evidence-case-lab/state/questions.json exists.[/]")
        raise typer.Exit(1)

    if count > 0:
        questions = questions[:count]

    # Shuffle questions — agent evaluates blind, like a real conversation.
    # The answer key is written separately for post-run scoring.
    import random as _random
    _random.seed(42)
    shuffled = list(enumerate(questions))
    _random.shuffle(shuffled)

    # Write answer key (separate file — agent never sees this)
    answer_key = []
    for orig_idx, q in shuffled:
        answer_key.append({
            "id": q.get("id", f"Q{orig_idx+1:02d}"),
            "expected": q.get("expected", "satisfied"),
            "poison_type": q.get("poison_type"),
            "rationale": q.get("rationale", ""),
        })

    key_path = Path(output).with_suffix(".answer_key.json")
    key_path.write_text(json.dumps(answer_key, indent=2))

    lines = []
    lines.append(f"# Evidence Case Stress Test — {len(questions)} Questions")
    lines.append("")
    lines.append(f"**Created**: {_time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Goal**: Agent-driven evidence case evaluation — blind stress test")
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append("Each task simulates a human asking a question. The agent runs the full")
    lines.append("`/create-evidence-case` 7-step SKILL.md flow, reads grounding evidence,")
    lines.append("and decides the verdict. The agent does NOT know which questions are")
    lines.append("adversarial — it evaluates each one on its merits, exactly like a real")
    lines.append("conversation where a human might ask a bad question.")
    lines.append("")
    lines.append("When `/create-evidence-case` cannot build a case, use `/memory clarify`.")
    lines.append("")
    lines.append("If the agent makes a wrong verdict, the human corrects it afterward")
    lines.append("via `evidence-case-lab correct <id> <verdict> --reason '...'`.")
    lines.append("Corrections become labeled data for Shadow-Lego classifier training.")
    lines.append("")
    lines.append("## Questions/Blockers")
    lines.append("")
    lines.append("None — all questions pre-validated.")
    lines.append("")
    lines.append("## Tasks")
    lines.append("")

    # P0: Setup
    lines.append("### P0: Setup (Sequential)")
    lines.append("")
    lines.append("- [ ] **Task 0**: Verify ArangoDB and /memory are healthy")
    lines.append("  - Agent: general-purpose")
    lines.append("  - Parallel: 0")
    lines.append("  - Dependencies: none")
    lines.append("  - **Definition of Done**:")
    lines.append("    - Test: `curl --unix-socket /run/user/1000/embry/memory.sock http://localhost/recall -d '{\"q\":\"SPARTA\",\"k\":1}'` returns results")
    lines.append("    - Assertion: ArangoDB is reachable and sparta_qra collection has data")
    lines.append("")

    # P1: All questions (parallel, blind — no adversarial hints)
    lines.append("### P1: Questions (Parallel)")
    lines.append("")
    task_num = 1
    for orig_idx, q in shuffled:
        qid = q.get("id", f"Q{task_num:02d}")
        question = q["question"]

        lines.append(f"- [ ] **Task {task_num}**: [{qid}] Evidence case")
        lines.append(f"  - Agent: general-purpose")
        lines.append(f"  - Parallel: 1")
        lines.append(f"  - Dependencies: Task 0")
        lines.append(f"  - Question: \"{question}\"")
        lines.append(f"  - Run `/create-evidence-case` following the 7-step SKILL.md flow.")
        lines.append(f"    Read the `resolution_map` and `unresolved_terms` from `/extract-entities`.")
        lines.append(f"    If entities don't bridge through a shared technique, verdict is INCONCLUSIVE.")
        lines.append(f"    If grounding_ok=false with fabricated IDs, verdict is NOT_SATISFIED.")
        lines.append(f"    If unresolved terms describe technology that doesn't exist on the F-36")
        lines.append(f"    (e.g., quantum modules, blockchain ledgers), use `/memory clarify` and decide.")
        lines.append(f"    Persist the case via `EvidenceCaseStore2.persist_case()`.")
        lines.append(f"  - **Definition of Done**:")
        lines.append(f"    - Assertion: Case persisted with verdict, gate_trace, and grounding_evidence visible")
        lines.append("")
        task_num += 1

    # P2: Score against answer key
    lines.append("### P2: Scoring (Sequential)")
    lines.append("")
    lines.append(f"- [ ] **Task {task_num}**: Score results against answer key")
    lines.append(f"  - Agent: general-purpose")
    lines.append(f"  - Parallel: 2")
    lines.append(f"  - Dependencies: all previous tasks")
    lines.append(f"  - Read answer key: `{key_path}`")
    lines.append(f"  - Compare each verdict against expected. Calculate:")
    lines.append(f"    - Overall accuracy")
    lines.append(f"    - False positives (expected not_satisfied, got satisfied)")
    lines.append(f"    - False negatives (expected satisfied, got not_satisfied)")
    lines.append(f"  - For each mismatch, run `evidence-case-lab correct <id> <expected> --reason '...'`")
    lines.append(f"  - Write summary to evidence-case-lab/state/stress_test_results.json")
    lines.append(f"  - **Definition of Done**:")
    lines.append(f"    - Assertion: Summary JSON exists with accuracy metrics and corrections recorded")
    lines.append("")

    # Completion criteria
    lines.append("## Completion Criteria")
    lines.append("")
    lines.append("- [ ] All tasks marked [x]")
    lines.append("- [ ] Every verdict has visible grounding evidence")
    lines.append("- [ ] Mismatches recorded as corrections for Shadow-Lego training")
    lines.append("")

    out_path = Path(output)
    out_path.write_text("\n".join(lines))
    console.print(f"[green]Task file written: {out_path}[/]")
    console.print(f"[green]Answer key written: {key_path}[/]")
    console.print(f"  {len(questions)} questions (shuffled, blind evaluation)")
    console.print(f"  {task_num + 1} tasks total (setup + questions + scoring)")
    console.print(f"\n[bold]Next step:[/] /orchestrate {out_path}")


def _load_stress_test_questions(questions_file: str = "") -> list[dict]:
    """Load questions from file or default locations."""
    if questions_file and Path(questions_file).exists():
        return json.loads(Path(questions_file).read_text())

    # Try evidence-case-lab/state/questions.json first
    lab_questions = Path(__file__).parent.parent / "evidence-case-lab" / "state" / "questions.json"
    if lab_questions.exists():
        return json.loads(lab_questions.read_text())

    # Fall back to batch_50_f36.py ADVERSARIAL_QUESTIONS + question_bank.py
    questions = []
    try:
        from batch_50_f36 import ADVERSARIAL_QUESTIONS, load_real_questions
        real = load_real_questions(40)
        for i, q in enumerate(real, 1):
            questions.append({
                "id": f"R{i:02d}",
                "question": q["question"],
                "expected": "satisfied",
                "source": q.get("source", "?"),
                "difficulty": q.get("difficulty", "?"),
                "category": q.get("category", "?"),
            })
        for i, q in enumerate(ADVERSARIAL_QUESTIONS, 1):
            questions.append({
                "id": f"ADV{i:02d}",
                "question": q["question"],
                "expected": q.get("expected_verdict", "not_satisfied"),
                "poison_type": q["poison_type"],
                "rationale": q.get("rationale", ""),
            })
    except ImportError:
        pass

    return questions


if __name__ == "__main__":
    app()
