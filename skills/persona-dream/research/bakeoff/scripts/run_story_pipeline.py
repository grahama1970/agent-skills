#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build story assets, contact sheets, and optionally run the A/V bake-off.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--contract", default=None)
    parser.add_argument("--render-contact-sheets", action="store_true")
    parser.add_argument("--contact-sheet-dry-run", action="store_true")
    parser.add_argument("--run-bakeoff", action="store_true")
    parser.add_argument("--skip-wavtts", action="store_true")
    parser.add_argument("--ref-audio", default=None)
    parser.add_argument("--ref-text", default=None)
    parser.add_argument("--confirm-voice-consent", action="store_true")
    parser.add_argument("--base-video-url", default=None)
    args = parser.parse_args()

    out = Path(args.out_dir).resolve()
    story_dir = out / "story_assets"

    build_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "build_story_assets.py"),
        "--out-dir",
        str(story_dir),
    ]
    if args.contract:
        build_cmd.extend(["--contract", args.contract])
    run(build_cmd)

    if args.render_contact_sheets:
        render_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "render_contact_sheets_fal.py"),
            "--contact-sheets",
            str(story_dir / "contact_sheets.json"),
            "--out-dir",
            str(story_dir / "contact_sheet_renders"),
        ]
        if args.contact_sheet_dry_run:
            render_cmd.append("--dry-run")
        run(render_cmd)

    if args.run_bakeoff:
        bakeoff_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_bakeoff.py"),
            "--out-dir",
            str(out / "av_bakeoff"),
        ]
        if args.contract:
            bakeoff_cmd.extend(["--contract", args.contract])
        if args.base_video_url:
            bakeoff_cmd.extend(["--base-video-url", args.base_video_url])
        if args.skip_wavtts:
            bakeoff_cmd.append("--skip-wavtts")
        if args.ref_audio:
            bakeoff_cmd.extend(["--ref-audio", args.ref_audio])
        if args.ref_text:
            bakeoff_cmd.extend(["--ref-text", args.ref_text])
        if args.confirm_voice_consent:
            bakeoff_cmd.append("--confirm-voice-consent")
        run(bakeoff_cmd)

    print(f"[done] story pipeline outputs under {out}")


if __name__ == "__main__":
    main()
