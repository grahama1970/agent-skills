#!/usr/bin/env python3
"""Module support for the personaplex skill."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from personaplex_p3_p5_live_services import (
    DEFAULT_SANITY_ROOT,
    build_conversation_document,
    memory_upsert,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PersonaPlex P6 real memory upsert probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--memory-url", default=None)
    parser.add_argument("--collection", default="conversation_history")
    parser.add_argument("--session-id", default="p6-session")
    parser.add_argument("--turn-id", type=int, default=1)
    parser.add_argument("--persona-id", default="embry")
    parser.add_argument("--transcript", default="Focus on the west gateway.")
    parser.add_argument("--skip-embedding", action="store_true")
    parser.add_argument("--timeout", type=float, default=2.5)
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless real_memory_upsert=true.")
    args = parser.parse_args(argv)

    doc = build_conversation_document(
        session_id=args.session_id,
        turn_id=args.turn_id,
        persona_id=args.persona_id,
        transcript=args.transcript,
    )
    receipt = memory_upsert(
        documents=[doc],
        collection=args.collection,
        skip_embedding=args.skip_embedding,
        memory_url=args.memory_url,
        out_dir=Path(args.out_dir),
        timeout=args.timeout,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_real and not receipt.get("real_memory_upsert"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
