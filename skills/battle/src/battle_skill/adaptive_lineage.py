"""Deterministic reducer + orchestration seam for Battle adaptive-lineage runs.

An adaptive-lineage qualification evolves ONE Red exploit across two descendant
generations and proves — objectively, from receipts — that the lineage is a real
adaptive search rather than a lucky single shot:

    G0                      the seed exploit (no mutation operator)
    ├── G1-A                method_replace mutation of G0
    ├── G1-B                oracle_or_parameter_mutation of G0
    │        (deterministic selection picks the stronger G1)
    └── G2                  failure_guided_crossover spawned from the selected G1

This module is PURE and DETERMINISTIC. Selection and qualification are pure
functions over "specimen receipts" (recorded Red exploits + their Judge
outcomes). The only place model/Docker work happens is inside an *injected*
``specimen_provider``; the deterministic reducers never touch the network, a
model, Docker, or Tau. Tests drive the whole seam with a ``RecordedSpecimenProvider``
built from fixtures. A separate later task (Task 5) fills in the live provider.

Receipts produced here
----------------------
``battle.candidate_fitness_receipt.v1``
    A per-candidate receipt binding a candidate to its parent via
    :func:`battle_skill.technique_signature.validate_technique_delta`, plus the
    candidate's Judge outcome and novelty distance.
``battle.lineage_selection_receipt.v1``
    The deterministic choice between G1-A and G1-B, with a full tie-break trace.
``battle.adaptive_lineage_qualification.v1``
    The fail-closed run verdict. ``status`` is PASS only when every structural
    invariant holds; otherwise FAIL with explicit ``reasons`` and a single
    authoritative ``stop_condition``.

A ``specimen`` (one Red exploit evaluated by Judge) is a plain dict with at least:

    specimen_id                 "G0" | "G1-A" | "G1-B" | "G2"
    exploit_py                  exploit source (str)
    source_sha256              sha256 of exploit_py (str; recomputed + checked)
    mutation_operator          None for G0; else a MUTATION_OPERATORS member
    technique_delta            human-readable mutation description (str)
    parent_evidence_packet_ref reference to the parent's evidence packet (str)
    judge_outcome              {vulnerable_original_confirmed: bool,
                                patched_bypass: bool,
                                duration_seconds: float}
    inputs                     (G2 only) binding fields proving G2 was spawned
                                from the selected G1 + both G1 outcomes + selection
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .technique_signature import (
    CROSSOVER_MIN_NOVELTY,
    MUTATION_OPERATORS,
    OPERATOR_DIMENSIONS,
    technique_signature,
    validate_technique_delta,
)

POLICY_ID = "battle-adaptive-lineage-qualification-v1"

CANDIDATE_FITNESS_SCHEMA = "battle.candidate_fitness_receipt.v1"
LINEAGE_SELECTION_SCHEMA = "battle.lineage_selection_receipt.v1"
QUALIFICATION_SCHEMA = "battle.adaptive_lineage_qualification.v1"
BUDGET_SCHEMA = "battle.adaptive_lineage_budget.v1"

# Canonical lineage shape. Exactly these four specimens, no more (a fifth Red
# specimen == an unauthorized "red-3" third descendant generation).
CANONICAL_SPECIMEN_IDS: tuple[str, ...] = ("G0", "G1-A", "G1-B", "G2")
DESCENDANT_IDS: tuple[str, ...] = ("G1-A", "G1-B", "G2")
G1_IDS: tuple[str, ...] = ("G1-A", "G1-B")

# Each descendant's mutation operator is fixed by the lineage design.
EXPECTED_OPERATOR: dict[str, str] = {
    "G1-A": "method_replace",
    "G1-B": "oracle_or_parameter_mutation",
    "G2": "failure_guided_crossover",
}

# Stages requested from the specimen provider, in order. G2 is requested only
# after selection, and nothing is requested after G2 (stop-after-G2).
PROVIDER_STAGES: tuple[str, ...] = ("G0", "G1-A", "G1-B", "G2")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _judge_outcome(specimen: dict[str, Any]) -> dict[str, Any]:
    outcome = specimen.get("judge_outcome") or {}
    return {
        "vulnerable_original_confirmed": bool(outcome.get("vulnerable_original_confirmed", False)),
        "patched_bypass": bool(outcome.get("patched_bypass", False)),
        "duration_seconds": float(outcome.get("duration_seconds", 0.0)),
    }


# ---------------------------------------------------------------------------
# Task 4 — budget accounting
# ---------------------------------------------------------------------------


@dataclass
class AdaptiveLineageBudget:
    """Fail-closed budget accounting for one adaptive-lineage qualification.

    Enforces the canonical envelope: <=6 primary SciLLM calls, <=8 HTTP
    completions (including JSON-repair retries), <=4 Red specimens, <=2
    descendant generations, exactly 1 fixed Blue artifact, <=1200 wall seconds,
    and no red-3 (third descendant generation). The run stops after the G2 Judge
    regardless of outcome.
    """

    max_primary_scillm_calls: int = 6
    max_http_completions: int = 8
    max_red_specimens: int = 4
    max_descendant_generations: int = 2
    fixed_blue_artifacts: int = 1
    max_seconds: float = 1200.0

    primary_scillm_calls: int = 0
    http_completions: int = 0
    red_specimens: int = 0
    descendant_generations: int = 0
    blue_artifacts: int = 0
    elapsed_seconds: float = 0.0
    g2_judge_complete: bool = False

    def record_primary_scillm_call(self, n: int = 1) -> None:
        self.primary_scillm_calls += n

    def record_http_completion(self, n: int = 1) -> None:
        self.http_completions += n

    def record_red_specimen(self, n: int = 1) -> None:
        self.red_specimens += n

    def record_descendant_generation(self, n: int = 1) -> None:
        self.descendant_generations += n

    def record_blue_artifact(self, n: int = 1) -> None:
        self.blue_artifacts += n

    def record_seconds(self, seconds: float) -> None:
        self.elapsed_seconds += float(seconds)

    def mark_g2_judge_complete(self) -> None:
        self.g2_judge_complete = True

    def overrun(self) -> tuple[bool, list[str]]:
        """Return ``(is_over, reasons)`` — True if ANY limit is exceeded."""
        reasons: list[str] = []
        if self.primary_scillm_calls > self.max_primary_scillm_calls:
            reasons.append(
                f"primary SciLLM calls {self.primary_scillm_calls} > "
                f"{self.max_primary_scillm_calls}"
            )
        if self.http_completions > self.max_http_completions:
            reasons.append(
                f"HTTP completions {self.http_completions} > {self.max_http_completions}"
            )
        if self.red_specimens > self.max_red_specimens:
            reasons.append(
                f"Red specimens {self.red_specimens} > {self.max_red_specimens} (red-3)"
            )
        if self.descendant_generations > self.max_descendant_generations:
            reasons.append(
                f"descendant generations {self.descendant_generations} > "
                f"{self.max_descendant_generations} (red-3)"
            )
        if self.blue_artifacts > self.fixed_blue_artifacts:
            reasons.append(
                f"Blue artifacts {self.blue_artifacts} != fixed {self.fixed_blue_artifacts}"
            )
        if self.elapsed_seconds > self.max_seconds:
            reasons.append(
                f"elapsed seconds {self.elapsed_seconds} > {self.max_seconds}"
            )
        return (bool(reasons), reasons)

    def to_dict(self) -> dict[str, Any]:
        over, reasons = self.overrun()
        payload = asdict(self)
        payload.update(
            {
                "schema": BUDGET_SCHEMA,
                "policy_id": POLICY_ID,
                "overrun": over,
                "overrun_reasons": reasons,
            }
        )
        return payload


# ---------------------------------------------------------------------------
# Task 1 — per-candidate fitness receipt
# ---------------------------------------------------------------------------


def build_candidate_fitness_receipt(
    parent_specimen: dict[str, Any],
    candidate_specimen: dict[str, Any],
    *,
    battle_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Build a ``battle.candidate_fitness_receipt.v1`` for one candidate.

    Runs :func:`validate_technique_delta` against the parent, embeds the delta
    receipt, and records the candidate's Judge outcome, novelty distance, and an
    overall candidate ``status`` (PASS iff the delta validation passed and the
    recorded source sha256 matches the exploit source).
    """
    parent_source = parent_specimen.get("exploit_py", "")
    child_source = candidate_specimen.get("exploit_py", "")
    operator = candidate_specimen.get("mutation_operator")

    parent_signature = technique_signature(parent_source)
    child_signature = technique_signature(child_source)
    delta = validate_technique_delta(
        parent_signature=parent_signature,
        child_signature=child_signature,
        mutation_operator=operator if isinstance(operator, str) else "",
        battle_id=battle_id,
        run_id=run_id,
    )

    computed_sha = _sha256_text(child_source)
    recorded_sha = candidate_specimen.get("source_sha256")
    sha_matches = recorded_sha is None or recorded_sha == computed_sha

    outcome = _judge_outcome(candidate_specimen)
    novelty_distance = int(delta["novelty_distance"])

    reasons: list[str] = []
    if delta["status"] != "PASS":
        reasons.append(f"technique delta validation FAILED: {delta['reasons']}")
    if not sha_matches:
        reasons.append(
            f"recorded source_sha256 {recorded_sha} != computed {computed_sha}"
        )

    status = "PASS" if (delta["status"] == "PASS" and sha_matches) else "FAIL"

    return {
        "schema": CANDIDATE_FITNESS_SCHEMA,
        "policy_id": POLICY_ID,
        "battle_id": battle_id,
        "run_id": run_id,
        "specimen_id": candidate_specimen.get("specimen_id"),
        "parent_specimen_id": parent_specimen.get("specimen_id"),
        "mutation_operator": operator,
        "technique_delta": candidate_specimen.get("technique_delta"),
        "parent_evidence_packet_ref": candidate_specimen.get("parent_evidence_packet_ref"),
        "source_sha256": computed_sha,
        "recorded_source_sha256": recorded_sha,
        "source_sha256_matches": sha_matches,
        "parent_sha256": parent_signature.get("sha256"),
        "technique_signature": child_signature,
        "delta_validation": delta,
        "delta_status": delta["status"],
        "novelty_distance": novelty_distance,
        "judge_outcome": outcome,
        "status": status,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Task 2 — deterministic lineage selection
# ---------------------------------------------------------------------------


def _selection_metrics(fitness: dict[str, Any]) -> dict[str, Any]:
    outcome = _judge_outcome(fitness)
    return {
        "specimen_id": fitness["specimen_id"],
        "vulnerable_original_confirmed": outcome["vulnerable_original_confirmed"],
        "patched_bypass": outcome["patched_bypass"],
        "novelty_distance": int(fitness.get("novelty_distance", 0)),
        "duration_seconds": outcome["duration_seconds"],
    }


# The EXACT tie-break priority (earlier criterion wins outright):
#   (a) vulnerable_original_confirmed  True beats False   -> higher wins
#   (b) patched_bypass                 True beats False   -> higher wins
#   (c) novelty_distance               greater wins       -> higher wins
#   (d) duration_seconds               lower wins         -> lower wins
#   (e) specimen_id                    lexicographically smaller wins
_SELECTION_CRITERIA: tuple[tuple[str, Callable[[dict[str, Any]], Any], str], ...] = (
    ("vulnerable_original_confirmed", lambda m: int(m["vulnerable_original_confirmed"]), "higher"),
    ("patched_bypass", lambda m: int(m["patched_bypass"]), "higher"),
    ("novelty_distance", lambda m: m["novelty_distance"], "higher"),
    ("duration_seconds", lambda m: m["duration_seconds"], "lower"),
    ("specimen_id", lambda m: m["specimen_id"], "lexicographic_smaller"),
)


def _decide(a_value: Any, b_value: Any, direction: str) -> int:
    """Return -1 if A wins, +1 if B wins, 0 if tie for one criterion."""
    if direction == "higher":
        if a_value > b_value:
            return -1
        if b_value > a_value:
            return 1
        return 0
    if direction in ("lower", "lexicographic_smaller"):
        if a_value < b_value:
            return -1
        if b_value < a_value:
            return 1
        return 0
    raise ValueError(f"unknown selection direction: {direction}")


def select_lineage(
    g1a_fitness: dict[str, Any] | None,
    g1b_fitness: dict[str, Any] | None,
    *,
    battle_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Build a ``battle.lineage_selection_receipt.v1`` (fail-closed on inputs).

    Deterministically selects the stronger of the two G1 candidates using the
    fixed tie-break order documented on ``_SELECTION_CRITERIA``. Constructible
    ONLY from BOTH G1 fitness receipts; raises ``ValueError`` if either is
    missing.
    """
    if g1a_fitness is None or g1b_fitness is None:
        raise ValueError(
            "select_lineage requires BOTH G1 fitness receipts "
            f"(g1a present={g1a_fitness is not None}, g1b present={g1b_fitness is not None})"
        )

    a = _selection_metrics(g1a_fitness)
    b = _selection_metrics(g1b_fitness)

    selection_trace: list[dict[str, Any]] = []
    winner_metrics: dict[str, Any] | None = None
    loser_metrics: dict[str, Any] | None = None
    deciding_criterion: str | None = None

    for name, key_fn, direction in _SELECTION_CRITERIA:
        a_value = key_fn(a)
        b_value = key_fn(b)
        result = _decide(a_value, b_value, direction)
        decisive = result != 0
        if result < 0:
            winner_id = a["specimen_id"]
        elif result > 0:
            winner_id = b["specimen_id"]
        else:
            winner_id = None
        selection_trace.append(
            {
                "criterion": name,
                "direction": direction,
                "a_id": a["specimen_id"],
                "a_value": a_value,
                "b_id": b["specimen_id"],
                "b_value": b_value,
                "winner": winner_id,
                "decisive": decisive,
            }
        )
        if decisive:
            deciding_criterion = name
            if result < 0:
                winner_metrics, loser_metrics = a, b
            else:
                winner_metrics, loser_metrics = b, a
            break

    if winner_metrics is None or loser_metrics is None or deciding_criterion is None:
        # Only reachable if both candidates share an identical specimen_id, which
        # violates the lineage invariant. Fail closed.
        raise ValueError(
            "lineage selection could not be decided; G1 candidates are "
            f"indistinguishable (ids {a['specimen_id']!r} vs {b['specimen_id']!r})"
        )

    return {
        "schema": LINEAGE_SELECTION_SCHEMA,
        "policy_id": POLICY_ID,
        "battle_id": battle_id,
        "run_id": run_id,
        "candidate_ids": [a["specimen_id"], b["specimen_id"]],
        "bound_g1_ids": sorted([a["specimen_id"], b["specimen_id"]]),
        "selected_id": winner_metrics["specimen_id"],
        "runner_up_id": loser_metrics["specimen_id"],
        "deciding_criterion": deciding_criterion,
        "selection_trace": selection_trace,
        "selected_metrics": winner_metrics,
        "runner_up_metrics": loser_metrics,
        "requires_both_g1_fitness": True,
    }


# ---------------------------------------------------------------------------
# Task 3 — fail-closed qualification receipt
# ---------------------------------------------------------------------------

# Fail-closed stop conditions, in the fixed priority order the reducer evaluates
# them. The first triggered condition becomes the authoritative ``stop_condition``.
STOP_CONDITIONS: tuple[str, ...] = (
    "red_3_present",
    "specimen_count_not_four",
    "invalid_mutation_contract",
    "duplicate_g1_signature",
    "g1_delta_validation_failed",
    "both_g1_failed_vulnerable_original",
    "selection_receipt_missing",
    "g2_bindings_missing",
    "g2_judge_attempt_count_invalid",
    "g2_reproduced_rejected_signature",
    "budget_overrun",
)

# Binding fields that MUST be present (and truthy) in the G2 specimen's inputs,
# proving G2 was spawned from the selected G1 + both G1 outcomes + the selection.
G2_REQUIRED_BINDINGS: tuple[str, ...] = (
    "selected_g1_id",
    "selected_g1_evidence_packet_ref",
    "g1a_outcome",
    "g1b_outcome",
    "selection_receipt_ref",
)


def _signature_dims(source: str) -> dict[str, Any]:
    return technique_signature(source)["dimensions"]


def build_qualification_receipt(
    specimens: list[dict[str, Any]],
    fitness_receipts: dict[str, dict[str, Any]],
    selection_receipt: dict[str, Any] | None,
    g2_outcome: dict[str, Any] | None,
    budget: AdaptiveLineageBudget,
    *,
    battle_id: str,
    run_id: str,
    early_stop_condition: str | None = None,
) -> dict[str, Any]:
    """Build a ``battle.adaptive_lineage_qualification.v1`` receipt, FAIL-CLOSED.

    ``status`` is PASS only when EVERY structural invariant holds; otherwise FAIL
    with explicit ``reasons`` and one authoritative ``stop_condition`` (the first
    triggered condition in :data:`STOP_CONDITIONS` order). ``early_stop_condition``
    lets the orchestrator record a stop that halted the run before G2.
    """
    by_id = {s.get("specimen_id"): s for s in specimens}
    present_ids = [s.get("specimen_id") for s in specimens]

    # Collect (condition, reason) failures. Order of insertion does not matter;
    # stop_condition is resolved via STOP_CONDITIONS priority at the end.
    failures: list[tuple[str, str]] = []
    checks: list[dict[str, Any]] = []

    def record(condition: str, ok: bool, detail: str) -> None:
        checks.append({"condition": condition, "ok": ok, "detail": detail})
        if not ok:
            failures.append((condition, detail))

    # 1. exactly 4 canonical specimens, no red-3 (no extra / non-canonical id).
    extra_ids = sorted(i for i in present_ids if i not in CANONICAL_SPECIMEN_IDS)
    missing_ids = [i for i in CANONICAL_SPECIMEN_IDS if i not in present_ids]
    record(
        "red_3_present",
        not extra_ids,
        "no red-3 / extra specimens" if not extra_ids else f"unauthorized specimens present: {extra_ids}",
    )
    record(
        "specimen_count_not_four",
        len(present_ids) == 4 and not missing_ids and len(set(present_ids)) == 4,
        f"specimens present: {sorted(str(i) for i in present_ids)}"
        if (len(present_ids) == 4 and not missing_ids and len(set(present_ids)) == 4)
        else f"expected exactly {CANONICAL_SPECIMEN_IDS}, got {sorted(str(i) for i in present_ids)}",
    )

    # 2. each descendant has a valid mutation contract.
    contract_problems: list[str] = []
    for did in DESCENDANT_IDS:
        spec = by_id.get(did)
        if spec is None:
            contract_problems.append(f"{did}: missing")
            continue
        operator = spec.get("mutation_operator")
        if operator not in MUTATION_OPERATORS:
            contract_problems.append(f"{did}: operator {operator!r} not in vocabulary")
        elif operator != EXPECTED_OPERATOR[did]:
            contract_problems.append(
                f"{did}: operator {operator!r} != expected {EXPECTED_OPERATOR[did]!r}"
            )
        if not (spec.get("technique_delta") or "").strip():
            contract_problems.append(f"{did}: empty technique_delta")
        if not spec.get("parent_evidence_packet_ref"):
            contract_problems.append(f"{did}: missing parent_evidence_packet_ref")
    record(
        "invalid_mutation_contract",
        not contract_problems,
        "all descendant mutation contracts valid" if not contract_problems else "; ".join(contract_problems),
    )

    # 3. G1-A and G1-B have DIFFERENT technique signatures.
    g1a, g1b = by_id.get("G1-A"), by_id.get("G1-B")
    if g1a is not None and g1b is not None:
        dims_a = _signature_dims(g1a.get("exploit_py", ""))
        dims_b = _signature_dims(g1b.get("exploit_py", ""))
        distinct = dims_a != dims_b
        record(
            "duplicate_g1_signature",
            distinct,
            "G1-A and G1-B signatures differ" if distinct else f"G1-A and G1-B share signature {dims_a}",
        )
    else:
        record("duplicate_g1_signature", False, "cannot compare G1 signatures; a G1 specimen is missing")

    # 4. both G1 candidates' delta validations passed.
    delta_problems: list[str] = []
    for gid in G1_IDS:
        fit = fitness_receipts.get(gid)
        if fit is None:
            delta_problems.append(f"{gid}: missing fitness receipt")
        elif fit.get("delta_status") != "PASS":
            delta_problems.append(f"{gid}: delta_status={fit.get('delta_status')}")
    record(
        "g1_delta_validation_failed",
        not delta_problems,
        "both G1 delta validations passed" if not delta_problems else "; ".join(delta_problems),
    )

    # 5. NOT both G1 candidates failed the vulnerable original.
    g1a_vuln = _judge_outcome(g1a)["vulnerable_original_confirmed"] if g1a else False
    g1b_vuln = _judge_outcome(g1b)["vulnerable_original_confirmed"] if g1b else False
    both_failed = (not g1a_vuln) and (not g1b_vuln)
    record(
        "both_g1_failed_vulnerable_original",
        not both_failed,
        "at least one G1 confirmed the vulnerable original"
        if not both_failed
        else "both G1 candidates failed to confirm the vulnerable original",
    )

    # 6. selection receipt present and built from BOTH G1 Judge receipts.
    selection_ok = (
        selection_receipt is not None
        and selection_receipt.get("schema") == LINEAGE_SELECTION_SCHEMA
        and sorted(selection_receipt.get("bound_g1_ids") or []) == sorted(G1_IDS)
    )
    record(
        "selection_receipt_missing",
        selection_ok,
        "selection receipt present and bound to both G1 receipts"
        if selection_ok
        else f"selection receipt missing or not bound to both G1s: {selection_receipt is not None}",
    )

    # 7. G2 bindings present + exactly one G2 Judge attempt.
    g2 = by_id.get("G2")
    g2_inputs = (g2 or {}).get("inputs") or {}
    missing_bindings = [k for k in G2_REQUIRED_BINDINGS if not g2_inputs.get(k)]
    selected_id = selection_receipt.get("selected_id") if selection_receipt else None
    binding_mismatch = (
        selected_id is not None and g2_inputs.get("selected_g1_id") != selected_id
    )
    bindings_ok = not missing_bindings and not binding_mismatch
    record(
        "g2_bindings_missing",
        bindings_ok,
        "G2 bound to selected-G1 evidence, both G1 outcomes, and selection receipt"
        if bindings_ok
        else f"missing G2 bindings {missing_bindings}"
        + (f"; selected_g1_id {g2_inputs.get('selected_g1_id')!r} != selected {selected_id!r}" if binding_mismatch else ""),
    )

    g2_attempts = (g2_outcome or {}).get("judge_attempts")
    attempts_ok = g2_attempts == 1
    record(
        "g2_judge_attempt_count_invalid",
        attempts_ok,
        "exactly one G2 Judge attempt ran" if attempts_ok else f"G2 judge_attempts={g2_attempts} (must be exactly 1)",
    )

    # 8. G2 did not reproduce a previously-rejected (runner-up G1) signature.
    reproduced = False
    reproduce_detail = "G2 signature differs from the rejected G1 signature"
    if selection_receipt is not None and g2 is not None:
        runner_up_id = selection_receipt.get("runner_up_id")
        runner_up = by_id.get(runner_up_id)
        if runner_up is not None:
            g2_dims = _signature_dims(g2.get("exploit_py", ""))
            rejected_dims = _signature_dims(runner_up.get("exploit_py", ""))
            reproduced = g2_dims == rejected_dims
            if reproduced:
                reproduce_detail = (
                    f"G2 reproduced the rejected {runner_up_id} signature {rejected_dims}"
                )
    record("g2_reproduced_rejected_signature", not reproduced, reproduce_detail)

    # 9. budgets not exceeded.
    over, overrun_reasons = budget.overrun()
    record(
        "budget_overrun",
        not over,
        "budget within envelope" if not over else "; ".join(overrun_reasons),
    )

    # Resolve the authoritative stop_condition by fixed priority.
    failed_conditions = {cond for cond, _ in failures}
    stop_condition: str | None = early_stop_condition
    if stop_condition is None:
        for cond in STOP_CONDITIONS:
            if cond in failed_conditions:
                stop_condition = cond
                break
    reasons = [detail for _, detail in failures]
    if early_stop_condition is not None:
        reasons = [f"run halted early: {early_stop_condition}"] + reasons

    status = "PASS" if (not failures and early_stop_condition is None) else "FAIL"

    return {
        "schema": QUALIFICATION_SCHEMA,
        "policy_id": POLICY_ID,
        "battle_id": battle_id,
        "run_id": run_id,
        "status": status,
        "stop_condition": stop_condition,
        "reasons": reasons,
        "checks": checks,
        "specimen_ids": [str(i) for i in present_ids],
        "selected_id": selected_id,
        "runner_up_id": selection_receipt.get("runner_up_id") if selection_receipt else None,
        "selection_receipt": selection_receipt,
        "g2_outcome": g2_outcome,
        "budget": budget.to_dict(),
    }


# ---------------------------------------------------------------------------
# Task 5 — orchestration seam + specimen providers
# ---------------------------------------------------------------------------


def _request_specimen(
    provider: Any, *, stage: str, context: dict[str, Any]
) -> dict[str, Any]:
    """Call the injected provider for one stage.

    Accepts either an object with a ``request(*, stage, context)`` method or a
    plain callable ``provider(stage=..., context=...)``. This is the ONLY seam
    through which model/Docker work enters the run.
    """
    if hasattr(provider, "request"):
        specimen = provider.request(stage=stage, context=context)
    elif callable(provider):
        specimen = provider(stage=stage, context=context)
    else:
        raise TypeError(
            "specimen_provider must be callable or expose a request(stage, context) method"
        )
    if not isinstance(specimen, dict):
        raise TypeError(f"specimen provider returned {type(specimen)!r} for stage {stage!r}")
    return specimen


class RecordedSpecimenProvider:
    """Deterministic provider that replays specimens recorded from fixtures.

    Built from a mapping of ``stage -> specimen`` (or ``stage -> callable``). It
    records every stage requested in ``requested_stages`` so tests can prove that
    the orchestration never asks for a 5th specimen (stop-after-G2). Requesting a
    stage that was not recorded fails closed.
    """

    def __init__(self, specimens_by_stage: dict[str, Any]) -> None:
        self._by_stage = dict(specimens_by_stage)
        self.requested_stages: list[str] = []
        self.request_contexts: list[dict[str, Any]] = []

    def request(self, *, stage: str, context: dict[str, Any]) -> dict[str, Any]:
        self.requested_stages.append(stage)
        self.request_contexts.append(context)
        if stage not in self._by_stage:
            raise KeyError(f"RecordedSpecimenProvider has no recorded specimen for stage {stage!r}")
        entry = self._by_stage[stage]
        specimen = entry(stage=stage, context=context) if callable(entry) else entry
        return dict(specimen)


def _operator_guidance(operator: str) -> str:
    """Plain-language mutation guidance for one operator, derived from the AST
    dimensions the validator (:data:`OPERATOR_DIMENSIONS`) requires that operator
    to move.

    This STEERS the descendant generator toward the right AST dimensions. It does
    NOT weaken or bypass the AST validator — the generated exploit is still checked
    by :func:`validate_technique_delta`.
    """
    allowed = ", ".join(sorted(OPERATOR_DIMENSIONS.get(operator, frozenset())))
    if operator == "method_replace":
        return (
            "MUTATION OPERATOR method_replace: make a STRUCTURAL change to HOW app.py "
            "is loaded (the app_load_mode dimension). Concretely, if the parent uses "
            "`from app import import_zip`, instead load the module dynamically, e.g. "
            "`import importlib; module = importlib.import_module('app'); "
            "import_zip = getattr(module, 'import_zip')`, OR "
            "`spec = importlib.util.spec_from_file_location('app', 'app.py'); "
            "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)`. "
            "Keep the archive construction, traversal path, and success oracle "
            "IDENTICAL to the parent. Do NOT merely wrap the call in a helper "
            "function or rename variables — that is NOT a method replacement and will "
            f"be rejected. Allowed dimensions: {allowed}."
        )
    if operator == "oracle_or_parameter_mutation":
        return (
            "MUTATION OPERATOR oracle_or_parameter_mutation: make a STRUCTURAL change "
            "to HOW the malicious archive entry is constructed (the "
            "archive_entry_construction dimension). Concretely, if the parent uses "
            "`zf.writestr('../x', data)`, instead write a real file through an "
            "explicit arcname, e.g. `zf.write(real_path, arcname='../x')` or build a "
            "`zipfile.ZipInfo('../x')` and pass it to writestr. Alternatively change "
            "the traversal KIND (e.g. an absolute-path entry or a symlink entry) — "
            "but do NOT merely deepen the traversal (`../` to `../../`), which is a "
            "cosmetic parameter tweak and will be rejected. Keep the app load mode "
            f"IDENTICAL to the parent. Allowed dimensions: {allowed}."
        )
    if operator == "failure_guided_crossover":
        return (
            "MUTATION OPERATOR failure_guided_crossover: combine the parent "
            f"lineage's signals and make STRUCTURAL changes to at least "
            f"{CROSSOVER_MIN_NOVELTY} of these dimensions: app_load_mode (dynamic "
            "importlib load), archive_entry_construction (ZipInfo / write+arcname), "
            "success_oracle (read-back vs existence vs printed marker), "
            "target_call_form. Use the concrete techniques from the method_replace "
            "and oracle_or_parameter_mutation operators. Cosmetic tweaks (renaming, "
            f"deeper `../`, wrapper functions) do not count toward the "
            f"{CROSSOVER_MIN_NOVELTY} required dimensions."
        )
    return f"MUTATION OPERATOR {operator}: produce a genuinely novel technique."


class LiveTauSpecimenProvider:
    """LIVE provider seam — materializes each lineage stage through Tau + Judge.

    For each requested stage :meth:`request`:

      1. Assembles the parent evidence packet for the requested descendant (the
         ``context`` carries the parent specimen and, for G2, the selection
         receipt + both G1 outcomes) plus operator-specific mutation guidance, and
         writes them into the ``--battle-context-json`` handed to Tau so the
         descendant prompt embeds ``battle.parent_evidence_packet.v1`` and steers
         toward the AST dimensions the operator requires.
      2. Subprocesses into Tau's public-only handoff bridge exactly as
         ``arena_live_battle_proof`` does: ``_run_tau_harness`` for the G0 seed
         (materializes Red red-0 + the single fixed Blue artifact) and
         ``_run_tau_spawn_child`` for each descendant (spawned WITH the parent's
         Tau subagent receipt). ``cwd=arena_live_battle_proof.TAU_REPO``.
      3. Judge-replays the materialized Red exploit against the fixed Blue artifact
         in Docker via ``arena_live_battle_proof._judge_pair`` and reads
         ``exploit_confirmed_before_patch`` -> ``vulnerable_original_confirmed``,
         ``exploit_still_succeeds_after_patch`` -> ``patched_bypass``, and
         ``duration_elapsed_seconds`` -> ``duration_seconds``.
      4. Returns a specimen dict in the shape documented in this module's header
         (for G2, ``inputs`` carries every field in :data:`G2_REQUIRED_BINDINGS`),
         recording SciLLM/HTTP/second/generation usage on the shared budget.

    ``live_config`` (via ``__init__``) supplies the arena that the orchestrator
    prepared once up front: ``out_dir``, ``battle_id``, ``run_id``, ``scenario_id``,
    ``scenario`` (for the Judge), ``context_path`` (the public Tau context),
    ``docker_image``, ``model``, ``scillm_base_url``, ``red_persona``,
    ``blue_persona``, ``timeout_s``, and the shared ``budget``. Exploit source bytes
    and their sha256 are preserved verbatim — generated exploit code is never
    rewritten.
    """

    def __init__(self, **live_config: Any) -> None:
        self._live_config = live_config
        # Per-stage materialization state keyed by specimen_id, so a descendant
        # can inherit its parent's Tau subagent receipt + evidence-packet ref.
        self._materialized: dict[str, dict[str, Any]] = {}
        # The single fixed Blue artifact, materialized once during G0 and reused.
        self._blue_entry: dict[str, Any] | None = None

    # -- config helpers ---------------------------------------------------
    def _cfg(self, key: str, default: Any = None) -> Any:
        value = self._live_config.get(key, default)
        return default if value is None else value

    def _require(self, key: str) -> Any:
        value = self._live_config.get(key)
        if value is None:
            raise ValueError(
                f"LiveTauSpecimenProvider requires live_config[{key!r}] for a live run"
            )
        return value

    def _budget(self, context: dict[str, Any]) -> AdaptiveLineageBudget | None:
        return context.get("budget") or self._live_config.get("budget")

    def _evidence_packet_ref(self, specimen_id: str) -> str:
        return f"{self._cfg('run_id', 'run')}:battle.parent_evidence_packet.v1:{specimen_id}"

    # -- public seam ------------------------------------------------------
    def request(self, *, stage: str, context: dict[str, Any]) -> dict[str, Any]:
        if stage not in PROVIDER_STAGES:
            raise ValueError(f"unknown stage {stage!r}; expected one of {PROVIDER_STAGES}")
        if stage == "G0":
            return self._materialize_g0(context)
        return self._materialize_descendant(stage=stage, context=context)

    # -- materialization --------------------------------------------------
    def _materialize_g0(self, context: dict[str, Any]) -> dict[str, Any]:
        from . import arena_live_battle_proof as alb

        out_dir = Path(self._require("out_dir")).resolve()
        stage_dir = out_dir / "stage-G0"
        stage_dir.mkdir(parents=True, exist_ok=True)
        budget = self._budget(context)

        manifest_path = alb._run_tau_harness(
            out_dir=stage_dir,
            battle_id=self._require("battle_id"),
            run_id=self._require("run_id"),
            scenario_id=self._require("scenario_id"),
            context_path=Path(self._require("context_path")),
            red_persona=self._cfg("red_persona", "battle-red-public-auditor"),
            blue_persona=self._cfg("blue_persona", "battle-blue-public-hardener"),
            model=self._cfg("model", "gpt-5.5"),
            scillm_base_url=self._cfg("scillm_base_url", "http://localhost:4001"),
            timeout_s=float(self._cfg("timeout_s", 900.0)),
            red_workers=int(self._cfg("red_workers", 1)),
            blue_workers=int(self._cfg("blue_workers", 1)),
        )
        if budget is not None:
            budget.record_primary_scillm_call()
            budget.record_http_completion()

        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        red_entries = alb._materialized_entries(manifest, "red")
        blue_entries = alb._materialized_entries(manifest, "blue")
        if not red_entries or not blue_entries:
            raise RuntimeError("Tau G0 handoff produced no Red/Blue materialized artifacts")
        red = next(
            (e for e in red_entries if e.get("worker_id") == "red-0"),
            red_entries[0],
        )
        self._blue_entry = blue_entries[0]

        exploit_py, source_sha256, _declared_op, _declared_delta = self._extract_red(red)
        judge = self._judge(
            stage="G0", red_entry=red, blue_entry=self._blue_entry, out_dir=out_dir, budget=budget
        )

        specimen: dict[str, Any] = {
            "specimen_id": "G0",
            "exploit_py": exploit_py,
            "source_sha256": source_sha256,
            "mutation_operator": None,
            "technique_delta": "seed exploit (no mutation operator)",
            "parent_evidence_packet_ref": None,
            "judge_outcome": judge,
            "judge_attempts": 1,
        }
        self._materialized["G0"] = {
            "entry": red,
            "subagent_receipt": red.get("subagent_receipt"),
            "manifest_path": str(manifest_path),
            "specimen": specimen,
            "evidence_packet_ref": self._evidence_packet_ref("G0"),
        }
        return specimen

    def _materialize_descendant(self, *, stage: str, context: dict[str, Any]) -> dict[str, Any]:
        from . import arena_live_battle_proof as alb

        out_dir = Path(self._require("out_dir")).resolve()
        stage_dir = out_dir / f"stage-{stage}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        budget = self._budget(context)
        operator = EXPECTED_OPERATOR[stage]

        if self._blue_entry is None:
            raise RuntimeError(
                "descendant requested before G0 materialized the fixed Blue artifact"
            )

        parent_specimen = context.get("parent_specimen") or {}
        parent_id = parent_specimen.get("specimen_id")
        parent_state = self._materialized.get(parent_id) or {}
        parent_receipt = parent_state.get("subagent_receipt") or parent_specimen.get(
            "parent_subagent_receipt"
        )

        # 1. augmented battle context: parent evidence packet + operator steering.
        aug_context_path = self._write_descendant_context(
            stage=stage,
            stage_dir=stage_dir,
            operator=operator,
            parent_specimen=parent_specimen,
            context=context,
        )

        # 2. spawn the descendant WITH the inherited parent Tau subagent receipt.
        spawn_manifest_path = alb._run_tau_spawn_child(
            out_dir=stage_dir,
            battle_id=self._require("battle_id"),
            run_id=self._require("run_id"),
            scenario_id=self._require("scenario_id"),
            context_path=aug_context_path,
            parent_subagent_receipt=(
                Path(parent_receipt)
                if parent_receipt
                else stage_dir / "missing-parent-subagent-receipt.json"
            ),
            red_persona=self._cfg("red_persona", "battle-red-public-auditor"),
            model=self._cfg("model", "gpt-5.5"),
            scillm_base_url=self._cfg("scillm_base_url", "http://localhost:4001"),
            timeout_s=float(self._cfg("timeout_s", 900.0)),
        )
        if budget is not None:
            budget.record_primary_scillm_call()
            budget.record_http_completion()
            # Generation accounting is owned by the orchestrator
            # (run_adaptive_lineage_qualification): generation 1 = the G1 pair,
            # generation 2 = G2. The provider must not also count per-descendant.
        if spawn_manifest_path is None:
            raise RuntimeError(f"Tau spawn for {stage} did not produce a manifest")

        manifest = json.loads(Path(spawn_manifest_path).read_text(encoding="utf-8"))
        red_entries = alb._materialized_entries(manifest, "red")
        if not red_entries:
            raise RuntimeError(f"Tau spawn for {stage} produced no Red materialized artifact")
        child = red_entries[-1]
        exploit_py, source_sha256, _declared_op, declared_delta = self._extract_red(child)

        judge = self._judge(
            stage=stage, red_entry=child, blue_entry=self._blue_entry, out_dir=out_dir, budget=budget
        )

        specimen = {
            "specimen_id": stage,
            "exploit_py": exploit_py,
            "source_sha256": source_sha256,
            "mutation_operator": operator,
            "technique_delta": declared_delta or f"{operator} mutation of {parent_id}",
            "parent_evidence_packet_ref": parent_state.get("evidence_packet_ref")
            or self._evidence_packet_ref(parent_id or "G0"),
            "judge_outcome": judge,
            "judge_attempts": 1,
        }
        if stage == "G2":
            specimen["inputs"] = self._g2_bindings(context=context)

        self._materialized[stage] = {
            "entry": child,
            "subagent_receipt": child.get("subagent_receipt"),
            "manifest_path": str(spawn_manifest_path),
            "specimen": specimen,
            "evidence_packet_ref": self._evidence_packet_ref(stage),
        }
        if stage == "G2" and budget is not None:
            budget.mark_g2_judge_complete()
        return specimen

    # -- extraction + judge -----------------------------------------------
    def _extract_red(self, entry: dict[str, Any]) -> tuple[str, str, Any, str]:
        """Return ``(exploit_py, source_sha256, mutation_operator, technique_delta)``.

        Reads the exploit source bytes verbatim from the materialized artifact path
        and recomputes the sha256 over them (never rewritten). ``mutation_operator``
        and ``technique_delta`` are the model-declared values Tau's Task-1 contract
        embeds in the materialized entry.
        """
        exploit_py = Path(entry["path"]).read_text(encoding="utf-8")
        source_sha256 = _sha256_text(exploit_py)
        materialized = entry.get("materialized")
        materialized = materialized if isinstance(materialized, dict) else {}
        mutation_operator = materialized.get("mutation_operator")
        technique_delta = (materialized.get("technique_delta") or "").strip()
        return exploit_py, source_sha256, mutation_operator, technique_delta

    def _judge(
        self,
        *,
        stage: str,
        red_entry: dict[str, Any],
        blue_entry: dict[str, Any],
        out_dir: Path,
        budget: AdaptiveLineageBudget | None,
    ) -> dict[str, Any]:
        from . import arena_live_battle_proof as alb

        judge_red = dict(red_entry)
        if stage != "G0":
            # Descendants all spawn as red-1; make the Judge replay dir stage-unique.
            judge_red["worker_id"] = f"{red_entry.get('worker_id', 'red-1')}-{stage}"
        attempt = alb._judge_pair(
            out_dir=out_dir,
            scenario=self._require("scenario"),
            docker_image=self._cfg("docker_image", "python:3.12-slim"),
            red=judge_red,
            blue=blue_entry,
            timing_origin=self._live_config.get("timing_origin"),
        )
        duration = float(
            attempt.get("duration_elapsed_seconds")
            or attempt.get("duration_seconds")
            or 0.0
        )
        if budget is not None:
            budget.record_seconds(duration)
        return {
            "vulnerable_original_confirmed": bool(
                attempt.get("exploit_confirmed_before_patch", False)
            ),
            "patched_bypass": bool(attempt.get("exploit_still_succeeds_after_patch", False)),
            "duration_seconds": duration,
        }

    # -- context assembly -------------------------------------------------
    def _write_descendant_context(
        self,
        *,
        stage: str,
        stage_dir: Path,
        operator: str,
        parent_specimen: dict[str, Any],
        context: dict[str, Any],
    ) -> Path:
        base_context: dict[str, Any] = {}
        base_path = self._live_config.get("context_path")
        if base_path and Path(base_path).exists():
            base_context = json.loads(Path(base_path).read_text(encoding="utf-8"))

        guidance = _operator_guidance(operator)
        packet = {
            "schema": "battle.parent_evidence_packet.v1",
            "packet_ref": self._evidence_packet_ref(
                parent_specimen.get("specimen_id") or "G0"
            ),
            "parent_specimen_id": parent_specimen.get("specimen_id"),
            "parent_source_sha256": parent_specimen.get("source_sha256"),
            "parent_mutation_operator": parent_specimen.get("mutation_operator"),
            "parent_technique_delta": parent_specimen.get("technique_delta"),
            "parent_judge_outcome": parent_specimen.get("judge_outcome"),
            "descendant_stage": stage,
            "descendant_mutation_operator": operator,
            "operator_guidance": guidance,
        }
        if stage == "G2":
            packet["selection_receipt"] = context.get("selection_receipt")
            packet["g1a_outcome"] = context.get("g1a_outcome")
            packet["g1b_outcome"] = context.get("g1b_outcome")

        augmented = dict(base_context)
        augmented["battle.parent_evidence_packet.v1"] = packet
        augmented["mutation_guidance"] = {
            "stage": stage,
            "mutation_operator": operator,
            "operator_guidance": guidance,
            "allowed_dimensions": sorted(OPERATOR_DIMENSIONS.get(operator, frozenset())),
            "min_changed_dimensions": (
                CROSSOVER_MIN_NOVELTY if operator == "failure_guided_crossover" else 1
            ),
        }

        path = stage_dir / f"battle-context-{stage}.json"
        path.write_text(json.dumps(augmented, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _g2_bindings(self, *, context: dict[str, Any]) -> dict[str, Any]:
        selection = context.get("selection_receipt") or {}
        selected_id = selection.get("selected_id")
        selected_state = self._materialized.get(selected_id) or {}
        return {
            "selected_g1_id": selected_id,
            "selected_g1_evidence_packet_ref": selected_state.get("evidence_packet_ref")
            or self._evidence_packet_ref(selected_id or "G1-A"),
            "g1a_outcome": context.get("g1a_outcome"),
            "g1b_outcome": context.get("g1b_outcome"),
            "selection_receipt_ref": selection.get("receipt_id")
            or f"{self._cfg('run_id', 'run')}-lineage-selection",
        }


def run_adaptive_lineage_qualification(
    specimen_provider: Any,
    *,
    battle_id: str,
    run_id: str,
    out_dir: Path,
    budget: AdaptiveLineageBudget | None = None,
) -> dict[str, Any]:
    """Orchestration seam for one adaptive-lineage qualification.

    Requests specimens IN ORDER from ``specimen_provider`` (G0, then G1-A, G1-B,
    then — given the deterministic selection — G2), runs the pure reducers, writes
    every receipt to ``out_dir``, and returns the ``battle.adaptive_lineage_qualification.v1``
    receipt whose ``status`` is authoritative for the run.

    Fail-closed stops (a pre-G2 structural violation) halt the run before G2 is
    ever requested, and no specimen is ever requested after G2 (stop-after-G2).
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    budget = budget or AdaptiveLineageBudget()

    receipts_dir = out_dir / "receipts"

    # --- G0 seed ---------------------------------------------------------
    g0 = _request_specimen(specimen_provider, stage="G0", context={})
    budget.record_red_specimen()
    budget.record_blue_artifact()  # the single fixed Blue artifact for the run
    _write_json(receipts_dir / "specimen-G0.json", g0)

    # --- G1 descendant generation ---------------------------------------
    g1a = _request_specimen(
        specimen_provider, stage="G1-A", context={"parent_specimen": g0}
    )
    budget.record_red_specimen()
    g1b = _request_specimen(
        specimen_provider, stage="G1-B", context={"parent_specimen": g0}
    )
    budget.record_red_specimen()
    budget.record_descendant_generation()  # generation 1 (G1-A + G1-B)
    _write_json(receipts_dir / "specimen-G1-A.json", g1a)
    _write_json(receipts_dir / "specimen-G1-B.json", g1b)

    g1a_fitness = build_candidate_fitness_receipt(g0, g1a, battle_id=battle_id, run_id=run_id)
    g1b_fitness = build_candidate_fitness_receipt(g0, g1b, battle_id=battle_id, run_id=run_id)
    _write_json(receipts_dir / "fitness-G1-A.json", g1a_fitness)
    _write_json(receipts_dir / "fitness-G1-B.json", g1b_fitness)

    selection_receipt = select_lineage(
        g1a_fitness, g1b_fitness, battle_id=battle_id, run_id=run_id
    )
    _write_json(receipts_dir / "lineage-selection.json", selection_receipt)

    fitness_receipts = {"G1-A": g1a_fitness, "G1-B": g1b_fitness}

    # --- Pre-G2 fail-closed gate: halt provider calls before spawning G2 -
    early_stop = _pre_g2_stop_condition(
        g1a=g1a,
        g1b=g1b,
        g1a_fitness=g1a_fitness,
        g1b_fitness=g1b_fitness,
    )
    if early_stop is not None:
        qualification = build_qualification_receipt(
            [g0, g1a, g1b],
            fitness_receipts,
            selection_receipt,
            None,
            budget,
            battle_id=battle_id,
            run_id=run_id,
            early_stop_condition=early_stop,
        )
        _write_json(out_dir / "adaptive-lineage-qualification.json", qualification)
        return qualification

    # --- G2 crossover from the selected G1 ------------------------------
    selected_id = selection_receipt["selected_id"]
    selected_specimen = g1a if selected_id == "G1-A" else g1b
    g2_context = {
        "parent_specimen": selected_specimen,
        "selection_receipt": selection_receipt,
        "g1a_outcome": _judge_outcome(g1a),
        "g1b_outcome": _judge_outcome(g1b),
    }
    g2 = _request_specimen(specimen_provider, stage="G2", context=g2_context)
    budget.record_red_specimen()
    budget.record_descendant_generation()  # generation 2 (G2)
    budget.mark_g2_judge_complete()  # stop-after-G2: no further provider calls
    _write_json(receipts_dir / "specimen-G2.json", g2)

    g2_fitness = build_candidate_fitness_receipt(
        selected_specimen, g2, battle_id=battle_id, run_id=run_id
    )
    _write_json(receipts_dir / "fitness-G2.json", g2_fitness)
    fitness_receipts["G2"] = g2_fitness

    g2_outcome = {
        "judge_attempts": int(g2.get("judge_attempts", 1)),
        **_judge_outcome(g2),
        "technique_signature": g2_fitness["technique_signature"],
    }

    qualification = build_qualification_receipt(
        [g0, g1a, g1b, g2],
        fitness_receipts,
        selection_receipt,
        g2_outcome,
        budget,
        battle_id=battle_id,
        run_id=run_id,
    )
    _write_json(out_dir / "adaptive-lineage-qualification.json", qualification)
    return qualification


def _pre_g2_stop_condition(
    *,
    g1a: dict[str, Any],
    g1b: dict[str, Any],
    g1a_fitness: dict[str, Any],
    g1b_fitness: dict[str, Any],
) -> str | None:
    """Return a stop_condition if a G1-level invariant is already violated.

    These are the fail-closed conditions detectable BEFORE G2 is spawned. When
    any triggers, the orchestration halts and never asks the provider for G2.
    """
    if g1a_fitness.get("delta_status") != "PASS" or g1b_fitness.get("delta_status") != "PASS":
        return "g1_delta_validation_failed"
    if _signature_dims(g1a.get("exploit_py", "")) == _signature_dims(g1b.get("exploit_py", "")):
        return "duplicate_g1_signature"
    a_vuln = _judge_outcome(g1a)["vulnerable_original_confirmed"]
    b_vuln = _judge_outcome(g1b)["vulnerable_original_confirmed"]
    if not a_vuln and not b_vuln:
        return "both_g1_failed_vulnerable_original"
    return None
