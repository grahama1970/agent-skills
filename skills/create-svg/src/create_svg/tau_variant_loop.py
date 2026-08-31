"""Tau-backed concurrent SVG variant fanout request builder.

This module emits `$ask tau-dag compete` launch receipts for N concurrent creator
candidates. It deliberately does not call SciLLM directly.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .tau_visual_loop import _handler_family, _repo_root, _shell_join, _skill_root, _ticket_template, _triage_template


class VariantDirection(BaseModel):
    """One bounded visual hypothesis assigned to one Tau creator node."""

    model_config = ConfigDict(extra="forbid")

    id: str
    direction: str
    handler: str | None = None


class TriageFailureCode(BaseModel):
    """Exact failure code surfaced for triage-error without prose scraping."""

    model_config = ConfigDict(extra="forbid")

    code: str
    layer: str = "create-svg"
    cause: str
    next_command: str
    recoverable: bool


class TauVariantLoopPlan(BaseModel):
    """Saved launch packet for N concurrent Tau SVG creator candidates."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["create_svg.tau_variant_loop_plan.v1"] = "create_svg.tau_variant_loop_plan.v1"
    status: Literal["PLANNED", "EXECUTED", "NEEDS_ATTENTION"]
    created_at: str
    goal: str
    target: str
    target_size: str
    max_attempts: int
    screenshot_command: str
    visual_gate_command_template: str
    triage_error_command_template: str
    ticket_command_template: str
    context_files: list[str]
    variants: list[VariantDirection]
    creator_handlers: list[str]
    judge_handler: str
    reviewer_specs: list[str]
    criteria: list[str]
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
    active_failure_code: str | None = None
    failure_codes: list[TriageFailureCode] = Field(default_factory=list)
    proof_boundary: str


_CREATE_SVG_FAILURE_CODES: tuple[TriageFailureCode, ...] = (
    TriageFailureCode(
        code="create_svg_variant_count_invalid",
        cause="A Tau SVG variant fanout requested malformed YAML, duplicate ids, fewer than two variants, or more than five concurrent creator candidates.",
        next_command="Fix variants.yml so it is valid create_svg.variant_pack.v1 YAML with 2..5 unique variants, then rerun create-svg tau-variant-loop before any provider execution.",
        recoverable=True,
    ),
    TriageFailureCode(
        code="create_svg_variant_handler_count_mismatch",
        cause="The Tau SVG variant fanout could not bind exactly one creator handler to each requested variant direction.",
        next_command="Pass one --creator-handler per variant, or put handler on every variants.yml entry, then rerun create-svg tau-variant-loop.",
        recoverable=True,
    ),
    TriageFailureCode(
        code="create_svg_variant_handler_family_overlap",
        cause="The Tau SVG variant fanout reused the same provider family for a creator and the judge, weakening independent visual adjudication.",
        next_command="Choose a --judge-handler from a different provider family than every creator handler, then rerun create-svg tau-variant-loop.",
        recoverable=True,
    ),
    TriageFailureCode(
        code="create_svg_tau_compile_or_execute_failed",
        cause="The create-svg Tau variant loop compile or execute command returned non-zero or did not emit a readable Tau run directory.",
        next_command="Run skills/triage-error/run.sh classify --receipt <receipt.ask.stderr.txt> --layer create-svg; if the classified code is ambiguous, file a skills/ticket bug with the receipt and scaffold an agentic eval.",
        recoverable=True,
    ),
    TriageFailureCode(
        code="create_svg_visual_gate_not_ready",
        cause="A rendered SVG candidate was screenshot-reviewed and failed goal representation or target-size attractiveness.",
        next_command="Use the visual-gate receipt issues and next_edit fields as the next variant direction; do not classify this as a runtime/tool defect unless the gate receipt itself is malformed.",
        recoverable=True,
    ),
)


def failure_code_catalog() -> list[TriageFailureCode]:
    """Return create-svg failure codes emitted for triage-error classification."""

    return list(_CREATE_SVG_FAILURE_CODES)


