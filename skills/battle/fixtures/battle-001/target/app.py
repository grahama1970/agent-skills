"""Vulnerable document reader used by the Battle path traversal fixture.

Inputs are document names relative to ``docs``. Output is file text. This
fixture intentionally allows traversal so Red can prove the seeded exploit.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent / "docs"


def read_doc(name: str) -> str:
    # Vulnerable fixture: allows path traversal outside docs/.
    return (ROOT / name).read_text(encoding="utf-8")
