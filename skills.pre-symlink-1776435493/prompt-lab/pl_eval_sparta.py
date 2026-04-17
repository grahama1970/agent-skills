"""SPARTA evaluation and end-to-end test CLI commands."""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.table import Table

from config import SKILL_DIR, ensure_dirs
from models import parse_qra_items_response
from llm import call_llm
from evaluation import load_prompt, load_models_config
from qra_evaluation import QRAEvalSummary, QRAGroundedResult, AmbiguityGate, check_entity_anchoring
from qra_validators import EntityAnchoring
from sparta_connector import SpartaConnector, SpartaTestCase
from prompt_extractor import PromptExtractor
from batch_checkpoint import BatchCheckpoint
from citation_validator import validate_citations, check_duplicate_answers, analyze_question_diversity
from task_monitor_client import PromptLabTaskClient

from pl_app import app, console


@app.command("eval-sparta")
def eval_sparta(
    prompt: str = typer.Option("tactic_control_prompt", "--prompt", "-p", help="Prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
    gt: str = typer.Option("sparta_qra", "--gt", help="Ground truth name"),
):
    """Evaluate SPARTA QRA generation from JSON ground truth."""
    ensure_dirs()
    models_config = load_models_config()

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found.[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]
    
    # Load prompt (treat as system prompt if no [USER] tag)
    content = (SKILL_DIR / "prompts" / f"{prompt}.txt").read_text()
    if "[USER]" in content:
        system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
    else:
        system_prompt = content
        user_template = "Generate QRAs about how this control relates to the technique in space systems.\nThe TACTIC HIERARCHY below is the anchor.\n\nPROMPT CONTEXT:\n{context}"

    # Load ground truth
    gt_path = SKILL_DIR / "ground_truth" / f"{gt}.json"
    if not gt_path.exists():
        console.print(f"[red]Ground truth '{gt}' not found at {gt_path}[/red]")
        raise typer.Exit(1)
        
    data = json.loads(gt_path.read_text())
    test_cases = data.get("cases", [])

    if cases > 0:
        test_cases = test_cases[:cases]

    console.print(f"[bold]Evaluating SPARTA QRA prompt '{prompt}' with model '{model}'[/bold]")
    console.print(f"Test cases: {len(test_cases)}")
    console.print()

    results = []

    requests = []
    for tc in test_cases:
        t_hierarchy = tc.get("input", {}).get("tactic_hierarchy", {})
        r_control = tc.get("input", {}).get("related_control", {})
        user_msg = f"TACTIC:\n{t_hierarchy.get('technique', {}).get('name', 'N/A')}\n{t_hierarchy.get('technique', {}).get('description', 'N/A')}\n\nCONTROL:\n{r_control.get('name', 'N/A')}\n{r_control.get('description', 'N/A')}"
        requests.append({"system": system_prompt, "user": user_msg})

    async def run_sparta_eval():
        from llm import call_llm_batch
        from models import parse_qra_items_response
        from qra_evaluation import QRAEvaluator

        llm_results = await call_llm_batch(requests, model_config)
        evaluator = QRAEvaluator(threshold=0.85)

        for i, res in enumerate(llm_results):
            tc = test_cases[i]
            context_keywords = []
            t_hierarchy = tc.get("input", {}).get("tactic_hierarchy", {})
            r_control = tc.get("input", {}).get("related_control", {})
            if t_hierarchy:
                tech = t_hierarchy.get("technique", {})
                context_keywords.extend([tech.get("name", ""), tech.get("id", "")])
            if r_control:
                context_keywords.extend([r_control.get("name", ""), r_control.get("id", "")])
            
            context_keywords = [k for k in context_keywords if k]
            
            try:
                if not res.success:
                    console.print(f"  {tc['id']}: [red]FAILED[/red] - {res.error}")
                    continue
                
                content = res.content
                qra_items_model = parse_qra_items_response(content)
                qra_items = qra_items_model.items
                
                all_source_text = tc.get("source_text", "")
                result = evaluator.evaluate(
                    case_id=tc["id"],
                    qra_items=qra_items,
                    source_text=all_source_text,
                    context_keywords=context_keywords,
                    latency_ms=res.total_latency_ms
                )
                results.append(result)

                status = "[green]PASS[/green]" if result.ambiguity_pass_rate > 0.8 and result.citation_grounding_rate > 0.8 else "[red]FAIL[/red]"
                console.print(f"  {tc['id']}: {status} | Amb: {result.ambiguity_pass_rate:.1%} | Gnd: {result.citation_grounding_rate:.1%} | QRAs: {len(qra_items)}")

            except Exception as e:
                console.print(f"  [red]{tc['id']}: ERROR - {e}[/red]")

    asyncio.run(run_sparta_eval())

    if results:
        avg_ambiguity = sum(r.ambiguity_pass_rate for r in results) / len(results)
        avg_grounding = sum(r.citation_grounding_rate for r in results) / len(results)
        avg_qras = sum(r.total_qras for r in results) / len(results)

        console.print()
        console.print("[bold]Summary[/bold]")
        table = Table()
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Avg Ambiguity Rate", f"{avg_ambiguity:.1%}")
        table.add_row("Avg Grounding Rate", f"{avg_grounding:.1%}")
        table.add_row("Avg QRAs per input", f"{avg_qras:.1f}")
        console.print(table)




@app.command("test-sparta")
def test_sparta(
    prompt_file: Path = typer.Option(None, "--prompt-file", "-f", help="Python file with prompts"),
    run_id: str = typer.Option("run-recovery-verify", "--run-id", "-r", help="SPARTA Run ID"),
    cases: int = typer.Option(100, "--cases", "-n", help="Number of test cases"),
    phase: int = typer.Option(0, "--phase", help="SPARTA phase (0=Rel, 1=Control)"),
    db_path: Path = typer.Option(
        Path.home() / "workspace" / "experiments" / "sparta" / "data" / "runs" / "run-recovery-verify" / "sparta.duckdb",
        "--db-path", help="Path to SPARTA DuckDB"
    ),
    threshold: float = typer.Option(0.85, "--threshold", "-t", help="Grounding threshold"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed citation failures"),
    converge: bool = typer.Option(False, "--converge", help="Enable iterative convergence mode"),
    min_anchoring: float = typer.Option(0.995, "--min-anchoring", help="Minimum entity anchoring rate (default 99.5% for LLM non-determinism)"),
    min_grounding: float = typer.Option(0.90, "--min-grounding", help="Minimum citation grounding rate"),
    min_ambiguity: float = typer.Option(0.995, "--min-ambiguity", help="Minimum ambiguity gate pass rate (default 99.5% for LLM non-determinism)"),
    max_iterations: int = typer.Option(3, "--max-iterations", help="Max convergence attempts"),
    output_json: bool = typer.Option(False, "--json", help="Output structured JSON for agent consumption"),
    json_stream: bool = typer.Option(False, "--json-stream", help="Output NDJSON per case for streaming progress"),
    task_monitor: bool = typer.Option(True, "--task-monitor/--no-task-monitor", help="Enable task-monitor integration"),
    resume: bool = typer.Option(False, "--resume", help="Resume from last checkpoint (skip completed cases)"),
    clear_checkpoint: bool = typer.Option(False, "--clear-checkpoint", help="Clear existing checkpoint and start fresh"),
    case_timeout: int = typer.Option(120, "--case-timeout", help="Timeout per case in seconds (default: 120)"),
):
    """End-to-End SPARTA QRA Test with real data."""
    ensure_dirs()
    console.print(f"[bold]SPARTA QRA Test[/bold]")
    console.print(f"DB: {db_path}")
    
    # Load prompt (either from file or default)
    system_prompt = ""
    if prompt_file:
        try:
            prompts = PromptExtractor.extract_from_file(prompt_file)
            # Heuristic to find the right prompt
            # If phase 0, look for TACTIC_CONTROL_PROMPT, else SIMPLE_SYSTEM_PROMPT
            target = "TACTIC_CONTROL_PROMPT" if phase == 0 else "SIMPLE_SYSTEM_PROMPT"
            if target in prompts:
                system_prompt = prompts[target]
                console.print(f"[green]Loaded {target} from {prompt_file}[/green]")
            else:
                # Fallback to first available or error
                system_prompt = list(prompts.values())[0] 
                console.print(f"[yellow]Warning: {target} not found, using first available prompt[/yellow]")
        except Exception as e:
            console.print(f"[red]Failed to load prompt file: {e}[/red]")
            raise typer.Exit(1)
    else:
        # Load default prompt based on phase
        if phase == 0:
            # Phase 0: Relationships - use relationship prompt with entity anchoring
            prompt_name = "relationship_system_prompt"
            prompt_path = SKILL_DIR / "prompts" / f"{prompt_name}.txt"
            if prompt_path.exists():
                system_prompt = prompt_path.read_text()
                console.print(f"[blue]Using relationship prompt: {prompt_name}[/blue]")
            else:
                # Fallback to generic
                s, _ = load_prompt("qra_grounded_v1", SKILL_DIR)
                system_prompt = s
                console.print("[yellow]Relationship prompt not found, using qra_grounded_v1[/yellow]")
        else:
            # Phase 1+: Controls - use generic prompt
            s, _ = load_prompt("qra_grounded_v1", SKILL_DIR)
            system_prompt = s
            console.print("[blue]Using default prompt: qra_grounded_v1[/blue]")

    # Connect to DB
    try:
        connector = SpartaConnector(db_path)
        test_cases = connector.fetch_test_cases(limit=cases, phase=phase)
        console.print(f"Fetched {len(test_cases)} test cases")
    except Exception as e:
        console.print(f"[red]DB Connection Error: {e}[/red]")
        raise typer.Exit(1)

    if not test_cases:
        console.print("[yellow]No test cases found.[/yellow]")
        raise typer.Exit(0)

    # Initialize checkpoint for resume capability
    task_name = f"test-sparta-{len(test_cases)}-phase{phase}"
    checkpoint = BatchCheckpoint.load_or_create(task_name, total_cases=len(test_cases))

    if clear_checkpoint:
        checkpoint.clear()
        console.print("[yellow]Cleared existing checkpoint, starting fresh[/yellow]")
    elif resume and checkpoint.completed_case_ids:
        console.print(f"[green]Resuming from checkpoint: {len(checkpoint.completed_case_ids)}/{len(test_cases)} already completed[/green]")
    elif checkpoint.completed_case_ids and not resume:
        console.print(f"[yellow]Found existing checkpoint ({len(checkpoint.completed_case_ids)} completed). Use --resume to continue or --clear-checkpoint to start fresh.[/yellow]")

    # Initialize task monitor for progress tracking
    monitor = None
    if task_monitor:
        monitor = PromptLabTaskClient(
            task_name=task_name,
            total_cases=len(test_cases),
            description=f"SPARTA QRA Test ({len(test_cases)} cases, phase {phase})",
        )
        console.print(f"[dim]Task monitor registered. View progress: uv run python monitor.py tui --filter prompt-lab[/dim]")

    # Run Eval
    models_config = load_models_config()
    model_config = models_config.get("chutes-deepseek", models_config.get("deepseek")) # Prefer chutes if avail
    if not model_config:
        model_config = list(models_config.values())[0]
        console.print(f"[yellow]Using fallback model: {model_config['model']}[/yellow]")

    results = []
    skipped_count = 0
    consecutive_failures = 0
    max_consecutive_failures = int(os.getenv("PROMPT_LAB_MAX_CONSECUTIVE_FAILURES", "5"))

    eval_failing_items = []

    async def run_eval(correction_context: str = ""):
        """Run evaluation with optional correction context from previous iteration."""
        nonlocal skipped_count, consecutive_failures
        eval_failing_items.clear()
        for tc in test_cases:
            # Skip if already completed (resume mode)
            if checkpoint.is_completed(tc.id):
                if verbose:
                    console.print(f"  [dim]{tc.id}: Skipped (already completed)[/dim]")
                continue
            if not tc.knowledge_excerpts and phase != 2:
                skipped_count += 1
                if verbose:
                    console.print(f"  [dim]{tc.id}: Skipped (no knowledge)[/dim]")
                continue

            # Construct user message based on test case type
            # Note: The system prompt from SPARTA usually expects specific context injection
            # For this test, we might need a template. 
            # If using extracted SPARTA prompt, it often expects raw JSON context or specific format.
            # We'll try to emulate the SPARTA pipeline context construction simply here.
            
            # Simple emulation of context construction for the user message
            if phase == 0:
                 user_msg = f"""Generate QRAs about how this control relates to the technique in space systems.
The TACTIC HIERARCHY below is the anchor.

PROMPT CONTEXT:
{json.dumps({
    "tactic_hierarchy": {
        "technique": {
            **tc.source_control,
            "knowledge_from_urls": tc.knowledge_excerpts
        }
    },
    "related_control": tc.target_control,
}, indent=2)}
"""
                 # Add correction context if this is a retry iteration
                 if correction_context:
                     user_msg += f"\n\n{correction_context}"
            elif phase == 1:
                # Phase 1: Control + Knowledge excerpts
                user_msg = f"""Generate factual questions about this SPARTA control.
Control:
{json.dumps({
    **tc.source_control,
    "knowledge_excerpts": tc.knowledge_excerpts
}, indent=2)}
"""
                # Add correction context if this is a retry iteration
                if correction_context:
                    user_msg += f"\n\n{correction_context}"
            else:
                # Phase 2: Description-only (no knowledge excerpts)
                # Explicitly separate citable text from metadata to prevent
                # LLM from citing JSON field names/values instead of description content
                description = tc.source_control.get("description", "")
                user_msg = f"""Generate factual questions about this SPARTA control.

CITABLE SOURCE TEXT (cite ONLY verbatim excerpts from this text):
{description}

Control metadata (for context only, do NOT cite these fields):
- ID: {tc.source_control.get("control_id", "")}
- Name: {tc.source_control.get("name", "")}
- Type: {tc.source_control.get("type", "")}
"""
                # Add correction context if this is a retry iteration
                if correction_context:
                    user_msg += f"\n\n{correction_context}"

            try:
                # Apply per-case timeout
                content, latency = await asyncio.wait_for(
                    call_llm(system_prompt, user_msg, model_config),
                    timeout=case_timeout
                )
                qra_items_model = parse_qra_items_response(content)
                qra_items = qra_items_model.items
                
                # Validation - combine ALL text the LLM saw for citation grounding
                # Bug fix: Previously only validated against knowledge_excerpts, but LLM
                # also sees control descriptions (source_control, target_control)
                all_source_text_parts = list(tc.knowledge_excerpts)
                if tc.source_control:
                    if tc.source_control.get("description"):
                        all_source_text_parts.append(tc.source_control["description"])
                    if tc.source_control.get("name"):
                        all_source_text_parts.append(tc.source_control["name"])
                if tc.target_control:
                    if tc.target_control.get("description"):
                        all_source_text_parts.append(tc.target_control["description"])
                    if tc.target_control.get("name"):
                        all_source_text_parts.append(tc.target_control["name"])
                all_source_text = " ".join(all_source_text_parts)
                
                citation_validation = validate_citations(qra_items, all_source_text, threshold)
                
                # Ambiguity & Anchoring
                ambiguity_passes = 0
                anchoring_passes = 0
                common_missing = []
                failing_items = []

                for item in qra_items:
                    q = item.get("question", "")
                    # Ambiguity
                    if AmbiguityGate.check(q, tc.context_keywords)["ok"]:
                        ambiguity_passes += 1

                    # Anchoring - use relationship check for phase 0
                    if phase == 0 and tc.target_control:
                        src_keywords = [tc.source_control.get("name", ""), tc.source_control.get("control_id", "")]
                        tgt_keywords = [tc.target_control.get("name", ""), tc.target_control.get("control_id", "")]
                        rel_result = EntityAnchoring.check_relationship(q, src_keywords, tgt_keywords)
                        if rel_result.ok:
                            anchoring_passes += 1
                        else:
                            common_missing.extend(src_keywords + tgt_keywords)
                            failing_items.append({"case_id": tc.id, "question": q, "failed_gate": "entity_anchoring", "reason": rel_result.reason})
                    else:
                        anchoring = check_entity_anchoring(q, tc.context_keywords)
                        if anchoring["anchored"]:
                            anchoring_passes += 1
                        else:
                            common_missing.extend(anchoring["missing_entities"])
                            failing_items.append({"case_id": tc.id, "question": q, "failed_gate": "entity_anchoring", "reason": f"Missing {anchoring['missing_entities']}"})

                ambiguity_rate = ambiguity_passes / len(qra_items) if qra_items else 1.0
                anchoring_rate = anchoring_passes / len(qra_items) if qra_items else 1.0
                
                # Check duplicates
                duplicates = check_duplicate_answers(qra_items)
                diversity = analyze_question_diversity(qra_items)
                
                results.append(QRAGroundedResult(
                    case_id=tc.id,
                    qra_items=qra_items,
                    source_text=" ".join(tc.knowledge_excerpts)[:100], # Trucated for display
                    latency_ms=latency,
                    total_qras=len(qra_items),
                    citation_grounding_rate=citation_validation.grounding_rate,
                    hallucination_count=citation_validation.ungrounded_citations,
                    duplicate_count=len(duplicates),
                    question_type_distribution=diversity["question_type_distribution"],
                    persona_distribution=diversity["persona_distribution"],
                    confidence_distribution=diversity["confidence_distribution"],
                    question_type_coverage=diversity["question_type_coverage"],
                    ambiguity_pass_rate=ambiguity_rate,
                    entity_anchoring_rate=anchoring_rate,
                    missing_entities_common=list(set(common_missing))
                ))

                eval_failing_items.extend(failing_items)

                # Update task monitor with per-case progress
                if monitor:
                    monitor.update(
                        case_id=tc.id,
                        ambiguity_rate=ambiguity_rate,
                        anchoring_rate=anchoring_rate,
                        grounding_rate=citation_validation.grounding_rate,
                        qra_count=len(qra_items),
                        failures=failing_items,
                    )

                # NDJSON streaming output (one JSON object per line)
                if json_stream:
                    import sys as sys_mod
                    ndjson_record = {
                        "case_id": tc.id,
                        "status": "pass" if (ambiguity_rate >= min_ambiguity and anchoring_rate >= min_anchoring and citation_validation.grounding_rate >= min_grounding) else "fail",
                        "qra_count": len(qra_items),
                        "metrics": {
                            "ambiguity": round(ambiguity_rate, 4),
                            "anchoring": round(anchoring_rate, 4),
                            "grounding": round(citation_validation.grounding_rate, 4),
                        },
                        "latency_ms": round(latency, 1),
                    }
                    sys_mod.stdout.write(json.dumps(ndjson_record) + "\n")
                    sys_mod.stdout.flush()
                else:
                    console.print(f"  {tc.id}: {len(qra_items)} QRAs | Gnd: {citation_validation.grounding_rate:.0%} | Amb: {ambiguity_rate:.0%} | Anch: {anchoring_rate:.0%}")

                # Verbose mode: Show failing citations
                if verbose and citation_validation.hallucinations:
                    for hall in citation_validation.hallucinations[:5]:  # Limit to 5 per test case
                        console.print(f"    [yellow]❌ Citation failed (score: {hall.score:.2f}, threshold: {threshold})[/yellow]")
                        console.print(f"       Question: {hall.question_preview}...")
                        console.print(f"       Citation: \"{hall.citation[:150]}...\"")

                # Mark case as completed in checkpoint
                checkpoint.mark_completed(
                    case_id=tc.id,
                    metrics={
                        "ambiguity_rate": ambiguity_rate,
                        "anchoring_rate": anchoring_rate,
                        "grounding_rate": citation_validation.grounding_rate,
                    },
                    result={
                        "case_id": tc.id,
                        "qra_count": len(qra_items),
                        "ambiguity": ambiguity_rate,
                        "anchoring": anchoring_rate,
                        "grounding": citation_validation.grounding_rate,
                    },
                )
                consecutive_failures = 0  # Reset on success

            except asyncio.TimeoutError:
                consecutive_failures += 1
                console.print(f"  [red]{tc.id} TIMEOUT: Case exceeded {case_timeout}s deadline[/red]")
                eval_failing_items.append({
                    "case_id": tc.id,
                    "failed_gate": "timeout",
                    "reason": f"Case exceeded {case_timeout}s timeout",
                })
                if consecutive_failures >= max_consecutive_failures:
                    console.print(f"[red]CIRCUIT BREAKER: {consecutive_failures} consecutive failures. Halting batch.[/red]")
                    if output_json:
                        error_output = {
                            "success": False,
                            "error": f"Circuit breaker triggered: {consecutive_failures} consecutive failures",
                            "error_code": "CIRCUIT_BREAKER",
                            "completed": len(checkpoint.completed_case_ids),
                            "total": len(test_cases),
                            "exit_code": 1,
                        }
                        console.print(json.dumps(error_output, indent=2))
                    if monitor:
                        monitor.finish(success=False)
                    checkpoint.finalize(success=False)
                    raise typer.Exit(1)

            except Exception as e:
                consecutive_failures += 1
                console.print(f"  [red]{tc.id} Error: {e}[/red]")
                eval_failing_items.append({
                    "case_id": tc.id,
                    "failed_gate": "error",
                    "reason": str(e)[:200],
                })
                if consecutive_failures >= max_consecutive_failures:
                    console.print(f"[red]CIRCUIT BREAKER: {consecutive_failures} consecutive failures. Halting batch.[/red]")
                    if output_json:
                        error_output = {
                            "success": False,
                            "error": f"Circuit breaker triggered: {consecutive_failures} consecutive failures",
                            "error_code": "CIRCUIT_BREAKER",
                            "last_error": str(e)[:200],
                            "completed": len(checkpoint.completed_case_ids),
                            "total": len(test_cases),
                            "exit_code": 1,
                        }
                        console.print(json.dumps(error_output, indent=2))
                    if monitor:
                        monitor.finish(success=False)
                    checkpoint.finalize(success=False)
                    raise typer.Exit(1)

    # Convergence loop: run eval, check thresholds, optionally iterate
    correction_context = ""  # Feedback from previous iteration

    for iteration in range(1, max_iterations + 1 if converge else 2):
        results.clear()

        asyncio.run(run_eval(correction_context))

        # Summary
        summary = QRAEvalSummary(
            prompt_name=prompt_file.name if prompt_file else "default",
            model_name=model_config['model'],
            timestamp=datetime.now().isoformat(),
            results=results,
        )

        # Threshold check
        amb_pass = summary.avg_ambiguity_pass_rate >= min_ambiguity
        anch_pass = summary.avg_entity_anchoring_rate >= min_anchoring
        gnd_pass = summary.avg_citation_grounding_rate >= min_grounding
        all_passed = amb_pass and anch_pass and gnd_pass

        if output_json:
            import json as json_mod
            json_output = {
                "iteration": iteration,
                "converged": all_passed,
                "metrics": {
                    "ambiguity_pass_rate": {"value": round(summary.avg_ambiguity_pass_rate, 4), "threshold": min_ambiguity, "passed": amb_pass},
                    "entity_anchoring_rate": {"value": round(summary.avg_entity_anchoring_rate, 4), "threshold": min_anchoring, "passed": anch_pass},
                    "citation_grounding_rate": {"value": round(summary.avg_citation_grounding_rate, 4), "threshold": min_grounding, "passed": gnd_pass},
                },
                "total_qras": summary.total_qras_generated,
                "skipped": skipped_count,
                "failing_examples": eval_failing_items[:10],
            }
            console.print(json_mod.dumps(json_output, indent=2))
        else:
            table = Table(title=f"SPARTA QRA Test Summary (Iteration {iteration})")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_column("Threshold", style="yellow")
            table.add_column("Status")

            table.add_row("Ambiguity Gate Pass", f"{summary.avg_ambiguity_pass_rate:.1%}", f"{min_ambiguity:.0%}", "[green]PASS[/green]" if amb_pass else "[red]FAIL[/red]")
            table.add_row("Entity Anchoring", f"{summary.avg_entity_anchoring_rate:.1%}", f"{min_anchoring:.0%}", "[green]PASS[/green]" if anch_pass else "[red]FAIL[/red]")
            table.add_row("Citation Grounding", f"{summary.avg_citation_grounding_rate:.1%}", f"{min_grounding:.0%}", "[green]PASS[/green]" if gnd_pass else "[red]FAIL[/red]")
            table.add_row("Total Generated", str(summary.total_qras_generated), "", "")
            if skipped_count > 0:
                table.add_row("Skipped (No Knowledge)", str(skipped_count), "", "[red]Action: Run /fetcher[/red]")

            console.print(table)

        if all_passed:
            if converge:
                console.print(f"[green]Converged after {iteration} iteration(s)[/green]")
            break

        if converge and iteration < max_iterations:
            console.print(f"[yellow]Thresholds not met. Retrying ({iteration}/{max_iterations})...[/yellow]")

            # Build correction context for next iteration
            failure_details = []
            if not amb_pass:
                failure_details.append(f"- Ambiguity Gate: {summary.avg_ambiguity_pass_rate:.1%} (need {min_ambiguity:.0%}). Questions must contain context keywords (entity names/IDs).")
            if not anch_pass:
                failure_details.append(f"- Entity Anchoring: {summary.avg_entity_anchoring_rate:.1%} (need {min_anchoring:.0%}). Questions must explicitly name the control/technique, not use pronouns.")
            if not gnd_pass:
                failure_details.append(f"- Citation Grounding: {summary.avg_citation_grounding_rate:.1%} (need {min_grounding:.0%}). Citations must be verbatim from source text.")

            # Include specific failing examples (up to 5)
            example_failures = []
            for fail in eval_failing_items[:5]:
                if fail.get("failed_gate") == "entity_anchoring":
                    example_failures.append(f'  BAD: "{fail.get("question", "")[:80]}..." - {fail.get("reason", "")}')
                elif fail.get("failed_gate") == "ambiguity_gate":
                    example_failures.append(f'  BAD: "{fail.get("question", "")[:80]}..." - missing context keywords')

            correction_context = f"""PREVIOUS ATTEMPT FAILED - COURSE CORRECT:
{chr(10).join(failure_details)}

Example failures from previous attempt:
{chr(10).join(example_failures) if example_failures else "  (see metrics above)"}

REQUIREMENTS FOR THIS ATTEMPT:
1. ALWAYS include the control/technique name or ID in each question (e.g., "How does CM-0049..." not "How does this control...")
2. For relationship QRAs (phase 0), BOTH entities must be named in each question
3. Citations must be exact verbatim quotes from the source text
"""

    if converge and not all_passed:
        console.print(f"[red]Failed to converge after {max_iterations} iterations[/red]")

    # Finalize checkpoint
    checkpoint_summary = checkpoint.finalize(success=all_passed)

    # Finish task monitor
    if monitor:
        monitor.finish(success=all_passed)

    if not all_passed:
        if output_json:
            error_output = {
                "success": False,
                "error": "Quality gates not met after all iterations",
                "error_code": "VALIDATION_FAILED",
                "metrics": {
                    "ambiguity": round(summary.avg_ambiguity_pass_rate, 4),
                    "anchoring": round(summary.avg_entity_anchoring_rate, 4),
                    "grounding": round(summary.avg_citation_grounding_rate, 4),
                },
                "thresholds": {
                    "ambiguity": min_ambiguity,
                    "anchoring": min_anchoring,
                    "grounding": min_grounding,
                },
                "completed": len(checkpoint.completed_case_ids),
                "total": len(test_cases),
                "checkpoint_file": str(checkpoint._checkpoint_file),
                "exit_code": 1,
            }
            console.print(json.dumps(error_output, indent=2))
        raise typer.Exit(1)

    # Success output
    if output_json:
        success_output = {
            "success": True,
            "metrics": {
                "ambiguity": round(summary.avg_ambiguity_pass_rate, 4),
                "anchoring": round(summary.avg_entity_anchoring_rate, 4),
                "grounding": round(summary.avg_citation_grounding_rate, 4),
            },
            "total_qras": summary.total_qras_generated,
            "completed": len(checkpoint.completed_case_ids),
            "total": len(test_cases),
            "checkpoint_file": str(checkpoint._checkpoint_file),
            "exit_code": 0,
        }
        console.print(json.dumps(success_output, indent=2))



