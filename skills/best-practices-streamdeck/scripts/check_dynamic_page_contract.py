#!/usr/bin/env python3
"""Check the Stream Deck dynamic-page safety contract text."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_TEXT = (
    (ROOT / "SKILL.md").read_text(encoding="utf-8")
    + "\n"
    + (ROOT / "rules" / "dynamic-page-contract.md").read_text(encoding="utf-8")
)
NORMALIZED_CONTRACT_TEXT = " ".join(CONTRACT_TEXT.split())

CHECKS = {
    "pipeline": {
        "sentinel": "DYNAMIC_PAGE_CONTRACT_PRESENT",
        "tokens": [
            "streamdeck.dynamic_page_request.v1",
            "bounded recipe/action plan",
            "deterministic manifest compiler",
            "staged preview",
            "hash-bound approval",
            "explicit deployment",
            "qid",
            "action_id",
            "binding_id",
            "page_instance_id",
            "deployment_id",
            "event_id",
            "REQUESTED",
            "NEEDS_CONFIRMATION",
            "RESOLVED",
            "STAGED",
            "APPROVED",
            "DEPLOYED",
            "REVOKED",
            "external_effects=false",
            "Pages `0-9`",
            "Dynamic pages use `10+`",
            "compare-and-swap deployment",
            "rollback receipts",
        ],
    },
    "denied-primitives": {
        "sentinel": "DENIED_WORKSTATION_PRIMITIVES_PRESENT",
        "tokens": [
            "KDE",
            "KWin",
            "KDED",
            "Plasma",
            "X11",
            "display",
            "global scale",
            "audio",
            "window",
            "process",
            "service",
            "sudo",
            "shell pipes",
            "command chaining",
            "redirection",
            "arbitrary filesystem",
            "arbitrary network",
            "xrandr",
            "kscreen-doctor",
            "nvidia-settings",
            "keys",
            "write",
            "~/.streamdeck_ui.json",
            "/tmp/streamdeck_ui.sock",
            "Meeting-off buttons must be receipt-only",
        ],
    },
    "catalog-and-evals": {
        "sentinel": "CATALOG_AND_EVAL_GUARDS_PRESENT",
        "tokens": [
            "do not bespoke-code page generators",
            "versioned recipe catalog",
            "action catalog",
            "fixed dispatcher bindings",
            "streamdeck-cli action invoke --binding <binding_id>",
            "Voice and SPARTA adapters may emit only semantic requests",
            "broad Memory `/list`",
            "ArangoDB scans",
            "dynamic recipe discovery",
            "Every change to dynamic-page request handling",
            "fixtures/agentic_eval.json",
            "Live hardware, voice, SPARTA, or physical-button claims require a separate canary receipt",
        ],
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=sorted(CHECKS))
    args = parser.parse_args()

    check = CHECKS[args.check]
    missing = [
        token
        for token in check["tokens"]
        if token not in CONTRACT_TEXT
        and " ".join(token.split()) not in NORMALIZED_CONTRACT_TEXT
    ]
    if missing:
        print(f"missing {args.check} contract tokens: {missing}")
        return 1

    print(check["sentinel"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
