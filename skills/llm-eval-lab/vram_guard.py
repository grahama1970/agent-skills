"""VRAM health guardrail for local (Ollama) model evaluation.

Local models on a shared 24 GB GPU fall to CPU offload when VRAM is scarce and
then time out inside scillm (APITimeoutError), which the grid otherwise records
as a 0 that looks like a capability failure. Check free VRAM before dispatching
any local-model benchmark so those runs are refused up front, not silently
scored as wrong.
"""
from __future__ import annotations

import subprocess
import sys


def free_vram_gb() -> float | None:
    """Return free VRAM on GPU 0 in GB, or None if it cannot be read.

    Reads back the effect (nvidia-smi output), never assumes success.
    """
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=15,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    line = res.stdout.strip().split("\n")[0].strip()
    try:
        return float(line) / 1024.0
    except ValueError:
        return None


def check_vram_headroom(min_free_gb: float = 6.0) -> bool:
    """True if at least *min_free_gb* VRAM is free (or the check can't run).

    Fails open (returns True) when nvidia-smi is absent/unparseable so the guard
    never blocks non-GPU environments; prints the reason to stderr either way.
    """
    free_gb = free_vram_gb()
    if free_gb is None:
        print("[GUARD] VRAM check skipped (nvidia-smi unavailable or unparseable)",
              file=sys.stderr)
        return True
    if free_gb < min_free_gb:
        print(f"[GUARD] Only {free_gb:.1f} GB VRAM free; require {min_free_gb:.1f} GB. "
              "Local model will CPU-offload and time out — refusing.", file=sys.stderr)
        return False
    print(f"[GUARD] {free_gb:.1f} GB VRAM free (>= {min_free_gb:.1f} GB required).",
          file=sys.stderr)
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI: exit 0 if VRAM headroom is sufficient, 3 if not.

    Usage: python vram_guard.py [min_free_gb]
    """
    argv = argv if argv is not None else sys.argv[1:]
    min_free = float(argv[0]) if argv else 6.0
    return 0 if check_vram_headroom(min_free) else 3


if __name__ == "__main__":
    raise SystemExit(main())
