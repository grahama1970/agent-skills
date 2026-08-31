"""Thin Typer CLI for README SVG generation, inspection, preview, and validation.

Business logic lives in named modules. CLI failures are logged with Loguru and exit
non-zero; successful commands print concrete artifact paths or typed receipts.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
import yaml
from loguru import logger

from .inspect_style import inspect_sources
from .io import available_templates, load_theme, template_path
from .preview import write_preview
from .render import render_scene_file
from .tau_provenance_gate import evaluate_tau_variant_provenance
from .tau_variant_loop import VariantDirection, failure_code_catalog, run_variant_plan
from .tau_visual_loop import run_plan
from .validate import validate_svg_file, verify_scene_file
from .visual_gate import VisualVerdict, evaluate_visual_gate

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _write_receipt(path: Path | None, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if path is None:
        typer.echo(rendered)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + "\n", encoding="utf-8")
    typer.echo(str(path))


@app.command("templates")
def list_templates() -> None:
    """List bundled semantic scene templates."""

    for name in available_templates():
        typer.echo(name)


@app.command()
def new(
    template: str = typer.Argument(..., help="Bundled template name"),
    output: Path = typer.Argument(..., help="Destination scene YAML"),
    force: bool = typer.Option(False, "--force", help="Replace an existing destination"),
) -> None:
    """Copy a starter semantic scene."""

    try:
        source = template_path(template)
        if output.exists() and not force:
            raise ValueError(f"destination exists; pass --force to replace it: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        typer.echo(str(output))
    except Exception as exc:
        logger.error("new command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def render(
    scene: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Argument(...),
) -> None:
    """Compile one validated scene into deterministic SVG."""

    try:
        render_scene_file(scene.resolve(), output.resolve())
        typer.echo(str(output.resolve()))
    except Exception as exc:
        logger.error("render command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def verify(
    scene: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Argument(...),
    receipt: Path = typer.Option(..., "--receipt", help="JSON validation receipt"),
    browser: bool = typer.Option(False, "--browser/--no-browser", help="Run real Chromium img-mode verification"),
) -> None:
    """Render twice, compare bytes, validate, and optionally verify in Chromium."""

    try:
        result = verify_scene_file(scene.resolve(), output.resolve(), browser=browser)
        _write_receipt(receipt.resolve(), result.model_dump(mode="json"))
        typer.echo(result.status)
        if result.status != "PASS":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.error("verify command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def validate(
    svg: Path = typer.Argument(..., exists=True, dir_okay=False),
    receipt: Path | None = typer.Option(None, "--receipt", help="Optional JSON receipt path"),
    theme: str | None = typer.Option(None, "--theme", help="Bundled theme name or YAML path"),
    strict_theme: bool = typer.Option(False, "--strict-theme", help="Reject colors and stroke widths outside the theme"),
    browser: bool = typer.Option(False, "--browser/--no-browser", help="Run real Chromium img-mode verification"),
) -> None:
    """Validate an existing SVG and fail closed on any error finding."""

    try:
        loaded_theme = load_theme(theme, Path.cwd()) if theme else None
        result = validate_svg_file(
            svg.resolve(),
            theme=loaded_theme,
            strict_theme=strict_theme,
            browser=browser,
        )
        _write_receipt(receipt.resolve() if receipt else None, result.model_dump(mode="json"))
        typer.echo(result.status)
        if result.status != "PASS":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.error("validate command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def inspect(
    sources: list[Path] = typer.Argument(..., exists=True),
    output: Path = typer.Option(..., "--output", help="YAML inspection report"),
) -> None:
    """Extract visual-system evidence from SVG files or directories."""

    try:
        report = inspect_sources(tuple(path.resolve() for path in sources))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
        typer.echo(str(output.resolve()))
    except Exception as exc:
        logger.error("inspect command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def preview(
    svg: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Argument(...),
) -> None:
    """Write a local self-contained HTML viewer."""

    try:
        write_preview(svg.resolve(), output.resolve())
        typer.echo(str(output.resolve()))
    except Exception as exc:
        logger.error("preview command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def snippet(
    svg: Path = typer.Argument(...),
    alt: str = typer.Option(..., "--alt", help="Meaningful image description"),
    width: int = typer.Option(850, "--width", min=1, max=4000),
) -> None:
    """Print centered README HTML without modifying README.md."""

    escaped_path = str(svg).replace("&", "&amp;").replace('"', "&quot;")
    escaped_alt = alt.replace("&", "&amp;").replace('"', "&quot;")
    typer.echo(
        "<p align=\"center\">\n"
        f"  <img src=\"{escaped_path}\" alt=\"{escaped_alt}\" width=\"{width}\">\n"
        "</p>"
    )


@app.command("visual-gate")
def visual_gate(
    svg: Path = typer.Argument(..., exists=True, dir_okay=False),
    screenshot: Path = typer.Argument(..., exists=True, dir_okay=False),
    receipt: Path = typer.Option(..., "--receipt", help="create_svg.visual_gate.v1 receipt path"),
    target: str = typer.Option(..., "--target", help="Target surface being reviewed"),
    target_size: str = typer.Option(..., "--target-size", help="Rendered target size, e.g. 400x260"),
    goal: str = typer.Option(..., "--goal", help="Immutable visual goal"),
    reviewer: str = typer.Option(..., "--reviewer", help="Reviewer identity/provider"),
    inspected_screenshot_sha256: str = typer.Option(..., "--inspected-screenshot-sha256"),
    inspected_screenshot_path: Path = typer.Option(..., "--inspected-screenshot-path"),
    represents_goal: bool = typer.Option(False, "--represents-goal/--does-not-represent-goal"),
    attractive: bool = typer.Option(False, "--attractive/--not-attractive"),
    issue: list[str] | None = typer.Option(None, "--issue", help="Concrete visible issue; repeatable"),
    next_edit: str = typer.Option("", "--next-edit", help="Next visual edit when NOT_READY"),
) -> None:
    """Fail closed unless a reviewer inspected the exact target screenshot."""

    try:
        verdict = VisualVerdict(
            screenshot_sha256=inspected_screenshot_sha256,
            inspected_screenshot_path=str(inspected_screenshot_path),
            reviewer=reviewer,
            represents_goal=represents_goal,
            attractive=attractive,
            issues=issue or [],
            next_edit=next_edit,
        )
        result = evaluate_visual_gate(
            svg=svg.resolve(),
            screenshot=screenshot.resolve(),
            target=target,
            target_size=target_size,
            goal=goal,
            verdict=verdict,
        )
        _write_receipt(receipt.resolve(), result.model_dump(mode="json"))
        typer.echo(result.status)
        if result.status != "PASS":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.error("visual-gate command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command("tau-provenance-gate")
def tau_provenance_gate(
    launch_receipt: Path = typer.Argument(..., exists=True, dir_okay=False, help="create_svg.tau_variant_loop_plan.v1 launch receipt"),
    svg: Path = typer.Argument(..., exists=True, dir_okay=False, help="SVG artifact proposed as Tau-produced output"),
    candidate_receipt: Path = typer.Option(..., "--candidate-receipt", help="create_svg.variant_candidate.v1 receipt path"),
    visual_gate_receipt: Path = typer.Option(..., "--visual-gate-receipt", help="create_svg.visual_gate.v1 PASS receipt path"),
    receipt: Path = typer.Option(..., "--receipt", help="create_svg.tau_variant_provenance_gate.v1 receipt path"),
    creator_node_id: str = typer.Option(..., "--creator-node-id", help="Tau creator node id that produced the SVG"),
    judge_node_id: str = typer.Option("judge", "--judge-node-id", help="Tau judge/reviewer node id that accepted the SVG"),
) -> None:
    """Fail closed unless a Tau variant SVG is receipt- and screenshot-bound."""

    try:
        result = evaluate_tau_variant_provenance(
            launch_receipt=launch_receipt.resolve(),
            svg=svg.resolve(),
            candidate_receipt=candidate_receipt,
            visual_gate_receipt=visual_gate_receipt,
            creator_node_id=creator_node_id,
            judge_node_id=judge_node_id,
        )
        _write_receipt(receipt.resolve(), result.model_dump(mode="json"))
        typer.echo(result.status)
        if result.status != "PASS":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(str(exc), err=True)
        logger.error("tau-provenance-gate command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command("tau-visual-loop")
def tau_visual_loop(
    svg: Path = typer.Argument(..., help="SVG path to create or repair"),
    goal: str = typer.Option(..., "--goal", help="Immutable visual goal"),
    target: str = typer.Option(..., "--target", help="Target surface"),
    target_size: str = typer.Option(..., "--target-size", help="Rendered target size"),
    screenshot_command: str = typer.Option(..., "--screenshot-command", help="Exact command that captures the target screenshot"),
    receipt: Path = typer.Option(..., "--receipt", help="Launch receipt path"),
    context_file: list[Path] | None = typer.Option(None, "--context-file", help="Shared context file; repeatable"),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo"),
    creator_handler: str = typer.Option("gpt-5.5-high", "--creator-handler"),
    reviewer_handler: str = typer.Option("claude-fable-low", "--reviewer-handler"),
    max_attempts: int = typer.Option(3, "--max-attempts", min=1, max=10),
    run_output_root: Path = typer.Option(Path("/mnt/storage12tb/skills/create-svg/outputs/tau-visual-loops"), "--run-output-root"),
    ask_id: str | None = typer.Option(None, "--ask-id"),
    execute: bool = typer.Option(False, "--execute/--plan-only"),
    allow_provider_calls: bool = typer.Option(False, "--allow-provider-calls/--no-provider-calls"),
    poll_timeout_seconds: float = typer.Option(120.0, "--poll-timeout-seconds"),
    open_viewer: bool = typer.Option(False, "--open-viewer/--no-open-viewer"),
) -> None:
    """Build or run the sequential Tau creator/reviewer SVG loop."""

    try:
        result = run_plan(
            svg=svg,
            goal=goal,
            target=target,
            target_size=target_size,
            screenshot_command=screenshot_command,
            max_attempts=max_attempts,
            context_files=context_file or [],
            repo=repo,
            creator_handler=creator_handler,
            reviewer_handler=reviewer_handler,
            run_output_root=run_output_root,
            ask_id=ask_id,
            execute=execute,
            allow_provider_calls=allow_provider_calls,
            poll_timeout_seconds=poll_timeout_seconds,
            open_viewer=open_viewer,
            receipt=receipt,
        )
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
        if result.status == "NEEDS_ATTENTION":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.error("tau-visual-loop command failed: {}", exc)
        raise typer.Exit(code=1) from exc


def _load_variant_spec(path: Path) -> list[VariantDirection]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != "create_svg.variant_pack.v1":
        raise ValueError("create_svg_variant_count_invalid: variant spec schema must be create_svg.variant_pack.v1")
    raw_variants = payload.get("variants")
    if not isinstance(raw_variants, list):
        raise ValueError("create_svg_variant_count_invalid: variants must be a list")
    return [VariantDirection.model_validate(item) for item in raw_variants]


@app.command("tau-variant-loop")
def tau_variant_loop(
    variants: Path = typer.Argument(..., exists=True, dir_okay=False, help="create_svg.variant_pack.v1 YAML"),
    goal: str = typer.Option(..., "--goal", help="Immutable visual goal"),
    target: str = typer.Option(..., "--target", help="Target surface"),
    target_size: str = typer.Option(..., "--target-size", help="Rendered target size"),
    screenshot_command: str = typer.Option(..., "--screenshot-command", help="Exact command that captures each target screenshot"),
    receipt: Path = typer.Option(..., "--receipt", help="Launch receipt path"),
    creator_handler: list[str] | None = typer.Option(None, "--creator-handler", help="Creator handler; repeat once per variant unless variants.yml embeds handlers"),
    judge_handler: str = typer.Option("claude-fable-low", "--judge-handler", help="Independent judge handler"),
    reviewer: list[str] | None = typer.Option(None, "--reviewer", help="Optional lens reviewer handler=criterion; repeatable"),
    criterion: list[str] | None = typer.Option(None, "--criterion", help="Judge criterion; repeatable"),
    context_file: list[Path] | None = typer.Option(None, "--context-file", help="Shared context file; repeatable"),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo"),
    max_attempts: int = typer.Option(3, "--max-attempts", min=1, max=10),
    run_output_root: Path = typer.Option(Path("/mnt/storage12tb/skills/create-svg/outputs/tau-variant-loops"), "--run-output-root"),
    ask_id: str | None = typer.Option(None, "--ask-id"),
    execute: bool = typer.Option(False, "--execute/--plan-only"),
    allow_provider_calls: bool = typer.Option(False, "--allow-provider-calls/--no-provider-calls"),
    poll_timeout_seconds: float = typer.Option(120.0, "--poll-timeout-seconds"),
    open_viewer: bool = typer.Option(False, "--open-viewer/--no-open-viewer"),
) -> None:
    """Build or run a Tau compete DAG with N concurrent SVG creator variants."""

    try:
        result = run_variant_plan(
            goal=goal,
            target=target,
            target_size=target_size,
            screenshot_command=screenshot_command,
            max_attempts=max_attempts,
            context_files=context_file or [],
            variants=_load_variant_spec(variants.resolve()),
            repo=repo,
            creator_handlers=creator_handler or [],
            judge_handler=judge_handler,
            reviewer_specs=reviewer or [],
            criteria=criterion or ["goal representation at target size", "visual attractiveness at target size"],
            run_output_root=run_output_root,
            ask_id=ask_id,
            execute=execute,
            allow_provider_calls=allow_provider_calls,
            poll_timeout_seconds=poll_timeout_seconds,
            open_viewer=open_viewer,
            receipt=receipt,
        )
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
        if result.status == "NEEDS_ATTENTION":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(str(exc), err=True)
        logger.error("tau-variant-loop command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command("failure-codes")
def failure_codes() -> None:
    """Print exact create-svg failure codes for triage-error."""

    typer.echo(json.dumps([code.model_dump(mode="json") for code in failure_code_catalog()], indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
