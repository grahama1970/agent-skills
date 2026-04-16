"""Vision evaluation CLI command for prompt-lab.

Evaluates prompts that take screenshots/images as input and produce
structured JSON output. Compares VLM output against expected JSON schema
and ground truth values.

Usage:
    prompt-lab eval-vision --prompt review_design_step1_audit \
        --images screenshots/*.png \
        --ground-truth ground_truth/design_review.json \
        --model vlm
"""
import asyncio
import json
import sys
from pathlib import Path

import typer
from loguru import logger

from pl_app import app, console

# Ensure this dir is importable
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import SKILL_DIR, ensure_dirs
from evaluation import load_prompt, load_models_config
from llm import call_vlm


def _load_ground_truth(gt_path: Path) -> dict:
    """Load ground truth JSON for vision eval."""
    if not gt_path.exists():
        return {}
    return json.loads(gt_path.read_text())


def _score_json_output(output: dict, ground_truth: dict) -> dict:
    """Score VLM JSON output against ground truth.

    Supports multiple scoring strategies:
    - schema_match: does the output have the expected keys?
    - value_match: do key values match expected values?
    - threshold: are numeric scores above expected thresholds?
    """
    scores = {}
    total_checks = 0
    passed_checks = 0

    # Schema match: check expected keys exist
    expected_keys = set(ground_truth.get("expected_keys", []))
    if expected_keys:
        output_keys = set(output.keys()) if isinstance(output, dict) else set()
        matched = expected_keys & output_keys
        scores["schema_match"] = len(matched) / len(expected_keys) if expected_keys else 1.0
        total_checks += len(expected_keys)
        passed_checks += len(matched)

    # Value match: check specific values
    expected_values = ground_truth.get("expected_values", {})
    if expected_values:
        value_hits = 0
        for key, expected in expected_values.items():
            actual = output.get(key) if isinstance(output, dict) else None
            if actual is not None:
                if isinstance(expected, list):
                    # Check if actual contains any expected value
                    if any(str(e).lower() in str(actual).lower() for e in expected):
                        value_hits += 1
                elif str(expected).lower() in str(actual).lower():
                    value_hits += 1
            total_checks += 1
        passed_checks += value_hits
        scores["value_match"] = value_hits / len(expected_values) if expected_values else 1.0

    # Contains check: does the output contain expected strings anywhere?
    expected_contains = ground_truth.get("expected_contains", [])
    if expected_contains:
        output_str = json.dumps(output).lower()
        contains_hits = sum(1 for s in expected_contains if s.lower() in output_str)
        scores["contains_match"] = contains_hits / len(expected_contains)
        total_checks += len(expected_contains)
        passed_checks += contains_hits

    # Threshold checks: numeric fields above minimum
    thresholds = ground_truth.get("thresholds", {})
    if thresholds:
        threshold_hits = 0
        for key, min_val in thresholds.items():
            actual = output.get(key) if isinstance(output, dict) else None
            if actual is not None and isinstance(actual, (int, float)):
                if actual >= min_val:
                    threshold_hits += 1
            total_checks += 1
        passed_checks += threshold_hits
        scores["threshold_match"] = threshold_hits / len(thresholds) if thresholds else 1.0

    # Overall score
    overall = passed_checks / total_checks if total_checks > 0 else 0.0
    scores["overall"] = overall
    scores["passed"] = passed_checks
    scores["total"] = total_checks

    return scores


