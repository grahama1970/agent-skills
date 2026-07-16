"""Command line interface for Embry audio-first campaigns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .case_compiler import compile_campaign
from .prepare_clone_assets import prepare_clone_assets
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

    prepare_parser = commands.add_parser("prepare-clone-assets")
    prepare_parser.add_argument("--manifest", type=Path, required=True)
    prepare_parser.add_argument("--source-contract-receipt", type=Path, required=True)
    prepare_parser.add_argument(
        "--qualified-wake-assets-manifest",
        type=Path,
        required=True,
        help=(
            "Existing embry.audio_e2e_audio_assets.v1 manifest whose wake_audio "
            "locators already passed the managed listener qualification boundary."
        ),
    )
    prepare_parser.add_argument("--orpheus-url", default="http://127.0.0.1:8767")
    prepare_parser.add_argument("--checkpoint-id", required=True)
    prepare_parser.add_argument("--checkpoint-sha256", required=True)
    prepare_parser.add_argument("--orpheus-checkpoints-root", type=Path, required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--timeout-seconds", type=float, default=300.0)
    prepare_parser.add_argument("--temperature", type=float, default=0.4)
    prepare_parser.add_argument("--top-p", type=float, default=0.4)
    prepare_parser.add_argument("--repetition-penalty", type=float, default=1.1)
    prepare_parser.add_argument("--qualification-model", default="small.en")
    prepare_parser.add_argument("--qualification-device", default="cpu")
    prepare_parser.add_argument(
        "--qualification-compute-type", default="int8"
    )
    prepare_parser.add_argument("--max-request-wer", type=float, default=0.25)
    prepare_parser.add_argument("--max-candidates", type=int, default=5)
    prepare_parser.add_argument(
        "--max-internal-silence-seconds",
        type=float,
        required=True,
        help=(
            "Reject query WAVs whose longest speech-bounded internal silence "
            "is greater than or equal to the managed listener post-speech "
            "silence boundary. Pass the same value used by the live listener."
        ),
    )
    prepare_parser.add_argument(
        "--regenerate-conflicts",
        action="store_true",
        help=(
            "Archive conflicting deterministic asset directories and regenerate "
            "them. Without this flag, incomplete or conflicting assets fail closed."
        ),
    )

    for name in ("run", "resume"):
        run_parser = commands.add_parser(name)
        run_parser.add_argument("--manifest", type=Path, required=True)
        run_parser.add_argument("--state", type=Path)
        run_parser.add_argument("--journal-db", type=Path, required=True)
        run_parser.add_argument("--campaign-dir", type=Path)
        run_parser.add_argument("--journal-url")
        run_parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
        run_parser.add_argument("--chatterbox-url", default="http://127.0.0.1:8018")
        run_parser.add_argument("--tau-repo", type=Path)
        run_parser.add_argument("--controller-python", type=Path)
        run_parser.add_argument(
            "--speaker-qualification-receipt",
            type=Path,
            help=(
                "Physical Horus enrollment/profile receipt. Physical modes also "
                "require an event-specific speaker.verification.completed event."
            ),
        )
        run_parser.add_argument(
            "--clone-source-contract-receipt",
            type=Path,
            help=(
                "PASS qualified_horus_clone source contract. This proves immutable "
                "synthetic-source provenance only; it cannot prove speaker identity "
                "or unlock personal Memory."
            ),
        )
        run_parser.add_argument(
            "--audio-assets-manifest",
            type=Path,
            help=(
                "Explicit per-case/per-turn path+sha256 locators for unattended "
                "qualified_horus_clone execution"
            ),
        )
        run_parser.add_argument("--memory-tau-timeout-seconds", type=float, default=300)
        run_parser.add_argument("--memory-answer-read-timeout-seconds", type=float, default=90.0)
        run_parser.add_argument(
            "--allow-memory-answer-retry-after-timeout", action="store_true"
        )
        run_parser.add_argument("--render-timeout-seconds", type=float, default=240)

        # Existing managed-listener boundary. These are required only when an
        # incomplete turn still needs listener execution.
        run_parser.add_argument("--realtimestt-repo", type=Path)
        run_parser.add_argument("--realtimestt-python", type=Path)
        run_parser.add_argument("--managed-listener-socket", type=Path)
        run_parser.add_argument("--listener-source-node")
        run_parser.add_argument("--listener-start-timeout-seconds", type=float, default=120)
        run_parser.add_argument("--turn-timeout-seconds", type=float, default=180)
        run_parser.add_argument("--max-request-wer", type=float, default=0.25)
        run_parser.add_argument("--listener-device", default="cpu")
        run_parser.add_argument("--listener-compute-type", default="int8")
        run_parser.add_argument(
            "--listener-post-speech-silence-seconds", type=float, default=2.0
        )

        # Backward-compatible one-case playback options. Multi-case unattended
        # runs should use --audio-assets-manifest.
        run_parser.add_argument("--turn-audio", type=Path, action="append", default=[])
        run_parser.add_argument("--wake-audio", type=Path)
        run_parser.add_argument("--source-playback-target")
        run_parser.add_argument("--source-playback-delay-seconds", type=float, default=2.0)
        run_parser.add_argument("--wake-playback-volume", type=float, default=3.0)
        run_parser.add_argument("--source-playback-volume", type=float, default=1.0)
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
        args.output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "campaign_id": manifest["campaign_id"],
                    "case_count": len(manifest["cases"]),
                    "manifest": str(args.output),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "prepare-clone-assets":
        prepare_clone_assets(
            manifest_path=args.manifest,
            source_contract_path=args.source_contract_receipt,
            qualified_wake_assets_manifest_path=(
                args.qualified_wake_assets_manifest
            ),
            orpheus_url=args.orpheus_url,
            checkpoint_id=args.checkpoint_id,
            checkpoint_sha256=args.checkpoint_sha256,
            orpheus_checkpoints_root=args.orpheus_checkpoints_root,
            output_dir=args.output_dir,
            timeout_seconds=args.timeout_seconds,
            temperature=args.temperature,
            top_p=args.top_p,
            repetition_penalty=args.repetition_penalty,
            qualification_model=args.qualification_model,
            qualification_device=args.qualification_device,
            qualification_compute_type=args.qualification_compute_type,
            max_request_wer=args.max_request_wer,
            max_candidates=args.max_candidates,
            max_internal_silence_seconds=args.max_internal_silence_seconds,
            regenerate_conflicts=args.regenerate_conflicts,
        )
        return 0

    if args.command in {"run", "resume"}:
        runtime_values = (
            args.campaign_dir,
            args.journal_url,
            args.tau_repo,
        )
        optional_runtime_values = (
            args.speaker_qualification_receipt,
            args.clone_source_contract_receipt,
            args.audio_assets_manifest,
        )
        live_config = None
        if any(runtime_values) or any(optional_runtime_values):
            if not all(runtime_values):
                raise ValueError("live_runtime_configuration_incomplete")
            live_config = {
                "campaign_dir": str(args.campaign_dir),
                "journal_url": args.journal_url,
                "memory_url": args.memory_url,
                "chatterbox_url": args.chatterbox_url,
                "tau_repo": str(args.tau_repo),
                "controller_python": (
                    str(args.controller_python) if args.controller_python else None
                ),
                "speaker_qualification_receipt": (
                    str(args.speaker_qualification_receipt)
                    if args.speaker_qualification_receipt
                    else None
                ),
                "clone_source_contract_receipt": (
                    str(args.clone_source_contract_receipt)
                    if args.clone_source_contract_receipt
                    else None
                ),
                "audio_assets_manifest": (
                    str(args.audio_assets_manifest)
                    if args.audio_assets_manifest
                    else None
                ),
                "memory_tau_timeout_seconds": args.memory_tau_timeout_seconds,
                "memory_answer_read_timeout_seconds": (
                    args.memory_answer_read_timeout_seconds
                ),
                "allow_memory_answer_retry_after_timeout": (
                    args.allow_memory_answer_retry_after_timeout
                ),
                "render_timeout_seconds": args.render_timeout_seconds,
                "realtimestt_repo": (
                    str(args.realtimestt_repo) if args.realtimestt_repo else None
                ),
                "realtimestt_python": (
                    str(args.realtimestt_python)
                    if args.realtimestt_python
                    else None
                ),
                "managed_listener_socket": (
                    str(args.managed_listener_socket)
                    if args.managed_listener_socket
                    else None
                ),
                "listener_source_node": args.listener_source_node,
                "listener_start_timeout_seconds": args.listener_start_timeout_seconds,
                "turn_timeout_seconds": args.turn_timeout_seconds,
                "max_request_wer": args.max_request_wer,
                "listener_device": args.listener_device,
                "listener_compute_type": args.listener_compute_type,
                "listener_post_speech_silence_seconds": (
                    args.listener_post_speech_silence_seconds
                ),
                "turn_audio": [str(path) for path in args.turn_audio],
                "wake_audio": str(args.wake_audio) if args.wake_audio else None,
                "source_playback_target": args.source_playback_target,
                "source_playback_delay_seconds": args.source_playback_delay_seconds,
                "wake_playback_volume": args.wake_playback_volume,
                "source_playback_volume": args.source_playback_volume,
                "pw_play": args.pw_play,
            }
        state = run_campaign(
            manifest_path=args.manifest,
            state_path=args.state,
            journal_db=args.journal_db,
            live_config=live_config,
        )
        print(json.dumps(state, sort_keys=True))
        return 1 if state.get("status") == "blocked_live_failure" else 0

    if args.command == "status":
        print(
            json.dumps(
                status(manifest_path=args.manifest, state_path=args.state),
                sort_keys=True,
            )
        )
        return 0

    if args.command == "bundle-failure":
        print(
            json.dumps(
                bundle_failure(
                    manifest_path=args.manifest,
                    state_path=args.state,
                    output=args.output,
                    reason=args.reason,
                ),
                sort_keys=True,
            )
        )
        return 0
    raise ValueError("unknown_command")


if __name__ == "__main__":
    raise SystemExit(main())
