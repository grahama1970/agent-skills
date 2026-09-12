"""The invariant Judge is wired as the scorekeeper authority in the orchestrator
completion path: PASS -> Blue-held verdict, FAIL -> Red-scored verdict, and
either way the run has a real (non-degraded) verdict. Regression for making
$battle the robust superset of $hack (independent Judge decides, not self-cert).
"""
from __future__ import annotations

import inspect

from battle_skill import orchestrator


def test_invariant_judge_is_scorekeeper_authority() -> None:
    src = inspect.getsource(orchestrator)
    assert "self.invariant_judge" in src
    assert "from .invariant_judge import run_judge" in src
    # PASS -> Blue verdict, FAIL -> Red verdict, both making had_verdict true.
    assert "self.state.blue_total_score = max(self.state.blue_total_score, 1.0)" in src
    assert "self.state.red_total_score = max(self.state.red_total_score, 1.0)" in src
    # The Judge block runs BEFORE the DEGRADED check, so a judged run is never
    # falsely reported as hollow.
    assert src.index("run_judge") < src.index("had_verdict")
    assert src.index("Invariant Judge") < src.index("NO VALID VERDICT")
