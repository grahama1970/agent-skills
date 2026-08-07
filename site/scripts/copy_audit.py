#!/usr/bin/env python3
"""copy-audit — deterministic guard for grahama.co's first-person human voice (#1298).

Scans the site's visible copy (content.json, research-map.json blurbs/aliases,
private-abstracts.json, and the JSX string literals in app/page.tsx) for voice
violations and exits non-zero on any hit. This does NOT rewrite prose — it flags
drift for a human to fix, so an automated pass can never quietly change the voice.

Voice contract (from #1298):
  - first-person singular ("I"), never collective ("we/our/us")
  - concrete language, no generic AI-startup superlatives
  - visible uncertainty / negative results are allowed and encouraged
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"

# Collective voice — the practice is one person; marketing "we/our/us" is out.
COLLECTIVE = re.compile(r"\b(we|we're|we've|we'll|our|ours|us)\b", re.IGNORECASE)

# Generic AI-startup / consulting superlatives.
SUPERLATIVES = [
    "cutting-edge", "cutting edge", "state-of-the-art", "best-in-class",
    "world-class", "game-chang", "game chang", "revolutionary", "seamless",
    "leverage", "empower", "unlock", "supercharge", "next-gen", "next gen",
    "disrupt", "synergy", "turnkey", "bleeding-edge", "paradigm shift",
    "effortless", "frictionless", "blazing", "lightning-fast", "10x",
    "transformative", "unparalleled", "unlock the power", "harness the power",
]
SUP_RE = re.compile("|".join(re.escape(s) for s in SUPERLATIVES), re.IGNORECASE)

# "we" appears legitimately nowhere in first-person copy, but allow it inside a
# quoted line the site is deliberately reporting (none today). Kept explicit so
# a future intentional exception is a code change, not a silent pass.
ALLOW_COLLECTIVE_IN = set()


def _strings_from_json(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            out.extend(_strings_from_json(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_strings_from_json(v))
    return out


def _jsx_text(path: Path) -> list[str]:
    """Visible text between JSX tags + string props like title=/aria-label=."""
    txt = path.read_text(encoding="utf-8")
    # text nodes between > and <
    nodes = re.findall(r">\s*([^<>{][^<>]*?)\s*<", txt)
    # human-facing string attributes
    attrs = re.findall(r'(?:title|aria-label|placeholder)=\{?"([^"]+)"', txt)
    return [t.strip() for t in nodes + attrs if t.strip()]


def main() -> None:
    sources: list[tuple[str, list[str]]] = []
    for name in ("content.json", "research-map.json", "private-abstracts.json"):
        p = SITE / name
        if p.exists():
            sources.append((name, _strings_from_json(json.loads(p.read_text()))))
    page = SITE / "app" / "page.tsx"
    if page.exists():
        sources.append(("app/page.tsx", _jsx_text(page)))

    violations: list[str] = []
    for name, strings in sources:
        for s in strings:
            for m in COLLECTIVE.finditer(s):
                if s in ALLOW_COLLECTIVE_IN:
                    continue
                violations.append(f"{name}: collective voice '{m.group(0)}' — {s[:80]!r}")
            for m in SUP_RE.finditer(s):
                violations.append(f"{name}: superlative '{m.group(0)}' — {s[:80]!r}")

    if violations:
        print("copy-audit FAILED — voice-contract violations:")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    total = sum(len(s) for _, s in sources)
    print(f"copy-audit OK: {total} visible strings across {len(sources)} sources; "
          "first-person voice, no collective 'we', no AI-startup superlatives.")


if __name__ == "__main__":
    main()
