#!/usr/bin/env python3
"""Run pinned FCaptcha defensive reference tests and emit a receipt.

This script uses FCaptcha only as a local defensive reference fixture. It runs
upstream bot-detection and input-forensics tests from a pinned Git commit. It
does not solve CAPTCHA challenges, contact public CAPTCHA providers, use
stealth browsers, or send traffic to public targets.
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/captcha-fcaptcha-reference-eval.json"))
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from captcha_skill.defensive_reference import run_fcaptcha_reference, write_receipt

    receipt = run_fcaptcha_reference()
    write_receipt(args.output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
