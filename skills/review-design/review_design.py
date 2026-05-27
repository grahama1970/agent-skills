"""
Main orchestrator for the review-design skill.

Implements the 3-step design review pipeline:
1. Audit - Analyze screenshots against tokens and reference
2. Judge - Critique the audit findings
3. Finalize - Produce actionable recommendations
"""
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()


import typer
import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import (
    AuditResult,
    DEFAULT_PROVIDER,
    DEFAULT_ROUNDS,
    MAX_IMAGE_DIM,
    OUTPUT_BASE,
    PROVIDERS,
    ReviewRequest,
    normalize_provider,
)
from memory_integration import recall_prior_design_reviews, learn_design_review
from prompts import (
    SYSTEM_PROMPT,
    build_persona_system_prompt,
    format_step1_prompt,
    format_step2_prompt,
    format_step3_prompt,
)


def _read_context(context: Optional[str], context_file: Optional[Path]) -> str:
    if context_file and context_file.exists():
        return context_file.read_text()
    if context:
        return context
    return (
        "No explicit context provided. Explain the product surface, current UX problem, "
        "constraints, prior failures, and what kind of review you need."
    )


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _summarize_test_interactions_manifest(path: Path) -> str:
    data = _read_json(path)
    if not data:
        return f"Manifest: {path}\nStatus: unreadable or not JSON."

    surfaces = data.get("surfaces") or []
    lines = [
        "## Test Interactions Manifest Contract",
        "",
        f"- Manifest: `{path}`",
        f"- Generator: `{data.get('generator', 'unknown')}`",
        f"- App: `{data.get('app', '')}`",
        f"- Base URL: `{data.get('base_url', '')}`",
        f"- Surfaces: {len(surfaces)}",
        "",
        "| Surface | Path | Elements | Interactions | QID Compliance |",
        "|---|---|---:|---:|---|",
    ]
    total_elements = 0
    total_interactions = 0
    target_rows = []
    for surface in surfaces:
        elements = surface.get("elements") or []
        interactions = [i for element in elements for i in (element.get("interactions") or [])]
        total_elements += len(elements)
        total_interactions += len(interactions)
        lines.append(
            f"| {surface.get('name', '')} | `{surface.get('path', '')}` | "
            f"{len(elements)} | {len(interactions)} | {surface.get('qid_compliance', False)} |"
        )
        for element in elements:
            for interaction in element.get("interactions") or []:
                target = interaction.get("target") or interaction.get("screenshot_selector") or interaction.get("container_selector") or ""
                if target:
                    target_rows.append((
                        surface.get("name", ""),
                        element.get("name", ""),
                        interaction.get("action", ""),
                        target,
                        interaction.get("description", ""),
                    ))

    lines.extend([
        "",
        f"- Total elements: {total_elements}",
        f"- Total interactions: {total_interactions}",
        "",
        "| Surface | Element | Action | Target | Description |",
        "|---|---|---|---|---|",
    ])
    for surface, element, action, target, description in target_rows[:80]:
        safe_description = str(description).replace("|", "/")
        lines.append(f"| {surface} | {element} | {action} | `{target}` | {safe_description} |")
    if len(target_rows) > 80:
        lines.append(f"| ... | ... | ... | ... | {len(target_rows) - 80} more targets omitted |")
    lines.append("")
    lines.append(
        "Reviewer obligation: compare visible screenshots against this manifest. "
        "If a live interactive target, graph state, pane, queue, or semantic workflow "
        "required by the manifest is not visible in the screenshots, return `blocked` "
        "with `missing_evidence`."
    )
    return "\n".join(lines)


def _summarize_test_interactions_results(path: Path) -> str:
    data = _read_json(path)
    if not data:
        return f"Results: {path}\nStatus: missing, unreadable, or not JSON."

    lines = [
        "## Test Interactions Deterministic Results",
        "",
        f"- Results: `{path}`",
        f"- Total: {data.get('total', 0)}",
        f"- Passed: {data.get('passed', 0)}",
        f"- Failed: {data.get('failed', 0)}",
        f"- Warnings: {data.get('warnings', data.get('warned', 0))}",
        "",
        "| Status | Surface | Element | Action | Evidence | Screenshots |",
        "|---|---|---|---|---|---|",
    ]
    for item in (data.get("interactions") or [])[:120]:
        screenshots = []
        if item.get("screenshot"):
            screenshots.append(item["screenshot"])
        for asset in item.get("screenshots") or []:
            if asset.get("path"):
                screenshots.append(f"{asset.get('kind', 'screenshot')}:{asset.get('path')}")
        evidence = str(item.get("evidence", "")).replace("|", "/")[:180]
        lines.append(
            f"| {item.get('status', '')} | {item.get('surface', '')} | {item.get('element', '')} | "
            f"{item.get('action', '')} | {evidence} | {'<br>'.join(screenshots[:4])} |"
        )
    lines.append("")
    lines.append(
        "Reviewer obligation: deterministic FAIL/WARN rows, missing focused screenshots, "
        "or mismatches between manifest targets and captured evidence are design-review "
        "blockers unless explicitly scoped out in context."
    )
    return "\n".join(lines)


def _read_modern_reference(path: Path, *, persona: str, require_persona_match: bool) -> str:
    if not path.exists():
        print(f"Modern reference report not found: {path}", file=sys.stderr)
        raise typer.Exit(2)

    reference_text = path.read_text()
    data = _read_json(path)
    if data:
        request_context = data.get("request_context") or {}
        reference_persona = request_context.get("persona") or ""
        if require_persona_match and not reference_persona:
            print(
                "--require-modern-reference requires a Dogpile JSON reference with request_context.persona.",
                file=sys.stderr,
            )
            raise typer.Exit(2)
        if require_persona_match and reference_persona != persona:
            print(
                f"Dogpile reference persona `{reference_persona}` does not match review persona `{persona}`. "
                "Rerun $dogpile with the same persona or omit --require-modern-reference.",
                file=sys.stderr,
            )
            raise typer.Exit(2)
        query = data.get("effective_query") or data.get("requested_query") or ""
        brave_results = (((data.get("results") or {}).get("stage1") or {}).get("brave") or {}).get("results") or []
        github_repos = (((data.get("results") or {}).get("stage1") or {}).get("github") or {}).get("repos") or []
        reference_rows = []
        design_requirements = [
            "Graph/editor state must make selected node, edge meaning, execution status, and inspector linkage visible together.",
            "Evidence/provenance panels must show source artifact, freshness, blocker state, and next action without log spelunking.",
            "Review/amendment queues must read as auditable work queues with clear accepted/rejected/blocked/pending/stale states.",
            "Controls must be targetable and inspectable through data-qid/data-qs-action/title evidence, not anonymous visual chrome.",
            "Dense workflow surfaces must prioritize repeated operator scanning over marketing-style cards or decorative dashboards.",
        ]
        for item in brave_results[:10]:
            title = item.get("title", "")
            description = item.get("description", "")
            url = item.get("url", "")
            reference_rows.append(f"| Brave | {title} | {url} | {description.replace('|', '/')} |")
        for item in github_repos[:10]:
            name = item.get("name") or item.get("full_name") or item.get("url") or ""
            url = item.get("url") or item.get("html_url") or ""
            description = item.get("description", "")
            reference_rows.append(f"| GitHub | {name} | {url} | {str(description).replace('|', '/')} |")
        return (
            "## Modern 2026 Reference / Dogpile Context\n\n"
            "This is a persona-bound benchmarking packet for current workflow-editor, graph, "
            "inspector, evidence, and review-queue UX patterns. Compare screenshots against "
            "these references and list missing benchmark evidence under `missing_evidence`.\n\n"
            f"- Dogpile persona: `{reference_persona or 'unknown'}`\n"
            f"- Review persona: `{persona}`\n"
            f"- Query: {query}\n"
            f"- Status: {data.get('status', '')}\n"
            f"- HTML report: `{data.get('html_report_path', '')}`\n\n"
            "### Design Requirements Derived From Reference Packet\n\n"
            + "\n".join(f"- {requirement}" for requirement in design_requirements)
            + "\n\n### Reference URLs From Dogpile\n\n"
            "| Source | Title/Repo | URL | Why relevant |\n"
            "|---|---|---|---|\n"
            + ("\n".join(reference_rows) if reference_rows else "| none | none | none | Dogpile did not return Brave/GitHub references. |\n")
            + "\n\n### Reference Screenshot Requirement\n\n"
            "Dogpile returns source URLs and reports, not guaranteed screenshot pixels. "
            "For serious workflow-editor review, attach captured reference screenshots "
            "with `--reference-screenshots`; otherwise reviewers must treat missing "
            "visual benchmark screenshots as `missing_evidence` when visual comparison is required.\n\n"
            + reference_text[:40000]
        )

    if require_persona_match:
        print(
            "--require-modern-reference requires Dogpile partial-results JSON so the persona can be verified.",
            file=sys.stderr,
        )
        raise typer.Exit(2)

    return (
        "## Modern 2026 Reference / Dogpile Context\n\n"
        "Use this as a benchmarking packet for current workflow-editor, graph, inspector, "
        "evidence, and review-queue UX patterns. Persona metadata was not machine-verifiable.\n\n"
        + reference_text[:40000]
    )


def _collect_reference_screenshot_images(directory: Optional[Path], max_images: int = 4) -> tuple[list[tuple[str, str]], str]:
    if not directory:
        return [], (
            "## Reference Screenshots\n\n"
            "No `--reference-screenshots` directory was supplied. If the review requires "
            "visual comparison to Dogpile examples, return `blocked` with "
            "`missing_evidence` for reference screenshots.\n"
        )
    if not directory.exists():
        print(f"Reference screenshots directory not found: {directory}", file=sys.stderr)
        raise typer.Exit(2)
    images = collect_images(directory, max_images=max_images, include_burst=False)
    if not images:
        return [], (
            "## Reference Screenshots\n\n"
            f"`--reference-screenshots {directory}` was supplied but no PNG/JPG images were found. "
            "Return `blocked` with `missing_evidence` when visual comparison is required.\n"
        )
    lines = [
        "## Reference Screenshots",
        "",
        f"- Directory: `{directory}`",
        f"- Attached reference screenshots: {len(images)}",
    ]
    for name, _uri in images:
        lines.append(f"- `REFERENCE_{name}`")
    lines.append("")
    lines.append(
        "Reviewer obligation: compare the target screenshot against these reference "
        "screenshots for workflow-editor conventions, not decorative sameness."
    )
    return [(f"REFERENCE_{name}", uri) for name, uri in images], "\n".join(lines)


def _copy_text_to_clipboard(text: str) -> str:
    try:
        subprocess.run(["wl-copy"], input=text.encode(), check=True)
        return "wl-copy"
    except (subprocess.CalledProcessError, FileNotFoundError):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        return "xclip"


def _copy_file_to_clipboard(path: Path) -> str:
    uri_payload = f"file://{path}\r\n".encode()
    try:
        subprocess.run(["wl-copy", "--type", "text/uri-list"], input=uri_payload, check=True)
        return "wl-copy"
    except (subprocess.CalledProcessError, FileNotFoundError):
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "text/uri-list"],
            input=uri_payload,
            check=True,
        )
        return "xclip"


def _lang_for_path(path: Path) -> str:
    ext = path.suffix[1:] if path.suffix else ""
    lang_map = {"tsx": "tsx", "ts": "typescript", "jsx": "jsx", "js": "javascript", "py": "python"}
    return lang_map.get(ext, ext)


def _write_design_review_request(
    output: Path,
    *,
    context_text: str,
    focus: str,
    files: list[Path],
    screenshot_names: list[str],
    target: str,
    known_issues: list[str],
    surface_roles: list[str],
    core_objective: Optional[str],
    audit_targets: list[str],
    request_mockup: bool,
) -> None:
    focus_lines = ""
    if focus:
        focus_lines = "\n".join(f"- {item.strip()}" for item in focus.split(",") if item.strip())
    file_lines = "\n".join(f"- `{file_path}`" for file_path in files)
    screenshot_lines = "\n".join(f"- `{name}`" for name in screenshot_names) or "- No screenshots included"
    issues_lines = "\n".join(f"- {item}" for item in known_issues) or (
        "- No explicit known issues provided. Add concrete prior failures so the reviewer critiques the real problems."
    )
    surface_lines = "\n".join(f"- {item}" for item in surface_roles) or (
        "- No explicit pane/tab roles provided. Add what each pane or tab is supposed to do so the reviewer can judge fit."
    )
    audit_target_lines = "\n".join(f"- {item}" for item in audit_targets) or (
        "- No explicit code-aware audit targets provided. Add concrete implementation tensions or file-level risks."
    )
    core_objective_text = core_objective or (
        "Conduct a decision-first UX audit that compares the intended workflow against the actual implementation, "
        "with emphasis on human-in-the-loop correction and clarity of evidence."
    )
    required_output_tail = [
        "6. When a finding is implementation-driven, cite the relevant file and explain the data-flow or layout consequence"
    ]
    if request_mockup:
        required_output_tail.insert(0, "6. A concrete HTML/CSS or layout mockup of the recommended information flow")
        required_output_tail[1] = "7. When a finding is implementation-driven, cite the relevant file and explain the data-flow or layout consequence"
    required_output_lines = "\n".join(required_output_tail)
    output.write_text(
        f"""# Design Review Request

Review the attached screenshot files, this request, the bundled implementation, and the focused diff.

Target reviewer: {target}

This is a tactical UX review, not a generic code review. Treat it as a delta audit: compare the stated requirements and observed failures against the actual React implementation and screenshots. Focus on hierarchy, density, information scent, visual weight, and whether the interface exposes the right information in the right order.

## Core Objective

{core_objective_text}

## Context

{context_text}

## Surface Roles

{surface_lines}

## Known Observed Problems

{issues_lines}

## Code-Aware Audit Targets

{audit_target_lines}

## Review Focus

{focus_lines or "- hierarchy\n- density\n- evidence summary clarity\n- inline entity emphasis\n- shared component fit"}

## Primary Questions

1. Is the current information hierarchy correct for the operator workflow?
2. Are any reading-surface entity styles still too heavy?
3. What belongs in the collapsed evidence summary versus hidden details?
4. Should the shared component be identical across explorer and chat, or use a thin variant layer?
5. What remaining UI is decorative, implementation-centric, or insufficiently informative?

## Required Output

1. Primary findings first, ordered by severity
2. For each finding:
   - what is wrong
   - why it hurts the workflow
   - exact recommendation
3. Recommended final information order
4. Recommended inline entity styling rules
5. Recommendation on shared-vs-variant component design
{required_output_lines}

## Included Screenshots

{screenshot_lines}

Use the screenshots intentionally:
- include at least one full-surface screenshot for hierarchy and context
- include cropped screenshots for specific defects
- include zoomed screenshots when the issue is local typography, spacing, badges, chips, or dense evidence UI
- if a cropped screenshot is attached, evaluate it as the primary evidence for that local defect

## Included Source Files

{file_lines}
"""
    )


def _write_code_bundle(output: Path, files: list[Path], css: list[Path]) -> None:
    parts = [
        "# Relevant Source Bundle\n\n",
        "Only the components relevant to the current design review are included here.\n",
    ]
    for file_path in [*files, *css]:
        if file_path.exists():
            content = file_path.read_text()
            parts.append(f"\n---\n\n## `{file_path}`\n\n```{_lang_for_path(file_path)}\n")
            parts.append(content)
            if not content.endswith("\n"):
                parts.append("\n")
            parts.append("```\n")
        else:
            parts.append(f"\n---\n\n## `{file_path}`\n\nERROR: file not found.\n")
    output.write_text("".join(parts))


def _write_diff_bundle(output: Path, git_diff: Optional[str], files: list[Path], css: list[Path]) -> None:
    if not git_diff:
        output.write_text("")
        return
    result = subprocess.run(
        ["git", "diff", "--no-color", git_diff, "--", *[str(p) for p in [*files, *css]]],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output.write_text(result.stdout if result.returncode == 0 else "")


def encode_image_base64(image_path: Path) -> str:
    """Encode an image file as base64 data URI."""
    suffix = image_path.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(suffix, "image/png")

    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{data}"


def resize_image_if_needed(image_path: Path, max_dim: int = MAX_IMAGE_DIM) -> Path:
    """Resize image if it exceeds max dimension. Returns path (may be temp file)."""
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            w, h = img.size
            if w <= max_dim and h <= max_dim:
                return image_path

            # Calculate new dimensions
            if w > h:
                new_w = max_dim
                new_h = int(h * (max_dim / w))
            else:
                new_h = max_dim
                new_w = int(w * (max_dim / h))

            # Resize and save to temp file
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            temp_path = Path(f"/tmp/review_design_{image_path.stem}_resized{image_path.suffix}")
            resized.save(temp_path)
            return temp_path
    except ImportError:
        # PIL not available, return original
        return image_path


def collect_images(directory: Path, max_images: int = 10, include_burst: bool = True) -> list[tuple[str, str]]:
    """Collect images from a directory. Returns list of (name, base64_uri) tuples.

    If include_burst is True, also collects frames from a burst/ subdirectory
    (filmstrip captures of animation transitions).
    """
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    images = []

    # Collect resting-state screenshots
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in image_extensions:
            resized = resize_image_if_needed(path)
            images.append((path.name, encode_image_base64(resized)))
            if len(images) >= max_images:
                break

    # Collect burst filmstrip frames (animation transitions)
    # Burst frames are CRITICAL for animation review — they show frame-by-frame
    # state transitions that static screenshots cannot capture.
    burst_dir = directory / "burst"
    if include_burst and burst_dir.is_dir():
        # Generous budget: burst frames ARE the review for animation-heavy UIs.
        # Gemini (max_images=50) gets up to 40 burst frames.
        # For smaller providers, still get at least 10.
        burst_budget = max(20, max_images * 2 - len(images))
        burst_count = 0
        for path in sorted(burst_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in image_extensions:
                resized = resize_image_if_needed(path)
                images.append((f"BURST_{path.name}", encode_image_base64(resized)))
                burst_count += 1
                if burst_count >= burst_budget:
                    break
        if burst_count > 0:
            print(f"  Including {burst_count} burst animation frames from {burst_dir}")
        else:
            print(f"  WARNING: burst/ directory exists but contains no images")
    elif include_burst:
        print(f"  NOTE: No burst/ subdirectory found — animation review will be limited to static frames only")
        print(f"        Run capture_matrix.py with --burst to capture animation filmstrips")

    return images


from providers import call_provider, call_scillm_async, check_scillm_health  # noqa: E402 — provider dispatch


def _artifact_dir() -> Path:
    override = os.environ.get("REVIEW_DESIGN_ARTIFACTS_DIR")
    if override:
        return Path(override)
    artifact_root = Path(
        os.environ.get("AGENT_SKILLS_ARTIFACT_ROOT", "/mnt/storage12tb/artifacts/agent-skills")
    )
    return artifact_root / "review-design"


def find_implementation_files(screenshots_dir: Path) -> list[Path]:
    """Find potential implementation files near the screenshots directory.

    Looks for common UI file patterns (QML, CSS, TSX, etc.) in parent directories.
    """
    impl_files = []
    search_patterns = [
        "*.qml", "*.css", "*.scss", "*.tsx", "*.jsx",
        "*.vue", "*.svelte", "*Style*.py", "*style*.ts"
    ]

    # Search near the screenshot bundle, but never walk broad system roots. Test
    # screenshots often live in /tmp; rglob from / would hang the review before
    # the provider call.
    blocked_roots = {
        Path("/"),
        Path("/tmp"),
        Path("/var"),
        Path("/home"),
        Path("/mnt"),
        Path("/mnt/storage12tb"),
    }
    search_dirs = []
    for candidate in (screenshots_dir.parent, screenshots_dir.parent.parent):
        resolved = candidate.resolve()
        if resolved in blocked_roots:
            continue
        if len(resolved.parts) < 5:
            continue
        if resolved not in search_dirs:
            search_dirs.append(resolved)

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for pattern in search_patterns:
            for path in search_dir.rglob(pattern):
                if path.is_file() and path.stat().st_size < 100000:  # Skip huge files
                    impl_files.append(path)
                    if len(impl_files) >= 5:
                        return impl_files

    return impl_files[:5]  # Limit to 5 most relevant


def extract_code_context(impl_files: list[Path], tokens_json: str) -> str:
    """Extract relevant code snippets that reference design tokens.

    This helps the vision model verify its observations against actual code.
    """
    if not impl_files:
        return ""

    # Parse tokens to find key property names
    try:
        tokens = json.loads(tokens_json)
        token_keywords = set()

        def extract_keys(obj, prefix=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k not in ("description", "value", "$schema", "meta"):
                        token_keywords.add(k)
                        extract_keys(v, f"{prefix}.{k}" if prefix else k)

        extract_keys(tokens)
    except json.JSONDecodeError:
        token_keywords = set()

    context_parts = []

    for impl_file in impl_files:
        try:
            content = impl_file.read_text()
            lines = content.split("\n")

            # Find lines that reference design tokens or colors
            relevant_lines = []
            for i, line in enumerate(lines, 1):
                line_lower = line.lower()
                if any(kw.lower() in line_lower for kw in token_keywords):
                    relevant_lines.append(f"{i}: {line.rstrip()}")
                elif any(term in line_lower for term in ["color", "background", "border", "font", "padding", "margin", "radius"]):
                    relevant_lines.append(f"{i}: {line.rstrip()}")

            if relevant_lines:
                context_parts.append(f"### {impl_file.name}\n```\n" + "\n".join(relevant_lines[:30]) + "\n```")
        except Exception:
            continue

    if context_parts:
        return "\n\n## Implementation Code Context\n\n" + "\n\n".join(context_parts)
    return ""


def run_review_round(
    request: ReviewRequest,
    round_num: int,
    images: list[tuple[str, str]],
    tokens_json: str,
    code_context: str = "",
    session_id: Optional[str] = None,
    output_dir: Optional[Path] = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> tuple[str, str, str]:
    """Run a single round of the 3-step review pipeline.

    Returns (step1_output, step2_output, step3_output) tuple.
    """
    if output_dir is None:
        output_dir = OUTPUT_BASE
    provider_config = PROVIDERS[request.provider]

    print(f"\n{'='*60}")
    print(f"ROUND {round_num} - {provider_config.name} (Persona: {request.persona})")
    print(f"{'='*60}")

    # Step 1: Audit
    print(f"\n[Step 1/3] Running audit...")
    step1_prompt = format_step1_prompt(tokens_json, request.focus_areas or None)

    # Add code context if available
    if code_context:
        step1_prompt += f"\n\n{code_context}\n\nIMPORTANT: The source code above is your PRIMARY input. Read it to understand what each component does, what data it queries, and what interactions it supports. Then verify against the screenshots that the code renders correctly."

    step1_output = call_provider(
        request.provider,
        system_prompt,
        step1_prompt,
        images,
        session_id,
    )

    # Save step 1 output
    step1_path = output_dir / f"round{round_num}_step1.md"
    step1_path.write_text(step1_output)
    print(f"    Saved: {step1_path}")

    # Step 2: Judge
    print(f"\n[Step 2/3] Running judge review...")
    step2_prompt = format_step2_prompt(step1_output)
    step2_output = call_provider(
        request.provider,
        system_prompt,
        step2_prompt,
        [],  # No images needed for judge step
        session_id,
    )

    # Save step 2 output
    step2_path = output_dir / f"round{round_num}_step2.md"
    step2_path.write_text(step2_output)
    print(f"    Saved: {step2_path}")

    # Step 3: Finalize
    print(f"\n[Step 3/3] Finalizing recommendations...")
    step3_prompt = format_step3_prompt(step1_output, step2_output)
    step3_output = call_provider(
        request.provider,
        system_prompt,
        step3_prompt,
        [],  # No images needed for finalize step
        session_id,
    )

    # Save step 3 output
    step3_path = output_dir / f"round{round_num}_final.md"
    step3_path.write_text(step3_output)
    print(f"    Saved: {step3_path}")

    return step1_output, step2_output, step3_output


def extract_token_changes(final_output: str) -> list[dict]:
    """Extract token changes from the final output."""
    changes = []

    # Look for JSON block with token changes
    import re
    json_match = re.search(r'```json\s*(\{[\s\S]*?"changes"[\s\S]*?\})\s*```', final_output)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            changes = data.get("changes", [])
        except json.JSONDecodeError:
            pass

    return changes


def load_persona_context(persona_name: str) -> str:
    """Load persona AGENTS.md and /memory recall for full context injection.

    This is NON-NEGOTIABLE. A review without persona context is a failure.
    Returns the full persona context string to inject into the system prompt.
    """
    context_parts = []

    # 1. Load persona AGENTS.md
    candidate_roots = []
    if os.environ.get("REVIEW_DESIGN_AGENTS_ROOT"):
        candidate_roots.append(Path(os.environ["REVIEW_DESIGN_AGENTS_ROOT"]))
    candidate_roots.extend([
        Path(__file__).parent.parent.parent / "agents",
        Path.home() / "workspace/experiments/pi-mono/.pi/agents",
        Path.home() / "workspace/experiments/agent-skills/agents",
    ])
    agents_md = None
    for agents_dir in candidate_roots:
        candidate = agents_dir / persona_name / "AGENTS.md"
        if candidate.exists():
            agents_md = candidate
            break
    if agents_md is not None and agents_md.exists():
        agents_content = agents_md.read_text()
        context_parts.append(f"## Persona Identity: {persona_name}\n\n{agents_content}")
        print(f"  Loaded persona AGENTS.md: {agents_md} ({len(agents_content):,} chars)")
    else:
        searched = ", ".join(str(root / persona_name / "AGENTS.md") for root in candidate_roots)
        message = f"No AGENTS.md found for persona {persona_name}. Searched: {searched}"
        if os.environ.get("REVIEW_DESIGN_ALLOW_MISSING_PERSONA") == "1":
            print(f"  WARNING: {message}")
        else:
            raise RuntimeError(message)

    # 2. Memory recall — get persona's QRA corpus, relationships, domain knowledge
    if os.environ.get("REVIEW_DESIGN_DISABLE_MEMORY") == "1":
        print("  Memory recall disabled by REVIEW_DESIGN_DISABLE_MEMORY=1")
    else:
        scope = persona_name.replace("-", "_")
        print(f"  Recalling memory for scope: {scope}")
        prior_context = recall_prior_design_reviews(project=scope, component="ux-lab")
        if prior_context:
            context_parts.append(f"## Prior Design Reviews from Memory\n\n{prior_context}")
            print(f"  Memory recall returned {len(prior_context):,} chars of prior context")
        else:
            print(f"  No prior design reviews found in memory for {scope}")

    if not context_parts:
        print(f"  WARNING: No persona context loaded for {persona_name} — review will lack domain focus")

    return "\n\n".join(context_parts)


def run_full_review(request: ReviewRequest) -> list[AuditResult]:
    """Run the full multi-round design review."""
    # Validate request
    errors = request.validate()
    if errors:
        print("Validation errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    # Load persona context (NON-NEGOTIABLE)
    print(f"\n{'='*60}")
    print(f"PERSONA: {request.persona}")
    print(f"{'='*60}")
    persona_context = load_persona_context(request.persona)

    # Build persona-aware system prompt
    system_prompt = build_persona_system_prompt(request.persona, persona_context)

    # Derive output directory from screenshots path (e.g. s2-midview → review-output/s2-midview/).
    # REVIEW_DESIGN_OUTPUT_BASE lets orchestrators avoid collisions in the global review-output tree.
    output_base = Path(os.environ.get("REVIEW_DESIGN_OUTPUT_BASE", str(OUTPUT_BASE)))
    surface_name = request.screenshots_dir.name  # e.g. "s2-midview"
    OUTPUT_DIR = output_base / surface_name
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load tokens
    tokens_json = "{}"
    if request.tokens_path:
        tokens_json = request.tokens_path.read_text()

    # Collect images
    provider_config = PROVIDERS[request.provider]
    print(f"\nCollecting screenshots from: {request.screenshots_dir}")
    images = collect_images(request.screenshots_dir, provider_config.max_images)
    print(f"  Found {len(images)} images")

    if len(images) == 0:
        print(
            "FATAL: No screenshots found. A design review without visual evidence "
            "is impossible. Use /surf or /surf-qml to capture screenshots first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Add reference images if provided
    if request.reference_dir:
        print(f"\nCollecting reference images from: {request.reference_dir}")
        ref_images = collect_images(request.reference_dir, provider_config.max_images // 2)
        print(f"  Found {len(ref_images)} reference images")
        # Prefix reference image names
        ref_images = [(f"REFERENCE_{name}", uri) for name, uri in ref_images]
        images.extend(ref_images)

    print(f"\nTotal images for review: {len(images)}")

    # Build code context from explicit files or auto-discovery
    code_context = ""
    if request.code_context_files:
        # Explicit source files provided — include FULL source (not just token-related lines)
        print(f"\nIncluding {len(request.code_context_files)} explicit code context files:")
        context_parts = []
        for f in request.code_context_files:
            fpath = Path(f)
            if fpath.exists():
                content = fpath.read_text()
                print(f"    - {fpath.name} ({len(content):,} chars)")
                context_parts.append(
                    f"### {fpath.name}\n"
                    f"Full source ({len(content.splitlines())} lines):\n"
                    f"```{fpath.suffix.lstrip('.')}\n{content}\n```"
                )
            else:
                print(f"    - {fpath} NOT FOUND, skipping")
        if context_parts:
            code_context = (
                "\n\n## Component Source Code (PRIMARY REVIEW INPUT)\n\n"
                "The following source files define the components visible in the screenshots. "
                "This code is the PRIMARY input for your review — it tells you what the application IS, "
                "what data it displays, and what interactions it supports. "
                "Cross-reference the code with the screenshots to verify that "
                "components render correctly and interactions work as the code intends.\n\n"
                + "\n\n".join(context_parts)
            )
            print(f"  Total code context: {len(code_context):,} chars")
    else:
        # Auto-discover implementation files near screenshots
        print(f"\nLooking for implementation files...")
        impl_files = find_implementation_files(request.screenshots_dir)
        if impl_files:
            print(f"  Found {len(impl_files)} implementation files:")
            for f in impl_files:
                print(f"    - {f.name}")
            code_context = extract_code_context(impl_files, tokens_json)
            if code_context:
                print(f"  Extracted {len(code_context)} chars of code context")
        else:
            print("  No implementation files found - running vision-only review")

    # Run review rounds
    results = []
    session_id = None  # For providers that support session continuity

    for round_num in range(1, request.rounds + 1):
        step1, step2, step3 = run_review_round(
            request,
            round_num,
            images,
            tokens_json,
            code_context,
            session_id,
            output_dir=OUTPUT_DIR,
            system_prompt=system_prompt,
        )

        # Extract structured data
        token_changes = extract_token_changes(step3)

        result = AuditResult(
            summary=f"Round {round_num} completed",
            findings=[],  # Would need parsing to extract
            token_changes=token_changes,
            praise=[],
            round_num=round_num,
            step=3,
            provider=request.provider,
            model=provider_config.model,
        )
        results.append(result)

        # Save structured result
        result_path = OUTPUT_DIR / f"round{round_num}_audit.json"
        result_path.write_text(json.dumps({
            "round": round_num,
            "provider": request.provider,
            "model": provider_config.model,
            "token_changes": token_changes,
            "timestamp": datetime.now().isoformat(),
        }, indent=2))
        print(f"\n    Structured output: {result_path}")

    print(f"\n{'='*60}")
    print("REVIEW COMPLETE")
    print(f"{'='*60}")
    print(f"\nOutput files in: {OUTPUT_DIR}")
    print(f"Final recommendations: {OUTPUT_DIR}/round{request.rounds}_final.md")

    # Post-hook: Learn review findings to memory
    final_output = (OUTPUT_DIR / f"round{request.rounds}_final.md").read_text()
    findings_summary = [f"Round {r.round_num}: {r.summary}" for r in results]
    learn_design_review(
        project=request.persona,
        component=request.title,
        findings=findings_summary,
        providers_used=[request.provider],
    )

    return results


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _write_loop_state(
    path: Path,
    *,
    state: str,
    round_num: int,
    surface: str,
    latest_screenshot: str = "",
    latest_verdict: str = "",
    next_action: str = "",
) -> None:
    path.write_text(json.dumps({
        "state": state,
        "round": round_num,
        "surface": surface,
        "latest_screenshot": latest_screenshot,
        "latest_verdict": latest_verdict,
        "next_action": next_action,
        "updated_at": datetime.now().isoformat(),
    }, indent=2) + "\n")


def _resolve_section_image_paths(section: dict, key: str, base_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for raw_item in section.get(key) or []:
        raw_path = raw_item.get("path") if isinstance(raw_item, dict) else raw_item
        if not raw_path:
            continue
        image_path = Path(raw_path)
        if not image_path.is_absolute():
            image_path = (base_dir / image_path).resolve()
        if image_path.exists() and image_path.is_file():
            paths.append(image_path)
    return paths


def _load_review_sections(sections_path: Optional[Path], screenshots_dir: Path, max_sections: int) -> list[dict]:
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    if sections_path:
        raw = json.loads(sections_path.read_text())
        sections = raw.get("sections", raw) if isinstance(raw, dict) else raw
        normalized = []
        for index, section in enumerate(sections, start=1):
            screenshot_path = Path(section["screenshot"])
            if not screenshot_path.is_absolute():
                screenshot_path = (sections_path.parent / screenshot_path).resolve()
            supporting_screenshots: list[Path] = []
            for key in ("supporting_screenshots", "context_screenshots", "screenshots"):
                supporting_screenshots.extend(_resolve_section_image_paths(section, key, sections_path.parent))
            # Keep the target screenshot first and do not send duplicate images.
            seen = {screenshot_path.resolve()}
            supporting_screenshots = [
                path for path in supporting_screenshots
                if path.resolve() not in seen and not seen.add(path.resolve())
            ]
            normalized.append({
                "id": section.get("id") or f"section-{index:03d}",
                "title": section.get("title") or screenshot_path.stem,
                "purpose": section.get("purpose") or "Review this captured UI state for design blockers.",
                "screenshot": screenshot_path,
                "supporting_screenshots": supporting_screenshots,
            })
        return normalized[:max_sections]

    screenshots = [
        path for path in screenshots_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in image_extensions
        and "vlm_preprocessed" not in path.parts
        and "semantic_review_selection" not in path.parts
    ]
    # Section review must not overfit tight crops. Focus/container crops are
    # useful supporting evidence, but a reviewer needs full context first to
    # judge workflow state, selected object, evidence/provenance, and next
    # action. Prefer full viewport captures, then container stitches, then
    # isolated focus crops.
    screenshots.sort(key=lambda path: (
        2 if "__focus" in path.name else 1 if "__container" in path.name else 0,
        str(path),
    ))
    return [
        {
            "id": f"section-{index:03d}",
            "title": path.stem,
            "purpose": "Auto-selected screenshot from deterministic interaction evidence.",
            "screenshot": path,
            "supporting_screenshots": [],
        }
        for index, path in enumerate(screenshots[:max_sections], start=1)
    ]


def _extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", stripped)
        if match:
            return json.loads(match.group(0))
        raise


def _section_end_state(verdict: dict) -> str:
    if verdict.get("verdict") == "blocked":
        return "blocked"
    missing_evidence = verdict.get("missing_evidence") or []
    if missing_evidence:
        return "blocked"
    screenshot_checks = verdict.get("screenshot_checks") or []
    if verdict.get("verdict") == "satisfied" and not screenshot_checks:
        return "blocked"
    for check in screenshot_checks:
        if isinstance(check, dict) and check.get("passed") is False:
            severity = str(check.get("severity", "medium")).lower()
            if severity in {"critical", "high", "medium"}:
                return "needs_patch"
    for check_group in ("reference_requirements_checked", "manifest_coverage_checks"):
        for check in verdict.get(check_group) or []:
            if isinstance(check, dict) and check.get("passed") is False:
                severity = str(check.get("severity", "medium")).lower()
                if severity in {"critical", "high", "medium"}:
                    return "needs_patch"
    findings = verdict.get("findings") or []
    for finding in findings:
        severity = str(finding.get("severity", "")).lower()
        if severity in {"critical", "high", "medium"}:
            return "needs_patch"
    if verdict.get("verdict") == "needs_changes":
        return "needs_patch"
    return "verified"


def _build_iterate_prompt(section: dict, context_text: str, code_context: str) -> str:
    supporting = section.get("supporting_screenshots") or []
    supporting_lines = "\n".join(f"- `{Path(path).name}`" for path in supporting) or "- none"
    return f"""Review section: {section['title']}

Section purpose:
{section['purpose']}

Attached current-state screenshots:
- Target section screenshot: `{Path(section['screenshot']).name}`
- Supporting context screenshots:
{supporting_lines}

Global context:
{context_text or 'No additional context provided.'}

{code_context}

Review the target screenshot as `{section['id']}`. This is a section-scoped
review inside `$review-design iterate`, but any supporting current-state
screenshots are part of the same evidence packet. Use supporting screenshots to
verify whole-interface context, adjacent panels, selected-object linkage,
event/prompt evidence, or lower-panel continuity before listing missing
evidence.

Your primary job is to catch obvious human-facing UX errors before the project
agent or human sees another false green. Be adversarial about visible workflow
clarity, not decorative polish.

Fail-closed review gates:
- If the screenshot is stale, too broad, too cropped, illegible, or does not show
  the section purpose, and no supporting current-state screenshot proves the
  missing context, return `blocked` and list the missing screenshot evidence.
- If this is an interaction-driven surface and no `$test-interactions` result,
  focused crop, or container screenshot is attached or referenced in the
  context, return `blocked` unless the section is explicitly static/read-only.
- If modern/reference context is provided, compare against it. If no current
  reference context is provided for a complex workflow editor, list that under
  `missing_evidence` instead of pretending the design has been benchmarked.
- If reference screenshots are attached, compare the target screenshot against
  them. If Dogpile references are only URLs/text and the task requires visual
  benchmark comparison, list missing reference screenshots under
  `missing_evidence`.
- Compare visible UI coverage against the `$test-interactions` manifest and
  deterministic results in the context. A target/control/semantic workflow in
  the manifest that is not visible in the target or supporting screenshot
  evidence is missing evidence.
- Repeated unsupported concerns are not consensus. Every critical/high/medium
  finding needs visible screenshot evidence and, when source is supplied, a
  concrete code/layout connection.

Obvious UX error checklist:
- Can the user tell what object is selected and what action happens next?
- Are primary status, evidence, provenance, and end state visible without
  hunting through logs?
- Are review queues, amendment queues, and approval/rejection states readable as
  operational state rather than decorative cards?
- Are disabled, blocked, pending, approved, rejected, stale, and failed states
  visually distinct without relying only on color?
- Are dense tables/panels scannable, non-overlapping, and sized for repeated
  work?
- Are graph nodes, edge labels, inspector panels, and artifact panes connected
  by visible selection/provenance cues?
- Are buttons/controls large enough, titled, and semantically obvious?
- Is any UI implying live truth from static/mock data or missing evidence?

Return strict JSON only with this schema:
{{
  "verdict": "satisfied | needs_changes | blocked",
  "section_id": "{section['id']}",
  "summary": "one sentence",
  "findings": [
    {{
      "severity": "critical | high | medium | low",
      "issue": "specific visual/workflow problem",
      "evidence": "what in the target/supporting screenshot proves it",
      "recommendation": "concrete patch direction"
    }}
  ],
  "modern_reference_gaps": [
    {{
      "reference": "specific modern UI pattern/repo/image/context item if provided",
      "gap": "what the screenshot lacks compared with that reference",
      "severity": "critical | high | medium | low"
    }}
  ],
  "blocking_changes": [],
  "non_blocking_changes": [],
  "screenshot_checks": [
    {{
      "check": "specific visible state or evidence requirement",
      "passed": true,
      "evidence": "exact visible target/supporting screenshot detail",
      "severity": "critical | high | medium | low"
    }}
  ],
  "missing_evidence": [],
  "reference_requirements_checked": [
    {{
      "requirement": "specific requirement from the Dogpile/reference packet",
      "evidence": "target screenshot evidence or reference screenshot/url checked",
      "passed": true,
      "severity": "critical | high | medium | low"
    }}
  ],
  "manifest_coverage_checks": [
    {{
      "manifest_target": "data-qid target or semantic workflow from manifest/results",
      "screenshot_evidence": "where the target/supporting screenshot proves it, or what is missing",
      "passed": true,
      "severity": "critical | high | medium | low"
    }}
  ],
  "do_not_do": []
}}

Critical/high/medium findings must be actionable implementation blockers. Low findings are non-blocking polish unless they hide evidence or user decisions.
"""


async def _review_section_async(
    *,
    section: dict,
    system_prompt: str,
    user_prompt: str,
    provider: str,
    round_dir: Path,
    events_path: Path,
    semaphore: asyncio.Semaphore,
    batch_id: str,
    reference_images: list[tuple[str, str]],
) -> dict:
    section_dir = round_dir / "sections" / section["id"]
    section_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = section_dir / "prompt.md"
    response_path = section_dir / "reviewer.md"
    verdict_path = section_dir / "verdict.json"
    raw_response_path = section_dir / "response.raw.json"
    prompt_path.write_text(user_prompt)

    _append_jsonl(events_path, {
        "event": "reviewer_started",
        "ts": datetime.now().isoformat(),
        "round": round_dir.name,
        "section_id": section["id"],
        "screenshot": str(section["screenshot"]),
    })
    async with semaphore:
        try:
            images = [
                (section["screenshot"].name, encode_image_base64(resize_image_if_needed(section["screenshot"])))
            ]
            for supporting_path in section.get("supporting_screenshots") or []:
                images.append((
                    f"context-{supporting_path.name}",
                    encode_image_base64(resize_image_if_needed(supporting_path)),
                ))
            images += reference_images
            result = await call_scillm_async(
                system_prompt,
                user_prompt,
                images,
                provider,
                item_id=section["id"],
                batch_id=batch_id,
                response_format={"type": "json_object"},
            )
            response_path.write_text(result["content"])
            raw_response_path.write_text(json.dumps(result["raw"], indent=2) + "\n")
            verdict = _extract_json_object(result["content"])
            verdict.setdefault("section_id", section["id"])
            verdict["end_state"] = _section_end_state(verdict)
            verdict["screenshot"] = str(section["screenshot"])
            verdict["supporting_screenshots"] = [
                str(path) for path in section.get("supporting_screenshots") or []
            ]
            verdict["requested_model"] = result["requested_model"]
            verdict["served_model"] = result["served_model"]
            verdict["elapsed_s"] = result["elapsed_s"]
            verdict["review_route"] = "$review-design iterate"
            verdict["persona_bound"] = bool(system_prompt.strip())
            verdict["proof"] = {
                "raw_response": str(raw_response_path),
                "scillm_reasoning": result["raw"].get("scillm_reasoning"),
                "scillm_multimodal": result["raw"].get("scillm_multimodal"),
                "image_seen_by": (
                    (result["raw"].get("scillm_multimodal") or {}).get("image_seen_by")
                ),
                "requested_model": result["requested_model"],
                "served_model": result["served_model"],
                "exact_model_required": True,
            }
            verdict_path.write_text(json.dumps(verdict, indent=2) + "\n")
            _append_jsonl(events_path, {
                "event": "reviewer_finished",
                "ts": datetime.now().isoformat(),
                "section_id": section["id"],
                "served_model": result["served_model"],
                "raw_response": str(raw_response_path),
                "end_state": verdict["end_state"],
                "verdict": verdict.get("verdict"),
                "artifact": str(verdict_path),
            })
            return verdict
        except Exception as exc:  # noqa: BLE001
            failure = {
                "section_id": section["id"],
                "verdict": "blocked",
                "findings": [{
                    "severity": "critical",
                    "issue": "reviewer call failed",
                    "evidence": str(exc),
                    "recommendation": "Fix the scillm/provider failure and rerun this section.",
                }],
                "blocking_changes": [str(exc)],
                "non_blocking_changes": [],
                "screenshot_checks": [],
                "do_not_do": [],
                "end_state": "failed",
                "screenshot": str(section["screenshot"]),
                "supporting_screenshots": [
                    str(path) for path in section.get("supporting_screenshots") or []
                ],
            }
            response_path.write_text(str(exc))
            verdict_path.write_text(json.dumps(failure, indent=2) + "\n")
            _append_jsonl(events_path, {
                "event": "reviewer_failed",
                "ts": datetime.now().isoformat(),
                "section_id": section["id"],
                "end_state": "failed",
                "error": str(exc),
                "artifact": str(verdict_path),
            })
            return failure


async def _run_parallel_iterate_reviews(
    *,
    sections: list[dict],
    system_prompt: str,
    context_text: str,
    code_context: str,
    provider: str,
    round_dir: Path,
    events_path: Path,
    max_concurrency: int,
    batch_id: str,
    reference_images: list[tuple[str, str]],
) -> list[dict]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    tasks = [
        asyncio.create_task(_review_section_async(
            section=section,
            system_prompt=system_prompt,
            user_prompt=_build_iterate_prompt(section, context_text, code_context),
            provider=provider,
            round_dir=round_dir,
            events_path=events_path,
            semaphore=semaphore,
            batch_id=batch_id,
            reference_images=reference_images,
        ))
        for section in sections
    ]
    results = []
    for task in asyncio.as_completed(tasks):
        results.append(await task)
    return results


def _write_iterate_matrix(path: Path, verdicts: list[dict], *, persona: str, round_num: int) -> None:
    lines = [
        "# Review Design Iterate Matrix",
        "",
        "| Round | Persona | Screenshot | Supporting Screenshots | Section | Verdict | Highest Severity | End State | Findings | Missing Evidence | Model/Proof | Artifact |",
        "|---|---|---|---:|---|---|---|---|---:|---|---|---|",
    ]
    for verdict in sorted(verdicts, key=lambda item: item.get("section_id", "")):
        findings = verdict.get("findings") or []
        severities = [str(f.get("severity", "low")).lower() for f in findings]
        rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        highest = max(severities, key=lambda severity: rank.get(severity, 0), default="none")
        section_id = verdict.get("section_id", "")
        proof = verdict.get("proof") or {}
        proof_bits = []
        if verdict.get("served_model"):
            proof_bits.append(f"served={verdict.get('served_model')}")
        if proof.get("image_seen_by"):
            proof_bits.append(f"image={proof.get('image_seen_by')}")
        missing = verdict.get("missing_evidence") or []
        supporting_count = len(verdict.get("supporting_screenshots") or [])
        lines.append(
            f"| {round_num} | `{persona}` | `{verdict.get('screenshot', '')}` | {supporting_count} | `{section_id}` | "
            f"{verdict.get('verdict', '')} | {highest} | {verdict.get('end_state', '')} | "
            f"{len(findings)} | {', '.join(map(str, missing)) if missing else ''} | "
            f"{'<br>'.join(proof_bits)} | "
            f"`rounds/001/sections/{section_id}/verdict.json` |"
        )
    path.write_text("\n".join(lines) + "\n")


app = typer.Typer(help="AI-powered design review for UI screenshots")


@app.command()
def review(
    screenshots: Path = typer.Option(..., "-s", "--screenshots", help="Directory containing UI screenshots to review"),
    persona: str = typer.Option(..., "--persona", help="REQUIRED: Persona agent name (e.g. brandon-bailey, rob-armstrong). No persona = no review."),
    tokens: Optional[Path] = typer.Option(None, "-t", "--tokens", help="Path to design tokens JSON file"),
    reference: Optional[Path] = typer.Option(None, "-r", "--reference", help="Directory containing reference/target design screenshots"),
    code_context_files: Optional[list[Path]] = typer.Option(None, "-c", "--code-context", help="Source files to include as animation/implementation context (e.g. EmbryThinkingIcon.tsx)"),
    provider: str = typer.Option(DEFAULT_PROVIDER, "-p", "--provider", help=f"Vision LLM provider (default: {DEFAULT_PROVIDER})"),
    rounds: int = typer.Option(DEFAULT_ROUNDS, "-n", "--rounds", help=f"Number of review rounds (default: {DEFAULT_ROUNDS})"),
    focus: Optional[list[str]] = typer.Option(None, help="Focus area for review (can be repeated)"),
    title: str = typer.Option("Design Review", help="Title for the review"),
):
    """Run design review. REQUIRES --persona — a review without a persona is a failure."""
    request = ReviewRequest(
        screenshots_dir=screenshots,
        persona=persona,
        tokens_path=tokens,
        reference_dir=reference,
        provider=provider,
        rounds=rounds,
        title=title,
        focus_areas=focus or [],
        code_context_files=code_context_files or [],
    )
    run_full_review(request)


@app.command("iterate")
def iterate_cmd(
    screenshots: Optional[Path] = typer.Option(None, "-s", "--screenshots", help="Directory containing fresh screenshots or test-interactions captures"),
    persona: str = typer.Option(..., "--persona", help="REQUIRED: Persona agent name"),
    manifest: Optional[Path] = typer.Option(None, "--manifest", help="Optional test-interactions manifest to run before review"),
    output_dir: Optional[Path] = typer.Option(None, "-o", "--output-dir", help="Durable loop artifact directory"),
    sections: Optional[Path] = typer.Option(None, "--sections", help="Optional JSON section manifest; otherwise one section per selected screenshot"),
    code_context_files: Optional[list[Path]] = typer.Option(None, "-c", "--code-context", help="Source files to include in every section review"),
    provider: str = typer.Option(DEFAULT_PROVIDER, "-p", "--provider", help="Provider; iterate batching currently requires scillm/vlm/subagent"),
    max_sections: int = typer.Option(8, "--max-sections", help="Maximum screenshots/sections to review in one batch"),
    max_concurrency: int = typer.Option(3, "--max-concurrency", help="Maximum concurrent scillm review calls"),
    context: str = typer.Option("", "--context", help="Global review context"),
    context_file: Optional[Path] = typer.Option(None, "--context-file", help="File containing global review context"),
    modern_reference: Optional[Path] = typer.Option(None, "--modern-reference", help="Dogpile/current-design reference report to require reviewers to compare against"),
    reference_screenshots: Optional[Path] = typer.Option(None, "--reference-screenshots", help="Directory of captured modern/reference screenshots to attach to each section review"),
    require_modern_reference: bool = typer.Option(False, "--require-modern-reference", help="Fail closed unless --modern-reference is supplied"),
    require_reference_persona_match: bool = typer.Option(True, "--require-reference-persona-match/--allow-reference-persona-mismatch", help="When modern reference is required, require Dogpile request_context.persona to match --persona"),
    title: str = typer.Option("Design Review Iterate", "--title", help="Surface title"),
):
    """Run a parallelized review-design iterate batch over fresh UI evidence.

    Deterministic browser interactions remain sequential in test-interactions.
    Independent screenshot/section reviewer calls are batched through scillm
    with asyncio.create_task + as_completed.
    """
    provider = normalize_provider(provider)
    if provider != "scillm":
        print("review-design iterate batches through scillm only; use --provider scillm/vlm/subagent", file=sys.stderr)
        raise typer.Exit(2)
    if require_modern_reference and not modern_reference:
        print(
            "--require-modern-reference was set but no --modern-reference report was supplied. "
            "Run $dogpile and pass its report/partial-results path.",
            file=sys.stderr,
        )
        raise typer.Exit(2)

    check_scillm_health()

    loop_root = output_dir or (
        Path(os.environ.get("REVIEW_DESIGN_OUTPUT_BASE", str(OUTPUT_BASE)))
        / f"{(screenshots or manifest or Path(title)).stem}-iterate"
    )
    loop_root.mkdir(parents=True, exist_ok=True)
    state_path = loop_root / "state.json"
    events_path = loop_root / "events.jsonl"
    round_num = 1
    round_dir = loop_root / "rounds" / f"{round_num:03d}"
    round_dir.mkdir(parents=True, exist_ok=True)

    _write_loop_state(
        state_path,
        state="running",
        round_num=round_num,
        surface=title,
        next_action="test_interactions" if manifest else "parallel_review",
    )
    _append_jsonl(events_path, {
        "event": "round_started",
        "ts": datetime.now().isoformat(),
        "round": round_num,
        "surface": title,
        "parallelizable": "section reviewer calls",
    })

    evidence_context_parts = []
    if manifest:
        if not manifest.exists():
            print(f"Test interactions manifest not found: {manifest}", file=sys.stderr)
            raise typer.Exit(2)
        (round_dir / "test-interactions-manifest.snapshot.json").write_text(manifest.read_text())
        evidence_context_parts.append(_summarize_test_interactions_manifest(manifest))
        test_run = Path(__file__).resolve().parent.parent / "test-interactions" / "run.sh"
        captures_dir = round_dir / "interaction-captures"
        cmd = [str(test_run), "run", "--manifest", str(manifest), "--output-dir", str(captures_dir)]
        _append_jsonl(events_path, {
            "event": "test_interactions_started",
            "ts": datetime.now().isoformat(),
            "command": cmd,
            "end_state": "running",
        })
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        (round_dir / "test-interactions.stdout.log").write_text(proc.stdout)
        (round_dir / "test-interactions.stderr.log").write_text(proc.stderr)
        if proc.returncode != 0:
            _append_jsonl(events_path, {
                "event": "test_interactions_finished",
                "ts": datetime.now().isoformat(),
                "returncode": proc.returncode,
                "end_state": "failed",
                "artifact": str(captures_dir / "results.json"),
            })
            _write_loop_state(
                state_path,
                state="failed",
                round_num=round_num,
                surface=title,
                latest_verdict=str(captures_dir / "results.json"),
                next_action="patch_test_interactions_failure",
            )
            raise typer.Exit(proc.returncode)
        screenshots = captures_dir
        _append_jsonl(events_path, {
            "event": "test_interactions_finished",
            "ts": datetime.now().isoformat(),
            "returncode": proc.returncode,
                "end_state": "verified",
                "artifact": str(captures_dir / "results.json"),
            })
        evidence_context_parts.append(_summarize_test_interactions_results(captures_dir / "results.json"))

    if screenshots is None:
        print("Either --screenshots or --manifest is required.", file=sys.stderr)
        raise typer.Exit(2)
    if not screenshots.exists():
        print(f"Screenshots/captures directory not found: {screenshots}", file=sys.stderr)
        raise typer.Exit(2)

    print(f"\n{'='*60}")
    print(f"PERSONA: {persona}")
    print(f"{'='*60}")
    persona_context = load_persona_context(persona)
    system_prompt = build_persona_system_prompt(persona, persona_context)
    context_text = _read_context(context or None, context_file)
    if evidence_context_parts:
        context_text += "\n\n" + "\n\n".join(evidence_context_parts)
    if modern_reference:
        context_text += "\n\n" + _read_modern_reference(
            modern_reference,
            persona=persona,
            require_persona_match=require_modern_reference and require_reference_persona_match,
        )
    reference_images, reference_screenshot_context = _collect_reference_screenshot_images(reference_screenshots)
    context_text += "\n\n" + reference_screenshot_context

    context_parts = []
    for fpath in code_context_files or []:
        if fpath.exists():
            content = fpath.read_text()
            context_parts.append(
                f"### {fpath}\nFull source ({len(content.splitlines())} lines):\n"
                f"```{fpath.suffix.lstrip('.')}\n{content}\n```"
            )
    code_context = ""
    if context_parts:
        code_context = (
            "Implementation context. Use this to connect visual findings to code, "
            "but do not claim satisfaction without screenshot evidence.\n\n"
            + "\n\n".join(context_parts)
        )

    review_sections = _load_review_sections(sections, screenshots, max_sections)
    if not review_sections:
        print(f"No screenshots found under {screenshots}", file=sys.stderr)
        raise typer.Exit(2)

    (round_dir / "sections_manifest.json").write_text(json.dumps(review_sections, indent=2, default=str) + "\n")
    batch_id = f"review-design-iterate-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    _append_jsonl(events_path, {
        "event": "parallel_review_started",
        "ts": datetime.now().isoformat(),
        "round": round_num,
        "batch_id": batch_id,
        "sections": len(review_sections),
        "max_concurrency": max_concurrency,
        "end_state": "running",
    })

    verdicts = asyncio.run(_run_parallel_iterate_reviews(
        sections=review_sections,
        system_prompt=system_prompt,
        context_text=context_text,
        code_context=code_context,
        provider=provider,
        round_dir=round_dir,
        events_path=events_path,
        max_concurrency=max_concurrency,
        batch_id=batch_id,
        reference_images=reference_images,
    ))

    matrix_path = loop_root / "DESIGN_REVIEW_ITERATE_MATRIX.md"
    _write_iterate_matrix(matrix_path, verdicts, persona=persona, round_num=round_num)
    aggregate_path = round_dir / "aggregate_verdict.json"
    state = "verified"
    next_action = "accept_or_record_low_followups"
    if any(v.get("end_state") == "failed" for v in verdicts):
        state = "failed"
        next_action = "fix_reviewer_failures"
    elif any(v.get("end_state") in {"blocked", "needs_patch"} for v in verdicts):
        state = "needs_patch"
        next_action = "patch_valid_blockers"
    aggregate = {
        "round": round_num,
        "state": state,
        "sections": len(verdicts),
        "matrix": str(matrix_path),
        "verdicts": verdicts,
        "updated_at": datetime.now().isoformat(),
    }
    aggregate_path.write_text(json.dumps(aggregate, indent=2) + "\n")
    _append_jsonl(events_path, {
        "event": "parallel_review_finished",
        "ts": datetime.now().isoformat(),
        "round": round_num,
        "sections": len(verdicts),
        "end_state": state,
        "artifact": str(aggregate_path),
        "matrix": str(matrix_path),
    })
    _write_loop_state(
        state_path,
        state=state,
        round_num=round_num,
        surface=title,
        latest_screenshot=str(review_sections[-1]["screenshot"]),
        latest_verdict=str(aggregate_path),
        next_action=next_action,
    )
    print(json.dumps({
        "state": state,
        "state_json": str(state_path),
        "events_jsonl": str(events_path),
        "matrix": str(matrix_path),
        "aggregate_verdict": str(aggregate_path),
    }, indent=2))
    if state in {"failed", "needs_patch"}:
        raise typer.Exit(1)


@app.command("check")
def check_cmd(
    provider: str = typer.Option(DEFAULT_PROVIDER, "-p", "--provider", help=f"Provider to check (default: {DEFAULT_PROVIDER})"),
):
    """Check provider access."""
    provider = normalize_provider(provider)
    prov = PROVIDERS[provider]
    print(f"Checking {prov.name}...")
    print(f"  CLI: {prov.cli}")
    print(f"  Model: {prov.model}")
    print(f"  Vision: {prov.supports_vision}")

    if provider == "scillm":
        check_scillm_health()
        print("  scillm health: ok")
    else:
        result = subprocess.run(
            ["which", prov.cli],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  CLI found: {result.stdout.strip()}")
        else:
            print(f"  CLI not found: {prov.cli}")
            raise typer.Exit(code=1)


@app.command()
def bundle(
    screenshots: Path = typer.Option(..., "-s", "--screenshots", help="Directory containing UI screenshots"),
    tokens: Optional[Path] = typer.Option(None, "-t", "--tokens", help="Path to design tokens JSON file"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output markdown file"),
):
    """Generate review request bundle."""
    if output is None:
        output_dir = _artifact_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "review_request.md"

    print(f"Generating review bundle: {output}")

    images = collect_images(screenshots)

    tokens_json = "{}"
    if tokens:
        tokens_json = tokens.read_text()

    bundle_content = f"# Design Review Request\n\n"
    bundle_content += f"Generated: {datetime.now().isoformat()}\n\n"
    bundle_content += "## Screenshots\n\n"
    for name, uri in images:
        bundle_content += f"### {name}\n![{name}]({uri})\n\n"
    bundle_content += "## Design Tokens\n\n```json\n"
    bundle_content += tokens_json
    bundle_content += "\n```\n\n"
    bundle_content += "## Review Prompt\n\n"
    bundle_content += format_step1_prompt(tokens_json)

    output.write_text(bundle_content)
    print(f"  Saved: {output}")
    print(f"  Size: {len(bundle_content):,} bytes")


@app.command("bundle-code")
def bundle_code(
    files: list[Path] = typer.Option([], "-f", "--files", help="Source files to include (repeatable)"),
    css: list[Path] = typer.Option([], "--css", help="CSS/style files to include (repeatable)"),
    test_results: Optional[Path] = typer.Option(None, "--test-results", help="Test results JSON file"),
    git_diff: Optional[str] = typer.Option(None, "--git-diff", help="Git ref to diff against (e.g., HEAD~3)"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output markdown file"),
    context: Optional[str] = typer.Option(None, "-c", "--context", help="Project context/rationale for the review"),
    context_file: Optional[Path] = typer.Option(None, "--context-file", help="File containing project context"),
    focus: str = typer.Option("", "--focus", help="Specific review focus areas (comma-separated)"),
    clipboard: bool = typer.Option(False, "--clipboard", help="Copy to clipboard instead of file"),
):
    """Generate COMPLETE code review bundle for external LLMs.

    Bundles ALL code from specified files with full context for honest review.
    No truncation - the reviewer sees everything.
    """
    from datetime import datetime
    import subprocess

    if output is None:
        output_dir = _artifact_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "REVIEW_BUNDLE.md"

    bundle_parts = []

    # === HEADER WITH RATIONALE ===
    bundle_parts.append("# Design Code Review Bundle\n\n")
    bundle_parts.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    bundle_parts.append(f"**Files included:** {len(files) + len(css)}\n")

    # Context/rationale section - REQUIRED for meaningful review
    bundle_parts.append("\n---\n\n## Context & Rationale\n\n")
    if context_file and context_file.exists():
        bundle_parts.append(context_file.read_text())
        bundle_parts.append("\n")
    elif context:
        bundle_parts.append(context)
        bundle_parts.append("\n")
    else:
        bundle_parts.append("**WARNING: No context provided.** Use --context or --context-file to explain:\n")
        bundle_parts.append("- What this code does\n")
        bundle_parts.append("- What problem it solves\n")
        bundle_parts.append("- What constraints apply (COTS, WCAG, etc.)\n")
        bundle_parts.append("- What specific feedback you need\n\n")

    # Review focus
    if focus:
        bundle_parts.append("\n### Review Focus\n")
        for item in focus.split(","):
            bundle_parts.append(f"- {item.strip()}\n")

    bundle_parts.append("\n---\n")

    # === TEST RESULTS (if provided) - FULL DETAILS ===
    if test_results and test_results.exists():
        try:
            results = json.loads(test_results.read_text())
            bundle_parts.append("\n## Test Results\n\n")

            # Summary
            passed = results.get('passed', results.get('summary', {}).get('pass', 0))
            failed = results.get('failed', results.get('summary', {}).get('fail', 0))
            total = results.get('total', results.get('summary', {}).get('total', 0))
            bundle_parts.append(f"**Summary:** {passed} PASS / {failed} FAIL / {total} total\n\n")

            # ALL failures - not truncated
            failures = results.get('failures', [])
            if failures:
                bundle_parts.append("### Failures (ALL)\n\n")
                for f in failures:
                    bundle_parts.append(f"- {f}\n")
                bundle_parts.append("\n")

            # Individual test details if available
            interactions = results.get('interactions', [])
            if interactions:
                bundle_parts.append("### Test Details\n\n")
                bundle_parts.append("| Test | Status | Evidence |\n")
                bundle_parts.append("|------|--------|----------|\n")
                for test in interactions:
                    status = test.get('status', 'UNKNOWN')
                    desc = test.get('description', 'N/A')[:50]
                    evidence = test.get('evidence', 'N/A')[:60].replace('|', '\\|')
                    bundle_parts.append(f"| {desc} | {status} | {evidence} |\n")
                bundle_parts.append("\n")

        except Exception as e:
            bundle_parts.append(f"\n## Test Results\n\n**Error parsing:** {e}\n\n")

    # === GIT DIFF (if provided) - FULL ===
    if git_diff:
        try:
            result = subprocess.run(
                ["git", "diff", "--no-color", git_diff],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                bundle_parts.append(f"\n## Git Diff (vs {git_diff})\n\n```diff\n")
                bundle_parts.append(result.stdout)  # FULL diff, no truncation
                bundle_parts.append("```\n\n")
        except Exception as e:
            bundle_parts.append(f"\n## Git Diff\n\n**Error:** {e}\n\n")

    # === SOURCE FILES - COMPLETE, NO TRUNCATION ===
    bundle_parts.append("\n---\n\n## Source Files\n")

    for file_path in files:
        if file_path.exists():
            content = file_path.read_text()
            lines = len(content.split('\n'))
            bundle_parts.append(f"\n### {file_path.name} ({lines} lines)\n\n")
            bundle_parts.append(f"**Path:** `{file_path}`\n\n")

            # Detect language from extension
            ext = file_path.suffix[1:] if file_path.suffix else ''
            lang_map = {'tsx': 'tsx', 'ts': 'typescript', 'jsx': 'jsx', 'js': 'javascript', 'py': 'python'}
            lang = lang_map.get(ext, ext)

            bundle_parts.append(f"```{lang}\n")
            bundle_parts.append(content)  # FULL content
            bundle_parts.append("\n```\n")
        else:
            bundle_parts.append(f"\n### {file_path.name}\n\n**ERROR:** File not found: `{file_path}`\n\n")

    # === CSS FILES - COMPLETE ===
    for css_path in css:
        if css_path.exists():
            content = css_path.read_text()
            lines = len(content.split('\n'))
            bundle_parts.append(f"\n### {css_path.name} ({lines} lines)\n\n")
            bundle_parts.append(f"**Path:** `{css_path}`\n\n")
            bundle_parts.append("```css\n")
            bundle_parts.append(content)  # FULL content
            bundle_parts.append("\n```\n")
        else:
            bundle_parts.append(f"\n### {css_path.name}\n\n**ERROR:** File not found: `{css_path}`\n\n")

    # === REVIEW QUESTIONS ===
    bundle_parts.append("\n---\n\n## Review Questions\n\n")
    bundle_parts.append("Please provide specific, actionable feedback on:\n\n")
    bundle_parts.append("1. **Bugs/Logic Errors** - Any code that won't work as intended?\n")
    bundle_parts.append("2. **Best Practices** - Violations of React/TypeScript/CSS conventions?\n")
    bundle_parts.append("3. **Accessibility** - WCAG 2.1 AA compliance issues?\n")
    bundle_parts.append("4. **Performance** - Unnecessary re-renders, memory leaks, slow paths?\n")
    bundle_parts.append("5. **Security** - XSS, injection, or data exposure risks?\n")
    bundle_parts.append("6. **Test Failures** - Root cause analysis of failing tests?\n")
    bundle_parts.append("\nFor each issue found, specify: file, line number, problem, and suggested fix.\n")

    bundle_content = ''.join(bundle_parts)

    # Calculate stats
    total_bytes = len(bundle_content)
    total_lines = bundle_content.count('\n')

    if clipboard:
        try:
            backend = _copy_text_to_clipboard(bundle_content)
            print(f"Copied to clipboard ({backend})")
            print(f"  Size: {total_bytes:,} bytes ({total_lines:,} lines)")
        except Exception as e:
            print(f"Clipboard copy failed: {e}")
            print("Falling back to file output...")
            output.write_text(bundle_content)
            print(f"Saved: {output}")
    else:
        output.write_text(bundle_content)
        print(f"Saved: {output}")
        print(f"  Size: {total_bytes:,} bytes ({total_lines:,} lines)")
        print(f"  Files: {len(files) + len(css)}")
        print(f"\nTo copy: cat {output} | wl-copy")


@app.command("bundle-upload")
def bundle_upload(
    screenshots: Path = typer.Option(..., "-s", "--screenshots", help="Directory containing screenshot files"),
    files: list[Path] = typer.Option([], "-f", "--files", help="Relevant source files to include (repeatable)"),
    css: list[Path] = typer.Option([], "--css", help="Relevant CSS/style files to include (repeatable)"),
    git_diff: Optional[str] = typer.Option(None, "--git-diff", help="Git ref to diff against (e.g., HEAD~3)"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output zip file"),
    context: Optional[str] = typer.Option(None, "-c", "--context", help="Project context/rationale for the review"),
    context_file: Optional[Path] = typer.Option(None, "--context-file", help="File containing project context"),
    focus: str = typer.Option("", "--focus", help="Specific review focus areas (comma-separated)"),
    target: str = typer.Option("external web LLM", "--target", help="Target review surface, e.g. Gemini web, Claude web"),
    core_objective: Optional[str] = typer.Option(None, "--core-objective", help="Primary decision or workflow objective for the review"),
    audit_target: list[str] = typer.Option([], "--audit-target", help="Specific code-aware audit target or requirement/implementation conflict (repeatable)"),
    known_issue: list[str] = typer.Option([], "--known-issue", help="Concrete UX failures or prior rejected patterns (repeatable)"),
    surface_role: list[str] = typer.Option([], "--surface-role", help="What each pane/tab is supposed to do (repeatable)"),
    request_mockup: bool = typer.Option(False, "--request-mockup", help="Ask the reviewer for an HTML/CSS or layout mockup of the proposed information flow"),
    max_files: int = typer.Option(10, "--max-files", min=3, help="Maximum files allowed inside the zip"),
    clipboard_file: bool = typer.Option(False, "--clipboard-file", help="Copy the resulting zip file to the clipboard as a file reference"),
):
    """Generate a low-file-count upload zip for external web LLM review."""
    if output is None:
        output_dir = _artifact_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "REVIEW_UPLOAD_PACKAGE.zip"

    if not screenshots.exists() or not screenshots.is_dir():
        raise typer.BadParameter(f"Screenshots directory not found: {screenshots}")

    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    screenshot_paths = [
        path for path in sorted(screenshots.iterdir())
        if path.is_file() and path.suffix.lower() in image_extensions
    ]
    if not screenshot_paths:
        raise typer.BadParameter("At least one screenshot is required.")

    reserved_files = 3  # request + code bundle + diff
    allowed_screenshots = max_files - reserved_files
    if allowed_screenshots < 1:
        raise typer.BadParameter("--max-files must allow at least one screenshot.")
    screenshot_paths = screenshot_paths[:allowed_screenshots]

    context_text = _read_context(context, context_file)

    with tempfile.TemporaryDirectory(prefix="review_design_upload_") as tmpdir:
        bundle_dir = Path(tmpdir)
        request_path = bundle_dir / "REVIEW_REQUEST.md"
        code_bundle_path = bundle_dir / "REACT_COMPONENTS_BUNDLE.md"
        diff_path = bundle_dir / "DIFF.md"

        _write_design_review_request(
            request_path,
            context_text=context_text,
            focus=focus,
            files=[*files, *css],
            screenshot_names=[path.name for path in screenshot_paths],
            target=target,
            known_issues=known_issue,
            surface_roles=surface_role,
            core_objective=core_objective,
            audit_targets=audit_target,
            request_mockup=request_mockup,
        )
        _write_code_bundle(code_bundle_path, files, css)
        _write_diff_bundle(diff_path, git_diff, files, css)

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(request_path, request_path.name)
            archive.write(code_bundle_path, code_bundle_path.name)
            archive.write(diff_path, diff_path.name)
            for screenshot_path in screenshot_paths:
                archive.write(screenshot_path, screenshot_path.name)

    with zipfile.ZipFile(output) as archive:
        count = len(archive.namelist())
        if count > max_files:
            raise RuntimeError(f"Generated zip has {count} files, exceeds --max-files={max_files}")

    print(f"Saved: {output}")
    print(f"  Files in zip: {count}")
    print(f"  Screenshots included: {len(screenshot_paths)}")
    print(f"  Target: {target}")
    if clipboard_file:
        backend = _copy_file_to_clipboard(output.resolve())
        print(f"Copied zip to clipboard as file reference ({backend})")


@app.command("webgpt-review")
def webgpt_review(
    persona: str = typer.Option(..., "--persona", help="REQUIRED: Persona agent name or reviewer role"),
    screenshots: Optional[Path] = typer.Option(None, "-s", "--screenshots", help="Directory containing screenshot files"),
    files: list[Path] = typer.Option([], "-f", "--files", help="Relevant source files to include (repeatable)"),
    css: list[Path] = typer.Option([], "--css", help="Relevant CSS/style files to include (repeatable)"),
    context: Optional[str] = typer.Option(None, "-c", "--context", help="Project context/rationale for the review"),
    context_file: Optional[Path] = typer.Option(None, "--context-file", help="File containing project context"),
    focus: str = typer.Option("", "--focus", help="Specific review focus areas (comma-separated)"),
    core_objective: Optional[str] = typer.Option(None, "--core-objective", help="Primary decision or workflow objective for the review"),
    audit_target: list[str] = typer.Option([], "--audit-target", help="Specific code-aware audit target or requirement/implementation conflict (repeatable)"),
    known_issue: list[str] = typer.Option([], "--known-issue", help="Concrete UX failures or prior rejected patterns (repeatable)"),
    surface_role: list[str] = typer.Option([], "--surface-role", help="What each pane/tab is supposed to do (repeatable)"),
    output_dir: Optional[Path] = typer.Option(None, "-o", "--output-dir", help="Directory for WebGPT review artifacts"),
    tab_id: str = typer.Option("", "--tab-id", help="ChatGPT tab id to use for surf webgpt.submit"),
    url: str = typer.Option("", "--url", help="Already-open ChatGPT conversation URL to resolve to a tab"),
    timeout: int = typer.Option(900, "--timeout", help="WebGPT timeout seconds"),
    submit_text_only: bool = typer.Option(False, "--submit-text-only", help="Submit the text bundle through surf; screenshots are listed but not visually attached"),
    clipboard_file: bool = typer.Option(False, "--clipboard-file", help="Copy upload zip to clipboard as a file reference"),
):
    """Generate a WebGPT design review handoff and optionally submit the text bundle.

    This command is honest about current automation limits: surf can reliably
    submit text to WebGPT, but this path does not attach screenshot files to
    ChatGPT. For actual visual review, upload the generated zip manually or use
    a future surf file-attachment path.
    """
    if not persona.strip():
        raise typer.BadParameter("--persona is required")

    if output_dir is None:
        output_dir = _artifact_dir() / "webgpt-review" / datetime.now().strftime("%Y%m%dT%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    context_text = _read_context(context, context_file)
    screenshot_paths: list[Path] = []
    if screenshots:
        if not screenshots.exists() or not screenshots.is_dir():
            raise typer.BadParameter(f"Screenshots directory not found: {screenshots}")
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        screenshot_paths = [
            path for path in sorted(screenshots.iterdir())
            if path.is_file() and path.suffix.lower() in image_extensions
        ]
        if not screenshot_paths:
            raise typer.BadParameter("Screenshots directory provided but contains no images.")

    request_path = output_dir / "WEBGPT_REVIEW_REQUEST.md"
    code_bundle_path = output_dir / "REACT_COMPONENTS_BUNDLE.md"
    zip_path = output_dir / "WEBGPT_REVIEW_UPLOAD_PACKAGE.zip"

    _write_code_bundle(code_bundle_path, files, css)
    _write_design_review_request(
        request_path,
        context_text=context_text,
        focus=focus,
        files=[*files, *css],
        screenshot_names=[path.name for path in screenshot_paths],
        target="WebGPT",
        known_issues=known_issue,
        surface_roles=surface_role,
        core_objective=core_objective,
        audit_targets=audit_target,
        request_mockup=False,
    )
    with request_path.open("a") as handle:
        handle.write(
            f"\n## Reviewer Persona\n\n"
            f"Review as `{persona}`. Apply that persona's domain priorities when weighing hierarchy, workflow fit, risk, and evidence clarity.\n"
            "\n## WebGPT Automation Note\n\n"
            "If this request is submitted through `surf webgpt.submit`, screenshot files are not visually attached. "
            "Do not claim screenshot inspection unless the screenshots are manually uploaded or a file-attachment path is used. "
            "For text-only submission, review the stated context, source excerpts, and design contract only.\n"
        )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(request_path, request_path.name)
        archive.write(code_bundle_path, code_bundle_path.name)
        for screenshot_path in screenshot_paths[:8]:
            archive.write(screenshot_path, screenshot_path.name)

    result = {
        "status": "bundle_created",
        "persona": persona,
        "request_md": str(request_path),
        "code_bundle": str(code_bundle_path),
        "upload_zip": str(zip_path),
        "screenshots": [str(path) for path in screenshot_paths],
        "submit_text_only": submit_text_only,
        "webgpt": None,
    }

    if clipboard_file:
        result["clipboard"] = _copy_file_to_clipboard(zip_path.resolve())

    if submit_text_only:
        surf_run = Path(__file__).resolve().parent.parent / "surf" / "run.sh"
        response_path = output_dir / "WEBGPT_RESPONSE.md"
        meta_path = output_dir / "WEBGPT_RESPONSE.meta.json"
        command = [
            str(surf_run), "webgpt.submit",
            "--input", str(request_path),
            "--output", str(response_path),
            "--meta-output", str(meta_path),
            "--timeout", str(timeout),
            "--stable-polls", "3",
        ]
        if tab_id:
            command.extend(["--tab-id", tab_id])
        if url:
            command.extend(["--url", url])
        proc = subprocess.run(command, cwd=surf_run.parent, capture_output=True, text=True, timeout=timeout + 60)
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        result["status"] = "submitted_text_only" if proc.returncode == 0 else "submission_failed"
        result["webgpt"] = {
            "command": command,
            "returncode": proc.returncode,
            "response_md": str(response_path),
            "meta_json": str(meta_path),
            "controlled_tab_id": meta.get("controlled_tab_id"),
            "requested_tab_id": meta.get("requested_tab_id"),
            "requested_url": meta.get("requested_url"),
            "raw_contains_sentinel": meta.get("raw_contains_sentinel"),
            "clean_contains_sentinel": meta.get("clean_contains_sentinel"),
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-8000:],
            "visual_review_status": "not_visual_unless_screenshots_uploaded",
        }

    result_path = output_dir / "webgpt-review-result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if result["status"] == "submission_failed":
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
