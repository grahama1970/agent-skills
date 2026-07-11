#!/usr/bin/env python3
"""Dispatch opt-in persona-dream research bakeoff commands.

Inputs are CLI subcommands and optional run paths. Outputs are story,
contact-sheet, A/V bakeoff, or NAVA research artifacts under the selected
output directory. Failure modes are explicit missing credentials, missing
fixtures, unwired backends, or failed child commands.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
BAKEOFF_DIR = SKILL_DIR / "research" / "bakeoff"
DEFAULT_RUN_ROOT = BAKEOFF_DIR / "runs"
FIXTURE_STORY_ASSETS = BAKEOFF_DIR / "fixtures" / "story_assets_minimal"


def run(cmd: list[str], *, cwd: Path = BAKEOFF_DIR) -> None:
    print("+ " + " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(cwd), check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def default_out_dir(command: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_RUN_ROOT / f"{command}_{stamp}"


def resolve_out_dir(args: argparse.Namespace, command: str) -> Path:
    if args.out_dir:
        return Path(args.out_dir).expanduser().resolve()
    return default_out_dir(command)


def require_fal_key() -> None:
    fal_key = os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
    if not fal_key:
        raise SystemExit("FAL_KEY or FAL_API_KEY is required for hosted fal bakeoff lanes.")
    os.environ.setdefault("FAL_KEY", fal_key)


def story_assets_dir(out_dir: Path) -> Path:
    return out_dir / "story_assets"


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out-dir", default=None, help="Run output directory. Defaults under research/bakeoff/runs/.")
    parser.add_argument("--contract", default=None, help="Optional contract JSON path.")


def build_story(out_dir: Path, contract: str | None) -> None:
    cmd = [
        sys.executable,
        str(BAKEOFF_DIR / "scripts" / "build_story_assets.py"),
        "--out-dir",
        str(story_assets_dir(out_dir)),
    ]
    if contract:
        cmd.extend(["--contract", contract])
    run(cmd)


def render_contact_sheet(
    *,
    contact_sheets: Path,
    out_dir: Path,
    backend: str,
    dry_run: bool,
    model: str | None,
    image_size: str,
    no_logs: bool,
) -> None:
    if backend in {"gpt_image", "scillm_image", "local_diffusion"} and not dry_run:
        raise SystemExit(
            f"contact-sheet backend {backend!r} is declared but not wired yet; "
            "use dry_run or fal_flux for this research bundle."
        )
    cmd = [
        sys.executable,
        str(BAKEOFF_DIR / "scripts" / "render_contact_sheets_fal.py"),
        "--contact-sheets",
        str(contact_sheets),
        "--out-dir",
        str(out_dir),
        "--backend",
        "dry_run" if dry_run else backend,
        "--image-size",
        image_size,
    ]
    if model:
        cmd.extend(["--model", model])
    if no_logs:
        cmd.append("--no-logs")
    run(cmd)


def cmd_smoke(args: argparse.Namespace) -> None:
    out_dir = resolve_out_dir(args, "smoke")
    cmd = [
        sys.executable,
        str(BAKEOFF_DIR / "scripts" / "run_story_pipeline.py"),
        "--out-dir",
        str(out_dir),
        "--render-contact-sheets",
        "--contact-sheet-dry-run",
    ]
    if args.contract:
        cmd.extend(["--contract", args.contract])
    run(cmd)


def cmd_story(args: argparse.Namespace) -> None:
    build_story(resolve_out_dir(args, "story"), args.contract)


def cmd_contact_sheet(args: argparse.Namespace) -> None:
    out_dir = resolve_out_dir(args, "contact_sheet")
    if args.contact_sheets:
        contact_sheets = Path(args.contact_sheets).expanduser().resolve()
    else:
        generated_contact_sheets = story_assets_dir(out_dir) / "contact_sheets.json"
        contact_sheets = generated_contact_sheets if generated_contact_sheets.exists() else FIXTURE_STORY_ASSETS / "contact_sheets.json"
    if not contact_sheets.exists():
        raise SystemExit(f"Missing contact sheets JSON: {contact_sheets}. Run `./run.sh research-bakeoff story --out-dir {out_dir}` first or pass --contact-sheets.")
    render_contact_sheet(
        contact_sheets=contact_sheets,
        out_dir=args.render_out_dir or story_assets_dir(out_dir) / "contact_sheet_renders",
        backend=args.backend,
        dry_run=args.dry_run,
        model=args.model,
        image_size=args.image_size,
        no_logs=args.no_logs,
    )


def cmd_elevenlabs(args: argparse.Namespace) -> None:
    require_fal_key()
    out_dir = resolve_out_dir(args, "elevenlabs")
    cmd = [
        sys.executable,
        str(BAKEOFF_DIR / "scripts" / "run_story_pipeline.py"),
        "--out-dir",
        str(out_dir),
        "--render-contact-sheets",
        "--contact-sheet-dry-run",
        "--run-bakeoff",
        "--skip-wavtts",
    ]
    if args.contract:
        cmd.extend(["--contract", args.contract])
    if args.base_video_url:
        cmd.extend(["--base-video-url", args.base_video_url])
    run(cmd)


def cmd_wavtts(args: argparse.Namespace) -> None:
    require_fal_key()
    if not args.confirm_voice_consent:
        raise SystemExit("--confirm-voice-consent is required for WavTTS.")
    out_dir = resolve_out_dir(args, "wavtts")
    cmd = [
        sys.executable,
        str(BAKEOFF_DIR / "scripts" / "run_story_pipeline.py"),
        "--out-dir",
        str(out_dir),
        "--render-contact-sheets",
        "--contact-sheet-dry-run",
        "--run-bakeoff",
        "--confirm-voice-consent",
    ]
    for flag, value in (
        ("--contract", args.contract),
        ("--base-video-url", args.base_video_url),
        ("--ref-audio", args.ref_audio),
        ("--ref-text", args.ref_text),
    ):
        if value:
            cmd.extend([flag, value])
    run(cmd)


def cmd_nava_inputs(args: argparse.Namespace) -> None:
    out_dir = resolve_out_dir(args, "nava_inputs")
    if args.dream_packet:
        dream_packet = Path(args.dream_packet).expanduser().resolve()
    else:
        generated_dream_packet = story_assets_dir(out_dir) / "dream_packet.json"
        dream_packet = generated_dream_packet if generated_dream_packet.exists() else FIXTURE_STORY_ASSETS / "dream_packet.json"
    if not dream_packet.exists():
        raise SystemExit(f"Missing dream packet JSON: {dream_packet}. Run `./run.sh research-bakeoff story --out-dir {out_dir}` first or pass --dream-packet.")
    cmd = [
        sys.executable,
        str(BAKEOFF_DIR / "scripts" / "build_nava_inputs.py"),
        "--dream-packet",
        str(dream_packet),
        "--out-dir",
        str(out_dir / "nava_lane"),
    ]
    if args.speaker_wav:
        cmd.extend(["--speaker-wav", args.speaker_wav])
    if args.first_frame_image:
        cmd.extend(["--first-frame-image", args.first_frame_image])
    run(cmd)


def cmd_nava_dry_run(args: argparse.Namespace) -> None:
    out_dir = resolve_out_dir(args, "nava_dry_run")
    data_file = Path(args.data_file).expanduser().resolve() if args.data_file else out_dir / "nava_lane" / "nava_prompts.jsonl"
    cmd = [
        sys.executable,
        str(BAKEOFF_DIR / "scripts" / "run_nava_local.py"),
        "--nava-repo",
        args.nava_repo,
        "--data-file",
        str(data_file),
        "--out-dir",
        str(out_dir / "nava_lane" / "outputs"),
        "--ckpt",
        args.ckpt,
        "--dry-run",
    ]
    if args.fp8:
        cmd.append("--fp8")
    if args.single_gpu:
        cmd.append("--single-gpu")
    run(cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run persona-dream research bakeoff modes.")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke", help="No-credit story + dry-run contact-sheet pipeline.")
    add_common(smoke)
    smoke.set_defaults(func=cmd_smoke)

    story = sub.add_parser("story", help="Build story assets only.")
    add_common(story)
    story.set_defaults(func=cmd_story)

    contact = sub.add_parser("contact-sheet", help="Render contact sheets from contact_sheets.json.")
    add_common(contact)
    contact.add_argument("--contact-sheets", default=None)
    contact.add_argument("--render-out-dir", type=Path, default=None)
    contact.add_argument("--dry-run", action="store_true")
    contact.add_argument("--backend", choices=["dry_run", "fal_flux", "gpt_image", "scillm_image", "local_diffusion"], default="dry_run")
    contact.add_argument("--model", default=None)
    contact.add_argument("--image-size", default="landscape_16_9")
    contact.add_argument("--no-logs", action="store_true")
    contact.set_defaults(func=cmd_contact_sheet)

    eleven = sub.add_parser("elevenlabs", help="Hosted ElevenLabs + Kling LipSync baseline.")
    add_common(eleven)
    eleven.add_argument("--base-video-url", default=None)
    eleven.set_defaults(func=cmd_elevenlabs)

    wavtts = sub.add_parser("wavtts", help="WavTTS + Kling LipSync bakeoff with consented reference audio.")
    add_common(wavtts)
    wavtts.add_argument("--base-video-url", default=None)
    wavtts.add_argument("--ref-audio", default=None)
    wavtts.add_argument("--ref-text", default=None)
    wavtts.add_argument("--confirm-voice-consent", action="store_true")
    wavtts.set_defaults(func=cmd_wavtts)

    nava_inputs = sub.add_parser("nava-inputs", help="Build NAVA prompt JSONL from a dream packet.")
    add_common(nava_inputs)
    nava_inputs.add_argument("--dream-packet", default=None)
    nava_inputs.add_argument("--speaker-wav", default=None)
    nava_inputs.add_argument("--first-frame-image", default=None)
    nava_inputs.set_defaults(func=cmd_nava_inputs)

    nava_dry = sub.add_parser("nava-dry-run", help="Write local NAVA command manifest without running inference.")
    add_common(nava_dry)
    nava_dry.add_argument("--nava-repo", required=True)
    nava_dry.add_argument("--data-file", default=None)
    nava_dry.add_argument("--ckpt", default="NAVA_fp8.safetensors")
    nava_dry.add_argument("--fp8", action="store_true")
    nava_dry.add_argument("--single-gpu", action="store_true")
    nava_dry.set_defaults(func=cmd_nava_dry_run)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
