#!/usr/bin/env python3
"""Regression guard: repair creator and reviewer must be independent.

Incident (agent-skills#1484): the reviewer seat was `webgpt` — a browser chat
that cannot run the ticket's live proof in the worktree, so `$ask tau-dag`
failed silently. And the reviewer that "worked" on #1480 was `gpt-5.5-high`
(`codex exec --model gpt-5.5`), the SAME provider as the codex creator — a model
reviewing its own family's work, not an independent second opinion.

This guard exercises the real config check and fails (exit 1) if:
  - a same-provider creator/reviewer pair is accepted, or
  - a browser reviewer (cannot run the proof) is accepted, or
  - a different-provider, code-running reviewer is rejected.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from watchdog import config as c  # noqa: E402


def _blocked(creator: str, reviewer: str) -> bool:
    try:
        c.assert_cross_provider_seats(creator, reviewer)
        return False
    except c.SeatIndependenceError:
        return True


def main() -> int:
    failures: list[str] = []

    # The Codex CLI harness is banned for either seat (codex, or gpt-*/Codex-*
    # which run via `codex exec --model`).
    for cr, rv in [("codex", "claude-opus-5-medium"), ("gpt-5.5-high", "claude-opus-5-medium"),
                   ("oc-deepseek", "Codex-opus-5-high")]:
        if not _blocked(cr, rv):
            failures.append(f"CODEX_HARNESS_ACCEPTED: {cr}+{rv}")

    # Same provider must be blocked (both Anthropic).
    if not _blocked("claude-opus-5", "claude-opus-5-medium"):
        failures.append("SAME_PROVIDER_ACCEPTED: claude+claude")

    # Browser reviewer (cannot run the proof) must be blocked.
    if not _blocked("oc-deepseek", "webclaude"):
        failures.append("BROWSER_REVIEWER_ACCEPTED: a browser reviewer cannot run the proof but was accepted.")

    # The valid config: non-codex OpenCode creator + a different-provider,
    # code-running Opus-5 reviewer.
    if _blocked("oc-deepseek", "claude-opus-5-medium"):
        failures.append("VALID_PAIR_REJECTED: oc-deepseek + claude-opus-5-medium should be valid.")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("SEAT_INDEPENDENCE_OK: reviewer must be a different provider AND run code locally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
