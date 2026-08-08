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

import argparse
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


# Accidental placeholders / generated boilerplate that must never ship.
PLACEHOLDER_RE = re.compile(
    r"\blorem ipsum\b|\bdolor sit\b|\bplaceholder\b|\bTODO\b|\bFIXME\b|\bXXXX\b"
    r"|\bYour (?:Name|Company|Text) Here\b|\blipsum\b", re.IGNORECASE)


def _anchors():
    """(anchors, allow_collective) from voice-anchors.yml. Empty if absent so the
    core audit still runs standalone."""
    p = SITE / "voice-anchors.yml"
    if not p.is_file():
        return [], set()
    import yaml
    d = yaml.safe_load(p.read_text()) or {}
    return d.get("anchors", []), set(d.get("allow_collective_in", []))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    sources: list[tuple[str, list[str]]] = []
    for name in ("content.json", "research-map.json", "private-abstracts.json"):
        p = SITE / name
        if p.exists():
            sources.append((name, _strings_from_json(json.loads(p.read_text()))))
    page = SITE / "app" / "page.tsx"
    if page.exists():
        sources.append(("app/page.tsx", _jsx_text(page)))

    anchors, allow_collective = _anchors()
    allow_collective |= ALLOW_COLLECTIVE_IN

    violations: list[str] = []
    for name, strings in sources:
        for s in strings:
            for m in COLLECTIVE.finditer(s):
                if s in allow_collective:
                    continue
                violations.append(f"{name}: collective voice '{m.group(0)}' — {s[:80]!r}")
            for m in SUP_RE.finditer(s):
                violations.append(f"{name}: superlative '{m.group(0)}' — {s[:80]!r}")
            if PLACEHOLDER_RE.search(s):
                violations.append(f"{name}: placeholder/boilerplate — {s[:80]!r}")

    # Signature lines must still be present (or explicitly retired by a human).
    corpus = re.sub(r"\s+", " ", " ".join(s for _, ss in sources for s in ss))
    missing_anchors = [
        a["id"] for a in anchors
        if not a.get("retired") and re.sub(r"\s+", " ", a["fragment"]) not in corpus
    ]
    for aid in missing_anchors:
        violations.append(f"voice-anchors.yml: signature line '{aid}' missing from copy")

    total = sum(len(s) for _, s in sources)
    # Em-dash cadence — advisory, not a violation (punctuation is voice-adjacent).
    # Research (bespoke-design audit) flags repeated "claim — clarification" dashes
    # as an "em-dash confetti" / sameness tell. Track density so it can't creep back.
    all_strings = [s for _, ss in sources for s in ss]
    em_dashes = sum(s.count("—") for s in all_strings)
    strings_with_em = sum(1 for s in all_strings if "—" in s)
    em_ratio = round(strings_with_em / max(len(all_strings), 1), 3)
    result = {
        "schema": "monitor_website.copy_audit.v1",
        "status": "FAIL" if violations else "PASS",
        "sources": [n for n, _ in sources],
        "strings_scanned": total,
        "anchors_checked": len(anchors),
        "violations": violations,
        "em_dash_cadence": {
            "advisory": em_ratio > 0.28,  # >~1/4 of strings using em-dashes reads as a mannerism
            "em_dashes": em_dashes,
            "strings_with_em_dash": strings_with_em,
            "ratio": em_ratio,
        },
    }
    if args.json:
        print(json.dumps(result, indent=2))
    elif violations:
        print("copy-audit FAILED — voice-contract violations:")
        for v in violations:
            print(f"  - {v}")
    else:
        print(f"copy-audit OK: {total} visible strings across {len(sources)} sources; "
              f"{len(anchors)} signature lines present; first-person voice, no "
              "collective 'we', no superlatives, no placeholders.")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
