#!/usr/bin/env python3
"""Copy persona-dream local proof artifacts into ux-lab public serving dir."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / ".artifacts/persona-dream-local-proof"
DEFAULT_UX_PUBLIC = Path(
    "/home/graham/workspace/experiments/pi-mono/packages/ux-lab/public/scillm-dag-runs"
)
PUBLIC_RUNGS = ("scillm-one", "scillm-two-concurrent", "real-gates")


def latest_output_dir(artifact_root: Path, rung: str) -> Path:
    matches = sorted(
        artifact_root.glob(f"*-{rung}-*"),
        key=lambda path: path.name,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(f"No artifact directory found for rung {rung!r} under {artifact_root}")
    return matches[0]


def install_run(source_dir: Path, dest_dir: Path) -> None:
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(source_dir, dest_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--ux-public", type=Path, default=DEFAULT_UX_PUBLIC)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="RUNG=DIR",
        help="Optional explicit mapping, e.g. scillm-one=/path/to/output",
    )
    parser.add_argument(
        "--default-run-id",
        default="scillm-two-concurrent",
        help="Default run selected by the viewer manifest",
    )
    args = parser.parse_args()

    explicit = {}
    for item in args.source:
        rung, _, path = item.partition("=")
        if not rung or not path:
            raise SystemExit(f"Invalid --source value: {item!r}")
        explicit[rung] = Path(path)

    args.ux_public.mkdir(parents=True, exist_ok=True)
    runs = []
    for rung in PUBLIC_RUNGS:
        source_dir = explicit.get(rung) or latest_output_dir(args.artifact_root, rung)
        if not (source_dir / "graph.yaml").is_file():
            raise FileNotFoundError(f"Missing graph.yaml in {source_dir}")
        if not (source_dir / "context/proof-summary.json").is_file():
            raise FileNotFoundError(f"Missing proof-summary.json in {source_dir}")
        dest_dir = args.ux_public / rung
        install_run(source_dir, dest_dir)
        runs.append(
            {
                "id": rung,
                "label": rung.replace("-", " "),
                "path": f"/scillm-dag-runs/{rung}",
                "source": str(source_dir),
            }
        )

    manifest = {
        "defaultRunId": args.default_run_id,
        "runs": runs,
    }
    (args.ux_public / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"installed": runs, "manifest": str(args.ux_public / "manifest.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
