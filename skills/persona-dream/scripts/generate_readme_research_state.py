#!/usr/bin/env python3
"""Generate the README's current-research-state block from CURRENT_STATUS.json.

Three times now the authority changed, one hand-written current-state paragraph
stayed stale, and the consistency checker passed until a new phrase rule was
added. Phrase rules are a rear-guard action: they catch the wording someone
already used, never the next one. This removes the drift surface instead of
policing it.

Only the operational facts are generated -- active successor issues, claim
dispositions, and current blockers. The research thesis, motivation,
architecture, novelty boundaries, interpretation, and limitations stay
hand-written, because those are judgements and a generator would flatten them.

Run with --check to fail when the committed README drifts from the machine
projection; that runs in the test suite so drift is a test failure rather than
something a reader discovers.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATUS = ROOT / "CURRENT_STATUS.json"
README = ROOT / "README.md"

BEGIN = "<!-- BEGIN GENERATED CURRENT RESEARCH STATE -->"
END = "<!-- END GENERATED CURRENT RESEARCH STATE -->"

#: Display order and human-facing names for the claim registry. A claim absent
#: here still renders, under its raw key, so a new claim cannot go unreported.
CLAIM_LABELS: dict[str, str] = {
    "pctom_measurement_validity": "PCTOM-R measurement validity",
    "pctom_heldout_benefit": "PCTOM-R held-out benefit",
    "pctom_apparatus_integrity": "PCTOM-R apparatus integrity",
    "human_perceived_emotion_and_identity": "Blinded listener study",
    "machine_speaker_identity_by_receipt_and_condition": "Machine speaker identity",
    "p2_continuity_feasibility_pilot": "Continuity feasibility pilot",
    "p2_continuity_reliability_soak": "Continuity reliability soak",
    "p2_restart_recovery": "Restart / recovery",
    "full_phase01_16_media_pipeline_reliability": "Full Phase 01-16 media pipeline",
    "previous_video_attachment_causality": "Previous-video causality",
}


def _cell(text: Any, limit: int = 240) -> str:
    """One table cell: single line, pipes escaped, bounded length."""
    out = " ".join(str(text or "").split()).replace("|", "\\|")
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def _issue_link(raw: str) -> str:
    match = re.search(r"#(\d+)", str(raw or ""))
    return f"#{match.group(1)}" if match else ""


def render(status: dict[str, Any]) -> str:
    claims: dict[str, Any] = status.get("current_claims") or {}
    ordered = [k for k in CLAIM_LABELS if k in claims]
    ordered += [k for k in claims if k not in CLAIM_LABELS and not k.startswith("_")]

    # An issue is labelled by the claim it OWNS (successor_issue), never by a
    # claim that merely points forward to it (next_scope_issue). Otherwise
    # #1008 renders as "measurement validity" -- the claim it follows -- rather
    # than the held-out benefit result it actually owns.
    owned: dict[str, str] = {}
    referenced: dict[str, str] = {}
    for key in ordered:
        claim = claims.get(key) or {}
        if claim.get("successor_resolved"):
            continue
        label = CLAIM_LABELS.get(key, key)
        primary = _issue_link(claim.get("successor_issue") or "")
        if primary:
            owned.setdefault(primary, label)
            continue
        secondary = _issue_link(claim.get("next_scope_issue") or "")
        if secondary:
            referenced.setdefault(secondary, label)

    successor_bullets = [f"- **{issue}** — {label}" for issue, label in owned.items()]
    successor_bullets += [
        f"- **{issue}** — next scope for {label}"
        for issue, label in referenced.items() if issue not in owned
    ]

    # A <=12-line digest, not a status dump. webclaude, 2026-08-03: 85 generated
    # lines of machine state contradicted the README's own sentence that it is
    # "deliberately not a status log", and duplicated CURRENT_STATUS.json which
    # the navigation table points at two lines earlier. Full dispositions stay
    # in the JSON; the README carries only what orients a cold reader.
    blockers = status.get("active_blockers") or []
    next_step = (status.get("next_step") or {}).get("default") or ""
    lines = [
        BEGIN,
        "",
        f"*Generated from `CURRENT_STATUS.json` by `scripts/generate_readme_research_state.py`;",
        "run `./run.sh generate-readme-research-state`. Full claim dispositions live in",
        "the JSON, not here.*",
        "",
        f"- **Phase:** `{_cell(status.get('current_phase'), 60)}`",
        f"- **Open claims:** {', '.join(f'{i} ({l})' for i, l in list(owned.items())[:6]) or 'none'}",
        f"- **Current blocker:** {_cell(blockers[0], 150) if blockers else 'none recorded'}",
        f"- **Next step:** {_cell(next_step, 150) or 'not recorded'}",
    ]
    lines += ["", END]
    return "\n".join(lines)


def splice(readme: str, block: str) -> str:
    if BEGIN not in readme or END not in readme:
        raise SystemExit(
            f"README is missing the generated-block markers.\nExpected {BEGIN} ... {END}"
        )
    head = readme.split(BEGIN)[0]
    tail = readme.split(END, 1)[1]
    return head + block + tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-status", type=Path, default=CURRENT_STATUS)
    parser.add_argument("--readme", type=Path, default=README)
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 when the committed README drifts from CURRENT_STATUS.json.")
    args = parser.parse_args()

    status = json.loads(args.current_status.read_text(encoding="utf-8"))
    readme = args.readme.read_text(encoding="utf-8")
    updated = splice(readme, render(status))

    if args.check:
        if updated != readme:
            print(
                "README current-research-state block drifts from CURRENT_STATUS.json — "
                "run ./run.sh generate-readme-research-state",
                file=sys.stderr,
            )
            return 1
        print("README current-research-state block matches CURRENT_STATUS.json")
        return 0

    args.readme.write_text(updated, encoding="utf-8")
    print(f"wrote {args.readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
