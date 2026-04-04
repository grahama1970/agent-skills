#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.12.3",
#   "loguru>=0.7.0",
#   "httpx>=0.27.0",
# ]
# ///
"""heal-failures: auto-triage and self-correct extraction failures.

Three modes:
  1. retry   — re-run retryable infra failures (timeout, 429) with pdf_oxide
  2. fixture — generate synthetic PDFs for quality failures, run /pdf-lab convergence
  3. analyze — VLM-powered failure analysis: screenshot TOC, extract S00/S04 delta

This is the agent loop that Nico's Corpus viewer triggers. Deterministic triage
decides what to do; the agent decides HOW to fix quality issues.
"""

from __future__ import annotations
import os

import json
import subprocess
import sys
from pathlib import Path

import httpx
import typer
from loguru import logger

from heal_analysis import FailureAnalysis, analyze_failure

app = typer.Typer(no_args_is_help=True, add_completion=False)

MANIFEST = Path("/mnt/storage12tb/extractor_corpus/metadata/manifest.jsonl")
PATTERN_REGISTRY = Path("/mnt/storage12tb/extractor_corpus/metadata/pattern_registry.json")
FIXTURES_DIR = Path("/mnt/storage12tb/extractor_corpus/fixtures/generated")
SKILLS_DIR = Path(__file__).parent.parent

RETRYABLE_ERRORS = {"timeout", "429", "preflight failed", "rate limit", "502"}
SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_AUTH = {"Authorization": "Bearer sk-dev-proxy-123"}

# All available /fixture-tricky trick names by category
AVAILABLE_TRICKS = {
    "false-tables": ["numbered-list", "address-block", "code-block", "signature-block",
                     "key-value-pairs", "toc-entries", "receipt-text", "form-fields", "toc-with-pagenums"],
    "malformed-tables": ["missing-columns", "ragged-rows", "empty-cells-chaos", "merged-simulation",
                         "numeric-alignment-hell", "unicode-in-tables", "borderless-nasa", "bibliography-single-column"],
    "cursed-text": ["ligatures", "math-notation", "subscript-superscript", "lookalike-chars",
                    "invisible-chars", "mixed-numbers", "symbol-fonts", "math-heavy"],
    "layout-traps": ["deep-nesting", "footnote-sections", "sidebar-content", "out-of-order",
                     "page-number-sections", "partial-header", "sentence-as-header", "allcaps-header-missed",
                     "numbered-sections-as-text", "toc-leaders-captured", "requirements-doc",
                     "section-merge-cascade", "code-heavy-font-skew", "front-matter-heavy", "boundary-heading-sizes"],
    "requirements": ["shall-variations", "mixed-numbering", "table-requirements", "traceability-matrix",
                     "conditional-requirements", "false-positive-shall", "nested-requirements",
                     "domain-specific-shall", "ambiguous-modal"],
    "math-noise": ["false-positive-equations", "text-heavy-centered", "inline-vs-display"],
}
ALL_TRICK_NAMES = {t for tricks in AVAILABLE_TRICKS.values() for t in tricks}


def load_manifest() -> list[dict]:
    """Load manifest.jsonl entries."""
    if not MANIFEST.exists():
        logger.error(f"Manifest not found: {MANIFEST}")
        return []
    entries = []
    for line in MANIFEST.read_text().splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def is_retryable(entry: dict) -> bool:
    """Infrastructure failure that just needs a retry."""
    err = (entry.get("error") or "").lower()
    return any(kw in err for kw in RETRYABLE_ERRORS)


def is_quality_failure(entry: dict) -> bool:
    """Quality issue that needs fixture + convergence."""
    if entry.get("status") != "completed":
        return not is_retryable(entry)
    return bool(entry.get("debug_patterns")) or entry.get("quality_signal") == "REVIEW_REQUIRED"


def fixture_exists(filename: str) -> bool:
    """Check if a synthetic fixture already exists for this file."""
    stem = Path(filename).stem
    return any(FIXTURES_DIR.glob(f"{stem}_fixture*"))


