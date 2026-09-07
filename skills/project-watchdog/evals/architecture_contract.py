#!/usr/bin/env python3
"""Verify the project-watchdog architecture doc and SVG stay useful.

This is intentionally small: rerender the scene, compare the checked-in SVG,
and check that the doc names the seams a maintainer needs to reason about.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

REQUIRED_LABELS = (
    "$ask",
    "Tau",
    "$ticket",
    "Pydantic",
    "$triage-error",
    "$agentic-evals",
    "closure audit",
    "GUARD + SCAN",
    "REPAIR LANE",
    "PROOF + CLOSE",
    "AUDIT + TRIAGE",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_of(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def skill_root(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[1]


def svg_text(path: Path) -> str:
    root = ElementTree.fromstring(path.read_bytes())
    return "\n".join(t.strip() for t in root.itertext() if t and t.strip())


def check_label(root: Path, label: str) -> bool:
    haystack = "\n".join(
        [
            text_of(root / "ARCHITECTURE.md"),
            text_of(root / "docs/project-watchdog-architecture.scene.yml"),
            svg_text(root / "docs/project-watchdog-architecture.svg"),
        ]
    )
    return label in haystack


def run_create_svg_verify(root: Path, output: Path, receipt: Path) -> None:
    repo = root.parents[1]
    cmd = [
        str(repo / "skills/create-svg/run.sh"),
        "verify",
        str(root / "docs/project-watchdog-architecture.scene.yml"),
        str(output),
        "--receipt",
        str(receipt),
        "--no-browser",
    ]
    result = subprocess.run(cmd, cwd=repo, text=True, capture_output=True, timeout=180, check=False)
    if result.returncode != 0:
        raise SystemExit(
            "create-svg verify failed\nSTDOUT:\n"
            + result.stdout[-2000:]
            + "\nSTDERR:\n"
            + result.stderr[-2000:]
        )


def validate(args: argparse.Namespace) -> int:
    root = skill_root(args.root)
    arch = root / "ARCHITECTURE.md"
    scene = root / "docs/project-watchdog-architecture.scene.yml"
    svg = root / "docs/project-watchdog-architecture.svg"
    receipt = root / "docs/project-watchdog-architecture.create-architecture.receipt.json"
    for path in (arch, scene, svg, receipt):
        if not path.is_file():
            raise SystemExit(f"missing required file: {path}")
    missing = [label for label in REQUIRED_LABELS if not check_label(root, label)]
    if missing:
        raise SystemExit("missing architecture labels: " + ", ".join(missing))
    if "docs/project-watchdog-architecture.svg" not in text_of(arch):
        raise SystemExit("ARCHITECTURE.md does not embed the checked-in SVG")
    if "fixtures/agentic_eval.architecture.json" not in text_of(arch):
        raise SystemExit("ARCHITECTURE.md does not name its retained agentic eval")
    with TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        rendered = tmpdir / "rendered.svg"
        render_receipt = tmpdir / "create-svg.receipt.json"
        run_create_svg_verify(root, rendered, render_receipt)
        render_doc = json.loads(render_receipt.read_text(encoding="utf-8"))
        if render_doc.get("status") != "PASS" or render_doc.get("deterministic_rebuild") is not True:
            raise SystemExit(f"create-svg receipt is not a deterministic PASS: {render_doc}")
        if rendered.read_bytes() != svg.read_bytes():
            raise SystemExit("checked-in SVG differs from deterministic render of the scene")
    delivery = json.loads(receipt.read_text(encoding="utf-8"))
    if delivery.get("route", {}).get("skill") != "create-svg" or delivery.get("seam_validation", {}).get("status") != "PASS":
        raise SystemExit("create-architecture receipt is not a create-svg PASS draft")
    report = {
        "schema": "agent_skills.project_watchdog.architecture_contract.v1",
        "status": "PASS",
        "svg_sha256": sha256(svg),
        "scene_sha256": sha256(scene),
        "architecture_sha256": sha256(arch),
        "create_architecture_receipt_sha256": sha256(receipt),
        "labels_checked": list(REQUIRED_LABELS),
        "proof_scope": "Deterministic create-svg rebuild, checked-in SVG byte comparison, create-architecture receipt shape, and required doc labels. No human visual approval.",
    }
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("ARCHITECTURE_CONTRACT_PASS")
    return 0


def assert_label(args: argparse.Namespace) -> int:
    root = skill_root(args.root)
    if check_label(root, args.label):
        print("ARCHITECTURE_CONTRACT_LABEL_PRESENT")
        return 0
    print(f"ARCHITECTURE_CONTRACT_LABEL_MISSING: {args.label}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--root")
    p_validate.add_argument("--report")
    p_validate.set_defaults(func=validate)
    p_label = sub.add_parser("assert-label")
    p_label.add_argument("--root")
    p_label.add_argument("--label", required=True)
    p_label.set_defaults(func=assert_label)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
