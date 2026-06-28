"""Patched document reader used by deterministic Battle Blue.

Inputs are document names relative to ``docs``. Output is file text when the
resolved path stays inside the approved root. Traversal attempts raise
``ValueError`` so the Judge can verify the exploit is blocked.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent / "docs"


def read_doc(name: str) -> str:
    candidate = (ROOT / name).resolve()
    root = ROOT.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("document path escapes approved root") from exc

    return candidate.read_text(encoding="utf-8")
