"""Thin orchestrator for /extract-pdf skill.

Delegates heavy lifting to pdf_oxide (Rust). This package handles:
- CLI entry point (Typer)
- LLM calls via /assistant and /scillm
- Shadow-LEGO cascade logging
- Output assembly (JSON envelope)
"""
