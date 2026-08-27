#!/usr/bin/env python3
"""Fail closed when an SVG project-card feature is only partially wired.

This checks the whole feature, not just the source SVG:
- canonical SVG bytes contain the required transform/sentinel
- published site assets match the canonical SVG bytes
- consumer source files reference the expected asset and not legacy assets
- optional built HTML references the expected asset and not legacy assets

It exists because a centered SVG can be committed correctly while /explore still
renders an older /projects/memory.svg path.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--asset", required=True, help="Expected project-card asset filename, e.g. memory-recall-card.svg")
    ap.add_argument("--source", type=Path, help="Canonical source SVG")
    ap.add_argument("--site-asset", action="append", type=Path, default=[], help="Published asset that must byte-match --source")
    ap.add_argument("--consumer", action="append", type=Path, default=[], help="Source file that must reference --asset")
    ap.add_argument("--registry", action="append", type=Path, default=[], help="Registry/manifest file that must reference --asset")
    ap.add_argument("--built-html", action="append", type=Path, default=[], help="Built HTML/RSC file that must reference --asset")
    ap.add_argument("--require-built", action="store_true", help="Fail if any --built-html path is missing")
    ap.add_argument("--require-transform", action="append", default=[], help="Sentinel text required in source and site assets")
    ap.add_argument("--legacy", action="append", default=[], help="Legacy asset string forbidden in consumers/built HTML")
    ap.add_argument("--skip-assets", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve()
    expected = args.asset
    legacy = args.legacy or [f"{args.slug}.svg", f"{args.slug}.webp", f"/projects/{args.slug}.svg", f"/projects/{args.slug}.webp"]
    errors: list[str] = []

    source_hash = None
    if args.source:
        source = (root / args.source).resolve() if not args.source.is_absolute() else args.source
        if not source.is_file():
            errors.append(f"missing source SVG: {rel(source, root)}")
        else:
            source_text = read(source)
            source_hash = sha256(source)
            for sentinel in args.require_transform:
                if sentinel not in source_text:
                    errors.append(f"source SVG missing sentinel {sentinel!r}: {rel(source, root)}")

    if not args.skip_assets:
        if args.site_asset and not args.source:
            errors.append("--site-asset requires --source unless --skip-assets is set")
        for raw in args.site_asset:
            p = (root / raw).resolve() if not raw.is_absolute() else raw
            if not p.is_file():
                errors.append(f"missing site asset: {rel(p, root)}")
                continue
            text = read(p)
            if source_hash is not None and sha256(p) != source_hash:
                errors.append(f"site asset bytes differ from source: {rel(p, root)}")
            for sentinel in args.require_transform:
                if sentinel not in text:
                    errors.append(f"site asset missing sentinel {sentinel!r}: {rel(p, root)}")

    for raw in args.consumer:
        p = (root / raw).resolve() if not raw.is_absolute() else raw
        if not p.is_file():
            errors.append(f"missing consumer source: {rel(p, root)}")
            continue
        text = read(p)
        if expected not in text:
            errors.append(f"consumer does not reference {expected}: {rel(p, root)}")
        for old in legacy:
            if old != expected and old in text:
                errors.append(f"consumer still references legacy asset {old!r}: {rel(p, root)}")

    for raw in args.registry:
        p = (root / raw).resolve() if not raw.is_absolute() else raw
        if not p.is_file():
            errors.append(f"missing asset registry: {rel(p, root)}")
            continue
        text = read(p)
        if expected not in text:
            errors.append(f"asset registry does not reference {expected}: {rel(p, root)}")
        for old in legacy:
            if old != expected and old in text:
                errors.append(f"asset registry still references legacy asset {old!r}: {rel(p, root)}")

    for raw in args.built_html:
        p = (root / raw).resolve() if not raw.is_absolute() else raw
        if not p.is_file():
            if args.require_built:
                errors.append(f"missing built HTML: {rel(p, root)}")
            continue
        text = read(p)
        if expected not in text:
            errors.append(f"built HTML does not reference {expected}: {rel(p, root)}")
        for old in legacy:
            if old != expected and old in text:
                errors.append(f"built HTML still references legacy asset {old!r}: {rel(p, root)}")

    if errors:
        print("PROJECT_CARD_FEATURE_FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    checked = len(args.consumer) + len(args.registry) + len(args.built_html) + (0 if args.skip_assets else len(args.site_asset))
    print(f"PROJECT_CARD_FEATURE_OK slug={args.slug} asset={expected} checks={checked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
