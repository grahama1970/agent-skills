#!/usr/bin/env python3
"""Module support for the personaplex skill."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from personaplex_p3_p5_live_services import DEFAULT_SANITY_ROOT, create_evidence_case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PersonaPlex P7 real evidence-case probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--evidence-case-url", default=None)
    parser.add_argument("--question", default="Focus on the west gateway.")
    parser.add_argument("--context-framework", default="SPARTA")
    parser.add_argument("--enable-llm", action="store_true")
    parser.add_argument("--include-cae-tree", action="store_true")
    parser.add_argument("--fail-on-degraded-evidence", action="store_true")
    parser.add_argument("--timeout", type=float, default=2.5)
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless real_create_evidence_case=true.")
    args = parser.parse_args(argv)

    receipt = create_evidence_case(
        question=args.question,
        evidence_case_url=args.evidence_case_url,
        context_framework=args.context_framework,
        enable_llm=args.enable_llm,
        include_cae_tree=args.include_cae_tree,
        fail_on_degraded_evidence=args.fail_on_degraded_evidence,
        out_dir=Path(args.out_dir),
        timeout=args.timeout,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_real and not receipt.get("real_create_evidence_case"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
