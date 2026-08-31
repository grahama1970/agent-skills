"""Tau-backed visual loop request builder for SVG work.

The command generated here routes creator/reviewer work through `$ask tau-dag` so
Tau owns provider/model dispatch, exposes a DAG viewer, and returns receipts.
This module deliberately does not call SciLLM directly.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TauVisualLoopPlan(BaseModel):
    """Saved launch packet for a Tau-backed SVG visual loop."""

    model_config = ConfigDict(extra="forbid")

    kind: str = "create_svg.tau_visual_loop_plan.v1"
    status: str
    created_at: str
    svg_path: str
    goal: str
    target: str
    target_size: str
    max_attempts: int
    screenshot_command: str
    visual_gate_command_template: str
    triage_error_command_template: str
    ticket_command_template: str
    context_files: list[str]
    creator_handler: str
    reviewer_handler: str
    ask_command: list[str]
    request_path: str
    ask_stdout_path: str | None = None
    ask_stderr_path: str | None = None
    ask_returncode: int | None = None
    run_dir: str | None = None
    tau_viewer_command: list[str] | None = None
    tau_viewer_returncode: int | None = None
    tau_viewer_stdout_path: str | None = None
    tau_viewer_stderr_path: str | None = None
    failure_codes: list[str] = Field(default_factory=list)
    proof_boundary: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _shell_join(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)


def _handler_family(handler: str) -> str:
    lowered = handler.lower()
    if "claude" in lowered:
        return "anthropic"
    if "gpt" in lowered or "codex" in lowered or "openai" in lowered:
        return "openai"
    if "kimi" in lowered or "moonshot" in lowered:
        return "moonshot"
    if "gemini" in lowered or "qwen" in lowered or "google" in lowered:
        return "google-qwen"
    if "grok" in lowered or "xai" in lowered:
        return "xai"
    if "deepseek" in lowered:
        return "deepseek"
    return lowered.split("-", 1)[0]


def _visual_gate_template(svg: Path, target: str, target_size: str, goal: str) -> str:
    return _shell_join(
        [
            str(_skill_root() / "run.sh"),
            "visual-gate",
            str(svg.resolve()),
            "<SCREENSHOT_PATH>",
            "--receipt",
            "<VISUAL_GATE_RECEIPT>",
            "--target",
            target,
            "--target-size",
            target_size,
            "--goal",
            goal,
            "--reviewer",
            "<REVIEWER_IDENTITY>",
            "--inspected-screenshot-sha256",
            "<SHA256_OF_SCREENSHOT_REVIEWER_INSPECTED>",
            "--inspected-screenshot-path",
            "<SCREENSHOT_PATH_REVIEWER_INSPECTED>",
            "--represents-goal|--does-not-represent-goal",
            "--attractive|--not-attractive",
            "--issue",
            "<VISIBLE_ISSUE>",
            "--next-edit",
            "<NEXT_EDIT>",
        ]
    )


def _triage_template() -> str:
    return _shell_join(
        [
            str(_repo_root() / "skills" / "triage-error" / "run.sh"),
            "classify",
            "--receipt",
            "<FAILING_RECEIPT_WITH_EXACT_CREATE_SVG_FAILURE_CODE>",
            "--layer",
            "create-svg",
        ]
    )


def _ticket_template(goal: str, target: str) -> str:
    title = "Repair create-svg Tau visual loop failure"
    return _shell_join(
        [
            str(_repo_root() / "skills" / "ticket" / "run.sh"),
            "bug",
            title,
            "--target",
            "skills/create-svg",
            "--observed",
            "<TRIAGED_FAILURE_CODE_AND_CAUSE>",
            "--expected",
            f"Tau visual loop reaches PASS only after target screenshot represents goal and is attractive for {target}.",
            "--repro",
            "<FAILING_TAU_VISUAL_LOOP_COMMAND_OR_RUN_DIR>",
            "--proof",
            "skills/agentic-evals/run.sh run skills/create-svg/fixtures/agentic_eval.json --output /mnt/storage12tb/skills/create-svg/outputs/agentic-eval.json",
            "--route",
            "backend_python_or_skill_runtime",
            "--agent",
            "agent-skill-maintainer",
            "--required-skill",
            "triage-error",
            "--required-skill",
            "agentic-evals",
            "--required-skill",
            "project-watchdog",
            "--context-file",
            "skills/create-svg/SKILL.md",
            "--context-file",
            "skills/create-svg/src/create_svg/tau_visual_loop.py",
            "--acceptance",
            goal,
        ]
    )


def build_visual_loop_request(
    *,
    svg: Path,
    goal: str,
    target: str,
    target_size: str,
    screenshot_command: str,
    max_attempts: int,
    context: str,
    creator_handler: str,
    reviewer_handler: str,
) -> str:
    """Render the immutable request body sent to `$ask tau-dag`."""

    context_block = context.strip() or "No extra project-state/context file was supplied."
    visual_gate_template = _visual_gate_template(svg, target, target_size, goal)
    triage_template = _triage_template()
    ticket_template = _ticket_template(goal, target)
    return f"""Create or repair the SVG at `{svg.resolve()}` through a bounded Tau visual loop.

