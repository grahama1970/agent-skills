#!/usr/bin/env python3
"""Build PCTOM-R2 Phase 6 compute-matched deterministic corpora."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_phase6_corpus_lib import build_corpus, default_phase6_paths
from pctom_r2_phase1_lib import ROOT_DEFAULT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--corpus-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output_path = args.corpus_out or default_phase6_paths(args.root)["corpus"]
    corpus = build_corpus(args.root, output_path)
    if args.json:
        print(json.dumps(corpus, indent=2, sort_keys=True))
    else:
        print(corpus["status"])
        print(output_path)
    return 0 if corpus.get("counts", {}).get("rows", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
