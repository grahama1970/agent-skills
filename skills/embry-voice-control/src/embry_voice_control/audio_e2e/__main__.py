"""Command line interface for Embry audio-first campaigns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .case_compiler import compile_campaign
from .runner import bundle_failure, run_campaign, status


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m embry_voice_control.audio_e2e")
    commands = root.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("compile")
    compile_parser.add_argument("--matrix", type=Path, required=True)
    compile_parser.add_argument("--source-policy", type=Path, required=True)
    selection = compile_parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case-id")
    selection.add_argument("--stratified-count", type=int)
    selection.add_argument("--all", action="store_true", dest="select_all")
    compile_parser.add_argument("--source-mode", default="physical_live_horus")
    compile_parser.add_argument("--output", type=Path, required=True)

    for name in ("run", "resume"):
        run_parser = commands.add_parser(name)
        run_parser.add_argument("--manifest", type=Path, required=True)
        run_parser.add_argument("--state", type=Path)
        run_parser.add_argument("--journal-db", type=Path, required=True)

    status_parser = commands.add_parser("status")
    status_parser.add_argument("--manifest", type=Path, required=True)
    status_parser.add_argument("--state", type=Path)

    failure_parser = commands.add_parser("bundle-failure")
    failure_parser.add_argument("--manifest", type=Path, required=True)
    failure_parser.add_argument("--state", type=Path)
    failure_parser.add_argument("--output", type=Path, required=True)
    failure_parser.add_argument("--reason", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "compile":
        manifest = compile_campaign(
            matrix_path=args.matrix,
            source_policy_path=args.source_policy,
            case_id=args.case_id,
            stratified_count=args.stratified_count,
            select_all=args.select_all,
            source_mode=args.source_mode,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"campaign_id": manifest["campaign_id"], "case_count": len(manifest["cases"]), "manifest": str(args.output)}, sort_keys=True))
        return 0
    if args.command in {"run", "resume"}:
        print(json.dumps(run_campaign(manifest_path=args.manifest, state_path=args.state, journal_db=args.journal_db), sort_keys=True))
        return 0
    if args.command == "status":
        print(json.dumps(status(manifest_path=args.manifest, state_path=args.state), sort_keys=True))
        return 0
    if args.command == "bundle-failure":
        print(json.dumps(bundle_failure(manifest_path=args.manifest, state_path=args.state, output=args.output, reason=args.reason), sort_keys=True))
        return 0
    raise ValueError("unknown_command")


if __name__ == "__main__":
    raise SystemExit(main())
