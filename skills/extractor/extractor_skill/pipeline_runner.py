#!/usr/bin/env python3
"""
Pipeline execution for PDF extraction.

This module handles running the extractor pipeline subprocess
and gathering outputs.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

from extractor_skill.config import EXTRACTOR_ROOT, ExtractionOptions
from extractor_skill.utils import format_error_guidance
from loguru import logger


def extract_pipeline(
    filepath: Path,
    opts: ExtractionOptions,
) -> Dict[str, Any]:
    """
    Full pipeline extraction for PDFs with preset detection.

    Args:
        filepath: Path to PDF file
        opts: Extraction options

    Returns:
        Dict with extraction result
    """
    # Build command
    python = str(EXTRACTOR_ROOT / ".venv" / "bin" / "python")
    cmd = [python, "-m", "extractor.pipeline", str(filepath)]

    # Output directory
    if opts.output_dir:
        out_path = Path(opts.output_dir)
    else:
        out_path = Path(tempfile.mkdtemp(prefix="extractor_"))

    cmd.extend(["--out", str(out_path)])

    # Mode flags
    if opts.mode == "fast":
        cmd.extend(["--offline-smoke"])
    elif opts.mode == "accurate":
        cmd.extend(["--use-llm"])
    elif opts.mode == "offline":
        # Offline mode: skip LLM-dependent stages but keep computational stages
        # like S05 table extraction (Camelot) which doesn't need LLM.
        # DO NOT use --offline-smoke here — it sets skip_tables05=True which
        # prevents table extraction entirely.
        cmd.extend([
            "--summary-only",
            "--skip-fig-descriptions",
            "--skip-export",
            "--skip-llm03",
            "--skip-reqs07",
            "--skip-annotator09a",
            "--skip-proving",
        ])

    # Add option flags
    _add_option_flags(cmd, opts)

    # Sync settings
    os.environ["SYNC_TO_MEMORY"] = "1" if opts.sync_to_memory else "0"

    # Run pipeline
    # Timeout is configurable via env var. Default 6 hours — the caller
    # (discovery.py) wraps with a per-PDF timeout so this is a safety net.
    pipeline_timeout = int(os.environ.get("EXTRACTOR_PIPELINE_TIMEOUT", 21600))
    try:
        env = {**os.environ}
        env["PYTHONPATH"] = str(EXTRACTOR_ROOT / "src") + ":" + env.get("PYTHONPATH", "")

        # Use Popen + communicate for proper process group cleanup on timeout.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(EXTRACTOR_ROOT),
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

        return _build_success_response(out_path, filepath, opts)

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


def _add_option_flags(cmd: list, opts: ExtractionOptions) -> None:
    """Add extraction option flags to command."""
    if opts.preset:
        cmd.extend(["--preset", opts.preset])
    if opts.auto_ocr is True:
        cmd.append("--auto-ocr")
    elif opts.auto_ocr is False:
        cmd.append("--no-auto-ocr")
    if opts.skip_scanned:
        cmd.append("--skip-scanned")
    if opts.ocr_lang:
        cmd.extend(["--ocr-lang", opts.ocr_lang])
    if opts.ocr_deskew:
        cmd.append("--ocr-deskew")
    if opts.ocr_force:
        cmd.append("--ocr-force")
    if opts.ocr_timeout:
        cmd.extend(["--ocr-timeout", str(opts.ocr_timeout)])
    if opts.continue_on_error:
        cmd.append("--continue-on-error")

    # PDF decryption options (auto_decrypt defaults to True)
    if opts.auto_decrypt is False:
        cmd.append("--no-auto-decrypt")
    if opts.decrypt_password:
        cmd.extend(["--decrypt-password", opts.decrypt_password])

    if opts.sections_only:
        cmd.extend([
            "--skip-tables05",
            "--skip-fig-descriptions",
            "--skip-annotator09a",
            "--skip-reqs07",
            "--skip-proving",
            "--skip-export",
        ])


def _build_success_response(
    out_path: Path,
    filepath: Path,
    opts: ExtractionOptions
) -> Dict[str, Any]:
    """Build success response from pipeline outputs."""
    outputs = _gather_pipeline_outputs(out_path, filepath)
    counts = _count_extracted_elements(out_path)

    # Get assessment from report
    assessment = None
    quality_signal = "UNKNOWN"
    report_path = out_path / "14_report_generator" / "json_output" / "final_report.json"
    if report_path.exists():
        try:
            report_data = json.loads(report_path.read_text())
            stats = report_data.get("statistics", {})
            assessment = stats.get("assessment_comparison")
            quality_signal = stats.get("quality_signal", "UNKNOWN")
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    # Get preset from context
    preset_name = opts.preset
    context_path = out_path / "pipeline_context.json"
    if context_path.exists():
        try:
            ctx = json.loads(context_path.read_text())
            preset_name = ctx.get("preset_name") or preset_name
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    # If markdown requested, read and return it
    markdown_content = None
    if opts.return_markdown and outputs.get("markdown"):
        try:
            markdown_content = Path(outputs["markdown"]).read_text()
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    response = {
        "success": True,
        "mode": opts.mode,
        "preset": preset_name,
        "output_dir": str(out_path),
        "outputs": outputs,
        "counts": counts,
        "assessment": assessment,
        "quality_signal": quality_signal,
    }

    if markdown_content:
        response["markdown"] = markdown_content

    return response


def _gather_pipeline_outputs(out_path: Path, filepath: Path) -> Dict[str, str]:
    """Gather output file paths from pipeline run."""
    outputs = {}

    # Markdown output
    md_candidates = [
        out_path / "10_markdown_exporter" / "document.md",
        out_path / "10_markdown_exporter" / f"{filepath.stem}.md",
    ]
    for md_path in md_candidates:
        if md_path.exists():
            outputs["markdown"] = str(md_path)
            break

    # Sections JSON
    sections_path = out_path / "04_section_builder" / "json_output" / "04_sections.json"
    if sections_path.exists():
        outputs["sections"] = str(sections_path)

    # Tables JSON
    tables_path = out_path / "05_table_extractor" / "json_output" / "05_tables.json"
    if tables_path.exists():
        outputs["tables"] = str(tables_path)

    # Figures JSON
    figures_path = out_path / "06_figure_extractor" / "json_output" / "06_figures.json"
    if figures_path.exists():
        outputs["figures"] = str(figures_path)

    # Report
    report_path = out_path / "14_report_generator" / "json_output" / "final_report.json"
    if report_path.exists():
        outputs["report"] = str(report_path)

    # Manifest
    manifest_path = out_path / "manifest.json"
    if manifest_path.exists():
        outputs["manifest"] = str(manifest_path)

    return outputs


def _count_extracted_elements(out_path: Path) -> Dict[str, int]:
    """Count extracted elements from pipeline outputs."""
    counts = {}

    # Sections
    sections_path = out_path / "04_section_builder" / "json_output" / "04_sections.json"
    if sections_path.exists():
        try:
            data = json.loads(sections_path.read_text())
            counts["sections"] = len(data.get("sections", []))
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    # Tables
    tables_path = out_path / "05_table_extractor" / "json_output" / "05_tables.json"
    if tables_path.exists():
        try:
            data = json.loads(tables_path.read_text())
            counts["tables"] = len(data.get("tables", []))
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    # Figures
    figures_path = out_path / "06_figure_extractor" / "json_output" / "06_figures.json"
    if figures_path.exists():
        try:
            data = json.loads(figures_path.read_text())
            counts["figures"] = len(data.get("figures", []))
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    return counts