def pattern_to_tricks(patterns: list[str]) -> list[str]:
    """Map debug patterns to /fixture-tricky trick types."""
    tricks = set()
    for p in patterns:
        if "underestimate" in p:
            tricks.update(["toc-entries", "multi-column"])
        if "overestimate" in p:
            tricks.update(["key-value-pairs", "numbered-list"])
        if "table" in p:
            tricks.update(["false-tables", "malformed-tables"])
    return sorted(tricks) or ["gauntlet"]


def generate_smart_fixture_spec(analysis: FailureAnalysis, entry: dict) -> dict:
    """Use /scillm text model to reason about which tricks reproduce a failure.

    Returns a fixture spec dict with keys: tricks, category, parameters, assertions.
    Falls back to pattern_to_tricks() if /scillm is unavailable.
    """
    patterns = entry.get("debug_patterns", [])
    fallback_tricks = pattern_to_tricks(patterns)
    fallback_spec = {
        "tricks": fallback_tricks,
        "category": fallback_tricks[0] if fallback_tricks != ["gauntlet"] else "gauntlet",
        "parameters": {},
        "assertions": {},
        "source": "fallback",
    }

    # Build context summary from the analysis
    context = (
        f"Filename: {entry.get('filename', 'unknown')}\n"
        f"Debug patterns: {patterns}\n"
        f"Layout: {analysis.layout_type}\n"
        f"S00 estimated sections: {analysis.s00_estimated_sections}, S04 actual: {analysis.s04_actual_sections}\n"
        f"Has TOC: {analysis.has_toc}, TOC coverage: {analysis.toc_coverage}\n"
        f"Body font size: {analysis.font_analysis.get('body_font_size', '?')}pt\n"
        f"Bold sizes: {analysis.font_analysis.get('bold_sizes', [])}\n"
        f"Misclassified fonts: {len(analysis.misclassified_fonts)}\n"
        f"Diagnosis: {analysis.diagnosis[:500]}\n"
    )

    tricks_list = json.dumps(
        {cat: tricks for cat, tricks in AVAILABLE_TRICKS.items()}, indent=1
    )

    prompt = (
        "You are a PDF test fixture designer. Given this extraction failure analysis, "
        "choose which /fixture-tricky tricks should be COMBINED to reproduce this failure.\n\n"
        f"FAILURE ANALYSIS:\n{context}\n"
        f"AVAILABLE TRICKS (by category):\n{tricks_list}\n\n"
        "Return ONLY valid JSON (no markdown fences) with these keys:\n"
        '  "tricks": list of 1-4 trick names from the available tricks above\n'
        '  "category": primary category name for the fixture command\n'
        '  "parameters": dict of custom params (e.g. {"font_size": 9, "columns": 2, "section_count": 15})\n'
        '  "assertions": dict of expected ground truth (e.g. {"min_sections": 5, "no_false_tables": true})\n'
    )

    try:
        resp = httpx.post(
            SCILLM_URL,
            headers=SCILLM_AUTH,
            json={
                "model": "text",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # Strip markdown fences if model wraps in ```json
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        spec = json.loads(content)

        # Validate: only keep tricks that actually exist
        valid_tricks = [t for t in spec.get("tricks", []) if t in ALL_TRICK_NAMES]
        if not valid_tricks:
            logger.warning("  /scillm returned no valid tricks, falling back")
            return fallback_spec

        spec["tricks"] = valid_tricks
        spec["source"] = "scillm"
        spec.setdefault("category", "gauntlet")
        spec.setdefault("parameters", {})
        spec.setdefault("assertions", {})
        logger.info(f"  Smart spec from /scillm: {valid_tricks}")
        return spec

    except Exception as e:
        logger.warning(f"  /scillm unavailable ({e}), using fallback mapping")
        return fallback_spec


def _run_fixture_tricky(spec: dict, output_path: Path) -> bool:
    """Call /fixture-tricky to generate a PDF from a fixture spec.

    Handles multi-trick specs by choosing the right command approach.
    Returns True if the fixture was generated successfully.
    """
    fixture_tricky = SKILLS_DIR / "fixture-tricky" / "generate.py"
    tricks = spec.get("tricks", [])
    category = spec.get("category", "")

    if not tricks:
        return False

    # Determine which command to use based on category or trick count
    if len(tricks) == 1:
        # Single trick: use the 'single' command
        cmd = ["uv", "run", str(fixture_tricky), "single", tricks[0], "--output", str(output_path)]
    elif category in ("false-tables", "malformed-tables", "cursed-text",
                       "layout-traps", "requirements", "math-noise"):
        # Category command with --tricks filter
        cmd = ["uv", "run", str(fixture_tricky), category, "--output", str(output_path),
               "--tricks", ",".join(tricks)]
    else:
        # Mixed categories: use gauntlet (generates all, good enough for stress test)
        cmd = ["uv", "run", str(fixture_tricky), "gauntlet", "--output", str(output_path)]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
        cwd=str(SKILLS_DIR / "fixture-tricky"),
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    return result.returncode == 0 and output_path.exists()


def _update_pattern_registry(pattern: str, spec: dict, fixture_path: str) -> None:
    """Write fixture spec into pattern_registry.json alongside the pattern entry."""
    try:
        if PATTERN_REGISTRY.exists():
            registry = json.loads(PATTERN_REGISTRY.read_text())
        else:
            registry = {"patterns": {}, "files": {}}

        pat_entry = registry.get("patterns", {}).get(pattern, {})
        pat_entry["fixture_spec"] = {
            "tricks": spec.get("tricks", []),
            "category": spec.get("category", ""),
            "parameters": spec.get("parameters", {}),
            "assertions": spec.get("assertions", {}),
            "fixture_path": fixture_path,
            "source": spec.get("source", "unknown"),
        }
        registry.setdefault("patterns", {})[pattern] = pat_entry
        PATTERN_REGISTRY.write_text(json.dumps(registry, indent=2, default=str))
        logger.info(f"  Pattern registry updated for '{pattern}'")
    except Exception as e:
        logger.warning(f"  Failed to update pattern registry: {e}")


@app.command()
def retry(
    dry_run: bool = typer.Option(False, help="Show what would be retried without executing"),
    limit: int = typer.Option(10, help="Max files to retry per run"),
) -> None:
    """Retry infrastructure failures (timeout, 429) with pdf_oxide."""
    entries = load_manifest()
    retryable = [e for e in entries if e.get("status") != "completed" and is_retryable(e)]

    logger.info(f"Found {len(retryable)} retryable failures out of {len(entries)} total")
    for entry in retryable[:limit]:
        fn = entry.get("filename") or Path(entry.get("original_path", "")).name
        err = (entry.get("error") or "")[:80]
        logger.info(f"  {fn}: {err}")

        if dry_run:
            continue

        # Re-extract with pdf_oxide (via /extract-pdf skill)
        pdf_path = entry.get("original_path", "")
        if not pdf_path or not Path(pdf_path).exists():
            logger.warning(f"  Skipping {fn}: file not found at {pdf_path}")
            continue

        logger.info(f"  Re-extracting {fn} with pdf_oxide...")
        result = subprocess.run(
            ["bash", str(SKILLS_DIR / "extract-pdf" / "run.sh"), pdf_path],
            capture_output=True, text=True, timeout=7200,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            logger.success(f"  {fn}: extraction succeeded")
            # TODO: update manifest entry with new results
        else:
            logger.error(f"  {fn}: extraction failed again — {result.stderr[:200]}")


@app.command()
def fixture(
    dry_run: bool = typer.Option(False, help="Show what fixtures would be generated"),
    limit: int = typer.Option(5, help="Max fixtures to generate per run"),
    pattern: str = typer.Option("", help="Only process this specific pattern"),
) -> None:
    """Generate synthetic PDFs for quality failures and run /pdf-lab convergence."""
    entries = load_manifest()
    quality_fails = [e for e in entries if is_quality_failure(e)]

    # Group by pattern
    pattern_groups: dict[str, list[dict]] = {}
    for entry in quality_fails:
        patterns = entry.get("debug_patterns", [])
        if not patterns:
            if entry.get("quality_signal") == "REVIEW_REQUIRED":
                patterns = ["review_required"]
            elif entry.get("s00_s04_label"):
                patterns = [entry["s00_s04_label"].lower()]
            else:
                patterns = ["unknown_failure"]
        for p in patterns:
            if pattern and p != pattern:
                continue
            pattern_groups.setdefault(p, []).append(entry)

    logger.info(f"Quality failures: {len(quality_fails)} files across {len(pattern_groups)} patterns")
    for pat, files in sorted(pattern_groups.items(), key=lambda x: -len(x[1])):
        has_fixture = any(fixture_exists(f.get("filename", "")) for f in files)
        logger.info(f"  {pat}: {len(files)} files {'[FIXTURE EXISTS]' if has_fixture else '[NO FIXTURE]'}")

    # Generate fixtures for patterns without one
    generated = 0
    for pat, files in sorted(pattern_groups.items(), key=lambda x: -len(x[1])):
        if generated >= limit:
            break
        if any(fixture_exists(f.get("filename", "")) for f in files):
            continue

        # Pick representative file (largest page count)
        rep = max(files, key=lambda f: f.get("page_count", 0))
        fn = rep.get("filename") or Path(rep.get("original_path", "")).name
        output_path = FIXTURES_DIR / f"{Path(fn).stem}_fixture.pdf"

        # Smart fixture spec: analyze failure then ask /scillm for trick selection
        logger.info(f"Analyzing failure for pattern '{pat}' based on {fn}...")
        analysis = analyze_failure(rep)
        spec = generate_smart_fixture_spec(analysis, rep)
        tricks = spec["tricks"]

        logger.info(f"Generating fixture for pattern '{pat}' based on {fn}")
        logger.info(f"  Tricks: {tricks} (source: {spec.get('source', '?')})")
        logger.info(f"  Parameters: {spec.get('parameters', {})}")
        logger.info(f"  Output: {output_path}")
        logger.info(f"  S00 estimated: {rep.get('s00_estimated_sections', '?')}, S04 actual: {rep.get('s04_actual_sections', '?')}")

        if dry_run:
            generated += 1
            continue

        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

        if _run_fixture_tricky(spec, output_path):
            logger.success(f"  Fixture generated: {output_path}")
            generated += 1

            # Store fixture spec in /memory and pattern_registry.json
            _store_fixture_spec(pat, fn, rep, tricks, str(output_path))
            _update_pattern_registry(pat, spec, str(output_path))

            # Run /pdf-lab convergence on the fixture
            logger.info(f"  Running /pdf-lab convergence on {output_path}...")
            pdf_lab = SKILLS_DIR / "pdf-lab" / "run.sh"
            if pdf_lab.exists():
                conv_result = subprocess.run(
                    ["bash", str(pdf_lab), "diagnose", str(output_path)],
                    capture_output=True, text=True, timeout=300,
                    cwd=str(SKILLS_DIR / "pdf-lab"),
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if conv_result.returncode == 0:
                    logger.success(f"  Convergence completed for {pat}")
                else:
                    logger.warning(f"  Convergence failed: {conv_result.stderr[:200]}")
            else:
                logger.warning(f"  /pdf-lab not found at {pdf_lab}")
        else:
            logger.error(f"  Fixture generation failed for pattern '{pat}'")


@app.command()
def triage(
    dry_run: bool = typer.Option(False, help="Report only, don't act"),
) -> None:
    """Full triage: retry infra failures, then generate fixtures for quality failures."""
    logger.info("=== Phase 1: Retry infrastructure failures ===")
    retry(dry_run=dry_run, limit=30)

    logger.info("\n=== Phase 2: Generate fixtures for quality failures ===")
    fixture(dry_run=dry_run, limit=5)


@app.command()
def analyze(
    file_id: str = typer.Argument("", help="Manifest entry ID or filename to analyze"),
    pattern: str = typer.Option("", help="Analyze first entry matching this debug pattern"),
    output_json: bool = typer.Option(False, "--json", help="Output analysis as JSON"),
    limit: int = typer.Option(1, help="Max entries to analyze (when using --pattern)"),
) -> None:
    """VLM-powered failure analysis: screenshot TOC, extract S00/S04 delta.

    Renders TOC pages, sends to VLM for visual section counting, compares
    against S00 estimate and S04 actual, and diagnoses the mismatch.
    """
    entries = load_manifest()
    if not entries:
        logger.error("No manifest entries found")
        raise typer.Exit(1)

    # Find matching entries
    targets: list[dict] = []
    if file_id:
        targets = [
            e for e in entries
            if e.get("id") == file_id
            or e.get("filename") == file_id
            or (e.get("original_path") or "").endswith(file_id)
        ]
        if not targets:
            logger.error(f"No manifest entry found for '{file_id}'")
            raise typer.Exit(1)
    elif pattern:
        targets = [
            e for e in entries
            if pattern in (e.get("debug_patterns") or [])
            or e.get("s00_s04_label", "").lower() == pattern.lower()
        ]
        if not targets:
            logger.error(f"No entries matching pattern '{pattern}'")
            raise typer.Exit(1)
        targets = targets[:limit]
    else:
        # Default: analyze first quality failure
        targets = [e for e in entries if is_quality_failure(e)][:limit]
        if not targets:
            logger.info("No quality failures to analyze")
            raise typer.Exit(0)

    logger.info(f"Analyzing {len(targets)} entry(ies)")

    results = []
    for entry in targets:
        analysis = analyze_failure(entry)
        if output_json:
            results.append({
                "id": entry.get("id"),
                "filename": entry.get("filename"),
                "s00_estimated_sections": analysis.s00_estimated_sections,
                "s04_actual_sections": analysis.s04_actual_sections,
                "vlm_section_count": analysis.vlm_section_count,
                "vlm_toc_analysis": analysis.vlm_toc_analysis,
                "font_analysis": analysis.font_analysis,
                "misclassified_fonts": analysis.misclassified_fonts,
                "layout_type": analysis.layout_type,
                "diagnosis": analysis.diagnosis,
                "toc_screenshots": [str(p) for p in analysis.toc_screenshots],
                "problem_screenshots": [str(p) for p in analysis.problem_screenshots],
            })

    if output_json:
        print(json.dumps(results, indent=2, default=str))


def _store_fixture_spec(pattern: str, source_file: str, entry: dict, tricks: list[str], fixture_path: str) -> None:
    """Store fixture spec in /memory so the Corpus viewer can show it."""
    try:
        spec = {
            "pattern": pattern,
            "source_file": source_file,
            "tricks": tricks,
            "fixture_path": fixture_path,
            "s00_estimated": entry.get("s00_estimated_sections"),
            "s04_actual": entry.get("s04_actual_sections"),
            "s00_s04_ratio": entry.get("s00_s04_ratio"),
            "category": entry.get("category"),
            "page_count": entry.get("page_count"),
        }
        httpx.post(
            "http://localhost:8601/learn",
            json={
                "collection": "lessons",
                "document": {
                    "problem": f"Synthetic fixture for pattern: {pattern} (from {source_file})",
                    "solution": json.dumps(spec),
                    "scope": "pdf-lab",
                    "tags": ["fixture-spec", "pdf-lab", "synthetic", pattern],
                },
            },
            timeout=10.0,
        )
        logger.info(f"  Fixture spec stored in /memory")
    except Exception as e:
        logger.warning(f"  Failed to store fixture spec: {e}")


if __name__ == "__main__":
    app()
