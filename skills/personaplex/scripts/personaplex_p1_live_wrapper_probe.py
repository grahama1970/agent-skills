#!/usr/bin/env python3
from __future__ import annotations
"""Deterministic P1 live-wrapper integration probe.

This probe does not claim live Deepgram/GPU PersonaPlex readiness.  It drives
P1 wrapper callbacks with final transcripts shaped like Deepgram `speech_final`
events and writes raw receipts for the next HTML progress update.
"""

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
COMPAT = SCRIPT_DIR / "_p1_compat"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if COMPAT.exists() and str(COMPAT) not in sys.path:
    sys.path.append(str(COMPAT))

from personaplex_p1_live_wrapper_integration import (
    DeterministicP1MemoryTransport,
    P1LiveTurnController,
    P1MemoryClient,
    P1TurnResult,
)


async def run_probe(fixture_path: Path, run_root: Path, *, transport_mode: str) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    transport = DeterministicP1MemoryTransport(force_ivanti_general_math=(transport_mode == "ivanti_general_math_misroute"))
    controller = P1LiveTurnController(
        session_id=fixture.get("session_id", "p1-session"),
        persona_id=fixture.get("persona_id", "embry"),
        run_root=run_root,
        memory_client=P1MemoryClient(transport, persona_id=fixture.get("persona_id", "embry")),
    )
    tasks: list[asyncio.Task[P1TurnResult]] = []
    elapsed = 0
    for turn in fixture["turns"]:
        wait_ms = int(turn.get("start_after_ms", 0)) - elapsed
        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000.0)
            elapsed += wait_ms
        ctx = controller.start_final_transcript(
            turn["transcript"],
            user_audio_bytes=(turn.get("user_audio_marker") or turn["transcript"]).encode("utf-8"),
            user_audio_codec=turn.get("user_audio_codec", "fixture/opus"),
            source=turn.get("source", "deepgram_fixture"),
        )
        tasks.append(asyncio.create_task(controller.run_turn(ctx, intent_delay_ms=int(turn.get("intent_delay_ms", 0)), route_delay_ms=int(turn.get("route_delay_ms", 0)))))
    results = await asyncio.gather(*tasks)
    final = controller.final_receipt(results)
    final["transport_calls"] = transport.calls
    final["transport_mode"] = transport_mode
    final_path = run_root / "p1-final-receipt.json"
    final_path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    final["final_receipt_path"] = str(final_path)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=Path("/tmp/personaplex-p1-live-wrapper-sanity"))
    parser.add_argument("--transport-mode", choices=["normal", "ivanti_general_math_misroute"], default="normal")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    final = asyncio.run(run_probe(args.fixture, args.run_root, transport_mode=args.transport_mode))
    if args.json:
        print(json.dumps(final, indent=2, sort_keys=True))
    else:
        print(f"p1 wrapper sanity ok={str(final['ok']).lower()} sealed_turns={final['sealed_turn_count']} stale_rejections={final['stale_rejection_count']}")
        print(f"final_receipt={final['final_receipt_path']}")
    return 0 if final.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