def _variant_visual_gate_template(target: str, target_size: str, goal: str) -> str:
    return _shell_join(
        [
            str(_skill_root() / "run.sh"),
            "visual-gate",
            "<WINNING_SVG_PATH>",
            "<WINNING_SCREENSHOT_PATH>",
            "--receipt",
            "<VISUAL_GATE_RECEIPT>",
            "--target",
            target,
            "--target-size",
            target_size,
            "--goal",
            goal,
            "--reviewer",
            "<JUDGE_IDENTITY>",
            "--inspected-screenshot-sha256",
            "<SHA256_OF_SCREENSHOT_JUDGE_INSPECTED>",
            "--inspected-screenshot-path",
            "<SCREENSHOT_PATH_JUDGE_INSPECTED>",
            "--represents-goal|--does-not-represent-goal",
            "--attractive|--not-attractive",
            "--issue",
            "<VISIBLE_ISSUE>",
            "--next-edit",
            "<NEXT_EDIT>",
        ]
    )


def _variant_table(variants: list[VariantDirection], handlers: list[str]) -> str:
    rows = []
    for index, (variant, handler) in enumerate(zip(variants, handlers, strict=True), start=1):
        rows.append(f"{index}. `{variant.id}` -> handler `{handler}` -> direction: {variant.direction}")
    return "\n".join(rows)


def build_variant_loop_request(
    *,
    goal: str,
    target: str,
    target_size: str,
    screenshot_command: str,
    max_attempts: int,
    context: str,
    variants: list[VariantDirection],
    creator_handlers: list[str],
    judge_handler: str,
) -> str:
    """Render the immutable request body for a concurrent creator fanout."""

    context_block = context.strip() or "No extra project-state/context file was supplied."
    variant_assignments = _variant_table(variants, creator_handlers)
    codes = "\n".join(
        f"- `{code.code}`: {code.cause} Next: {code.next_command}" for code in _CREATE_SVG_FAILURE_CODES
    )
    return f"""Create N concurrent SVG design candidates through a Tau compete DAG.

Immutable goal: {goal}
Target surface: {target}
Target rendered size: {target_size}
Maximum attempts per candidate: {max_attempts}
Judge handler: {judge_handler}

Variant assignment table. Each creator must produce ONLY its assigned variant id:
{variant_assignments}

Shared context for every node, including project-state when supplied:
{context_block}

Creator node contract:
1. Use `$create-svg` and `$best-practices-svg-design`; do not freehand a detached raster or unconstrained SVG.
2. Produce one self-contained SVG candidate for the assigned variant id only.
3. Encode the assigned direction visibly; do not converge toward the other variants.
4. Preserve README/project-card constraints: no JavaScript, no external resources, accessible title/desc, reduced-motion fallback.
5. Return exactly one fenced SVG payload in a ```svg code block. The payload must start with `<svg` and end with `</svg>`.
6. Return a machine-readable candidate receipt containing `schema: create_svg.variant_candidate.v1`, `variant_id`, `handler`, `svg_path`, `direction`, `mocked`, `live`, and concrete proof commands.
7. Do not claim visual acceptance. Only the judge/reviewer plus visual-gate can accept a candidate.

Screenshot and gate contract:
- Every candidate must be rendered in the target surface with this exact screenshot command:
  `{screenshot_command}`
- The screenshot is the visual authority. The judge must inspect screenshot bytes for every candidate before choosing a winner.
- The judge must compute and cite the SHA256 of every screenshot inspected.
- The winning candidate is accepted only when `$create-svg visual-gate` exits 0 with a receipt bound to the winning screenshot path and hash.
- A non-winning or rejected candidate must have a typed reason; do not rely on prose-only rejection.

Judge node contract:
1. Use `$surf` and `$best-practices-svg-design`.
2. Be a different provider family from every creator where possible. This run requested judge `{judge_handler}`.
3. Compare candidates at the actual target size, not source SVG or full-size artwork alone.
4. Choose exactly one winner only if it represents the immutable goal and is attractive at target size.
5. Emit `schema: create_svg.variant_judge_receipt.v1` with `winner_variant_id`, `winner_handler`, `screenshot_path`, `screenshot_sha256`, `visual_gate_receipt`, `mocked`, `live`, `rejected_variants`, and `failure_code` when no winner is accepted.

Typed error contract for `$triage-error`:
{codes}

Error path:
- Any create-svg failure receipt must include one of the exact `create_svg_*` codes above so `$triage-error classify --receipt <receipt> --layer create-svg` can route without regexing prose.
- `create_svg_visual_gate_not_ready` is normal design loop control, not a tool defect.
- If the triaged issue is a skill/runtime defect or recurs after one focused repair, file a project-watchdog-routable ticket with `$ticket` and add/update an `$agentic-evals` case before closure.
- Do not push, publish, or claim completion inside this DAG. The project agent applies scoped git transport only after Tau receipt, visual-gate PASS, local build, deployment checks, and live screenshot readback pass.
"""


def build_compete_command(
    *,
    request: str,
    repo: str,
    target: str,
    goal: str,
    creator_handlers: list[str],
    judge_handler: str,
    reviewer_specs: list[str],
    criteria: list[str],
    run_output_root: Path,
    ask_id: str | None,
    attach_files: list[Path],
    execute: bool,
    allow_provider_calls: bool,
    poll_timeout_seconds: float,
) -> list[str]:
    """Build the `$ask tau-dag compete` command for concurrent creators."""

    _ = allow_provider_calls
    command = [
        str(_repo_root() / "skills" / "ask" / "run.sh"),
        "tau-dag",
        "compete",
        request,
        "--repo",
        repo,
        "--target",
        target,
        "--immutable-goal",
        goal,
        "--judge-handler",
        judge_handler,
        "--run-output-root",
        str(run_output_root),
        "--poll-timeout-seconds",
        str(poll_timeout_seconds),
        "--viewer-link",
        "--json",
    ]
    for handler in creator_handlers:
        command.extend(["--handler", handler])
    for reviewer in reviewer_specs:
        command.extend(["--reviewer", reviewer])
    for criterion in criteria:
        command.extend(["--criterion", criterion])
    for path in attach_files:
        command.extend(["--attach-file", str(path.resolve())])
    if ask_id:
        command.extend(["--ask-id", ask_id])
    if execute:
        command.append("--execute")
    return command


def _resolve_context(context_files: list[Path]) -> tuple[list[Path], str]:
    context_parts: list[str] = []
    resolved_context_files: list[Path] = []
    for path in context_files:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"context file not found: {resolved}")
        resolved_context_files.append(resolved)
        text = resolved.read_text(encoding="utf-8", errors="replace")
        context_parts.append(f"\n--- Context file: {resolved} ---\n{text[:12000]}")
    return resolved_context_files, "\n".join(context_parts)


