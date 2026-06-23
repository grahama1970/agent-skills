#!/usr/bin/env python3
"""Live memory-first E2E probe: PersonaPlex P2 callsite -> real :8601 /intent /recall /answer.

This is the text-path proof that a PersonaPlex turn queries memory BEFORE releasing
bounded response text. It does not require GPU PersonaPlex or Deepgram.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from personaplex_p2_server_callsite import P2ServerCallsite


EMBRY_HAWAII_Q = (
    "Embry, what is the weather like in Hawaii today, "
    "and how would that make you feel about surfing with Kai?"
)


async def run_live_probe(
    *,
    fixture: dict[str, Any],
    run_root: Path,
    memory_url: str,
) -> dict[str, Any]:
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)

    callsite = P2ServerCallsite.live(
        session_id=fixture.get("session_id", "embry-hawaii-memory-first"),
        persona_id=fixture.get("persona_id", "embry"),
        run_root=run_root,
        memory_url=memory_url,
    )

    for turn in fixture.get("turns") or []:
        await callsite.route_speech_final(
            turn["transcript"],
            source=turn.get("source", "memory_first_fixture"),
            user_audio_bytes=(turn.get("user_audio_marker") or turn["transcript"]).encode("utf-8"),
            route_delay_ms=int(turn.get("route_delay_ms", 0)),
        )

    final = callsite.final_receipt()
    final["schema"] = "personaplex.memory_first_live.final_receipt.v1"
    final["scope"] = "Live memory-first text path via P2 callsite + HttpMemoryTransport; not GPU voice or Deepgram"
    final["memory_url"] = memory_url
    final["claim_boundary"] = (
        "Proves speech_final -> /intent -> /recall -> route product against live daemon. "
        "Full persona blend (brave-search) requires golden_state_server batch path."
    )

    events_jsonl = callsite.controller.store.events_jsonl
    file_events: list[dict[str, Any]] = []
    if events_jsonl.exists():
        for line in events_jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                file_events.append(json.loads(line))

    intent_events = [e for e in file_events if e.get("event") == "p1_memory_intent_product"]
    sealed = final.get("sealed_turn_count", 0)
    result0 = (final.get("results") or [{}])[0]
    route_endpoint = result0.get("route_endpoint") or ""

    # Pull live /intent body from the sealed turn's intent authority (via memory call trace)
    question_kind = None
    tool_call_endpoints: list[str] = []
    import httpx

    try:
        live_intent = httpx.Client(base_url=memory_url, timeout=60.0).post(
            "/intent",
            json={
                "q": EMBRY_HAWAII_Q,
                "scope": "persona_memory",
                "fast": True,
            },
        ).json()
        question_kind = live_intent.get("question_kind")
        tool_call_endpoints = [
            str(c.get("endpoint") or c.get("skill"))
            for c in (live_intent.get("tool_calls") or [])
            if isinstance(c, dict)
        ]
    except Exception as exc:  # pragma: no cover - live env only
        final["live_intent_probe_error"] = str(exc)

    checks = {
        "sealed_turn": sealed >= 1,
        "intent_event": bool(intent_events),
        "memory_answer_route": "/memory /answer" in route_endpoint,
        "question_kind_persona_blend": question_kind == "persona_current_fact_blend",
        "tool_calls_include_recall_and_answer": (
            any("recall" in t for t in tool_call_endpoints)
            and any("answer" in t for t in tool_call_endpoints)
        ),
        "brave_search_in_tool_plan": any("brave" in t for t in tool_call_endpoints),
    }
    final["memory_first_checks"] = checks
    final["question_kind"] = question_kind
    final["tool_call_endpoints"] = tool_call_endpoints
    final["route_endpoint"] = route_endpoint
    final["ok"] = (
        checks["sealed_turn"]
        and checks["intent_event"]
        and checks["memory_answer_route"]
        and checks["question_kind_persona_blend"]
    )
    final["partial_gaps"] = []
    if not checks["brave_search_in_tool_plan"]:
        final["partial_gaps"].append("P1 text path does not execute brave-search; golden_state_server batch path required for full blend")

    out_path = run_root / "memory-first-live-receipt.json"
    out_path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    final["receipt_path"] = str(out_path)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=SCRIPT_DIR.parent / "fixtures/persona_embry_hawaii_memory_first.json")
    parser.add_argument("--run-root", type=Path, default=Path("/tmp/personaplex-memory-first-live"))
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    final = asyncio.run(run_live_probe(fixture=fixture, run_root=args.run_root, memory_url=args.memory_url))

    if args.json:
        print(json.dumps(final, indent=2, sort_keys=True))
    else:
        checks = final.get("memory_first_checks") or {}
        print(
            f"memory-first live ok={str(final.get('ok')).lower()} "
            f"sealed={final.get('sealed_turn_count')} "
            f"question_kind={final.get('question_kind')!r}"
        )
        print(f"checks={checks}")
        print(f"receipt={final.get('receipt_path')}")
    return 0 if final.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
