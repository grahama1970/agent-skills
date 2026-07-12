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
        run_parser.add_argument("--campaign-dir", type=Path)
        run_parser.add_argument("--journal-url")
        run_parser.add_argument("--realtimestt-repo", type=Path)
        run_parser.add_argument("--realtimestt-python", type=Path)
        run_parser.add_argument("--managed-listener-socket", type=Path)
        run_parser.add_argument("--listener-source-node")
        run_parser.add_argument("--listener-start-timeout-seconds", type=float, default=120)
        run_parser.add_argument("--turn-timeout-seconds", type=float, default=180)
        run_parser.add_argument("--max-request-wer", type=float, default=0.25)
        run_parser.add_argument("--listener-device", default="cpu")
        run_parser.add_argument("--listener-compute-type", default="int8")
        run_parser.add_argument("--turn-audio", type=Path, action="append", default=[])
        run_parser.add_argument("--wake-audio", type=Path)
        run_parser.add_argument("--source-playback-target")
        run_parser.add_argument("--source-playback-delay-seconds", type=float, default=2.0)
        run_parser.add_argument("--pw-play", default="/usr/bin/pw-play")

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
        live_values = (
            args.campaign_dir, args.journal_url, args.realtimestt_repo,
            args.realtimestt_python, args.managed_listener_socket, args.listener_source_node,
        )
        live_config = None
        if any(live_values):
            if not all(live_values):
                raise ValueError("live_listener_configuration_incomplete")
            live_config = {
                "campaign_dir": str(args.campaign_dir),
                "journal_url": args.journal_url,
                "realtimestt_repo": str(args.realtimestt_repo),
                "realtimestt_python": str(args.realtimestt_python),
                "managed_listener_socket": str(args.managed_listener_socket),
                "listener_source_node": args.listener_source_node,
                "listener_start_timeout_seconds": args.listener_start_timeout_seconds,
                "turn_timeout_seconds": args.turn_timeout_seconds,
                "max_request_wer": args.max_request_wer,
                "listener_device": args.listener_device,
                "listener_compute_type": args.listener_compute_type,
                "turn_audio": [str(path) for path in args.turn_audio],
                "wake_audio": str(args.wake_audio) if args.wake_audio else None,
                "source_playback_target": args.source_playback_target,
                "source_playback_delay_seconds": args.source_playback_delay_seconds,
                "pw_play": args.pw_play,
            }
            if args.turn_audio and not args.source_playback_target:
                raise ValueError("source_playback_target_required")
        print(json.dumps(run_campaign(manifest_path=args.manifest, state_path=args.state, journal_db=args.journal_db, live_config=live_config), sort_keys=True))
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
