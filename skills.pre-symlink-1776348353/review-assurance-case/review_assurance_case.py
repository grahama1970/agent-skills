"""Multi-provider AI review of assurance cases (GSN/CAE).

47 checks across 7 categories grounded in ISO 15026, DO-178C,
IEC 61508, ISO 26262, CMMC, and Assurance 2.0.

Commands:
  review       Single-pass review of an assurance case report
  review-full  3-step pipeline: Structural → Semantic → Verdict
  check        Verify provider CLI and auth
  models       List available models
  checks       List all 47 review checks
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from config import (
    CATEGORY_WEIGHTS,
    CHECKS,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    PROVIDERS,
    VERDICT_ADEQUATE,
    VERDICT_NEEDS_WORK,
)
from prompts import (
    CONTEXT_BRIDGE_STEP2,
    CONTEXT_BRIDGE_STEP3,
    STEP1_PROMPT,
    STEP2_PROMPT,
    STEP3_PROMPT,
)
from providers import find_provider_cli, run_provider_async

console = Console(stderr=True)
app = typer.Typer(
    add_completion=False,
    help="Multi-provider AI review of assurance cases (GSN/CAE). 47 checks across 7 categories.",
)

# ---------------------------------------------------------------------------
# Memory integration (graceful degradation)
# ---------------------------------------------------------------------------
_HAS_MEMORY = False
try:
    from memory_integration import learn_review, recall_prior_reviews
    _HAS_MEMORY = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def review(
    file: Path = typer.Option(..., "--file", "-f", help="Path to assurance case report (markdown)"),
    json_file: Optional[Path] = typer.Option(None, "--json", "-j", help="Path to evidence case JSON"),
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P", help="Provider name"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    reasoning: Optional[str] = typer.Option(None, "--reasoning", "-r", help="Reasoning effort (openai)"),
) -> None:
    """Single-pass review: send the full case to one provider."""
    case_content = _load_case(file, json_file)
    if not case_content:
        console.print("[red]No case content to review.[/red]")
        raise typer.Exit(1)

    actual_model = model or PROVIDERS.get(provider, {}).get("default_model", DEFAULT_MODEL)
    _warn_paid(provider)

    prompt = STEP2_PROMPT.format(
        case_content=case_content,
        step1_output="(structural audit not performed — single-pass mode)",
    )

    t0 = time.time()
    result, rc = asyncio.run(run_provider_async(
        prompt=prompt,
        model=actual_model,
        provider=provider,
        step_name="Single-pass review",
        reasoning=reasoning,
    ))
    elapsed = time.time() - t0

    out_dir = output or Path("review_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review.md").write_text(result)

    output_json = {
        "provider": provider,
        "model": actual_model,
        "elapsed_sec": round(elapsed, 1),
        "return_code": rc,
        "output_file": str(out_dir / "review.md"),
    }
    print(json.dumps(output_json, indent=2))


@app.command(name="review-full")
def review_full(
    file: Path = typer.Option(..., "--file", "-f", help="Path to assurance case report (markdown)"),
    json_file: Optional[Path] = typer.Option(None, "--json", "-j", help="Path to evidence case JSON"),
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P", help="Provider name"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    rounds: int = typer.Option(1, "--rounds", "-n", help="Number of review rounds"),
    save_intermediate: bool = typer.Option(True, "--save-intermediate/--no-save", help="Save step outputs"),
    reasoning: Optional[str] = typer.Option(None, "--reasoning", "-r", help="Reasoning effort (openai)"),
) -> None:
    """Full 3-step pipeline: Structural Audit → Semantic Review → Final Verdict."""
    case_content = _load_case(file, json_file)
    if not case_content:
        console.print("[red]No case content to review.[/red]")
        raise typer.Exit(1)

    actual_model = model or PROVIDERS.get(provider, {}).get("default_model", DEFAULT_MODEL)
    _warn_paid(provider)

    out_dir = output or Path("review_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    supports_continue = PROVIDERS.get(provider, {}).get("supports_continue", False)

    # Memory pre-hook
    prior_context = ""
    if _HAS_MEMORY:
        try:
            prior_context = recall_prior_reviews("assurance-case")
        except Exception:
            pass

    t0 = time.time()
    result = asyncio.run(_review_full_async(
        case_content=case_content,
        model=actual_model,
        provider=provider,
        rounds=rounds,
        supports_continue=supports_continue,
        out_dir=out_dir,
        save_intermediate=save_intermediate,
        reasoning=reasoning,
        prior_context=prior_context,
    ))
    elapsed = time.time() - t0

    # Memory post-hook
    if _HAS_MEMORY and result.get("final_output"):
        try:
            learn_review(
                project_name="assurance-case",
                findings=result["final_output"][:4000],
                provider=provider,
                model=actual_model,
                rounds_completed=rounds,
            )
        except Exception:
            pass

    result["elapsed_sec"] = round(elapsed, 1)
    result["provider"] = provider
    result["model"] = actual_model

    # Save final result
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))


@app.command()
def check(
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P"),
) -> None:
    """Verify provider CLI is available."""
    cli_path = find_provider_cli(provider)
    result = {
        "provider": provider,
        "cli": PROVIDERS.get(provider, {}).get("cli", "?"),
        "available": cli_path is not None,
        "path": str(cli_path) if cli_path else None,
        "models": list(PROVIDERS.get(provider, {}).get("models", {}).keys()),
        "cost": PROVIDERS.get(provider, {}).get("cost", "?"),
    }
    print(json.dumps(result, indent=2))


@app.command()
def models(
    provider: Optional[str] = typer.Option(None, "--provider", "-P"),
) -> None:
    """List available models for provider(s)."""
    providers_to_show = [provider] if provider else list(PROVIDERS.keys())
    result = {}
    for p in providers_to_show:
        cfg = PROVIDERS.get(p, {})
        result[p] = {
            "cli": cfg.get("cli", "?"),
            "default_model": cfg.get("default_model", "?"),
            "models": list(cfg.get("models", {}).keys()),
            "cost": cfg.get("cost", "?"),
        }
    print(json.dumps(result, indent=2))


@app.command()
def checks(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    severity: Optional[str] = typer.Option(None, "--severity", "-s", help="Filter by severity"),
) -> None:
    """List all 47 review checks."""
    table = Table(title="Assurance Case Review Checks")
    table.add_column("ID", style="cyan")
    table.add_column("Category", style="green")
    table.add_column("Title")
    table.add_column("Severity", style="yellow")
    table.add_column("Type", style="blue")

    for check_id, check in sorted(CHECKS.items()):
        if category and check["category"] != category:
            continue
        if severity and check["severity"] != severity:
            continue
        table.add_row(
            check_id,
            check["category"],
            check["title"],
            check["severity"],
            check["type"],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Pipeline implementation
# ---------------------------------------------------------------------------

async def _review_full_async(
    case_content: str,
    model: str,
    provider: str,
    rounds: int,
    supports_continue: bool,
    out_dir: Path,
    save_intermediate: bool,
    reasoning: Optional[str],
    prior_context: str,
) -> dict:
    """Run the 3-step review pipeline."""
    all_rounds = []

    for round_num in range(1, rounds + 1):
        console.print(f"\n[bold]Round {round_num}/{rounds}[/bold]")

        # --- Step 1: Structural Audit ---
        step1_prompt = STEP1_PROMPT.format(case_content=case_content)
        if prior_context:
            step1_prompt = f"## Prior Review Context\n{prior_context}\n\n{step1_prompt}"

        step1_log = out_dir / f"round{round_num}_step1.md" if save_intermediate else None
        step1_output, step1_rc = await run_provider_async(
            prompt=step1_prompt,
            model=model,
            provider=provider,
            log_file=step1_log,
            continue_session=(round_num > 1 and supports_continue),
            step_name=f"R{round_num} Step 1: Structural Audit",
            reasoning=reasoning,
        )

        # --- Step 2: Semantic Review ---
        if supports_continue:
            step2_prompt = STEP2_PROMPT.format(
                case_content=case_content,
                step1_output=step1_output,
            )
        else:
            # Context bridging for stateless providers
            step2_prompt = CONTEXT_BRIDGE_STEP2.format(
                step1_output=step1_output,
                step2_prompt=STEP2_PROMPT.format(
                    case_content=case_content,
                    step1_output=step1_output,
                ),
            )

        step2_log = out_dir / f"round{round_num}_step2.md" if save_intermediate else None
        step2_output, step2_rc = await run_provider_async(
            prompt=step2_prompt,
            model=model,
            provider=provider,
            log_file=step2_log,
            continue_session=supports_continue,
            step_name=f"R{round_num} Step 2: Semantic Review",
            reasoning=reasoning,
        )

        # --- Step 3: Final Verdict ---
        if supports_continue:
            step3_prompt = STEP3_PROMPT.format(
                case_content=case_content,
                step1_output=step1_output,
                step2_output=step2_output,
            )
        else:
            step3_prompt = CONTEXT_BRIDGE_STEP3.format(
                step1_output=step1_output,
                step2_output=step2_output,
                step3_prompt=STEP3_PROMPT.format(
                    case_content=case_content,
                    step1_output=step1_output,
                    step2_output=step2_output,
                ),
            )

        step3_log = out_dir / f"round{round_num}_step3.md" if save_intermediate else None
        step3_output, step3_rc = await run_provider_async(
            prompt=step3_prompt,
            model=model,
            provider=provider,
            log_file=step3_log,
            continue_session=supports_continue,
            step_name=f"R{round_num} Step 3: Final Verdict",
            reasoning=reasoning,
        )

        round_result = {
            "round": round_num,
            "step1_length": len(step1_output),
            "step2_length": len(step2_output),
            "step3_length": len(step3_output),
            "step1_rc": step1_rc,
            "step2_rc": step2_rc,
            "step3_rc": step3_rc,
        }
        all_rounds.append(round_result)

        # Save final report for this round
        if save_intermediate:
            report_path = out_dir / f"round{round_num}_report.md"
            report_path.write_text(_format_round_report(
                round_num, step1_output, step2_output, step3_output, provider, model,
            ))

    # The last round's step3 is the final output
    final_output = step3_output if rounds > 0 else ""
    verdict = _extract_verdict(final_output)

    return {
        "rounds": all_rounds,
        "final_output": final_output,
        "verdict": verdict,
        "output_dir": str(out_dir),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_case(file: Optional[Path], json_file: Optional[Path]) -> str:
    """Load assurance case content from markdown or JSON."""
    content = ""

    if json_file and json_file.exists():
        data = json.loads(json_file.read_text())
        # Convert JSON evidence case to readable format for review
        content = _json_to_review_format(data)

    if file and file.exists():
        md_content = file.read_text()
        if content:
            content = f"{md_content}\n\n---\n\n## JSON Evidence Data\n\n{content}"
        else:
            content = md_content

    return content


def _json_to_review_format(data: dict) -> str:
    """Convert evidence case JSON to a format suitable for review."""
    lines = []
    claim = data.get("claim", {})
    verdict = data.get("verdict", {})
    evidence = data.get("evidence", [])

    lines.append(f"**Question:** {claim.get('text', '?')}")
    lines.append(f"**Verdict:** {verdict.get('state', '?').upper()}")
    lines.append(f"**Grade:** {verdict.get('grade', '?')}")
    lines.append(f"**Controls:** {', '.join(claim.get('control_ids', []))}")
    lines.append("")

    if evidence:
        lines.append("### Evidence Items")
        for i, e in enumerate(evidence, 1):
            lines.append(f"{i}. [{e.get('method', '?')}] {e.get('layer', '?')} — "
                        f"confidence={e.get('confidence', 0):.2f}, "
                        f"controls={', '.join(e.get('control_ids', []))}")
    lines.append("")

    gate_trace = data.get("gate_trace", [])
    if gate_trace:
        lines.append("### Execution Steps")
        for g in gate_trace:
            status = "PASS" if g.get("passed") else "FAIL"
            lines.append(f"- [{status}] {g.get('gate', '?')}: {g.get('detail', '')}")

    return "\n".join(lines)


def _extract_verdict(output: str) -> str:
    """Extract verdict from final output."""
    output_upper = output.upper()
    if "ADEQUATE" in output_upper and "INADEQUATE" not in output_upper:
        return "ADEQUATE"
    if "INADEQUATE" in output_upper:
        return "INADEQUATE"
    if "NEEDS_WORK" in output_upper or "NEEDS WORK" in output_upper:
        return "NEEDS_WORK"
    return "UNKNOWN"


def _format_round_report(
    round_num: int,
    step1: str,
    step2: str,
    step3: str,
    provider: str,
    model: str,
) -> str:
    """Format a complete round report."""
    return f"""# Assurance Case Review — Round {round_num}

> **Provider:** {provider} | **Model:** {model}

## Step 1: Structural Audit

{step1}

---

## Step 2: Semantic Review

{step2}

---

## Step 3: Final Verdict

{step3}
"""


def _warn_paid(provider: str) -> None:
    """Warn if using a paid provider."""
    cost = PROVIDERS.get(provider, {}).get("cost", "?")
    if cost == "paid":
        console.print(
            f"[yellow]WARNING: Provider '{provider}' makes paid API calls. "
            f"Use --provider github for free reviews.[/yellow]"
        )


if __name__ == "__main__":
    app()
