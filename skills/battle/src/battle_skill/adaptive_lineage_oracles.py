"""Concrete fitness oracles and live role wiring for Battle adaptive lineages.

Round 2 supplies the universal engine, daemon-backed memory hooks, and adapters for
Battle's verified population/review/Judge primitives. This module adds the five
role-specific fitness rules without changing that engine:

* Red survives only on a Judge ``RED_SUCCESS`` verdict.
* Blue survives only on a Judge ``BLUE_SUCCESS`` verdict.
* Judge methodologies survive only with repeated real replay, deterministic and
  replay-consistent verdicts, and explicit non-gameability.
* Research findings survive only when receipt-bound evidence shows that the
  finding led to a selected specimen; dead ends are retained through /memory.
* Arena candidates survive only when past decisive games were sufficiently even;
  an all-``INSUFFICIENT_EVIDENCE`` arena is degenerate and cannot survive.

Every oracle independently validates the role/public recall boundary before
examining fitness. The real runtime factory composes ``MemoryBackend`` with
``VerifiedPopulationHooks``. Arena creation is deliberately left behind a clean
Tau creator-reviewer DAG protocol; this round does not implement the DAG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .adaptive_lineage_engine import (
    AdaptiveLineageContractError,
    AdaptiveLineageEngine,
    FitnessOracle,
    GenerationRequest,
    JudgedPopulation,
    OracleSelection,
    PopulationHooks,
    PopulationStageResult,
    RecallResult,
    candidate_id,
    canonical_sha256,
    json_safe,
)
from .adaptive_lineage_memory import (
    MEMORY_COLLECTION,
    MEMORY_NODE_SCHEMA,
    MemoryBackend,
    RoleMemoryScope,
)
from .adaptive_lineage_verified_primitives import (
    VerifiedPopulationHooks,
    load_verified_primitive_bundle,
)

ROLE_RED = "red"
ROLE_BLUE = "blue"
ROLE_JUDGE = "judge"
ROLE_RESEARCHER = "researcher"
ROLE_ARENA_CREATOR = "arena-creator"
CONCRETE_ROLES = (
    ROLE_ARENA_CREATOR,
    ROLE_RED,
    ROLE_BLUE,
    ROLE_JUDGE,
    ROLE_RESEARCHER,
)

RED_SUCCESS = "RED_SUCCESS"
BLUE_SUCCESS = "BLUE_SUCCESS"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _nested_mappings(item: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    mappings: list[Mapping[str, Any]] = [item]
    for key in (
        "judge",
        "judge_outcome",
        "replay",
        "replay_evidence",
        "methodology_evidence",
        "soundness_evidence",
        "usefulness_evidence",
        "balance_evidence",
        "evidence",
    ):
        value = item.get(key)
        if isinstance(value, Mapping):
            mappings.append(value)
    return tuple(mappings)


def _first_value(item: Mapping[str, Any], *keys: str) -> Any:
    for mapping in _nested_mappings(item):
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
    return None


def _bool_value(item: Mapping[str, Any], *keys: str) -> bool:
    value = _first_value(item, *keys)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "passed"}
    return bool(value)


def _int_value(item: Mapping[str, Any], *keys: str) -> int:
    value = _first_value(item, *keys)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(item: Mapping[str, Any], *keys: str) -> float:
    value = _first_value(item, *keys)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _verdict(item: Mapping[str, Any]) -> str:
    value = _first_value(
        item,
        "judge_verdict",
        "verdict",
        "outcome",
        "result",
    )
    return str(value or "").strip().upper()


def _stable_best(
    items: Sequence[Mapping[str, Any]],
    *,
    score: Any | None = None,
) -> Mapping[str, Any] | None:
    if not items:
        return None
    score = score or (lambda _item: ())
    return sorted(
        items,
        key=lambda item: (
            tuple(-float(value) for value in score(item)),
            candidate_id(item),
        ),
    )[0]


def _bad_record(
    item: Mapping[str, Any],
    *,
    oracle_id: str,
    reason_codes: Sequence[str],
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "specimen_id": candidate_id(item),
        "source": oracle_id,
        "reason_codes": sorted(set(str(reason) for reason in reason_codes)),
        "evidence": json_safe(evidence or {}),
    }


def _selection(
    *,
    oracle_id: str,
    population: JudgedPopulation,
    survivor: Mapping[str, Any] | None,
    reasons: Mapping[str, Sequence[str]],
    evidence: Mapping[str, Any],
) -> OracleSelection:
    survivor_id = candidate_id(survivor) if survivor is not None else None
    bad = []
    for item in population.judged.items:
        identifier = candidate_id(item)
        if identifier == survivor_id:
            continue
        reason_codes = reasons.get(identifier) or (
            "not_selected_by_oracle",
        )
        bad.append(
            _bad_record(
                item,
                oracle_id=oracle_id,
                reason_codes=reason_codes,
                evidence={"judge_verdict": _verdict(item)},
            )
        )
    return OracleSelection(
        survivor=survivor,
        bad_genetic_material={
            "schema": "battle.role_oracle_bad_genetic_material.v1",
            "oracle_id": oracle_id,
            "specimens": bad,
        },
        evidence=json_safe(evidence),
        oracle_id=oracle_id,
    )


def _validate_role_recall(
    *,
    expected_role: str,
    request: GenerationRequest,
    recall: RecallResult,
) -> None:
    if request.role != expected_role:
        raise AdaptiveLineageContractError(
            f"{expected_role} oracle cannot evaluate role {request.role!r}"
        )
    allowed_private = f"battle:{request.battle_id}:role:{expected_role}"
    allowed_public = f"battle:{request.battle_id}:public"
    for document in recall.documents:
        scope = str(document.get("scope") or document.get("scope_id") or "")
        tags = {str(tag) for tag in document.get("tags") or []}
        if scope == allowed_public:
            continue
        if scope != allowed_private or f"role:{expected_role}" not in tags:
            identifier = (
                document.get("_key")
                or document.get("memory_id")
                or document.get("id")
                or "<unidentified>"
            )
            raise AdaptiveLineageContractError(
                f"ISOLATION BREACH: {expected_role} oracle received {identifier} "
                f"from scope {scope!r}"
            )


class RedOracle:
    """Select the deterministic rare candidate with a Judge RED_SUCCESS verdict."""

    oracle_id = "battle-red-success-oracle-v1"
    required_role = ROLE_RED

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection:
        _validate_role_recall(
            expected_role=self.required_role, request=request, recall=recall
        )
        successes = [
            item for item in judged_population.judged.items if _verdict(item) == RED_SUCCESS
        ]
        survivor = _stable_best(
            successes,
            score=lambda item: (
                _float_value(item, "judge_confidence", "confidence", "score"),
                _int_value(item, "replay_count", "judge_attempts"),
            ),
        )
        reasons = {
            candidate_id(item): (
                ["red_success_tie_break_loser"]
                if _verdict(item) == RED_SUCCESS
                else [f"judge_verdict:{_verdict(item) or 'MISSING'}"]
            )
            for item in judged_population.judged.items
        }
        return _selection(
            oracle_id=self.oracle_id,
            population=judged_population,
            survivor=survivor,
            reasons=reasons,
            evidence={
                "fitness_rule": "judge_verdict == RED_SUCCESS",
                "success_count": len(successes),
                "selected_id": candidate_id(survivor) if survivor else None,
                "all_insufficient": bool(judged_population.judged.items)
                and all(
                    _verdict(item) == INSUFFICIENT_EVIDENCE
                    for item in judged_population.judged.items
                ),
            },
        )


class BlueOracle:
    """Select the defense whose Judge replay returns BLUE_SUCCESS."""

    oracle_id = "battle-blue-success-oracle-v1"
    required_role = ROLE_BLUE

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection:
        _validate_role_recall(
            expected_role=self.required_role, request=request, recall=recall
        )
        successes = [
            item for item in judged_population.judged.items if _verdict(item) == BLUE_SUCCESS
        ]
        survivor = _stable_best(
            successes,
            score=lambda item: (
                _float_value(item, "judge_confidence", "confidence", "score"),
                _int_value(item, "replay_count", "judge_attempts"),
            ),
        )
        reasons = {
            candidate_id(item): (
                ["blue_success_tie_break_loser"]
                if _verdict(item) == BLUE_SUCCESS
                else [f"judge_verdict:{_verdict(item) or 'MISSING'}"]
            )
            for item in judged_population.judged.items
        }
        return _selection(
            oracle_id=self.oracle_id,
            population=judged_population,
            survivor=survivor,
            reasons=reasons,
            evidence={
                "fitness_rule": "judge_verdict == BLUE_SUCCESS",
                "success_count": len(successes),
                "selected_id": candidate_id(survivor) if survivor else None,
            },
        )


def _replay_count(item: Mapping[str, Any]) -> int:
    count = _int_value(item, "replay_count", "judge_replay_count", "attempt_count")
    receipts = _first_value(item, "replay_receipts", "judge_replay_receipts")
    if isinstance(receipts, Sequence) and not isinstance(receipts, (str, bytes)):
        count = max(count, len(receipts))
    verdicts = _first_value(item, "replay_verdicts", "verdicts")
    if isinstance(verdicts, Sequence) and not isinstance(verdicts, (str, bytes)):
        count = max(count, len(verdicts))
    return count


def _judge_soundness(item: Mapping[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    deterministic = _bool_value(item, "deterministic", "determinism_confirmed")
    replay_consistent = _bool_value(
        item, "replay_consistent", "replay_consistency_confirmed"
    )
    non_gameable = _bool_value(
        item, "non_gameable", "non_gameability_confirmed", "anti_gaming_passed"
    )
    real_replay = _bool_value(
        item, "real_replay", "replay_executed", "judge_replay_executed"
    )
    count = _replay_count(item)
    marker_only = _bool_value(
        item,
        "success_marker_only",
        "marker_only",
        "spoofed_success_marker",
        "prints_success_marker_without_replay",
        "exploit_success_marker_only",
    )
    has_marker = _first_value(
        item, "success_marker", "exploit_success_marker", "printed_marker"
    ) not in (None, "")

    reasons: list[str] = []
    if marker_only or (has_marker and not real_replay):
        reasons.append("spoofed_success_marker_without_real_replay")
    if not real_replay:
        reasons.append("real_replay_missing")
    if count < 2:
        reasons.append("insufficient_replays_for_determinism")
    if not deterministic:
        reasons.append("methodology_not_deterministic")
    if not replay_consistent:
        reasons.append("verdict_not_replay_consistent")
    if not non_gameable:
        reasons.append("methodology_gameable")

    checks = {
        "deterministic": deterministic,
        "replay_consistent": replay_consistent,
        "non_gameable": non_gameable,
        "real_replay": real_replay,
        "replay_count": count,
        "success_marker_only": marker_only,
        "has_success_marker": has_marker,
    }
    return not reasons, reasons, checks


class JudgeOracle:
    """Select a deterministic, replay-consistent, non-gameable Judge method."""

    oracle_id = "battle-judge-soundness-oracle-v1"
    required_role = ROLE_JUDGE

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection:
        _validate_role_recall(
            expected_role=self.required_role, request=request, recall=recall
        )
        viable: list[Mapping[str, Any]] = []
        reasons: dict[str, Sequence[str]] = {}
        checks: dict[str, Mapping[str, Any]] = {}
        for item in judged_population.judged.items:
            valid, item_reasons, item_checks = _judge_soundness(item)
            identifier = candidate_id(item)
            checks[identifier] = item_checks
            if valid:
                viable.append(item)
                reasons[identifier] = ["sound_methodology_tie_break_loser"]
            else:
                reasons[identifier] = item_reasons
        survivor = _stable_best(
            viable,
            score=lambda item: (
                _replay_count(item),
                _float_value(item, "coverage", "soundness_score", "confidence"),
            ),
        )
        return _selection(
            oracle_id=self.oracle_id,
            population=judged_population,
            survivor=survivor,
            reasons=reasons,
            evidence={
                "fitness_rule": (
                    "real replay count >= 2 AND deterministic AND replay-consistent "
                    "AND non-gameable AND not marker-only"
                ),
                "checks": checks,
                "selected_id": candidate_id(survivor) if survivor else None,
            },
        )


@runtime_checkable
class ResearchNegativeEvidenceSink(Protocol):
    def retain_dead_ends(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        findings: Sequence[Mapping[str, Any]],
        reason_by_id: Mapping[str, Sequence[str]],
    ) -> Mapping[str, Any]: ...


def _safe_fragment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value).strip("-")
    if not cleaned:
        raise ValueError("negative evidence key fragment normalized to empty")
    return cleaned


class MemoryResearchNegativeEvidenceSink:
    """Persist researcher dead ends via the existing daemon-backed /upsert hook."""

    def __init__(self, memory: MemoryBackend) -> None:
        self.memory = memory

    def retain_dead_ends(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        findings: Sequence[Mapping[str, Any]],
        reason_by_id: Mapping[str, Sequence[str]],
    ) -> Mapping[str, Any]:
        scope = RoleMemoryScope(
            battle_id=request.battle_id,
            lineage_id=request.lineage_id,
            role=request.role,
        )
        documents: list[dict[str, Any]] = []
        for finding in findings:
            identifier = candidate_id(finding)
            reasons = sorted(set(reason_by_id.get(identifier) or ("dead_end",)))
            digest = canonical_sha256(
                {
                    "battle_id": request.battle_id,
                    "lineage_id": request.lineage_id,
                    "role": request.role,
                    "finding_id": identifier,
                    "finding": json_safe(finding),
                    "reasons": reasons,
                }
            )[:24]
            key = ":".join(
                (
                    "battle-lineage",
                    _safe_fragment(request.battle_id),
                    _safe_fragment(request.lineage_id),
                    "research-dead-end",
                    digest,
                )
            )
            documents.append(
                {
                    "_key": key,
                    "schema": MEMORY_NODE_SCHEMA,
                    "collection": self.memory.collection,
                    "battle_id": request.battle_id,
                    "lineage_id": request.lineage_id,
                    "run_id": request.run_id,
                    "generation": request.generation,
                    "role": request.role,
                    "owner_role": request.role,
                    "scope": scope.private_scope,
                    "node_kind": "research_dead_end",
                    "finding_id": identifier,
                    "text": (
                        f"Research finding {identifier} did not produce a surviving "
                        "specimen; retain this negative evidence to avoid re-search."
                    ),
                    "retrieval_text": str(finding.get("finding") or finding.get("text") or identifier),
                    "finding": json_safe(finding),
                    "reason_codes": reasons,
                    "tags": [
                        *scope.base_tags,
                        f"role:{request.role}",
                        f"access:{request.role}",
                        "visibility:role-only",
                        "kind:research-dead-end",
                        "do-not-research-again",
                    ],
                    "graph_edges_raw": [],
                    "qdrant": {
                        "sync": "memory-daemon-owned",
                        "vector_inline": False,
                    },
                }
            )
        if not documents:
            return {
                "status": "PASS",
                "retained_count": 0,
                "collection": self.memory.collection,
            }
        acknowledgement = self.memory.upsert_documents(
            collection=self.memory.collection,
            documents=documents,
        )
        return {
            "status": "PASS",
            "retained_count": len(documents),
            "collection": self.memory.collection,
            "keys": [document["_key"] for document in documents],
            "acknowledgement": json_safe(acknowledgement),
        }


def _research_usefulness(
    item: Mapping[str, Any],
) -> tuple[bool, list[str], dict[str, Any]]:
    survivor_id = _first_value(
        item,
        "led_to_survivor_id",
        "surviving_specimen_id",
        "survivor_id",
        "selected_specimen_id",
    )
    receipt_ref = _first_value(
        item,
        "survivor_receipt_ref",
        "selection_receipt_ref",
        "oracle_receipt_ref",
        "lineage_receipt_ref",
    )
    led_to_survivor = _bool_value(
        item, "led_to_survivor", "survivor_selected", "usefulness_confirmed"
    )
    outcome = str(
        _first_value(item, "survivor_verdict", "downstream_verdict", "outcome")
        or ""
    ).upper()
    outcome_confirms = outcome in {
        RED_SUCCESS,
        BLUE_SUCCESS,
        "SURVIVED",
        "SELECTED",
        "PASS",
    }
    source_receipts = _first_value(item, "source_receipts", "evidence_receipts")
    if not receipt_ref and isinstance(source_receipts, Sequence) and not isinstance(
        source_receipts, (str, bytes)
    ):
        receipt_ref = next((str(value) for value in source_receipts if value), None)

    reasons: list[str] = []
    if not survivor_id:
        reasons.append("no_surviving_specimen_binding")
    if not receipt_ref:
        reasons.append("survivor_receipt_missing")
    if not (led_to_survivor or outcome_confirms):
        reasons.append("finding_did_not_lead_to_survivor")
    evidence = {
        "survivor_id": survivor_id,
        "receipt_ref": receipt_ref,
        "led_to_survivor": led_to_survivor,
        "downstream_outcome": outcome,
    }
    return not reasons, reasons, evidence


class ResearcherOracle:
    """Select receipt-proven useful findings and retain all dead ends in /memory."""

    oracle_id = "battle-research-usefulness-oracle-v1"
    required_role = ROLE_RESEARCHER

    def __init__(
        self,
        negative_evidence_sink: ResearchNegativeEvidenceSink | None = None,
    ) -> None:
        self.negative_evidence_sink = negative_evidence_sink

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection:
        _validate_role_recall(
            expected_role=self.required_role, request=request, recall=recall
        )
        viable: list[Mapping[str, Any]] = []
        dead_ends: list[Mapping[str, Any]] = []
        reasons: dict[str, Sequence[str]] = {}
        checks: dict[str, Mapping[str, Any]] = {}
        for item in judged_population.judged.items:
            useful, item_reasons, evidence = _research_usefulness(item)
            identifier = candidate_id(item)
            checks[identifier] = evidence
            if useful:
                viable.append(item)
                reasons[identifier] = ["useful_finding_tie_break_loser"]
            else:
                dead_ends.append(item)
                reasons[identifier] = item_reasons

        retention: Mapping[str, Any] = {
            "status": "NOT_CONFIGURED",
            "retained_count": 0,
        }
        if self.negative_evidence_sink is not None:
            retention = self.negative_evidence_sink.retain_dead_ends(
                request=request,
                recall=recall,
                findings=dead_ends,
                reason_by_id=reasons,
            )

        survivor = _stable_best(
            viable,
            score=lambda item: (
                len(_first_value(item, "source_receipts", "evidence_receipts") or ()),
                _float_value(item, "usefulness_score", "confidence"),
            ),
        )
        return _selection(
            oracle_id=self.oracle_id,
            population=judged_population,
            survivor=survivor,
            reasons=reasons,
            evidence={
                "fitness_rule": (
                    "finding has a surviving specimen binding, a survivor receipt, "
                    "and a confirmed downstream survival outcome"
                ),
                "checks": checks,
                "negative_evidence_retention": json_safe(retention),
                "selected_id": candidate_id(survivor) if survivor else None,
            },
        )


def _past_game_verdicts(item: Mapping[str, Any]) -> list[str]:
    raw = _first_value(
        item,
        "past_game_judge_outcomes",
        "past_game_outcomes",
        "judge_outcomes",
        "past_games",
    )
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    verdicts: list[str] = []
    for outcome in raw:
        if isinstance(outcome, Mapping):
            verdicts.append(_verdict(outcome))
        else:
            verdicts.append(str(outcome or "").strip().upper())
    return [verdict for verdict in verdicts if verdict]


def _arena_balance(
    item: Mapping[str, Any],
    *,
    min_decisive_games: int,
    min_balance_score: float,
) -> tuple[bool, list[str], dict[str, Any]]:
    verdicts = _past_game_verdicts(item)
    red = sum(verdict == RED_SUCCESS for verdict in verdicts)
    blue = sum(verdict == BLUE_SUCCESS for verdict in verdicts)
    insufficient = sum(verdict == INSUFFICIENT_EVIDENCE for verdict in verdicts)
    decisive = red + blue
    total = len(verdicts)
    balance_score = 0.0 if decisive == 0 else 1.0 - abs(red - blue) / decisive
    insufficient_rate = 1.0 if total == 0 else insufficient / total

    reasons: list[str] = []
    if total == 0:
        reasons.append("past_game_history_missing")
    if total > 0 and insufficient == total:
        reasons.append("degenerate_all_insufficient_arena")
    if decisive < min_decisive_games:
        reasons.append("too_few_decisive_past_games")
    if red == 0 or blue == 0:
        reasons.append("one_side_never_survived")
    if balance_score < min_balance_score:
        reasons.append("past_games_not_evenly_matched")
    evidence = {
        "past_game_count": total,
        "red_success_count": red,
        "blue_success_count": blue,
        "insufficient_evidence_count": insufficient,
        "decisive_game_count": decisive,
        "balance_score": balance_score,
        "insufficient_rate": insufficient_rate,
    }
    return not reasons, reasons, evidence


class ArenaCreatorOracle:
    """Select an arena whose past decisive games were genuinely even."""

    oracle_id = "battle-arena-balance-oracle-v1"
    required_role = ROLE_ARENA_CREATOR

    def __init__(
        self,
        *,
        min_decisive_games: int = 2,
        min_balance_score: float = 0.8,
    ) -> None:
        if min_decisive_games < 2:
            raise ValueError("min_decisive_games must be >= 2")
        if not 0.0 <= min_balance_score <= 1.0:
            raise ValueError("min_balance_score must be between 0 and 1")
        self.min_decisive_games = min_decisive_games
        self.min_balance_score = min_balance_score

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection:
        _validate_role_recall(
            expected_role=self.required_role, request=request, recall=recall
        )
        viable: list[Mapping[str, Any]] = []
        reasons: dict[str, Sequence[str]] = {}
        checks: dict[str, Mapping[str, Any]] = {}
        for item in judged_population.judged.items:
            balanced, item_reasons, evidence = _arena_balance(
                item,
                min_decisive_games=self.min_decisive_games,
                min_balance_score=self.min_balance_score,
            )
            identifier = candidate_id(item)
            checks[identifier] = evidence
            if balanced:
                viable.append(item)
                reasons[identifier] = ["balanced_arena_tie_break_loser"]
            else:
                reasons[identifier] = item_reasons
        survivor = _stable_best(
            viable,
            score=lambda item: (
                float(checks[candidate_id(item)]["balance_score"]),
                float(checks[candidate_id(item)]["decisive_game_count"]),
                1.0 - float(checks[candidate_id(item)]["insufficient_rate"]),
            ),
        )
        return _selection(
            oracle_id=self.oracle_id,
            population=judged_population,
            survivor=survivor,
            reasons=reasons,
            evidence={
                "fitness_rule": (
                    f"decisive_games >= {self.min_decisive_games}, both sides win, "
                    f"balance_score >= {self.min_balance_score}"
                ),
                "checks": checks,
                "selected_id": candidate_id(survivor) if survivor else None,
            },
        )


@runtime_checkable
class TauArenaCreatorDagBackend(Protocol):
    """Clean seam for the future sequential Tau creator-reviewer DAG.

    Implementations must execute the real Tau topology and return normalized stage
    results. This round deliberately defines but does not implement that backend.
    """

    def create_population(
        self, *, request: GenerationRequest, recall: RecallResult
    ) -> PopulationStageResult: ...

    def review_population(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
    ) -> PopulationStageResult: ...

    def judge_population(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        reviewed: PopulationStageResult,
    ) -> PopulationStageResult: ...


class UnconfiguredTauArenaCreatorDagBackend:
    """Explicit fail-closed placeholder; it never hand-simulates a Tau DAG."""

    @staticmethod
    def _blocked() -> PopulationStageResult:
        raise AdaptiveLineageContractError(
            "Tau arena creator-reviewer DAG backend is not configured"
        )

    def create_population(
        self, *, request: GenerationRequest, recall: RecallResult
    ) -> PopulationStageResult:
        return self._blocked()

    def review_population(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
    ) -> PopulationStageResult:
        return self._blocked()

    def judge_population(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        reviewed: PopulationStageResult,
    ) -> PopulationStageResult:
        return self._blocked()


class TauArenaPopulationHooks:
    """PopulationHooks adapter around the future real Tau DAG backend."""

    def __init__(self, backend: TauArenaCreatorDagBackend) -> None:
        if not isinstance(backend, TauArenaCreatorDagBackend):
            raise TypeError("backend must implement TauArenaCreatorDagBackend")
        self.backend = backend

    def synthesize(
        self, *, request: GenerationRequest, recall: RecallResult
    ) -> PopulationStageResult:
        return self.backend.create_population(request=request, recall=recall)

    def review(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
    ) -> PopulationStageResult:
        return self.backend.review_population(
            request=request,
            recall=recall,
            generated=generated,
        )

    def judge(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        reviewed: PopulationStageResult,
    ) -> PopulationStageResult:
        return self.backend.judge_population(
            request=request,
            recall=recall,
            generated=generated,
            reviewed=reviewed,
        )


def oracle_for_role(
    role: str,
    *,
    memory: MemoryBackend | None = None,
) -> FitnessOracle:
    if role == ROLE_RED:
        return RedOracle()
    if role == ROLE_BLUE:
        return BlueOracle()
    if role == ROLE_JUDGE:
        return JudgeOracle()
    if role == ROLE_RESEARCHER:
        sink = MemoryResearchNegativeEvidenceSink(memory) if memory else None
        return ResearcherOracle(sink)
    if role == ROLE_ARENA_CREATOR:
        return ArenaCreatorOracle()
    raise ValueError(f"unsupported adaptive-lineage role {role!r}")


@dataclass(frozen=True)
class LiveRoleRuntime:
    """Concrete composition of engine, oracle, population hooks, and /memory."""

    role: str
    engine: AdaptiveLineageEngine
    oracle: FitnessOracle
    memory: MemoryBackend
    population_hooks: PopulationHooks


def build_live_role_runtime(
    role: str,
    *,
    memory_base_url: str = "http://127.0.0.1:8601",
    memory_collection: str = MEMORY_COLLECTION,
    primitive_module: str = "battle_skill.adaptive_red_blue_lineage_canary",
    memory: MemoryBackend | None = None,
    population_hooks: PopulationHooks | None = None,
    tau_arena_backend: TauArenaCreatorDagBackend | None = None,
) -> LiveRoleRuntime:
    """Wire the real daemon and verified canary primitives for one role.

    Red and Blue default to the lazy adapter over the real
    ``_population_genomes``, ``_review_population``, ``_judge_population``, and
    ``_select_survivor`` helpers. Arena creation uses the explicit Tau DAG seam.
    Judge and Researcher population producers are not part of Round 3 and must be
    injected; the factory fails closed rather than pretending the Red/Blue canary
    can synthesize those candidate types.
    """

    if role not in CONCRETE_ROLES:
        raise ValueError(f"unsupported adaptive-lineage role {role!r}")
    memory_backend = memory or MemoryBackend(
        base_url=memory_base_url,
        collection=memory_collection,
    )
    if population_hooks is None:
        if role == ROLE_ARENA_CREATOR:
            population_hooks = TauArenaPopulationHooks(
                tau_arena_backend or UnconfiguredTauArenaCreatorDagBackend()
            )
        elif role in {ROLE_RED, ROLE_BLUE}:
            population_hooks = VerifiedPopulationHooks(
                load_verified_primitive_bundle(primitive_module)
            )
        else:
            raise AdaptiveLineageContractError(
                f"population_hooks must be injected for {role}; Round 3 implements "
                "its oracle but not its role-specific candidate producer"
            )
    oracle = oracle_for_role(role, memory=memory_backend)
    engine = AdaptiveLineageEngine(
        population_hooks=population_hooks,
        oracle=oracle,
        memory_hooks=memory_backend,
    )
    return LiveRoleRuntime(
        role=role,
        engine=engine,
        oracle=oracle,
        memory=memory_backend,
        population_hooks=population_hooks,
    )


ASSUMPTIONS = (
    "The verified _judge_population output carries a verdict in judge_verdict, "
    "verdict, outcome, or a supported nested evidence object.",
    "If more than one Red/Blue success exists, confidence/replay count and then "
    "candidate_id form a deterministic tie-break; the oracle does not claim that "
    "multiple successes are common.",
    "Judge soundness requires at least two real replays; a printed success marker "
    "without replay is always rejected even when other booleans claim PASS.",
    "A research finding is demonstrably useful only when it binds both a surviving "
    "specimen id and a survivor/selection receipt to a confirmed downstream outcome.",
    "Arena balance ignores INSUFFICIENT_EVIDENCE for the Red-vs-Blue ratio but "
    "requires at least two decisive games and at least one win by each side.",
    "The real Tau arena creator-reviewer DAG is intentionally not implemented in "
    "Round 3; UnconfiguredTauArenaCreatorDagBackend fails closed.",
    "Only Red and Blue have a verified live population adapter in this round; Judge "
    "and Researcher runtimes require injected role-specific PopulationHooks.",
)
