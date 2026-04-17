#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.12.3",
#   "pymupdf>=1.24.0",
#   "loguru>=0.7.0",
# ]
# ///
"""review-pdf entrypoint.

Purpose:
- expose the Typer CLI for PDF extraction fidelity auditing.

Inputs:
- CLI args delegated to `verify.cli`.

Outputs:
- process exit code and console summary for per-doc and aggregate audits.

Failure modes:
- non-zero exit when audits report FAIL-level outcomes or invalid inputs.
"""

from verify.cli import app

if __name__ == "__main__":
    app()
