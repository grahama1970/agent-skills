"""Gate-based scoring for evidence cases.

UCT (Upper Confidence Bound for Trees) for strategy selection.
Gate pass/fail replaces composite float scoring — each gate is a boolean
decision point, not a weighted average.

6-gate technique-centric tree:
  1. On-topic
  2. Recall techniques
  2b. Grounding — block SATISFIED when fabricated entities detected
  3. Technique coverage
  4. Decompose
  5. Lean4 formal verification — proof success/failure is a real signal.
     The lean4_provable classifier (93.8% CV) determines if a question is
     formalizable. If yes, /lean4-prove attempts a proof. If proof fails,
     gate 5 fails, dropping max verdict to "satisfied" only when all 6 pass.

     When the classifier says "not formalizable" or confidence < 0.6,
     gate 5 is marked as passed (skip = no negative signal). This means
     non-technical questions aren't penalized for not being provable.

Inputs: GateResult lists, StrategyNode fields.
Outputs: Boolean verdicts + UCT scores — no magic floats.
Failures: ZeroDivisionError guarded (visits=0 → inf).
"""

from __future__ import annotations

import math

# Exploration constant — standard sqrt(2) ≈ 1.414
UCT_C = 1.4

# Gate count thresholds for verdict mapping
GATES_TOTAL = 6
GATES_FOR_SATISFIED = 6  # all gates must pass for SATISFIED
GATES_FOR_INCONCLUSIVE = 2  # gates 1-2 pass but not all


def _normalize_gate_count(gates_passed: int, total_gates: int) -> tuple[int, int]:
    """Clamp gate counts so scoring cannot exceed [0, total_gates]."""
    total = max(total_gates, 1)
    passed = min(max(gates_passed, 0), total)
    return passed, total


def uct_score(wins: int, visits: int, parent_visits: int) -> float:
    """Upper Confidence Bound for Trees.

    Args:
        wins: Number of times this strategy won (partial wins count as 0.5).
        visits: Number of times this strategy was tried.
        parent_visits: Total visits across all strategies for this category.

    Returns:
        UCT score. inf for untried strategies (always explore first).
    """
    if visits == 0:
        return float("inf")
    exploit = wins / visits
    # parent_visits can be 0/1 in cold-start categories.
    if parent_visits <= 1:
        explore = 0.0
    else:
        explore = UCT_C * math.sqrt(math.log(parent_visits) / visits)
    return exploit + explore


def win_credit(gates_passed: int) -> float:
    """How much 'win' credit a strategy earns based on gates passed.

    Returns:
        1.0 for all 6 gates passed (SATISFIED), 0.5 for >=2 gates, 0.0 below.
    """
    if gates_passed >= GATES_FOR_SATISFIED:
        return 1.0
    if gates_passed >= GATES_FOR_INCONCLUSIVE:
        return 0.5
    return 0.0


def gates_to_verdict(
    gates_passed: int,
    total_gates: int = GATES_TOTAL,
    t2_override: str | None = None,
) -> str:
    """Map gate pass count to verdict state.

    Args:
        gates_passed: Number of gates that passed.
        total_gates: Total gates in the decision tree.
        t2_override: If provided by T2 LLM adjudication, overrides
            "inconclusive" verdicts. Only applied when the T0 verdict
            would be "inconclusive" — cannot override "not_satisfied"
            (too few gates) or "satisfied" (already definitive).

    Returns:
        "satisfied" | "inconclusive" | "not_satisfied"
    """
    passed, total = _normalize_gate_count(gates_passed, total_gates)
    if passed >= total:
        return "satisfied"
    if passed >= GATES_FOR_INCONCLUSIVE:
        if t2_override in ("satisfied", "not_satisfied"):
            return t2_override
        return "inconclusive"
    return "not_satisfied"


def gates_to_grade(gates_passed: int, total_gates: int = GATES_TOTAL) -> str:
    """Map gate pass count to letter grade.

    Args:
        gates_passed: Number of gates that passed.
        total_gates: Total gates in the decision tree.

    Returns:
        Letter grade: A+, A, B, C, or F.
    """
    passed, total = _normalize_gate_count(gates_passed, total_gates)
    if passed >= total:
        return "A+"
    ratio = passed / total
    if ratio >= 0.75:  # 3/4
        return "A"
    if ratio >= 0.50:  # 2/4
        return "B"
    if ratio >= 0.25:  # 1/4
        return "C"
    return "F"


def gates_to_score(gates_passed: int, total_gates: int = GATES_TOTAL) -> float:
    """Convert gate count to a score in [0, 1] for UCT compatibility.

    This is NOT used for verdict decisions (those use gates_to_verdict).
    Only used for UCT cache backward compatibility.
    """
    passed, total = _normalize_gate_count(gates_passed, total_gates)
    return passed / total


def select_best_strategy(
    strategies: list[dict], parent_visits: int
) -> dict | None:
    """Select strategy with highest UCT score.

    Args:
        strategies: List of strategy dicts with wins/visits fields.
        parent_visits: Total visits across all strategies.

    Returns:
        Best strategy dict, or None if empty.
    """
    if not strategies:
        return None
    return max(
        strategies,
        key=lambda s: uct_score(s.get("wins", 0), s.get("visits", 0), parent_visits),
    )
