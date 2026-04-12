#!/usr/bin/env python3
"""
Common utilities for extractor skill.

This module provides:
- Error formatting and guidance
"""
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------
# Error Formatting
# --------------------------------------------------------------------------


def format_error_guidance(error: str, filepath: Optional[Path] = None, mode: Optional[str] = None) -> str:
    """
    Generate actionable guidance based on error type.

    Args:
        error: Error message
        filepath: Optional file path for context
        mode: Optional extraction mode for context

    Returns:
        Human-readable guidance string
    """
    guidance = []
    error_lower = error.lower()

    # LLM/API errors
    if any(kw in error_lower for kw in ["api", "chutes", "connection", "timeout", "503", "429", "unauthorized"]):
        guidance.extend([
            "Try these solutions:",
            "  1. Check CHUTES_API_KEY environment variable is set",
            "  2. Try --fast mode (no LLM required): ./run.sh file.pdf --fast",
            "  3. Check network connectivity to llm.chutes.ai",
            "  4. If Chutes is overloaded (503), wait and retry",
        ])

    # File/corrupt errors
    elif any(kw in error_lower for kw in ["corrupt", "invalid pdf", "unable to read", "file not found", "permission"]):
        guidance.extend([
            "File may be corrupted or inaccessible:",
            "  1. Verify the file exists and is readable",
            "  2. Try opening the PDF in a viewer to verify it's not corrupt",
            "  3. Check file permissions",
            "  4. If password-protected, the PDF must be unlocked first",
        ])

    # Memory/resource errors
    elif any(kw in error_lower for kw in ["memory", "oom", "killed", "resource"]):
        guidance.extend([
            "Resource limit exceeded:",
            "  1. Try --fast mode to reduce memory usage",
            "  2. Process smaller batches",
            "  3. Increase system memory/swap",
        ])

    # Syntax errors in pipeline code (not a dependency issue)
    elif any(kw in error_lower for kw in ["syntaxerror", "indentationerror"]):
        guidance.extend([
            "Syntax error in pipeline code:",
            "  1. Check the traceback above for the file and line number",
            "  2. Fix the syntax error in the source file",
            "  3. Run: python -m py_compile <file> to verify",
        ])

    # Import/dependency errors
    elif any(kw in error_lower for kw in ["no module named", "importerror", "modulenotfounderror"]):
        guidance.extend([
            "Missing dependency:",
            "  1. Activate the virtual environment: source .venv/bin/activate",
            "  2. Install dependencies: pip install -e .",
            "  3. Check PYTHONPATH includes extractor/src",
        ])

    # Pipeline errors
    elif "pipeline" in error_lower or "stage" in error_lower:
        guidance.extend([
            "Pipeline processing failed:",
            "  1. Try --fast mode: ./run.sh file.pdf --fast",
            "  2. Try with explicit preset: ./run.sh file.pdf --preset arxiv",
            "  3. Check the pipeline logs in output directory",
        ])

    # Generic fallback
    else:
        guidance.extend([
            "Troubleshooting steps:",
            "  1. Try --fast mode (no LLM): ./run.sh file.pdf --fast",
            "  2. Try with explicit preset: ./run.sh file.pdf --preset arxiv",
            "  3. Check CHUTES_API_KEY is set if using LLM features",
            "  4. Run sanity check: ./sanity.sh",
        ])

    return "\n".join(guidance)
