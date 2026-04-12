#!/usr/bin/env python3
"""
Pipeline execution for PDF extraction.

Delegates to /extract-pdf (pdf_oxide) for Rust-native extraction.
This module handles running the extraction subprocess and gathering outputs.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

from extractor_skill.config import ExtractionOptions
from extractor_skill.utils import format_error_guidance
from loguru import logger


# /extract-pdf skill path
EXTRACT_PDF_SKILL = Path.home() / ".pi" / "skills" / "extract-pdf" / "run.sh"

# pdf_oxide project root (for direct execution if skill not found)
PDF_OXIDE_ROOT = Path(os.getenv(
    "PDF_OXIDE_ROOT",
    Path.home() / "workspace" / "experiments" / "pdf_oxide"
))


def extract_pipeline(
    filepath: Path,
    opts: ExtractionOptions,
) -> Dict[str, Any]:
    """
    Full pipeline extraction for PDFs via pdf_oxide (Rust-native).

    Delegates to /extract-pdf skill for fast, MIT-licensed extraction.

    Args:
        filepath: Path to PDF file
        opts: Extraction options

    Returns:
        Dict with extraction result
    """
    # Output directory
    if opts.output_dir:
        out_path = Path(opts.output_dir)
    else:
        out_path = Path(tempfile.mkdtemp(prefix="extractor_"))

    # Build command for pdf_oxide pipeline (includes table extraction)
    # Use the full pipeline module which calls extract_content() + tables + figures
    cmd = [
        "uv", "run", "--directory", str(PDF_OXIDE_ROOT),
        "python", "-m", "pdf_oxide.pipeline", str(filepath),
        "--output-dir", str(out_path),
    ]

    # Map mode to features
    features = []
    if opts.mode == "accurate":
        # Enable LLM features for figure descriptions, requirements, etc.
        features.extend(["describe", "requirements"])
    if opts.sync_to_memory:
        features.append("arango")
    else:
        cmd.append("--no-arango")

    if features:
        cmd.extend(["--features", ",".join(features)])

    # Decryption options
    if opts.decrypt_password:
        cmd.extend(["--password", opts.decrypt_password])

    # Sync settings
    os.environ["SYNC_TO_MEMORY"] = "1" if opts.sync_to_memory else "0"
    os.environ["SYNC_TO_ARANGO"] = "1" if opts.sync_to_memory else "0"

    # Run pipeline
    # Timeout is configurable via env var. Default 30 min for Rust extraction
    # (much faster than the old Python pipeline)
    pipeline_timeout = int(os.environ.get("EXTRACTOR_PIPELINE_TIMEOUT", 1800))
    try:
        env = {**os.environ}
        # Strip inherited venv to prevent uv conflicts
        env.pop("VIRTUAL_ENV", None)

        # Use Popen + communicate for proper process group cleanup on timeout.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,  # New process group for clean kill
        )
        stdout, stderr = proc.communicate(timeout=pipeline_timeout)

        if proc.returncode != 0:
            error_msg = stderr or "Pipeline failed"
            return {
                "success": False,
                "error": error_msg,
                "stdout": stdout,
                "command": " ".join(cmd),
                "guidance": format_error_guidance(error_msg, filepath, opts.mode),
            }

        return _build_success_response_oxide(out_path, filepath, opts, stdout)

    except subprocess.TimeoutExpired:
        # Kill the entire process group to prevent orphaned children
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        timeout_minutes = pipeline_timeout // 60
        return {
            "success": False,
            "error": f"Pipeline timeout ({timeout_minutes} minutes exceeded)",
            "guidance": format_error_guidance("timeout", filepath, opts.mode),
        }
    except Exception as e:
        error_msg = str(e)
        return {
            "success": False,
            "error": error_msg,
            "guidance": format_error_guidance(error_msg, filepath, opts.mode),
        }




def _build_success_response_oxide(
    out_path: Path,
    filepath: Path,
    opts: ExtractionOptions,
    stdout: str,
) -> Dict[str, Any]:
    """Build success response from pdf_oxide output.

    pdf_oxide writes JSON to output_dir/<stem>.json when --output-dir is used.
    Falls back to parsing stdout if no file found.
    """
    result_data = {}

    # First, try to read from output file (preferred when --output-dir used)
    # Pipeline writes to extracted.json, CLI writes to {stem}.json
    for candidate in [out_path / "extracted.json", out_path / f"{filepath.stem}.json"]:
        if candidate.exists():
            try:
                result_data = json.loads(candidate.read_text())
                logger.debug(f"Read result from {candidate}")
                break
            except Exception as e:
                logger.debug(f"Failed to read {candidate}: {e}")

    # Fall back to parsing stdout if no file
    if not result_data:
        try:
            result_data = json.loads(stdout)
        except json.JSONDecodeError:
            # Try to find JSON in output (may have logs before it)
            for line in reversed(stdout.strip().split("\n")):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        result_data = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue

    # Extract counts from result
    counts = {
        "sections": len(result_data.get("sections", [])),
        "tables": len(result_data.get("tables", [])),
        "figures": len(result_data.get("figures", [])),
        "blocks": len(result_data.get("blocks", [])),
        "pages": result_data.get("page_count", 0),
    }

    # Gather output files from output_dir
    outputs = _gather_oxide_outputs(out_path, filepath)

    # Extract metadata
    metadata = result_data.get("metadata", {})
    timings = result_data.get("timings", {})

    # Build markdown content if requested
    markdown_content = None
    if opts.return_markdown:
        # pdf_oxide flattens to markdown sections
        flattened = result_data.get("flattened", [])
        if flattened:
            markdown_content = "\n\n".join(
                f.get("markdown", f.get("text", "")) for f in flattened
            )

    response = {
        "success": True,
        "mode": opts.mode,
        "engine": "pdf_oxide",
        "preset": metadata.get("preset") or opts.preset,
        "output_dir": str(out_path),
        "outputs": outputs,
        "counts": counts,
        "timings": timings,
        "quality_signal": "GOOD",  # pdf_oxide is high quality by default
    }

    if markdown_content:
        response["markdown"] = markdown_content

    return response


def _gather_oxide_outputs(out_path: Path, filepath: Path) -> Dict[str, str]:
    """Gather output file paths from pdf_oxide extraction."""
    outputs = {}

    # pdf_oxide writes result.json to output_dir
    result_path = out_path / "result.json"
    if result_path.exists():
        outputs["result"] = str(result_path)

    # Markdown output (if generated)
    md_path = out_path / f"{filepath.stem}.md"
    if md_path.exists():
        outputs["markdown"] = str(md_path)

    # Sections JSON
    sections_path = out_path / "sections.json"
    if sections_path.exists():
        outputs["sections"] = str(sections_path)

    # Tables JSON
    tables_path = out_path / "tables.json"
    if tables_path.exists():
        outputs["tables"] = str(tables_path)

    # Figures directory
    figures_dir = out_path / "figures"
    if figures_dir.exists() and figures_dir.is_dir():
        outputs["figures_dir"] = str(figures_dir)

    # Blocks JSON (raw blocks from Rust)
    blocks_path = out_path / "blocks.json"
    if blocks_path.exists():
        outputs["blocks"] = str(blocks_path)

    return outputs
