#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from persona_dream_av_bakeoff.contact_sheet_render import render_contact_sheets  # noqa: E402
from persona_dream_av_bakeoff.io_utils import read_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Render contact-sheet prompts to images and compile PNG/HTML sheets.")
    parser.add_argument("--contact-sheets", required=True, help="Path to contact_sheets.json.")
    parser.add_argument("--out-dir", required=True, help="Output directory for rendered contact sheets.")
    parser.add_argument("--dry-run", action="store_true", help="Render prompt-card PNGs locally instead of calling fal.")
    parser.add_argument(
        "--backend",
        choices=["dry_run", "fal_flux", "gpt_image", "scillm_image", "local_diffusion"],
        default=None,
        help="Renderer backend. Future backends are declared here but not executed by this research importer yet.",
    )
    parser.add_argument("--model", default="fal-ai/flux/dev", help="fal image model.")
    parser.add_argument("--image-size", default="landscape_16_9")
    parser.add_argument("--no-logs", action="store_true")
    args = parser.parse_args()

    backend = args.backend or ("dry_run" if args.dry_run else "fal_flux")
    if backend in {"gpt_image", "scillm_image", "local_diffusion"}:
        raise SystemExit(
            f"contact-sheet backend {backend!r} is declared but not wired yet; "
            "use dry_run or fal_flux for this research bundle."
        )

    data = read_json(args.contact_sheets)
    results = render_contact_sheets(
        contact_sheets=data,
        out_dir=args.out_dir,
        dry_run=backend == "dry_run",
        model_id=args.model,
        image_size=args.image_size,
        with_logs=not args.no_logs,
    )

    print(f"[contact-sheets] wrote {args.out_dir}")
    for sheet in results["sheets"]:
        print(f"  {sheet['contact_sheet_id']}: {sheet['contact_sheet_png']}")


if __name__ == "__main__":
    main()
