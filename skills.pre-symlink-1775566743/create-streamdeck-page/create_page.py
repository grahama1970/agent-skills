#!/usr/bin/env python3
"""create-streamdeck-page: Create, evaluate, and optimize Stream Deck pages.

Shells out to the streamdeck CLI for actual hardware interaction.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

STREAMDECK_ROOT = Path.home() / "workspace" / "streamdeck"
STREAMDECK_CLI = STREAMDECK_ROOT / ".venv" / "bin" / "streamdeck-cli"
TEMPLATES_DIR = STREAMDECK_ROOT / "config" / "page_templates"
SKILL_DIR = Path(__file__).parent
GROUND_TRUTH_DIR = SKILL_DIR / "ground_truth"
LAYOUTS_DIR = SKILL_DIR / "layouts"
RESULTS_DIR = SKILL_DIR / "results"


def _run_cli(*args) -> subprocess.CompletedProcess:
    """Run a streamdeck CLI command."""
    cmd = [str(STREAMDECK_CLI)] + list(args)
    logger.debug(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)


import typer
from typing import Optional

app = typer.Typer()


@app.command("create")
def cmd_create(
    context: Optional[str] = typer.Option(None, help="App context (e.g. browser, terminal)"),
    workflows: Optional[str] = typer.Option(None, help="Comma-separated workflow names"),
    from_template: Optional[str] = typer.Option(None, "--from-template", help="Deploy from existing template"),
    interactive: bool = typer.Option(False, "--interactive"),
    page: Optional[int] = typer.Option(None, help=""),
):
    if from_template:
        cli_args = ["page", "create", from_template, "--from-template", from_template]
        if page is not None:
            cli_args.extend(["--page", str(page)])
        result = _run_cli(*cli_args)
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
        return

    if interactive:
        print("Interactive page creation:")
        print("Enter button definitions as JSON (one per line, empty line to finish):")
        buttons = []
        while True:
            line = input("> ").strip()
            if not line:
                break
            try:
                buttons.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Invalid JSON: {e}")

        if not buttons:
            print("No buttons defined.")
            return

        # Pipe JSON to CLI
        json_str = json.dumps(buttons)
        cmd = [str(STREAMDECK_CLI), "page", "create", "interactive"]
        if page is not None:
            cmd.extend(["--page", str(page)])
        proc = subprocess.run(cmd, input=json_str, capture_output=True, text=True)
        print(proc.stdout)
        return

    if context and workflows:
        workflow_list = [w.strip() for w in workflows.split(",")]
        buttons = []
        for wf in workflow_list:
            buttons.append({"text": wf, "command": f"echo {wf}"})
        json_str = json.dumps(buttons)

        cmd = [str(STREAMDECK_CLI), "page", "create", f"{context}_page"]
        if page is not None:
            cmd.extend(["--page", str(page)])
        proc = subprocess.run(cmd, input=json_str, capture_output=True, text=True)
        print(proc.stdout)
        return

    print("Specify --from-template, --interactive, or --context + --workflows")


@app.command("deploy")
def cmd_deploy(
    template: str = typer.Option(..., help=""),
    page: int = typer.Option(..., help=""),
):
    result = _run_cli("page", "create", template, "--from-template", template, "--page", str(page))
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)


@app.command("evaluate")
def cmd_evaluate(
    template: str = typer.Option(..., help=""),
    ground_truth: str = typer.Option("contexts.json", "--ground-truth", help=""),
):
    gt_path = GROUND_TRUTH_DIR / ground_truth
    if not gt_path.exists():
        print(f"Ground truth not found: {gt_path}")
        sys.exit(1)

    template_path = TEMPLATES_DIR / f"{template}.json"
    if not template_path.exists():
        print(f"Template not found: {template_path}")
        sys.exit(1)

    gt_data = json.loads(gt_path.read_text())
    template_data = json.loads(template_path.read_text())

    template_buttons = {b.get("text", "").lower() for b in template_data.get("buttons", []) if b.get("text")}

    total = len(gt_data)
    matched = 0
    missing_all = []

    for case in gt_data:
        expected = set(b.lower() for b in case.get("expected_buttons", []))
        found = expected & template_buttons
        missing = expected - template_buttons
        coverage = len(found) / len(expected) if expected else 1.0

        if coverage >= 0.8:
            matched += 1
        if missing:
            missing_all.extend(missing)

    score = matched / total if total else 0
    print(f"Template: {template}")
    print(f"Score: {score:.0%} ({matched}/{total} cases passed)")
    if missing_all:
        print(f"Missing buttons: {', '.join(sorted(set(missing_all)))}")

    # Save result
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "template": template,
        "score": score,
        "matched": matched,
        "total": total,
        "missing": sorted(set(missing_all)),
        "timestamp": datetime.now().isoformat(),
    }
    result_path = RESULTS_DIR / f"{template}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result_path.write_text(json.dumps(result, indent=2))
    print(f"Result saved: {result_path}")


@app.command("optimize")
def cmd_optimize(
    template: str = typer.Option(..., help=""),
    rounds: int = typer.Option(3, help=""),
    ground_truth: str = typer.Option("contexts.json", "--ground-truth", help=""),
):
    for i in range(1, rounds + 1):
        print(f"\n--- Round {i}/{rounds} ---")
        cmd_evaluate(template=template, ground_truth=ground_truth)
        # In a full implementation, this would feed errors back to an LLM
        # to generate improved layouts. For now, just report.
        print(f"(Self-correction would apply here in round {i})")


@app.command("history")
def cmd_history(
    template: str = typer.Option(..., help=""),
):
    results = sorted(RESULTS_DIR.glob(f"{template}_*.json"))
    if not results:
        print(f"No results found for template '{template}'")
        return

    print(f"History for '{template}':")
    for r in results:
        data = json.loads(r.read_text())
        print(f"  {data['timestamp']}: {data['score']:.0%} ({data['matched']}/{data['total']})")


if __name__ == "__main__":
    app()
