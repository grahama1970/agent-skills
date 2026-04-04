#!/usr/bin/env python3
"""
PDF extraction with preset detection and OCR support.

This module handles:
- PDF profile detection (s00_profile_detector)
- OCR preprocessing for scanned PDFs
- Interactive preset selection
- Collaboration flow for preset selection
"""
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from extractor_skill.config import (
    CONFIDENCE_THRESHOLD,
    ExtractionOptions,
)
from extractor_skill.pipeline_runner import extract_pipeline


# --------------------------------------------------------------------------
# Scanned PDF Detection
# --------------------------------------------------------------------------


def detect_scanned_pdf(filepath: Path) -> Optional[Dict[str, Any]]:
    """
    Detect if a PDF is scanned (image-based).

    Args:
        filepath: Path to PDF file

    Returns:
        Dict with scanned detection info, or None on error
    """
    try:
        import fitz
        from extractor.pipeline.steps.s02_pymupdf_extractor import _detect_scanned_pdf

        with fitz.open(str(filepath)) as doc:
            return _detect_scanned_pdf(doc)
    except Exception:
        return None


# --------------------------------------------------------------------------
# OCR Support
# --------------------------------------------------------------------------


def _docker_image_exists(image: str) -> bool:
    """Check if a Docker image exists locally."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_ocrmypdf_available() -> Dict[str, Any]:
    """
    Ensure OCRmyPDF is available (local or docker).

    Pulls docker image if needed.

    Returns:
        Dict with availability info
    """
    if shutil.which("ocrmypdf"):
        return {"available": True, "method": "local"}

    if not shutil.which("docker"):
        return {"available": False, "method": "none", "error": "docker_not_found"}

    if _docker_image_exists("extractor-ocr"):
        return {"available": True, "method": "docker", "image": "extractor-ocr"}
    if _docker_image_exists("jbarlow83/ocrmypdf"):
        return {"available": True, "method": "docker", "image": "jbarlow83/ocrmypdf"}

    try:
        pull = subprocess.run(
            ["docker", "pull", "jbarlow83/ocrmypdf"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if pull.returncode == 0:
            return {
                "available": True,
                "method": "docker",
                "image": "jbarlow83/ocrmypdf",
                "pulled": True,
            }
        return {
            "available": False,
            "method": "docker",
            "error": pull.stderr.strip() or pull.stdout.strip() or "pull_failed",
        }
    except Exception as e:
        return {"available": False, "method": "docker", "error": str(e)}


def maybe_prefetch_ocr_resources(filepath: Path) -> None:
    """Pre-check OCR availability for scanned PDFs."""
    scanned_info = detect_scanned_pdf(filepath)
    if not scanned_info or not scanned_info.get("is_scanned"):
        return

    status = ensure_ocrmypdf_available()
    if status.get("available"):
        if status.get("pulled"):
            print("INFO: Pulled OCRmyPDF docker image for scanned PDF.", file=sys.stderr)
        else:
            print("INFO: OCRmyPDF available for scanned PDF.", file=sys.stderr)
    else:
        print(
            "WARN: Scanned PDF detected but OCRmyPDF not available "
            f"({status.get('error', 'unknown error')}).",
            file=sys.stderr,
        )


# --------------------------------------------------------------------------
# Profile Detection
# --------------------------------------------------------------------------


def profile_pdf(filepath: Path) -> Dict[str, Any]:
    """Run s00_profile_detector to analyze PDF without extraction."""
    try:
        from extractor.pipeline.steps.s00_profile_detector import detect_preset
        return detect_preset(filepath)
    except Exception as e:
        return {"error": str(e)}


def format_profile_display(profile: Dict[str, Any], filename: str) -> str:
    """Format profile for human-readable display."""
    lines = [f"\nAnalyzing: {filename}"]

    layout = profile.get("layout", {})
    cols = "multi-column" if layout.get("columns", 1) > 1 else "single-column"
    pages = profile.get("page_count", "?")
    lines.append(f"Detected: {cols} layout, {pages} pages")

    elements = profile.get("elements", {})
    parts = []
    if elements.get("tables"):
        parts.append("tables")
    if elements.get("figures"):
        parts.append("figures")
    if elements.get("formulas"):
        parts.append("formulas")
    if elements.get("requirements"):
        parts.append("requirements")

    if parts:
        lines.append(f"Contains: {', '.join(parts)}")

    return "\n".join(lines)


def get_preset_choices() -> List[Dict[str, Any]]:
    """Get available presets from registry."""
    try:
        from extractor.core.presets import PRESET_REGISTRY
        choices = []
        for name, config in PRESET_REGISTRY.items():
            desc = config.get("description", name)
            choices.append({"name": name, "description": desc})
        return choices
    except Exception:
        return [
            {"name": "arxiv", "description": "Academic papers (2-column, math)"},
            {"name": "requirements_spec", "description": "Engineering specs (REQ-xxx)"},
        ]


def recommend_mode(profile: Dict[str, Any]) -> str:
    """Determine recommended mode based on profile."""
    elements = profile.get("elements", {})
    layout = profile.get("layout", {})

    if (elements.get("tables") or elements.get("figures") or
        elements.get("formulas") or layout.get("columns", 1) > 1):
        return "accurate"

    return "fast"


def interactive_preset_prompt(profile: Dict[str, Any], filename: str) -> Tuple[Optional[str], str]:
    """Show interactive prompt for preset selection."""
    print(format_profile_display(profile, filename), file=sys.stderr)

    presets = get_preset_choices()
    preset_match = profile.get("preset_match", {})
    matched = preset_match.get("matched")

    options = []
    default_idx = 1

    if matched:
        for p in presets:
            if p["name"] == matched:
                options.append(f"{p['name']} - {p['description']} [DETECTED]")
                break
        else:
            options.append(f"{matched} - Detected preset [DETECTED]")

    for p in presets:
        if p["name"] != matched:
            options.append(f"{p['name']} - {p['description']}")

    options.append("auto - Let pipeline decide")
    options.append("fast - Quick extraction, no LLM")

    print("\nSelect extraction preset:", file=sys.stderr)
    for i, opt in enumerate(options, 1):
        marker = " [RECOMMENDED]" if i == default_idx else ""
        print(f"  [{i}] {opt}{marker}", file=sys.stderr)

    try:
        choice = input(f"Enter choice [1-{len(options)}] (default: {default_idx}): ").strip()
        if not choice:
            choice_idx = default_idx
        else:
            choice_idx = int(choice)

        if choice_idx < 1 or choice_idx > len(options):
            choice_idx = default_idx

    except (ValueError, EOFError):
        choice_idx = default_idx

    selected = options[choice_idx - 1].split(" - ")[0]

    if selected == "fast":
        return None, "fast"
    elif selected == "auto":
        return None, recommend_mode(profile)
    else:
        return selected, recommend_mode(profile)


# --------------------------------------------------------------------------
# Main PDF Extraction Entry Point
# --------------------------------------------------------------------------


def extract_pdf_with_collaboration(
    filepath: Path,
    opts: ExtractionOptions,
) -> Dict[str, Any]:
    """
    Extract PDF with preset collaboration flow.

    Flow:
    1. If preset provided -> use it directly
    2. If explicit mode (fast/accurate/offline) -> respect it
    3. If no preset and mode is "auto":
       a. Run s00_profile_detector
       b. If confidence >= 8 -> auto-extract
       c. If low confidence:
          - TTY: interactive prompt
          - Non-TTY: auto mode with warning
    """
    if opts.auto_ocr is not False:
        maybe_prefetch_ocr_resources(filepath)

    # If preset explicitly provided, skip detection
    if opts.preset:
        print(f"Using preset: {opts.preset}", file=sys.stderr)
        return extract_pipeline(filepath, opts)

    # If explicit mode (not "auto"), respect user's choice and skip mode recommendation
    explicit_mode = opts.mode in ("fast", "accurate", "offline")
    if explicit_mode:
        print(f"Using explicit {opts.mode} mode for: {filepath.name}", file=sys.stderr)
        return extract_pipeline(filepath, opts)

    # Run profile detection for auto mode
    profile = profile_pdf(filepath)

    if "error" in profile:
        print(f"WARN: Profile detection failed: {profile['error']}. Using auto mode.", file=sys.stderr)
        return extract_pipeline(filepath, opts)

    preset_match = profile.get("preset_match", {})
    matched_preset = preset_match.get("matched")
    confidence = preset_match.get("confidence", 0)

    # High confidence -> auto-extract with recommended settings
    if matched_preset and confidence >= CONFIDENCE_THRESHOLD:
        recommended_mode = recommend_mode(profile)
        print(
            f"Detected preset: {matched_preset} (confidence: {confidence}). "
            f"Extracting in {recommended_mode} mode...",
            file=sys.stderr
        )
        opts.preset = matched_preset
        opts.mode = recommended_mode
        return extract_pipeline(filepath, opts)

    # Low confidence / no match
    is_tty = sys.stdin.isatty() and opts.interactive

    if is_tty:
        selected_preset, selected_mode = interactive_preset_prompt(profile, filepath.name)
        if selected_preset:
            print(f"Using preset: {selected_preset} in {selected_mode} mode", file=sys.stderr)
        else:
            print(f"Using {selected_mode} mode", file=sys.stderr)

        opts.preset = selected_preset
        opts.mode = selected_mode
        return extract_pipeline(filepath, opts)
    else:
        auto_mode = recommend_mode(profile)
        print(
            f"WARN: Non-interactive environment. Using auto ({auto_mode}) mode for: {filepath.name}",
            file=sys.stderr
        )
        opts.mode = auto_mode
        return extract_pipeline(filepath, opts)
