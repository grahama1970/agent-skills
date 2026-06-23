#!/usr/bin/env python3
from __future__ import annotations
"""Run the deterministic P0 multi-turn PersonaPlex/memory compliance probe."""

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from personaplex_compliance_harness import PersonaPlexP0Harness, TurnPipelineResult


async def run_fixture(fixture_path: Path, run_root: Path) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    harness = PersonaPlexP0Harness(
        session_id=fixture["session_id"],
        persona_id=fixture.get("persona_id", "embry"),
        run_root=run_root,
    )
    tasks: list[asyncio.Task[TurnPipelineResult]] = []
    start_ms = 0
    for turn in fixture["turns"]:
        wait_ms = int(turn.get("start_after_ms", 0)) - start_ms
        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000.0)
            start_ms += wait_ms
        ctx = harness.start_speech_final_turn(
            turn["transcript"],
            user_audio_bytes=(turn.get("user_audio_marker") or turn["transcript"]).encode("utf-8"),
            user_audio_codec=turn.get("user_audio_codec", "fixture/opus"),
        )
        task = harness.create_turn_task(
            ctx,
            intent_delay_ms=int(turn.get("intent_delay_ms", 0)),
            route_delay_ms=int(turn.get("route_delay_ms", 0)),
            recall_delay_ms=int(turn.get("recall_delay_ms", 0)),
            evidence_delay_ms=int(turn.get("evidence_delay_ms", 0)),
            answer_delay_ms=int(turn.get("answer_delay_ms", 0)),
        )
        tasks.append(task)
    results = await asyncio.gather(*tasks)
    final = harness.final_receipt(list(results))
    final_path = run_root / "final-receipt.json"
    final_path.write_text(json.dumps(final, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    final["final_receipt_path"] = str(final_path)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="print final receipt JSON")
    args = parser.parse_args(argv)
    final = asyncio.run(run_fixture(args.fixture, args.run_root))
    if args.json:
        print(json.dumps(final, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(f"ok={str(final['ok']).lower()} sealed_turns={final['sealed_turn_count']} stale_rejections={final['stale_rejection_count']}")
        print(f"final_receipt={final['final_receipt_path']}")
    return 0 if final.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
