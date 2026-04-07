"""Prompt optimization CLI command."""
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import List

import typer
from rich.table import Table

from config import SKILL_DIR, PROMPTS_DIR, TIER0_CONCEPTUAL, TIER1_TACTICAL
from models import parse_qra_items_response
from llm import call_llm, call_llm_raw
from evaluation import load_models_config, EvalResult
from qra_evaluation import load_qra_ground_truth

from pl_app import app, console


@app.command()
def optimize(
    prompt: str = typer.Option("tactic_control_prompt", "--prompt", "-p", help="Base prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to evaluate variations with"),
    meta_model: str = typer.Option("deepseek", "--meta-model", help="High-reasoning model for generating variations"),
    cases: int = typer.Option(3, "--cases", "-n", help="Number of cases for iteration"),
    gt: str = typer.Option("sparta_qra", "--gt", help="Ground truth name"),
    failures: str = typer.Option("", "--failures", "-f", help="Path to failure cases JSON (from batch monitoring)"),
):
    """Systematically optimize a prompt using Agent-as-Judge loop.

    When --failures is provided, the optimizer uses real failure data to drive
    targeted improvements instead of generic optimization. This is the primary
    self-correction path: batch monitoring detects failures, extracts them to
    a JSON file, and prompt-lab uses them to fix the root cause.
    """
    from config import PROMPTS_DIR
    import asyncio

    base_prompt_file = PROMPTS_DIR / f"{prompt}.txt"
    if not base_prompt_file.exists():
        console.print(f"[red]Prompt '{prompt}' not found.[/red]")
        return

    base_prompt_content = base_prompt_file.read_text()

    # Load failure cases if provided
    failure_cases_text = ""
    if failures and Path(failures).exists():
        failure_data = json.loads(Path(failures).read_text())
        console.print(f"[bold yellow]Loaded {len(failure_data)} failure cases for targeted optimization[/bold yellow]")
        failure_cases_text = "\n\nREAL FAILURE CASES FROM BATCH MONITORING (fix these specifically):\n"
        for i, fc in enumerate(failure_data[:15], 1):
            failure_cases_text += f"\nCase {i}: {fc.get('entity_check', fc.get('error', 'unknown'))}"
            if fc.get('question'):
                failure_cases_text += f"\n  Question: {fc['question']}"
            if fc.get('expected'):
                failure_cases_text += f"\n  Expected: {fc['expected']}"

    console.print(f"[bold]Optimizing prompt '{prompt}' using Agent-as-Judge loop[/bold]")

    # 1. Generate variations using meta-model
    meta_prompt = f"""You are a meta-prompt engineer. Your goal is to optimize a system prompt for generating Question-Reasoning-Answer (QRA) pairs.
Current prompt:
{base_prompt_content}

Evaluation criteria for success:
1. Ambiguity: Questions must be self-contained and unambiguous (must name entities).
2. Grounding: Answers must be strictly grounded in text with verbatim citations.
3. Diversity: Cover different personas (lay_person, cybersecurity_expert) and tactical tags.
{failure_cases_text}

CRITICAL: Your variations MUST preserve ALL entity anchoring rules, examples, and template patterns from the original prompt. Do NOT remove or simplify these - they exist to prevent real failures. If failure cases are provided above, your variations must specifically address those failures.

Generate 5 diverse variations of the system prompt that aim to improve these criteria.
Each variation should try a different strategy (e.g. stronger examples, restructured instructions, tighter constraints, different ordering, simplified language).
Return ONLY valid JSON:
{{
  "variations": [
    {{
      "name": "variant_a",
      "rationale": "Why this variation helps",
      "prompt": "..."
    }}
  ]
}}"""
    
    models_config = load_models_config()
    if meta_model not in models_config:
        console.print(f"[red]Meta-model '{meta_model}' config not found.[/red]")
        return
        
    console.print(f"Generating variations using [cyan]{meta_model}[/cyan]...")
    
    async def get_variations():
        from llm import call_llm_raw
        return await call_llm_raw([{"role": "user", "content": meta_prompt}], models_config[meta_model], max_tokens=2048)
    
    var_response = asyncio.run(get_variations())
    if "error" in var_response:
        console.print(f"[red]Failed to generate variations: {var_response['error']}[/red]")
        return
        
    variations = var_response.get("variations", [])
    if not variations:
        console.print("[red]No variations returned in JSON.[/red]")
        return
        
    console.print(f"Generated {len(variations)} variations.")
    
    # 2. Evaluate each variation
    best_variant = None
    best_score = -1.0
    
    results_summary = []
    
    for i, var in enumerate(variations):
        v_name = var["name"]
        v_prompt = var["prompt"]
        v_rationale = var["rationale"]
        
        console.print(f"\n[bold cyan]Evaluating Variation {i+1}: {v_name}[/bold cyan]")
        console.print(f"[dim]Rationale: {v_rationale}[/dim]")
        
        # Run eval
        try:
            from qra_evaluation import load_qra_ground_truth as load_gt_qra
            test_cases = load_gt_qra(SKILL_DIR)
            if cases > 0: test_cases = test_cases[:cases]

            from qra_evaluation import QRAEvaluator
            evaluator = QRAEvaluator()

            # Build user messages from failure cases when available, otherwise use ground truth
            def build_user_msg(tc, failure_data=None):
                """Build realistic user messages instead of hardcoded dummy data."""
                if failure_data:
                    # Use entities from actual failures for targeted testing
                    fc = failure_data[hash(tc.id) % len(failure_data)]
                    entity_check = fc.get("entity_check", "")
                    # Extract entity names from the check string
                    if "entity_B=" in entity_check:
                        import re
                        match = re.search(r"\['([^']+)',\s*'([^']+)'\]", entity_check)
                        if match:
                            entity_name, entity_id = match.group(1), match.group(2)
                            return (
                                f"TACTIC:\n{entity_name} ({entity_id})\n"
                                f"A technique that targets system components.\n\n"
                                f"CONTROL:\n{tc.name}\n{tc.description}"
                            )
                return f"TACTIC:\n{tc.name}\n{tc.description}\n\nCONTROL:\nTest Control\nA security control for mitigating {tc.name}."

            # Parse failure data if available
            _failure_data = None
            if failures and Path(failures).exists():
                _failure_data = json.loads(Path(failures).read_text())

            async def run_v_eval():
                v_results = []
                for tc in test_cases:
                    user_msg = build_user_msg(tc, _failure_data)
                    content, latency = await call_llm(v_prompt, user_msg, models_config[model])
                    # Ensure we get the list of items
                    items_model = parse_qra_items_response(content)
                    items_list = items_model.items if hasattr(items_model, 'items') else []
                    
                    res = evaluator.evaluate(tc.id, items_list, tc.description, tc.question_keywords, latency)
                    v_results.append(res)
                return v_results
                
            v_results = asyncio.run(run_v_eval())
            
            avg_amb = sum(r.ambiguity_pass_rate for r in v_results) / len(v_results)
            avg_gnd = sum(r.citation_grounding_rate for r in v_results) / len(v_results)
            
            score = (avg_amb + avg_gnd) / 2
            results_summary.append({
                "name": v_name,
                "ambiguity": avg_amb,
                "grounding": avg_gnd,
                "score": score
            })
            
            if score > best_score:
                best_score = score
                best_variant = var
                
        except Exception as e:
            console.print(f"[red]Error evaluating {v_name}: {e}[/red]")

    # 3. Summary and Final Selection
    console.print("\n[bold]Optimization Results[/bold]")
    table = Table()
    table.add_column("Variant", style="cyan")
    table.add_column("Ambiguity", style="green")
    table.add_column("Grounding", style="green")
    table.add_column("Overall", style="bold yellow")
    
    for r in results_summary:
        table.add_row(r["name"], f"{r['ambiguity']:.1%}", f"{r['grounding']:.1%}", f"{r['score']:.2f}")
    
    console.print(table)
    
    if best_variant:
        console.print(f"\n[bold green]Winner: {best_variant['name']}[/bold green]")
        out_file = PROMPTS_DIR / f"{prompt}_optimized_{best_variant['name']}.txt"
        out_file.write_text(best_variant["prompt"])
        console.print(f"Optimized prompt saved to: {out_file.name}")

        # Append to prompt changelog for version tracking
        _log_prompt_change(
            prompt_name=out_file.stem,
            parent=prompt,
            description=best_variant["rationale"],
            score=best_score,
        )


