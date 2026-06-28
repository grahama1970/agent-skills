"""Agentic-first pdf-lab orchestration facade.

Inputs: PDF extraction artifacts and second-pass review payloads.
Outputs: JSON comparison, triage, prompt bundle, and HTML review artifacts.
Failure modes: delegated implementation functions raise explicit exceptions or return fail-closed artifacts.
"""

from __future__ import annotations

from pathlib import Path


def _load_agentic_parts() -> None:
    parts_dir = Path(__file__).resolve().parent / "agentic_parts"
    for part in sorted(parts_dir.glob("part*.py")):
        code = compile(part.read_text(encoding="utf-8"), str(part), "exec")
        exec(code, globals())


_load_agentic_parts()
