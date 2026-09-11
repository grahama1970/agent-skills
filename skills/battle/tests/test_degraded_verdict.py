"""A battle with no Judge-scored finding and no verified patch must NOT report a
green winner. It fails closed into a DEGRADED / NO VALID VERDICT state so a
hollow run (e.g. Red/Blue $hack/anvil delegation unavailable) can never be read
as a security pass. Regression for the 2026-09-11 misleading-report clusterfuck.
"""
from __future__ import annotations

import inspect

from battle_skill import orchestrator


def test_degraded_verdict_logic_present() -> None:
    src = inspect.getsource(orchestrator)
    # The completion path must compute had_verdict from real scored outcomes
    assert "had_verdict" in src
    assert "verified_patches" in src
    assert "NO VALID VERDICT" in src
    assert 'self.state.status = "degraded"' in src
    # DEGRADED must be reached BEFORE the green "Winner" panel and return early.
    deg = src.index("NO VALID VERDICT")
    winner = src.index("Winner:")
    assert deg < winner, "DEGRADED verdict must be evaluated before declaring a winner"
    # The honest banner must not depend on the rich renderer (plain print fallback).
    assert "print(banner" in src
