from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import write_json
from .stage import stage_candidate
from .synthesize import synthesize
from .validate_candidate import validate_candidate_files


def _print_json(data: object, enabled: bool) -> None:
    if enabled:
        print(json.dumps(data, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project-dream")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("synthesize")
    p.add_argument("--packet", required=True, type=Path)
    p.add_argument("--model", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--command-spec", type=Path)
    p.add_argument("--cache-dir", type=Path)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("validate-candidate")
    p.add_argument("--packet", required=True, type=Path)
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("stage-candidate")
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--validation", required=True, type=Path)
    p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "synthesize":
            code, receipt = synthesize(args.packet, args.model, args.output, args.command_spec, args.cache_dir)
            _print_json(receipt, args.json)
            return code
        if args.command == "validate-candidate":
            receipt = validate_candidate_files(args.packet, args.candidate, args.output)
            _print_json(receipt, args.json)
            return 0 if receipt["status"] == "accepted" else 1
        if args.command == "stage-candidate":
            code, receipt = stage_candidate(args.candidate, args.validation)
            _print_json(receipt, args.json)
            return code
    except Exception as exc:
        payload = {"status": "blocked", "errors": [str(exc)]}
        _print_json(payload, getattr(args, "json", False))
        if not getattr(args, "json", False):
            print(str(exc), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