@app.command("eval-vision")
def eval_vision(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt name (in prompts/ dir)"),
    images: list[str] = typer.Option([], "--images", "-i", help="Image file paths"),
    image_dir: str = typer.Option("", "--image-dir", help="Directory of images to include"),
    ground_truth: str = typer.Option("", "--ground-truth", "-g", help="Ground truth JSON file"),
    model: str = typer.Option("vlm", "--model", "-m", help="Model alias (default: vlm)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full VLM output"),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON"),
    seal: bool = typer.Option(False, "--seal", help="Seal the prompt with hash if eval passes"),
) -> None:
    """Evaluate a vision prompt against screenshots with ground truth scoring."""
    ensure_dirs()
    models_config = load_models_config()

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    # Load prompt — handle both [SYSTEM]/[USER] format and single-section prompts
    prompt_path = SKILL_DIR / "prompts" / f"{prompt}.txt"
    if not prompt_path.exists():
        console.print(f"[red]Prompt not found: {prompt_path}[/red]")
        raise typer.Exit(1)
    raw = prompt_path.read_text()
    if "[SYSTEM]" in raw and "[USER]" in raw:
        system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
    else:
        # Single-section prompt — strip prompt-lab headers, use as user message
        lines = raw.split("\n")
        content_lines = [l for l in lines if not l.startswith("# prompt-lab-")]
        user_template = "\n".join(content_lines).strip()
        # Load companion system prompt if it exists (e.g. review_design_system.txt)
        base = prompt.rsplit("_step", 1)[0] if "_step" in prompt else prompt
        sys_path = SKILL_DIR / "prompts" / f"{base}_system.txt"
        if sys_path.exists():
            sys_lines = sys_path.read_text().split("\n")
            system_prompt = "\n".join(l for l in sys_lines if not l.startswith("# prompt-lab-")).strip()
        else:
            system_prompt = "You are an expert UI/UX designer reviewing screenshots."

    # Collect images
    image_paths = list(images)
    if image_dir:
        img_dir = Path(image_dir)
        if img_dir.is_dir():
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                image_paths.extend(str(p) for p in sorted(img_dir.glob(ext)))

    if not image_paths:
        console.print("[red]No images provided. Use --images or --image-dir[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Vision Eval: prompt='{prompt}' model='{model}'[/bold]")
    console.print(f"Images: {len(image_paths)}")

    # Load ground truth
    gt = {}
    if ground_truth:
        gt_path = Path(ground_truth)
        if not gt_path.exists():
            # Try in ground_truth/ dir
            gt_path = SKILL_DIR / "ground_truth" / ground_truth
        if gt_path.exists():
            gt = _load_ground_truth(gt_path)
            console.print(f"Ground truth: {gt_path.name} ({len(gt)} keys)")
        else:
            console.print(f"[yellow]Ground truth not found: {ground_truth}[/yellow]")

    # Format user message (template may have {tokens_json}, {focus_areas} etc.)
    try:
        format_args = {k: v for k, v in gt.items() if isinstance(v, str)}
        format_args.setdefault("tokens_json", "{}")
        format_args.setdefault("focus_areas", "None specified")
        user_msg = user_template.format(**format_args)
    except (KeyError, IndexError):
        # Template has placeholders we can't fill — use raw
        user_msg = user_template

    # Call VLM via /review-design subprocess (handles image encoding + subagent routing)
    import subprocess as sp
    import time as _time
    console.print("[dim]Calling /review-design via subprocess...[/dim]")
    review_design_dir = SKILL_DIR.parent / "review-design"
    # Build --code-context args from ground truth if available
    code_context_args = []
    for f in gt.get("code_context_files", []):
        if Path(f).exists():
            code_context_args.extend(["-c", f])
    start_t = _time.perf_counter()
    try:
        cmd = ["python", "review_design.py", "review",
             "-s", str(Path(image_dir) if image_dir else Path(image_paths[0]).parent),
             "--persona", gt.get("persona", "nico-bailon"),
             "-n", "1", "--title", "prompt-lab-eval"] + code_context_args
        result = sp.run(cmd, capture_output=True, text=True, cwd=str(review_design_dir), timeout=300
        )
        latency = (_time.perf_counter() - start_t) * 1000
        # Read the output file
        output_dir = Path("/home/graham/workspace/experiments/embry-os/docs/review-output") / (Path(image_dir).name if image_dir else "eval")
        step1_file = output_dir / "round1_step1.md"
        if step1_file.exists():
            content = step1_file.read_text()
        else:
            content = result.stdout
    except Exception as e:
        console.print(f"[red]review-design subprocess failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Response: {len(content)} chars, {latency:.0f}ms[/dim]")

    # Parse JSON output
    try:
        output = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if json_match:
            try:
                output = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                output = {"raw_text": content}
        else:
            output = {"raw_text": content}

    if verbose:
        console.print("\n[bold]VLM Output:[/bold]")
        console.print(json.dumps(output, indent=2)[:2000])

    # Score against ground truth
    if gt:
        scores = _score_json_output(output, gt)
        overall = scores["overall"]

        console.print(f"\n[bold]Scores:[/bold]")
        for metric, value in scores.items():
            if metric in ("passed", "total"):
                continue
            color = "green" if value >= 0.7 else "yellow" if value >= 0.4 else "red"
            console.print(f"  [{color}]{metric}: {value:.2f}[/{color}]")

        console.print(f"\n[bold]Overall: {overall:.2f} ({scores['passed']}/{scores['total']} checks)[/bold]")

        passed = overall >= 0.7

        if json_output:
            print(json.dumps({
                "prompt": prompt,
                "model": model,
                "images": len(image_paths),
                "latency_ms": latency,
                "scores": scores,
                "passed": passed,
                "output": output,
            }, indent=2))

        # Seal if requested and passed
        if seal and passed:
            from prompt_hash import seal_prompt
            prompt_path = SKILL_DIR / "prompts" / f"{prompt}.txt"
            if prompt_path.exists():
                digest = seal_prompt(prompt_path, score=overall, model=model)
                console.print(f"\n[green]Prompt sealed: {digest[:16]}[/green]")
            else:
                console.print(f"[yellow]Cannot seal — prompt file not found: {prompt_path}[/yellow]")

        if not passed:
            console.print("\n[red]VISION EVAL FAILED — prompt needs iteration[/red]")
            raise typer.Exit(1)
        else:
            console.print("\n[green]VISION EVAL PASSED[/green]")
    else:
        # No ground truth — just show output
        console.print("\n[yellow]No ground truth provided — showing raw output only[/yellow]")
        if json_output:
            print(json.dumps({
                "prompt": prompt,
                "model": model,
                "images": len(image_paths),
                "latency_ms": latency,
                "output": output,
            }, indent=2))
