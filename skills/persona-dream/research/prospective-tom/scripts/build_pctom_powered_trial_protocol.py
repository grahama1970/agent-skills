#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_phase7_protocol_lib import DEFAULT_PROTOCOL_PATH, build_protocol


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the sealed PCTOM-R2 powered-trial protocol.")
    parser.add_argument("--root", type=Path, default=Path("skills/persona-dream/research/prospective-tom"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    out = args.out or args.root / DEFAULT_PROTOCOL_PATH
    protocol = build_protocol(args.root, out)
    if args.json:
        print(json.dumps(protocol, indent=2, sort_keys=True))
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