Immutable goal: {goal}
Target surface: {target}
Target rendered size: {target_size}
Maximum attempts: {max_attempts}
Creator handler: {creator_handler}
Reviewer handler: {reviewer_handler}

Shared context for every node, including project-state when supplied:
{context_block}

Hard closure rule:
- Every attempt must render the SVG in the target surface with this exact screenshot command:
  `{screenshot_command}`
- The reviewer must inspect the produced screenshot bytes. The screenshot is the authority.
- The reviewer must compute and cite the SHA256 of the exact screenshot they inspected.
- The attempt is accepted only when this visual gate command exits 0:
  `{visual_gate_template}`
- `visual-gate` must pass both `represents_goal` and `attractive`, and its `--inspected-screenshot-sha256` / `--inspected-screenshot-path` must match the rendered screenshot argument.
- If either is false, the reviewer must write visible issues and the next edit, and the creator must revise the SVG before the next attempt.
- Stop with NEEDS_ATTENTION after {max_attempts} attempts if no screenshot passes.
- Do not push, publish, or claim completion inside this DAG. The project agent applies scoped git transport only after Tau receipt, visual-gate PASS, local build, and deployment checks pass.

Creator node contract:
1. Use `$create-svg` and `$best-practices-svg-design`; do not freehand a detached image outside those contracts.
2. Read the shared context and immutable goal before editing.
3. Edit only the SVG or explicitly allowed layout files named by the project agent.
4. Preserve self-contained SVG constraints: no JavaScript, no external resources, reduced-motion fallback, accessible title/desc.
5. Prefer component groups with stable `id` and `data-component` over loose primitives.
6. Use the prior screenshot's visible failures as the next edit; do not make unrelated changes.

Reviewer node contract:
1. Use `$surf` and `$best-practices-svg-design`.
2. Be a different provider family from the creator. This run requested creator `{creator_handler}` and reviewer `{reviewer_handler}`.
3. Read the target screenshot artifact for every attempt; do not review from source alone.
4. Judge exactly two acceptance questions: does it represent the goal, and is it attractive at target size?
5. Run `sha256sum <SCREENSHOT_PATH>` after inspecting the image and pass that exact hash to `visual-gate`.
6. Run `visual-gate` with PASS flags only when both answers are yes.
7. If not ready, run `visual-gate` with failing flags plus concrete `--issue` and `--next-edit` values.
8. Do not accept SVG source, hashes, browser-load status, build output, DOM dimensions, or model prose as a substitute for the screenshot.

Error path:
- On any generic, ambiguous, missing-receipt, screenshot, Tau viewer, Surf, Ask, or visual-gate failure, run:
  `{triage_template}`
- If the triaged issue is a skill/runtime defect or recurs after one focused repair, file a project-watchdog-routable ticket using:
  `{ticket_template}`
