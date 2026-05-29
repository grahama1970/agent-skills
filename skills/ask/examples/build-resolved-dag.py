#!/usr/bin/env python3
"""Emit a resolved persona-review-implement DAG with absolute review file paths."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ASK_SRC = Path(__file__).resolve().parents[1] / "src"
if str(ASK_SRC) not in sys.path:
    sys.path.insert(0, str(ASK_SRC))

from ask.ask_dag import build_persona_review_implement_dag  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", default="Harden normalize_handoff_id and add tests in the ask DAG example module")
    parser.add_argument("--persona", default="Brandon")
    parser.add_argument("--scope", default="ask")
    parser.add_argument("--agent-worker", default="")
    parser.add_argument("--no-dogpile", action="store_true")
    parser.add_argument("-o", "--output", type=Path, default=Path(__file__).with_name("persona-review-implement.resolved.json"))
    args = parser.parse_args()
    dag = build_persona_review_implement_dag(
        args.question,
        scope=args.scope,
        persona=args.persona,
        agent_worker_id=args.agent_worker or None,
        include_dogpile=not args.no_dogpile,
    )
    args.output.write_text(json.dumps(dag, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