def _log_prompt_change(prompt_name: str, parent: str, description: str, score: float) -> None:
    """Append entry to prompts/changelog.jsonl for prompt version tracking."""
    from datetime import datetime
    changelog = PROMPTS_DIR / "changelog.jsonl"
    entry = json.dumps({
        "prompt": prompt_name,
        "parent": parent,
        "description": description,
        "score": round(score, 4),
        "timestamp": datetime.now().isoformat(),
    })
    with open(changelog, "a") as f:
        f.write(entry + "\n")


def _closest_valid_tag(tag: str, valid_tags: set) -> str:
    """Find the closest valid tag to a hallucinated one using simple string similarity."""
    tag_lower = tag.lower()
    # Prefix or containment match first
    for valid in sorted(valid_tags):
        if valid.lower().startswith(tag_lower[:4]) or tag_lower.startswith(valid.lower()[:4]):
            return valid
    # Fallback: character overlap ratio
    best = ""
    best_score = 0.0
    for valid in sorted(valid_tags):
        common = sum(1 for c in tag_lower if c in valid.lower())
        score = common / max(len(tag_lower), len(valid))
        if score > best_score:
            best_score = score
            best = valid
    return best if best_score > 0.5 else ""


def compile_failures(results: List[EvalResult]) -> str:
    """Compile evaluation failures into a structured brief for the meta-model prompt rewriter.

    Groups failures by type:
    - Hallucinated tags: invalid tags produced by the model, with frequency counts
    - Parse errors: cases where correction failed entirely
    - Wrong classifications: valid-vocab tags predicted but incorrect

    The returned string is intended as direct input to the meta-model prompt rewriter
    so it can target the specific failure patterns observed in the eval run.

    Args:
        results: List of EvalResult objects from an evaluation run.

    Returns:
        A human-readable structured brief string.
    """
    if not results:
        return "No failures to compile."

    total = len(results)
    lines: list[str] = []
    all_valid = TIER0_CONCEPTUAL | TIER1_TACTICAL

    # ── 1. Hallucinated tags (rejected_tags: raw LLM output not in valid vocab) ──
    hallucination_counter: Counter = Counter()
    hallucination_cases: dict[str, list[str]] = {}
    for r in results:
        for tag in r.rejected_tags:
            hallucination_counter[tag] += 1
            hallucination_cases.setdefault(tag, []).append(r.case_id)

    if hallucination_counter:
        lines.append("## Hallucinated Tags")
        for tag, count in hallucination_counter.most_common():
            suggestion = _closest_valid_tag(tag, all_valid)
            if suggestion:
                tier = (
                    "valid conceptual tag"
                    if suggestion in TIER0_CONCEPTUAL
                    else "valid tactical tag"
                )
                confusion = (
                    f"Model confuses {tag} (not a valid tag) with {suggestion} ({tier})."
                )
            else:
                confusion = f"Tag '{tag}' has no close match in the valid vocabulary."
            lines.append(
                f"Tag '{tag}' hallucinated {count}/{total} times. {confusion}"
            )
            case_sample = ", ".join(hallucination_cases[tag][:5])
            if len(hallucination_cases[tag]) > 5:
                case_sample += f" (+{len(hallucination_cases[tag]) - 5} more)"
            lines.append(f"  Affected cases: {case_sample}")

    # ── 2. Parse / correction errors ──
    parse_errors = [r for r in results if not r.correction_success]
    if parse_errors:
        lines.append("\n## Parse Errors")
        lines.append(
            f"{len(parse_errors)}/{total} cases failed to parse or self-correct."
        )
        for r in parse_errors[:5]:
            lines.append(
                f"  Case {r.case_id} (rounds={r.correction_rounds}): "
                f"predicted conceptual={r.predicted_conceptual}, "
                f"tactical={r.predicted_tactical}"
            )
            lines.append(
                f"    Expected: conceptual={r.expected_conceptual}, "
                f"tactical={r.expected_tactical}"
            )

    # ── 3. Wrong classifications (parsed OK but tags do not match ground truth) ──
    wrong = [r for r in results if r.correction_success and r.f1 < 1.0]
    if wrong:
        lines.append("\n## Wrong Classifications")
        lines.append(
            f"{len(wrong)}/{total} cases parsed correctly but produced wrong tags."
        )
        for r in wrong[:8]:
            fp_conceptual = sorted(set(r.predicted_conceptual) - set(r.expected_conceptual))
            fn_conceptual = sorted(set(r.expected_conceptual) - set(r.predicted_conceptual))
            fp_tactical = sorted(set(r.predicted_tactical) - set(r.expected_tactical))
            fn_tactical = sorted(set(r.expected_tactical) - set(r.predicted_tactical))
            deltas: list[str] = []
            if fp_conceptual:
                deltas.append(f"spurious conceptual={fp_conceptual}")
            if fn_conceptual:
                deltas.append(f"missed conceptual={fn_conceptual}")
            if fp_tactical:
                deltas.append(f"spurious tactical={fp_tactical}")
            if fn_tactical:
                deltas.append(f"missed tactical={fn_tactical}")
            delta_str = "; ".join(deltas) if deltas else "unknown delta"
            lines.append(
                f"  Case {r.case_id} (F1={r.f1:.2f}): "
                f"predicted conceptual={r.predicted_conceptual}, tactical={r.predicted_tactical} | "
                f"expected conceptual={r.expected_conceptual}, tactical={r.expected_tactical} | "
                f"{delta_str}"
            )

    if not lines:
        return "No failures detected: all results passed."

    return "\n".join(lines)
