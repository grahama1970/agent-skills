#!/usr/bin/env python3
"""Module support for the personaplex skill."""
from __future__ import annotations
"""Deterministic server-level P2 callsite smoke.

The probe drives the same P2 callsite object that the patched
`personaplex_golden_state_server.py` chat route uses, but without importing
PersonaPlex, torch, aiohttp, sphn, or Deepgram.  It proves callsite wiring into
P1 turn-state/gating/persistence code and writes raw receipt artifacts.
"""

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
COMPAT = SCRIPT_DIR / "_p2_compat"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if COMPAT.exists() and str(COMPAT) not in sys.path:
    sys.path.append(str(COMPAT))

from personaplex_p2_server_callsite import run_p2_server_callsite_smoke


async def run_probe(fixture_path: Path, run_root: Path, *, force_ivanti_general_math: bool = False) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    final = await run_p2_server_callsite_smoke(fixture, run_root, force_ivanti_general_math=force_ivanti_general_math)
    final_path = run_root / "p2-final-receipt.json"
    final_path.write_text(json.dumps(final, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    final["final_receipt_path"] = str(final_path)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--force-ivanti-general-math", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    final = asyncio.run(run_probe(args.fixture, args.run_root, force_ivanti_general_math=args.force_ivanti_general_math))
    if args.json:
        print(json.dumps(final, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(f"p2 server callsite sanity ok={str(final['ok']).lower()} sealed_turns={final['sealed_turn_count']} stale_rejections={final['stale_rejection_count']}")
        print(f"final_receipt={final['final_receipt_path']}")
    return 0 if final.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