- Add or update an `$agentic-evals` case before closing the ticket so the failure cannot regress.
"""


def run_plan(
    *,
    svg: Path,
    goal: str,
    target: str,
    target_size: str,
    screenshot_command: str,
    max_attempts: int,
    context_files: list[Path],
    repo: str,
    creator_handler: str,
    reviewer_handler: str,
    run_output_root: Path,
    ask_id: str | None,
    execute: bool,
    allow_provider_calls: bool,
    poll_timeout_seconds: float,
    open_viewer: bool,
    receipt: Path,
) -> TauVisualLoopPlan:
    """Create a Tau visual-loop launch receipt and optionally execute Ask."""

    if max_attempts < 1 or max_attempts > 10:
        raise ValueError("max_attempts must be between 1 and 10")
    if _handler_family(creator_handler) == _handler_family(reviewer_handler):
        raise ValueError("creator_handler and reviewer_handler must be different provider families")

    context_parts: list[str] = []
    resolved_context_files: list[Path] = []
    for path in context_files:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"context file not found: {resolved}")
        resolved_context_files.append(resolved)
        text = resolved.read_text(encoding="utf-8", errors="replace")
        context_parts.append(f"\n--- Context file: {resolved} ---\n{text[:12000]}")

    request = build_visual_loop_request(
        svg=svg,
        goal=goal,
        target=target,
        target_size=target_size,
        screenshot_command=screenshot_command,
        max_attempts=max_attempts,
        context="\n".join(context_parts),
        creator_handler=creator_handler,
        reviewer_handler=reviewer_handler,
    )
    run_output_root = run_output_root.resolve()
    run_output_root.mkdir(parents=True, exist_ok=True)
    request_path = receipt.resolve().with_suffix(".request.md")
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(request, encoding="utf-8")

    ask_command = build_ask_command(
        request=request,
        repo=repo,
        target=target,
        goal=goal,
        creator_handler=creator_handler,
        reviewer_handler=reviewer_handler,
        run_output_root=run_output_root,
        ask_id=ask_id,
        attach_files=resolved_context_files,
        execute=execute,
        allow_provider_calls=allow_provider_calls,
        poll_timeout_seconds=poll_timeout_seconds,
    )
    plan = TauVisualLoopPlan(
        status="PLANNED",
        created_at=datetime.now(timezone.utc).isoformat(),
        svg_path=str(svg.resolve()),
        goal=goal,
        target=target,
        target_size=target_size,
        max_attempts=max_attempts,
        screenshot_command=screenshot_command,
        visual_gate_command_template=_visual_gate_template(svg, target, target_size, goal),
        triage_error_command_template=_triage_template(),
        ticket_command_template=_ticket_template(goal, target),
        context_files=[str(path) for path in resolved_context_files],
        creator_handler=creator_handler,
        reviewer_handler=reviewer_handler,
        ask_command=ask_command,
        request_path=str(request_path),
        proof_boundary="This command builds or runs an Ask/Tau DAG request. Closure still requires Tau receipts, an opened Tau DAG viewer for human inspection, and a PASS create-svg.visual_gate.v1 receipt from the target screenshot.",
    )

    if execute:
        stdout_path = receipt.resolve().with_suffix(".ask.stdout.json")
        stderr_path = receipt.resolve().with_suffix(".ask.stderr.txt")
        completed = subprocess.run(ask_command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        run_dir = None
        try:
            payload = json.loads(completed.stdout)
            run_dir = payload.get("run_dir") or payload.get("run_directory")
        except json.JSONDecodeError:
            run_dir = None
        update = {
            "status": "EXECUTED" if completed.returncode == 0 else "NEEDS_ATTENTION",
            "ask_stdout_path": str(stdout_path),
            "ask_stderr_path": str(stderr_path),
            "ask_returncode": completed.returncode,
            "run_dir": run_dir,
            "tau_viewer_command": [str(_repo_root() / "skills" / "tau" / "run.sh"), "dag-view", run_dir] if run_dir else None,
        }
        if run_dir and open_viewer:
            viewer_stdout = receipt.resolve().with_suffix(".viewer.stdout.txt")
            viewer_stderr = receipt.resolve().with_suffix(".viewer.stderr.txt")
            viewer_command = [str(_repo_root() / "skills" / "tau" / "run.sh"), "dag-view", run_dir]
            viewed = subprocess.run(viewer_command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            viewer_stdout.write_text(viewed.stdout, encoding="utf-8")
            viewer_stderr.write_text(viewed.stderr, encoding="utf-8")
            update.update(
                {
                    "tau_viewer_returncode": viewed.returncode,
                    "tau_viewer_stdout_path": str(viewer_stdout),
                    "tau_viewer_stderr_path": str(viewer_stderr),
                    "status": "NEEDS_ATTENTION" if viewed.returncode != 0 else update["status"],
                }
            )
        plan = plan.model_copy(update=update)

    receipt.resolve().parent.mkdir(parents=True, exist_ok=True)
    receipt.resolve().write_text(json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan
