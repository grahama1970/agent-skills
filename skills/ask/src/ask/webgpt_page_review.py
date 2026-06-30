"""Explorer page review dispatch: /review-page builds packets; /ask calls WebGPT.

Flow:
  1. $ask webgpt /review-page coverage …
  2. subprocess → review-page run.sh (optional run-ti, then build/package)
  3. fail closed when review_page.gate.v1.json has ask_blocked (unless force)
  4. call_webgpt with review-bundle.zip (preferred) or REVIEW_PACKET.md
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .webgpt_runtime import WebgptBackendError, call_webgpt

REVIEW_PAGE_RUN = Path(
    os.environ.get(
        "ASK_REVIEW_PAGE_RUN",
        str(Path(__file__).resolve().parents[3] / "review-page" / "run.sh"),
    )
)

PAGE_VERDICT_RE = re.compile(
    r"(?im)^\s*VERDICT\s*:\s*(PASS|NEEDS_CHANGES|BLOCKED|HUMAN_REQUIRED)\b"
)
NEXT_STEP_RE = re.compile(r"(?im)^\s*NEXT_STEP\s*:\s*(IMPLEMENT|CLARIFY|NONE)\b")
PAGE_ONLY_VERDICT_RE = re.compile(
    r"(?im)^\s*PAGE_VERDICT\s*:\s*(pass|degraded|fail|insufficient_evidence)\b"
)

STEP_VERDICT_RE = re.compile(
    r"(?im)^\s*STEP_VERDICT\s*:\s*(pass|degraded|fail|insufficient_evidence)\b"
)
VISUAL_AGREES_RE = re.compile(
    r"(?im)^\s*VISUAL_AGREES_WITH_TI\s*:\s*(yes|no|unclear)\b"
)


@dataclass
class WebgptStepLoopResult:
    page_id: str
    package: dict[str, Any]
    steps_manifest: dict[str, Any]
    step_results: list[dict[str, Any]]
    response: str
    verdict: Optional[str]
    page_verdict: Optional[str]
    next_step: Optional[str]
    controlled_tab_id: str
    artifact_dir: str
    blocked_before_webgpt: bool = False
    block_reason: str = ""


@dataclass
class WebgptPageReviewRequest:
    page_id: str
    round_label: str = "1"
    capture_suffix: str = ""
    run_ti: bool = False
    capture_dir: str = ""
    out_dir: str = ""
    force: bool = False
    tab_id: str = ""
    url: str = ""
    project: str = "sparta-explorer-review"
    create_tab: bool = False
    timeout: float = 900.0
    step_loop: bool = False
    max_steps: int = 0
    steps_manifest: str = ""


@dataclass
class WebgptPageReviewResult:
    page_id: str
    package: dict[str, Any]
    response: str
    verdict: Optional[str]
    page_verdict: Optional[str]
    next_step: Optional[str]
    controlled_tab_id: str
    artifact_dir: str
    blocked_before_webgpt: bool = False
    block_reason: str = ""


def _run_review_page(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    if not REVIEW_PAGE_RUN.exists():
        raise WebgptBackendError(f"review-page skill not found: {REVIEW_PAGE_RUN}")
    cmd = [str(REVIEW_PAGE_RUN), *args]
    return subprocess.run(
        cmd,
        cwd=str(cwd or REVIEW_PAGE_RUN.parent),
        capture_output=True,
        text=True,
        timeout=1800,
    )


def build_page_review_package(req: WebgptPageReviewRequest) -> dict[str, Any]:
    """Invoke /review-page to materialize REVIEW_PACKET + gate JSON."""
    if req.run_ti:
        ti_args = ["run-ti", "--page", req.page_id]
        if req.capture_suffix:
            ti_args.extend(["--capture-suffix", req.capture_suffix])
        proc = _run_review_page(ti_args)
        if proc.returncode != 0:
            raise WebgptBackendError(
                f"review-page run-ti failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
            )

    package_args = ["package", "--page", req.page_id, "--round-label", req.round_label]
    if req.capture_dir:
        package_args.extend(["--capture-dir", req.capture_dir])
    if req.out_dir:
        package_args.extend(["--out-dir", req.out_dir])

    proc = _run_review_page(package_args)
    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise WebgptBackendError(
            f"review-page package produced no output ({proc.returncode}): {proc.stderr.strip()}"
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise WebgptBackendError(f"review-page package returned invalid JSON: {exc}") from exc
    if proc.returncode not in (0, 2):
        raise WebgptBackendError(
            f"review-page package failed ({proc.returncode}): {proc.stderr.strip() or stdout[:400]}"
        )
    return payload


def build_adjudication_prompt(package: dict[str, Any]) -> str:
    page = package.get("page", "")
    title = package.get("title", page)
    persona = package.get("persona_id", "")
    hint = package.get("ask_prompt_hint") or (
        "Adjudicate the attached SPARTA Explorer page review packet."
    )
    return (
        f"{hint}\n\n"
        f"Page id: `{page}`\n"
        f"Page title: {title}\n"
        f"Lead persona: {persona}\n\n"
        "Required response shape (no prose before VERDICT:):\n"
        "VERDICT: PASS | NEEDS_CHANGES | BLOCKED | HUMAN_REQUIRED\n"
        "PAGE_VERDICT: pass | degraded | fail | insufficient_evidence\n"
        "NEXT_STEP: IMPLEMENT | CLARIFY | NONE\n"
        "CODE_RUNNER_ACTIONS: (max 3 numbered steps)\n"
        "CLARIFYING_QUESTIONS: (max 3 numbered questions)\n\n"
        "Rules:\n"
        "- Do not override deterministic test-interactions FAIL to PASS.\n"
        "- Judge layout, hierarchy, evidence clarity, and degraded-state visibility from attached screenshots.\n"
        "- Do not run commands or edit the repo.\n"
    )


def extract_page_review_verdict(response: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    verdict = PAGE_VERDICT_RE.search(response or "")
    page_verdict = PAGE_ONLY_VERDICT_RE.search(response or "")
    next_step = NEXT_STEP_RE.search(response or "")
    return (
        verdict.group(1).upper() if verdict else None,
        page_verdict.group(1).lower() if page_verdict else None,
        next_step.group(1).upper() if next_step else None,
    )


def prepare_webgpt_steps_package(req: WebgptPageReviewRequest, package: dict[str, Any]) -> dict[str, Any]:
    """Invoke review-page prepare-webgpt-steps in the package out_dir."""
    out_dir = str(package.get("out_dir") or req.out_dir or "")
    if not out_dir:
        raise WebgptBackendError("prepare-webgpt-steps requires package out_dir")
    args = ["prepare-webgpt-steps", "--page", req.page_id, "--out-dir", out_dir]
    proc = _run_review_page(args)
    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise WebgptBackendError(
            f"review-page prepare-webgpt-steps produced no output ({proc.returncode}): {proc.stderr.strip()}"
        )
    try:
        manifest = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise WebgptBackendError(f"prepare-webgpt-steps returned invalid JSON: {exc}") from exc
    if proc.returncode != 0:
        raise WebgptBackendError(
            f"review-page prepare-webgpt-steps failed ({proc.returncode}): {proc.stderr.strip() or stdout[:400]}"
        )
    return manifest


def build_step_adjudication_prompt(step: dict[str, Any], *, page_id: str, zip_path: str) -> str:
    return (
        "Adjudicate this single test-interactions step for SPARTA Explorer.\n\n"
        f"Page id: `{page_id}`\n"
        f"Step: {step.get('step_index')} of {step.get('total_steps')}\n"
        f"Interaction id: `{step.get('interaction_id')}`\n"
        f"Element: {step.get('element')}\n"
        f"Action: {step.get('action')}\n"
        f"Expected result: {step.get('expected')}\n"
        f"TI status: {step.get('ti_status')}\n"
        f"TI evidence: {step.get('ti_evidence')}\n\n"
        "Required response shape (no prose before STEP_VERDICT:):\n"
        "STEP_VERDICT: pass | degraded | fail | insufficient_evidence\n"
        "VISUAL_AGREES_WITH_TI: yes | no | unclear\n"
        "NOTES: one short paragraph citing what the screenshot shows\n\n"
        "Rules:\n"
        "- Do not override deterministic TI FAIL to pass without visual justification.\n"
        "- Judge only this step; ignore other steps.\n"
        "- Do not run commands or edit the repo.\n\n"
        f"Evidence zip: {zip_path}\n"
    )


def extract_step_verdict(response: str) -> tuple[Optional[str], Optional[str]]:
    step = STEP_VERDICT_RE.search(response or "")
    visual = VISUAL_AGREES_RE.search(response or "")
    return (
        step.group(1).lower() if step else None,
        visual.group(1).lower() if visual else None,
    )


def rollup_step_verdicts(step_results: list[dict[str, Any]]) -> tuple[str, str, str]:
    """Return (verdict, page_verdict, next_step) from per-step adjudication."""
    if not step_results:
        return "BLOCKED", "insufficient_evidence", "CLARIFY"
    step_verdicts = [str(r.get("step_verdict") or "insufficient_evidence") for r in step_results]
    if any(v == "fail" for v in step_verdicts):
        page_verdict = "fail"
    elif any(v in {"degraded", "insufficient_evidence"} for v in step_verdicts):
        page_verdict = "degraded"
    elif all(v == "pass" for v in step_verdicts):
        page_verdict = "pass"
    else:
        page_verdict = "insufficient_evidence"
    disagreements = [
        r for r in step_results
        if r.get("ti_status") == "FAIL" and r.get("step_verdict") == "pass"
    ]
    if disagreements:
        page_verdict = "fail" if page_verdict == "pass" else page_verdict
    verdict = "PASS" if page_verdict == "pass" else "NEEDS_CHANGES"
    next_step = "NONE" if verdict == "PASS" else "IMPLEMENT"
    return verdict, page_verdict, next_step


def _load_steps_manifest(req: WebgptPageReviewRequest, package: dict[str, Any]) -> dict[str, Any]:
    if req.steps_manifest:
        manifest_path = Path(req.steps_manifest)
        if not manifest_path.exists():
            raise WebgptBackendError(f"steps manifest not found: {manifest_path}")
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path = Path(str(package.get("out_dir") or "")) / "webgpt-steps" / "webgpt_steps_manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return prepare_webgpt_steps_package(req, package)


def run_webgpt_step_loop(
    req: WebgptPageReviewRequest,
    *,
    package: dict[str, Any] | None = None,
    run_state: object | None = None,
) -> WebgptStepLoopResult:
    package = package or build_page_review_package(req)
    blocked = bool(package.get("ask_blocked")) and not req.force
    if blocked:
        gate = package.get("gate") or {}
        return WebgptStepLoopResult(
            page_id=req.page_id,
            package=package,
            steps_manifest={},
            step_results=[],
            response="",
            verdict="BLOCKED",
            page_verdict="insufficient_evidence",
            next_step="CLARIFY",
            controlled_tab_id=req.tab_id,
            artifact_dir=str(package.get("out_dir") or ""),
            blocked_before_webgpt=True,
            block_reason=str(gate.get("reason") or "preflight_blocked"),
        )

    manifest = _load_steps_manifest(req, package)
    steps = list(manifest.get("steps") or [])
    total = int(manifest.get("total_steps") or len(steps))
    if req.max_steps and req.max_steps > 0:
        steps = steps[: req.max_steps]
    if not steps:
        raise WebgptBackendError("step loop manifest has zero steps")

    step_results: list[dict[str, Any]] = []
    controlled_tab_id = req.tab_id
    artifact_dir = str(package.get("out_dir") or "")
    combined_lines = [
        f"# WebGPT step loop rollup ({req.page_id})",
        "",
        f"Total steps adjudicated: {len(steps)} of {total}",
        "",
        "| step | interaction_id | element | expected | TI | step_verdict | visual_agrees |",
        "|---:|---|---|---|---|---|---|",
    ]

    for step in steps:
        step = dict(step)
        step["total_steps"] = total
        zip_path = str(step.get("zip") or "")
        if not zip_path or not Path(zip_path).exists():
            raise WebgptBackendError(f"step zip missing for {step.get('interaction_id')}: {zip_path!r}")
        prompt = build_step_adjudication_prompt(step, page_id=req.page_id, zip_path=zip_path)
        result = call_webgpt(
            prompt,
            tab_id=controlled_tab_id,
            url=req.url,
            create_tab=req.create_tab and not controlled_tab_id,
            project=req.project,
            attach_file=zip_path,
            timeout=req.timeout,
            no_activate=True,
            run_state=run_state,
            iteration=int(step.get("step_index") or 0),
        )
        controlled_tab_id = result.controlled_tab_id or controlled_tab_id
        artifact_dir = str(result.artifact_dir or artifact_dir)
        step_verdict, visual_agrees = extract_step_verdict(result.response)
        row = {
            **{k: step.get(k) for k in (
                "step_index", "ti_index", "interaction_id", "element", "action",
                "expected", "ti_status", "ti_evidence", "zip",
            )},
            "step_verdict": step_verdict or "insufficient_evidence",
            "visual_agrees_with_ti": visual_agrees or "unclear",
            "response": result.response,
            "artifact_dir": str(result.artifact_dir),
        }
        step_results.append(row)
        combined_lines.append(
            f"| {row['step_index']} | `{row['interaction_id']}` | {row['element']} | {row['expected']} | {row['ti_status']} | {row['step_verdict']} | {row['visual_agrees_with_ti']} |"
        )
        response_path = Path(artifact_dir) / "webgpt-steps" / f"step-{row['step_index']:03d}-response.md"
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(result.response.strip() + "\n", encoding="utf-8")

    verdict, page_verdict, next_step = rollup_step_verdicts(step_results)
    combined_lines += [
        "",
        f"VERDICT: {verdict}",
        f"PAGE_VERDICT: {page_verdict}",
        f"NEXT_STEP: {next_step}",
        "",
    ]
    rollup_md = "\n".join(combined_lines) + "\n"
    rollup_path = Path(artifact_dir) / "webgpt-steps" / "webgpt-step-rollup.md"
    rollup_path.parent.mkdir(parents=True, exist_ok=True)
    rollup_path.write_text(rollup_md, encoding="utf-8")
    rollup_json = {
        "schema": "review_page.webgpt_step_loop.v1",
        "page": req.page_id,
        "verdict": verdict,
        "page_verdict": page_verdict,
        "next_step": next_step,
        "total_steps": total,
        "adjudicated_steps": len(step_results),
        "step_results": step_results,
        "rollup_md": str(rollup_path),
    }
    (Path(artifact_dir) / "webgpt-steps" / "webgpt_step_loop.json").write_text(
        json.dumps(rollup_json, indent=2) + "\n",
        encoding="utf-8",
    )

    return WebgptStepLoopResult(
        page_id=req.page_id,
        package=package,
        steps_manifest=manifest,
        step_results=step_results,
        response=rollup_md,
        verdict=verdict,
        page_verdict=page_verdict,
        next_step=next_step,
        controlled_tab_id=controlled_tab_id,
        artifact_dir=artifact_dir,
    )


def run_webgpt_page_review(
    req: WebgptPageReviewRequest,
    *,
    run_state: object | None = None,
) -> WebgptPageReviewResult:
    if req.step_loop:
        loop = run_webgpt_step_loop(req, run_state=run_state)
        return WebgptPageReviewResult(
            page_id=loop.page_id,
            package=loop.package,
            response=loop.response,
            verdict=loop.verdict,
            page_verdict=loop.page_verdict,
            next_step=loop.next_step,
            controlled_tab_id=loop.controlled_tab_id,
            artifact_dir=loop.artifact_dir,
            blocked_before_webgpt=loop.blocked_before_webgpt,
            block_reason=loop.block_reason,
        )
    package = build_page_review_package(req)
    blocked = bool(package.get("ask_blocked")) and not req.force
    if blocked:
        gate = package.get("gate") or {}
        return WebgptPageReviewResult(
            page_id=req.page_id,
            package=package,
            response="",
            verdict="BLOCKED",
            page_verdict="insufficient_evidence",
            next_step="CLARIFY",
            controlled_tab_id=req.tab_id,
            artifact_dir=str(package.get("out_dir") or ""),
            blocked_before_webgpt=True,
            block_reason=str(gate.get("reason") or "preflight_blocked"),
        )

    attach = str(package.get("webgpt_attach") or package.get("review_bundle_zip") or package.get("review_packet") or "")
    if not attach or not Path(attach).exists():
        raise WebgptBackendError(f"review-page package missing attach path: {attach!r}")

    prompt = build_adjudication_prompt(package)
    result = call_webgpt(
        prompt,
        tab_id=req.tab_id,
        url=req.url,
        create_tab=req.create_tab,
        project=req.project,
        attach_file=attach,
        timeout=req.timeout,
        no_activate=True,
        run_state=run_state,
        iteration=1,
    )
    verdict, page_verdict, next_step = extract_page_review_verdict(result.response)
    return WebgptPageReviewResult(
        page_id=req.page_id,
        package=package,
        response=result.response,
        verdict=verdict,
        page_verdict=page_verdict,
        next_step=next_step,
        controlled_tab_id=result.controlled_tab_id,
        artifact_dir=str(result.artifact_dir),
    )
