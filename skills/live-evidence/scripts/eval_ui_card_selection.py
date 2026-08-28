#!/usr/bin/env python3
"""Static UI guard for card ordering and auto-follow selection."""

from __future__ import annotations

import sys
from pathlib import Path


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{name}: {'PASS' if ok else 'FAIL'}" + (f" ({detail})" if detail else ""))
    return ok


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    app = (root / "ui" / "src" / "App.tsx").read_text(encoding="utf-8")
    live_surface = (root / "ui" / "src" / "components" / "LiveMeetingSurface.tsx").read_text(encoding="utf-8")
    types = (root / "ui" / "src" / "types.ts").read_text(encoding="utf-8")
    helper = (root / "ui" / "src" / "lib" / "cardSelection.ts").read_text(encoding="utf-8")

    checks = [
        check(
            "App delegates visible card ordering to helper",
            "visibleCardOrder(snapshot.cards)" in app,
        ),
        check(
            "App no longer timestamp-sorts cards",
            "created_at" not in app and ".sort(" not in app,
        ),
        check(
            "selection distinguishes auto from manual",
            'mode: "auto"' in app and 'mode: "manual"' in app,
        ),
        check(
            "helper preserves backend order within pinned partitions",
            "return [...pinned, ...unpinned];" in helper and ".sort(" not in helper,
        ),
        check(
            "helper falls back to backend top card in auto mode",
            "return cards[0];" in helper,
        ),
        check(
            "card type exposes backend question lineage",
            "question_id?: string | null;" in types
            and "question_revision?: number;" in types
            and "policy_digest?: string | null;" in types,
        ),
        check(
            "live card surface renders compact lineage",
            "function lineageLabel(card: EvidenceCard)" in live_surface
            and "q:${card.question_id.slice(0, 8)}" in live_surface
            and "rev ${card.question_revision}" in live_surface
            and "card:{card.card_id.slice(0, 8)}" in live_surface,
        ),
    ]
    if not all(checks):
        print("ui card selection: FAIL")
        return 1
    print("ui card selection preserves backend reducer order: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
