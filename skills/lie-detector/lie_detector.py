"""CLI entrypoint for /lie-detector: deterministic process verification.

Purpose:
    Typer CLI that wires all 6 detection layers together. Provides seal, verify,
    prove, detect, report, train, label, ingest, chain, install-hook, and
    self-seal subcommands.

Inputs:
    - File globs (seal), seal manifests (verify), conversation JSONL (detect),
      training data (train), context descriptions (chain)

Outputs:
    - JSON results to stdout (machine-parseable)
    - Rich formatted output for human consumption

Failure modes:
    - Missing required args → Typer handles with help text
    - Individual layer failures → captured in cascade results
    - Missing HMAC key → seal warns (verify still works for hash comparison)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

import typer
from dotenv import find_dotenv, load_dotenv
from loguru import logger
from rich.console import Console
from rich.table import Table

load_dotenv(find_dotenv(usecwd=True), override=False)

app = typer.Typer(no_args_is_help=True, help="Deterministic process verification for AI self-improvement loops.")
console = Console()

STORAGE_DIR = Path(os.getenv("LIE_DETECTOR_STORAGE", "/mnt/storage12tb/skills/lie-detector"))
SKILLS_DIR = Path(__file__).resolve().parent.parent
MEMORY_PATH = SKILLS_DIR / "memory"

# Verdicts that render green
_GREEN_VERDICTS = {"CLEAN", "PROVEN", "STABLE", "HONEST", "PASS", "DENSE", "ADEQUATE", "FLAG"}


@app.command()
def seal(
    file_globs: list[str] = typer.Argument(..., help="File globs to seal (e.g., 'scripts/*.py')"),
    output: Path = typer.Option(Path(".lie-detector-seal.json"), "--output", "-o", help="Seal manifest output path"),
) -> None:
    """Create sealed hash manifest of evaluation files (HMAC-signed if key set)."""
    from sealed_grading import seal as do_seal
    manifest = do_seal(file_globs, output)
    hmac_status = "HMAC signed" if manifest.hmac_sig else "UNSIGNED (set LIE_DETECTOR_HMAC_KEY)"
    console.print(f"[green]Sealed {len(manifest.files)} files[/green] → {output} ({hmac_status})")
    for f in manifest.files:
        fn_count = len(f.functions)
        console.print(f"  {f.path} ({fn_count} fns)")


@app.command()
def verify(
    seal_file: Path = typer.Argument(..., help="Seal manifest JSON to verify against"),
) -> None:
    """Verify files match a previously created seal (checks HMAC if key set)."""
    from sealed_grading import verify as do_verify
    result = do_verify(seal_file)
    if result.verdict == "CLEAN":
        console.print("[green bold]CLEAN[/green bold] — all files match seal")
    else:
        console.print("[red bold]TAMPERED[/red bold]")
        for tf in result.tampered_files:
            detail = tf.get("detail", tf.get("path", "unknown"))
            console.print(f"  [red]FILE:[/red] {detail}")
        for tf in result.tampered_functions:
            console.print(f"  [red]FN:[/red] {tf.get('path')}:{tf.get('function')}")
        for mf in result.missing_files:
            console.print(f"  [yellow]MISSING:[/yellow] {mf}")
    print(json.dumps(result.to_dict()))
    raise typer.Exit(code=0 if result.verdict == "CLEAN" else 1)


@app.command()
def prove(
    grading_file: Optional[Path] = typer.Option(None, "--grading-file", "-g", help="Python grading file to verify (REQUIRED)"),
) -> None:
    """Verify grading invariants against canonical values (fail-closed)."""
    from invariants import verify_invariants
    if grading_file is None:
        console.print("[red]--grading-file is required (fail-closed: no file = no proof)[/red]")
        raise typer.Exit(code=1)
    result = verify_invariants(grading_file)
    if result.verdict == "PROVEN":
        console.print("[green bold]PROVEN[/green bold] — all invariants hold")
    elif result.verdict == "PROOF_FAILED":
        console.print("[red bold]PROOF_FAILED[/red bold]")
        if result.errors:
            console.print(f"  {result.errors}")
        for m in result.mismatches:
            console.print(f"  [red]MISMATCH:[/red] {m}")
    else:
        console.print(f"[yellow]{result.verdict}[/yellow]")
        if result.errors:
            console.print(f"  {result.errors}")
    print(json.dumps(result.to_dict()))
    raise typer.Exit(code=0 if result.verdict == "PROVEN" else 1)


@app.command()
def detect(
    conversation: Path = typer.Argument(..., help="Conversation JSONL to analyze"),
    seal_file: Optional[Path] = typer.Option(None, "--seal", "-s", help="Seal manifest for Layer 1"),
    grading_file: Optional[Path] = typer.Option(None, "--grading-file", "-g", help="Grading file for Layer 2"),
    layer: Optional[str] = typer.Option(None, "--layer", "-l", help="Comma-separated layers to run (e.g., '1,2,3')"),
    stated_intent: str = typer.Option("", "--intent", "-i", help="Stated intent for pre-gate"),
    actual_activity: str = typer.Option("", "--activity", "-a", help="Actual activity summary"),
) -> None:
    """Full 6-layer cascade on conversation transcript."""
    from cascade import run_cascade

    layers = None
    if layer:
        layer_names = {"1": "seal", "2": "prove", "3": "conform", "3b": "taxonomy",
                       "4": "classify", "5": "llm_audit", "0": "chain"}
        layers = [layer_names.get(l.strip(), l.strip()) for l in layer.split(",")]

    result = run_cascade(
        conversation_path=conversation,
        seal_path=seal_file,
        grading_file=grading_file,
        layers=layers,
        stated_intent=stated_intent,
        actual_activity=actual_activity,
    )

    if result.verdict == "PASS":
        console.print(f"[green bold]PASS[/green bold] (confidence {result.confidence:.2f}, {result.total_latency_ms:.0f}ms)")
    elif result.verdict == "FAIL":
        console.print(f"[red bold]FAIL[/red bold] (confidence {result.confidence:.2f}, {result.total_latency_ms:.0f}ms)")
        for flag in result.flags:
            console.print(f"  [red]{flag['layer']}:[/red] {flag['detail']}")
    elif result.verdict == "SUSPICIOUS":
        console.print(f"[yellow bold]SUSPICIOUS[/yellow bold] (confidence {result.confidence:.2f}, {result.total_latency_ms:.0f}ms)")
        for flag in result.flags:
            console.print(f"  [yellow]{flag['layer']}:[/yellow] {flag['detail']}")
    else:
        console.print(f"[yellow]{result.verdict}[/yellow]")

    print(json.dumps(result.to_dict()))
    raise typer.Exit(code=0 if result.verdict == "PASS" else 1)


@app.command()
def report(
    conversation: Path = typer.Argument(..., help="Conversation JSONL"),
    seal_file: Optional[Path] = typer.Option(None, "--seal", "-s"),
    grading_file: Optional[Path] = typer.Option(None, "--grading-file", "-g"),
) -> None:
    """Markdown report with verdicts per turn."""
    from cascade import run_cascade

    result = run_cascade(
        conversation_path=conversation,
        seal_path=seal_file,
        grading_file=grading_file,
    )

    table = Table(title="Lie Detector Report")
    table.add_column("Layer", style="cyan")
    table.add_column("Verdict", style="bold")
    table.add_column("Detail")
    table.add_column("Latency")

    for lr in result.layer_results:
        style = "green" if lr.verdict in _GREEN_VERDICTS else "red"
        table.add_row(lr.layer, f"[{style}]{lr.verdict}[/{style}]", lr.detail[:80], f"{lr.latency_ms:.0f}ms")

    console.print(table)
    verdict_style = "green" if result.verdict == "PASS" else ("yellow" if result.verdict == "SUSPICIOUS" else "red")
    console.print(f"\nFinal: [{verdict_style}]{result.verdict}[/{verdict_style}] "
                  f"({result.confidence:.2f} confidence, {result.total_latency_ms:.0f}ms)")


@app.command()
def train(
    training_data: Path = typer.Argument(..., help="JSONL with {text, label} pairs"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Model output directory"),
) -> None:
    """Train/retrain SetFit classifier (Layer 4). Requires >= 8 examples per class."""
    from classifier import train as do_train
    result = do_train(training_data, output_dir)
    console.print(f"[green]Model trained[/green]: {result['examples']} examples → {result['model_dir']}")
    console.print(f"  Labels: {result['labels']}")
    console.print("[yellow]Note: 25 seed examples is minimal. Collect more via 'label' command.[/yellow]")


@app.command()
def label(
    conversation: Path = typer.Argument(..., help="Conversation JSONL to label"),
    output: Path = typer.Option(Path("labeled.jsonl"), "--output", "-o"),
) -> None:
    """Interactive labeling for training data."""
    entries = []
    for line in conversation.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("role") != "assistant":
            continue
        content = entry.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if not content.strip():
            continue
        entries.append(content.strip()[:500])

    labeled = []
    for i, text in enumerate(entries):
        console.print(f"\n[cyan]Turn {i+1}/{len(entries)}:[/cyan]")
        console.print(text[:200])
        label_choice = typer.prompt("Label (honest/gaming/drift/skip)", default="skip")
        if label_choice in ("honest", "gaming", "drift"):
            labeled.append({"text": text, "label": label_choice})

    with open(output, "w") as f:
        for item in labeled:
            f.write(json.dumps(item) + "\n")
    console.print(f"[green]Labeled {len(labeled)} turns[/green] → {output}")


@app.command()
def ingest(
    conversation: Path = typer.Argument(..., help="Conversation JSONL to analyze and store"),
) -> None:
    """Learn findings to /memory."""
    from cascade import run_cascade

    result = run_cascade(conversation_path=conversation)

    problem = f"lie-detection verdict: {result.verdict} ({len(result.flags)} flags)"
    solution = json.dumps(result.to_dict())

    try:
        proc = subprocess.run(
            ["bash", str(MEMORY_PATH / "run.sh"), "learn",
             "--problem", problem,
             "--solution", solution,
             "--tag", "lie_detection",
             "--tag", result.verdict.lower()],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if proc.returncode == 0:
            console.print("[green]Findings stored to /memory[/green]")
        else:
            logger.warning("/memory learn failed: {}", proc.stderr.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("could not store findings: {}", e)


@app.command()
def chain(
    context: str = typer.Argument(..., help="Context description for skill chain routing"),
) -> None:
    """Show which layers /recommend-skill-chain selects."""
    from skill_chain import get_verification_chain

    layers = get_verification_chain({"summary": context})
    console.print(f"[cyan]Verification chain:[/cyan] {' → '.join(layers)}")
    print(json.dumps({"layers": layers}))


@app.command()
def audit(
    session_file: Path = typer.Argument(..., help="Nico→Embry session JSONL to audit"),
    previous: Optional[Path] = typer.Option(None, "--previous", "-p", help="Previous run JSONL for cross-run regression detection"),
    no_store: bool = typer.Option(False, "--no-store", help="Don't store rewards to /memory"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write full audit JSON to file"),
) -> None:
    """Audit Nico→Embry sessions: find regressions, reward self-detection.

    The agent earns credit for catching its own lies. Each regression found
    generates a reward with: what went wrong, where, and how to prevent it.
    """
    from conversation_audit import audit_conversations

    result = audit_conversations(
        session_path=session_file,
        previous_path=previous,
        store_rewards=not no_store,
    )

    # Summary table
    table = Table(title="Conversation Audit")
    table.add_column("#", style="dim")
    table.add_column("Session", style="cyan", max_width=40)
    table.add_column("Grade")
    table.add_column("Verdict", style="bold")
    table.add_column("Regressions")
    table.add_column("Details", max_width=50)

    for i, s in enumerate(result.sessions, 1):
        v_style = "green" if s.verdict == "CLEAN" else ("red" if s.verdict == "MENDACIOUS" else "yellow")
        details = "; ".join(f"{r.regression_type}@t{r.turn_number}" for r in s.regressions) or "—"
        table.add_row(
            str(i), s.session_id[-30:], s.grade,
            f"[{v_style}]{s.verdict}[/{v_style}]",
            str(len(s.regressions)), details,
        )

    console.print(table)

    # Rewards summary
    if result.rewards:
        console.print(f"\n[green bold]Self-detection rewards: {len(result.rewards)} "
                      f"(total score: {result.summary['total_reward_score']:.1f})[/green bold]")
        for reward in result.rewards[:10]:
            console.print(f"  +{reward.reward_score:.1f} [{reward.regression.severity}] "
                          f"{reward.regression.regression_type}: {reward.regression.evidence[:80]}")
        if len(result.rewards) > 10:
            console.print(f"  ... and {len(result.rewards) - 10} more")

    # Cross-run regressions
    if result.cross_run_regressions:
        console.print(f"\n[yellow bold]Cross-run regressions: {len(result.cross_run_regressions)}[/yellow bold]")
        for cr in result.cross_run_regressions[:5]:
            console.print(f"  {cr['prev_grade']}→{cr['curr_grade']} "
                          f"({cr['delta']:+.4f}): {cr['question'][:60]}")

    # Summary
    s = result.summary
    console.print(f"\n{s['clean']}/{s['total_sessions']} clean ({s['clean_pct']}%), "
                  f"{s['total_regressions']} regressions, "
                  f"{s['rewards_earned']} rewards earned")

    # Write full JSON if requested
    if output:
        output.write_text(json.dumps(result.to_dict(), indent=2))
        console.print(f"\nFull audit → {output}")

    print(json.dumps(result.summary))


@app.command(name="install-hook")
def install_hook(
    repo: Path = typer.Argument(..., help="Git repo root to install pre-commit hook"),
    seal_file: Path = typer.Option(Path(".lie-detector-seal.json"), "--seal", "-s", help="Seal manifest path"),
) -> None:
    """Install git pre-commit hook that blocks edits to sealed files."""
    from sealed_grading import install_git_hook
    hook_path = install_git_hook(repo, seal_file)
    console.print(f"[green]Git hook installed[/green] → {hook_path}")
    console.print("  Commits modifying sealed files will be blocked.")


@app.command(name="self-seal")
def self_seal_cmd() -> None:
    """Create integrity seal of the lie-detector's own code (run once by human)."""
    from sealed_grading import self_seal
    self_seal()
    console.print("[green]Self-seal created.[/green] The lie-detector will now verify its own integrity.")


@app.command(name="self-verify")
def self_verify_cmd() -> None:
    """Verify the lie-detector's own code hasn't been tampered with."""
    from sealed_grading import self_verify
    result = self_verify()
    if result.verdict == "CLEAN":
        console.print("[green bold]CLEAN[/green bold] — lie-detector code is intact")
    else:
        console.print("[red bold]TAMPERED[/red bold] — lie-detector code has been modified")
        for tf in result.tampered_files:
            console.print(f"  [red]{tf.get('detail', tf.get('path', 'unknown'))}[/red]")
    raise typer.Exit(code=0 if result.verdict == "CLEAN" else 1)


if __name__ == "__main__":
    app()