def run_variant_plan(
    *,
    goal: str,
    target: str,
    target_size: str,
    screenshot_command: str,
    max_attempts: int,
    context_files: list[Path],
    variants: list[VariantDirection],
    repo: str,
    creator_handlers: list[str],
    judge_handler: str,
    reviewer_specs: list[str],
    criteria: list[str],
    run_output_root: Path,
    ask_id: str | None,
    execute: bool,
    allow_provider_calls: bool,
    poll_timeout_seconds: float,
    open_viewer: bool,
    receipt: Path,
) -> TauVariantLoopPlan:
    """Create a Tau compete launch receipt for N concurrent SVG creators."""

    if max_attempts < 1 or max_attempts > 10:
        raise ValueError("create_svg_variant_count_invalid: max_attempts must be between 1 and 10")
    if len(variants) < 2 or len(variants) > 5:
        raise ValueError("create_svg_variant_count_invalid: variant count must be between 2 and 5")
    if len({variant.id for variant in variants}) != len(variants):
        raise ValueError("create_svg_variant_count_invalid: variant ids must be unique")

    embedded_handlers = [variant.handler for variant in variants if variant.handler]
    if embedded_handlers and creator_handlers:
        raise ValueError(
            "create_svg_variant_handler_count_mismatch: pass handlers either in variants.yml or as --creator-handler, not both"
        )
    resolved_creator_handlers = [str(handler) for handler in embedded_handlers] if embedded_handlers else list(creator_handlers)
    if len(resolved_creator_handlers) != len(variants):
        raise ValueError("create_svg_variant_handler_count_mismatch: expected exactly one creator handler per variant")
    if any(not handler.strip() for handler in resolved_creator_handlers):
        raise ValueError("create_svg_variant_handler_count_mismatch: creator handlers must be non-empty")

    judge_family = _handler_family(judge_handler)
    overlapping = [handler for handler in resolved_creator_handlers if _handler_family(handler) == judge_family]
    if overlapping:
        raise ValueError(
            "create_svg_variant_handler_family_overlap: judge handler must use a different provider family than creator handlers; "
            f"overlap={overlapping}"
        )

    resolved_context_files, context = _resolve_context(context_files)
    request = build_variant_loop_request(
        goal=goal,
        target=target,
        target_size=target_size,
        screenshot_command=screenshot_command,
        max_attempts=max_attempts,
        context=context,
        variants=variants,
        creator_handlers=resolved_creator_handlers,
        judge_handler=judge_handler,
    )
    run_output_root = run_output_root.resolve()
    run_output_root.mkdir(parents=True, exist_ok=True)
    request_path = receipt.resolve().with_suffix(".request.md")
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(request, encoding="utf-8")

    ask_command = build_compete_command(
        request=request,
        repo=repo,
        target=target,
        goal=goal,
        creator_handlers=resolved_creator_handlers,
        judge_handler=judge_handler,
        reviewer_specs=reviewer_specs,
        criteria=criteria,
        run_output_root=run_output_root,
        ask_id=ask_id,
        attach_files=resolved_context_files,
        execute=execute,
        allow_provider_calls=allow_provider_calls,
        poll_timeout_seconds=poll_timeout_seconds,
    )
    plan = TauVariantLoopPlan(
        status="PLANNED",
        created_at=datetime.now(timezone.utc).isoformat(),
        goal=goal,
        target=target,
        target_size=target_size,
        max_attempts=max_attempts,
        screenshot_command=screenshot_command,
        visual_gate_command_template=_variant_visual_gate_template(target, target_size, goal),
        triage_error_command_template=_triage_template(),
        ticket_command_template=_ticket_template(goal, target),
        context_files=[str(path) for path in resolved_context_files],
        variants=[
            variant.model_copy(update={"handler": handler})
            for variant, handler in zip(variants, resolved_creator_handlers, strict=True)
        ],
        creator_handlers=resolved_creator_handlers,
        judge_handler=judge_handler,
        reviewer_specs=reviewer_specs,
        criteria=criteria,
        ask_command=ask_command,
        request_path=str(request_path),
        failure_codes=failure_code_catalog(),
        proof_boundary="This command builds or runs an Ask/Tau compete DAG request with concurrent SVG creator candidates. Closure still requires Tau receipts, an opened Tau DAG viewer for human inspection, per-candidate screenshots, and a PASS create-svg.visual_gate.v1 receipt bound to the winning target screenshot.",
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
            run_dir = payload.get("run_dir") or payload.get("run_directory") or (payload.get("bundle") or {}).get("run_dir")
        except json.JSONDecodeError:
            run_dir = None
        active_failure_code = "create_svg_tau_compile_or_execute_failed" if completed.returncode != 0 or not run_dir else None
        update = {
            "status": "EXECUTED" if active_failure_code is None else "NEEDS_ATTENTION",
            "ask_stdout_path": str(stdout_path),
            "ask_stderr_path": str(stderr_path),
            "ask_returncode": completed.returncode,
            "run_dir": run_dir,
            "tau_viewer_command": [str(_repo_root() / "skills" / "tau" / "run.sh"), "dag-view", run_dir] if run_dir else None,
            "active_failure_code": active_failure_code,
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
                    "active_failure_code": "create_svg_tau_compile_or_execute_failed"
                    if viewed.returncode != 0
                    else update["active_failure_code"],
                }
            )
        plan = plan.model_copy(update=update)

    receipt.resolve().parent.mkdir(parents=True, exist_ok=True)
    receipt.resolve().write_text(json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan
