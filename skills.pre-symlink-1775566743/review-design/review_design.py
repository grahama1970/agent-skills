"""
Main orchestrator for the review-design skill.

Implements the 3-step design review pipeline:
1. Audit - Analyze screenshots against tokens and reference
2. Judge - Critique the audit findings
3. Finalize - Produce actionable recommendations
"""

import typer
import base64
import json
import subprocess
import sys
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
)
from memory_integration import recall_prior_design_reviews, learn_design_review
from prompts import (
    SYSTEM_PROMPT,
    build_persona_system_prompt,
    format_step1_prompt,
    format_step2_prompt,
    format_step3_prompt,
)


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


from providers import call_provider  # noqa: E402 — provider dispatch (claude, openai, gemini, subagent)


def find_implementation_files(screenshots_dir: Path) -> list[Path]:
    """Find potential implementation files near the screenshots directory.

    Looks for common UI file patterns (QML, CSS, TSX, etc.) in parent directories.
    """
    impl_files = []
    search_patterns = [
        "*.qml", "*.css", "*.scss", "*.tsx", "*.jsx",
        "*.vue", "*.svelte", "*Style*.py", "*style*.ts"
    ]

    # Search up to 3 levels up from screenshots dir
    search_dirs = [screenshots_dir.parent, screenshots_dir.parent.parent]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for pattern in search_patterns:
            for path in search_dir.rglob(pattern):
                if path.is_file() and path.stat().st_size < 100000:  # Skip huge files
                    impl_files.append(path)

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
    agents_dir = Path(__file__).parent.parent.parent / "agents"
    agents_md = agents_dir / persona_name / "AGENTS.md"
    if agents_md.exists():
        agents_content = agents_md.read_text()
        context_parts.append(f"## Persona Identity: {persona_name}\n\n{agents_content}")
        print(f"  Loaded persona AGENTS.md: {agents_md} ({len(agents_content):,} chars)")
    else:
        print(f"  WARNING: No AGENTS.md found at {agents_md}")

    # 2. Memory recall — get persona's QRA corpus, relationships, domain knowledge
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

    # Derive output directory from screenshots path (e.g. s2-midview → review-output/s2-midview/)
    surface_name = request.screenshots_dir.name  # e.g. "s2-midview"
    OUTPUT_DIR = OUTPUT_BASE / surface_name
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


@app.command("check")
def check_cmd(
    provider: str = typer.Option(DEFAULT_PROVIDER, "-p", "--provider", help=f"Provider to check (default: {DEFAULT_PROVIDER})"),
):
    """Check provider access."""
    prov = PROVIDERS[provider]
    print(f"Checking {prov.name}...")
    print(f"  CLI: {prov.cli}")
    print(f"  Model: {prov.model}")
    print(f"  Vision: {prov.supports_vision}")

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
    output: Path = typer.Option(Path("review_request.md"), "-o", "--output", help="Output markdown file"),
):
    """Generate review request bundle."""
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


if __name__ == "__main__":
    app()
