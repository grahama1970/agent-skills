"""Universal oracle-parameterized adaptive-lineage engine for /battle.

One normal generation is exactly::

    recall -> population -> review -> judge -> oracle-select
        -> survivor write-back OR valid no-survivor lineage death -> bounded STOP

The engine is role-agnostic. Roles differ only by the injected fitness oracle and
by the role/public scope sent to the /memory daemon. The engine never issues AQL,
never imports a direct Memory client, and never stores vector arrays in ArangoDB.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

ENGINE_SCHEMA = "battle.universal_adaptive_lineage_generation.v2"
BAD_MATERIAL_SCHEMA = "battle.bad_genetic_material.v2"
ORACLE_SELECTION_SCHEMA = "battle.oracle_selection.v1"
RECALL_SCHEMA = "battle.lineage_memory_recall.v2"
MATERIALIZATION_SCHEMA = "battle.lineage_materialization.v1"


class AdaptiveLineageContractError(RuntimeError):
    """Raised only for an invalid engine/oracle/primitive contract."""


def json_safe(value: Any) -> Any:
    """Return a deterministic JSON-compatible representation."""

    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [json_safe(item) for item in sorted(value, key=lambda item: repr(item))]
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            json_safe(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def candidate_id(candidate: Mapping[str, Any]) -> str:
    for key in (
        "specimen_id",
        "candidate_id",
        "genome_id",
        "worker_id",
        "id",
        "_key",
    ):
        value = candidate.get(key)
        if value not in (None, ""):
            return str(value)
    for key in ("candidate", "specimen", "genome", "artifact"):
        nested = candidate.get(key)
        if isinstance(nested, Mapping) and nested is not candidate:
            return candidate_id(nested)
    return f"candidate-{canonical_sha256(candidate)[:24]}"


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


@dataclass(frozen=True)
class RecallResult:
    """Role-scoped items returned by the daemon-owned multihop recall."""

    documents: tuple[Mapping[str, Any], ...] = ()
    confidence: float = 0.0
    should_scan: bool = True
    item_scores: tuple[Mapping[str, float], ...] = ()
    receipt: Mapping[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        return {
            "schema": RECALL_SCHEMA,
            "documents": [json_safe(item) for item in self.documents],
            "confidence": self.confidence,
            "should_scan": self.should_scan,
            "item_scores": [json_safe(item) for item in self.item_scores],
            "receipt": json_safe(self.receipt),
            "multihop_owner": "memory_daemon",
        }


@dataclass(frozen=True)
class PopulationStageResult:
    """Normalized output from one existing verified population primitive."""

    items: tuple[Mapping[str, Any], ...]
    bad_genetic_material: tuple[Mapping[str, Any], ...] = ()
    raw: Any = None


@dataclass(frozen=True)
class JudgedPopulation:
    """The complete population state presented to a fitness oracle."""

    generated: PopulationStageResult
    reviewed: PopulationStageResult
    judged: PopulationStageResult

    @property
    def bad_genetic_material(self) -> tuple[Mapping[str, Any], ...]:
        return (
            *self.generated.bad_genetic_material,
            *self.reviewed.bad_genetic_material,
            *self.judged.bad_genetic_material,
        )

    @property
    def generated_by_id(self) -> dict[str, Mapping[str, Any]]:
        return {candidate_id(item): item for item in self.generated.items}

    @property
    def judged_by_id(self) -> dict[str, Mapping[str, Any]]:
        return {candidate_id(item): item for item in self.judged.items}

    def as_oracle_payload(self) -> dict[str, Any]:
        return {
            "generated": [json_safe(item) for item in self.generated.items],
            "reviewed": [json_safe(item) for item in self.reviewed.items],
            "judged": [json_safe(item) for item in self.judged.items],
            "bad_genetic_material": [
                json_safe(item) for item in self.bad_genetic_material
            ],
        }


@dataclass(frozen=True)
class OracleSelection:
    """Universal oracle result: rare survivor or None, plus bad material."""

    survivor: Mapping[str, Any] | None
    bad_genetic_material: Mapping[str, Any]
    evidence: Mapping[str, Any] = field(default_factory=dict)
    oracle_id: str = "unspecified-oracle"


@dataclass(frozen=True)
class GenerationRequest:
    battle_id: str
    lineage_id: str
    run_id: str
    role: str
    generation: int
    population_size: int
    max_generations: int
    max_recall_hops: int
    out_dir: Path
    subgraph_scope: Mapping[str, Any]
    context: Mapping[str, Any] = field(default_factory=dict)
    recall_k: int = 64
    materialize_only: bool = False

    def __post_init__(self) -> None:
        if not self.battle_id.strip():
            raise ValueError("battle_id must be non-empty")
        if not self.lineage_id.strip():
            raise ValueError("lineage_id must be non-empty")
        if not self.run_id.strip():
            raise ValueError("run_id must be non-empty")
        if not self.role.strip():
            raise ValueError("role must be non-empty")
        if self.generation < 1:
            raise ValueError("generation must be >= 1")
        if self.population_size < 1:
            raise ValueError("population_size must be >= 1")
        if self.max_generations < self.generation:
            raise ValueError("max_generations must be >= generation")
        if self.max_recall_hops < 2:
            raise ValueError(
                "max_recall_hops must be >= 2; the lineage contract is multihop"
            )
        if self.recall_k < 1:
            raise ValueError("recall_k must be >= 1")


@runtime_checkable
class PopulationHooks(Protocol):
    def synthesize(
        self, *, request: GenerationRequest, recall: RecallResult
    ) -> PopulationStageResult: ...

    def review(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
    ) -> PopulationStageResult: ...

    def judge(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        reviewed: PopulationStageResult,
    ) -> PopulationStageResult: ...


@runtime_checkable
class FitnessOracle(Protocol):
    oracle_id: str

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection: ...


@runtime_checkable
class MemoryHooks(Protocol):
    def recall(self, *, request: GenerationRequest) -> RecallResult: ...

    def write_survivor(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        survivor: Mapping[str, Any],
        oracle_evidence: Mapping[str, Any],
        bad_genetic_material: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


def _extract_bad_candidate_id(record: Mapping[str, Any]) -> str | None:
    for key in (
        "specimen_id",
        "candidate_id",
        "genome_id",
        "worker_id",
        "id",
        "_key",
    ):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    candidate = record.get("candidate")
    if isinstance(candidate, Mapping):
        return candidate_id(candidate)
    return None


def _reason_codes(record: Mapping[str, Any]) -> list[str]:
    output: list[str] = []
    for key in ("reason_codes", "reasons", "failures", "errors"):
        value = record.get(key)
        if isinstance(value, str) and value:
            output.append(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            output.extend(str(item) for item in value if item not in (None, ""))
    for key in ("reason", "failure", "error", "status", "verdict"):
        value = record.get(key)
        if value not in (None, "", "PASS"):
            output.append(f"{key}:{value}")
    return sorted(set(output))


def build_bad_genetic_material_record(
    *,
    request: GenerationRequest,
    judged_population: JudgedPopulation,
    selection: OracleSelection,
) -> dict[str, Any]:
    """Canonicalize all rejected/failed candidates into one generation record."""

    generated = judged_population.generated_by_id
    if len(generated) != len(judged_population.generated.items):
        raise AdaptiveLineageContractError(
            "population contains duplicate candidate identities"
        )

    survivor_id = candidate_id(selection.survivor) if selection.survivor else None
    bad_by_id: dict[str, dict[str, Any]] = {}
    unattributed: list[dict[str, Any]] = []
    records: list[Mapping[str, Any]] = list(
        judged_population.bad_genetic_material
    )

    oracle_bad = selection.bad_genetic_material
    oracle_items = oracle_bad.get("specimens") or oracle_bad.get("items") or []
    if isinstance(oracle_items, Sequence) and not isinstance(
        oracle_items, (str, bytes)
    ):
        records.extend(item for item in oracle_items if isinstance(item, Mapping))
    elif oracle_bad:
        records.append(oracle_bad)

    for record in records:
        identifier = _extract_bad_candidate_id(record)
        normalized = {
            "source": str(record.get("source") or record.get("stage") or "unknown"),
            "reason_codes": _reason_codes(record),
            "evidence": json_safe(
                record.get("evidence")
                or record.get("receipt")
                or record.get("details")
                or {}
            ),
        }
        if identifier is None:
            unattributed.append({**normalized, "raw": json_safe(record)})
            continue
        item = bad_by_id.setdefault(
            identifier,
            {
                "candidate_id": identifier,
                "reason_codes": [],
                "sources": [],
                "evidence": [],
            },
        )
        item["reason_codes"] = sorted(
            set([*item["reason_codes"], *normalized["reason_codes"]])
        )
        item["sources"] = sorted(set([*item["sources"], normalized["source"]]))
        if normalized["evidence"]:
            item["evidence"].append(normalized["evidence"])

    # Every generated non-survivor is genetic material, including runnable losers.
    for identifier, candidate in generated.items():
        if identifier == survivor_id:
            bad_by_id.pop(identifier, None)
            continue
        item = bad_by_id.setdefault(
            identifier,
            {
                "candidate_id": identifier,
                "reason_codes": [],
                "sources": [],
                "evidence": [],
            },
        )
        if not item["reason_codes"]:
            item["reason_codes"] = [
                "oracle_no_viable_survivor"
                if survivor_id is None
                else "not_selected_by_oracle"
            ]
        if not item["sources"]:
            item["sources"] = ["oracle"]
        item["candidate_sha256"] = canonical_sha256(candidate)

    specimens = [bad_by_id[key] for key in sorted(bad_by_id)]
    population_size = len(generated)
    bad_count = len(specimens)
    expected_bad = population_size - (1 if survivor_id else 0)
    if bad_count != expected_bad:
        raise AdaptiveLineageContractError(
            f"bad material count {bad_count} != expected {expected_bad}"
        )

    return {
        "schema": BAD_MATERIAL_SCHEMA,
        "battle_id": request.battle_id,
        "lineage_id": request.lineage_id,
        "run_id": request.run_id,
        "role": request.role,
        "generation": request.generation,
        "population_size": population_size,
        "bad_count": bad_count,
        "bad_rate": bad_count / population_size if population_size else 0.0,
        "all_bad": survivor_id is None,
        "survivor_id": survivor_id,
        "specimens": specimens,
        "unattributed_events": unattributed,
        "pipeline_bad_event_count": len(judged_population.bad_genetic_material),
        "oracle_bad_record": json_safe(selection.bad_genetic_material),
    }


class AdaptiveLineageEngine:
    """One universal engine; roles differ only by oracle and memory scope."""

    def __init__(
        self,
        *,
        population_hooks: PopulationHooks,
        oracle: FitnessOracle | None,
        memory_hooks: MemoryHooks,
    ) -> None:
        self.population_hooks = population_hooks
        self.oracle = oracle
        self.memory_hooks = memory_hooks

    def run_generation(self, request: GenerationRequest) -> dict[str, Any]:
        out_dir = request.out_dir.resolve()
        generation_dir = out_dir / f"generation-{request.generation:04d}"
        generation_dir.mkdir(parents=True, exist_ok=True)

        recall = self.memory_hooks.recall(request=request)
        generated = self.population_hooks.synthesize(request=request, recall=recall)
        generated_ids = self._validate_generated(request, generated)

        if request.materialize_only:
            return self._materialization_receipt(
                request=request,
                recall=recall,
                generated=generated,
                generated_ids=generated_ids,
                generation_dir=generation_dir,
            )

        if self.oracle is None or not isinstance(self.oracle, FitnessOracle):
            raise AdaptiveLineageContractError(
                "normal lineage execution requires a FitnessOracle"
            )

        reviewed = self.population_hooks.review(
            request=request,
            recall=recall,
            generated=generated,
        )
        judged = self.population_hooks.judge(
            request=request,
            recall=recall,
            generated=generated,
            reviewed=reviewed,
        )
        population = JudgedPopulation(
            generated=generated,
            reviewed=reviewed,
            judged=judged,
        )

        selection = self.oracle.select(
            population,
            request=request,
            recall=recall,
        )
        if not isinstance(selection, OracleSelection):
            raise AdaptiveLineageContractError("oracle must return OracleSelection")

        survivor_id: str | None = None
        survivor: Mapping[str, Any] | None = None
        if selection.survivor is not None:
            survivor_id = candidate_id(selection.survivor)
            if survivor_id not in population.judged_by_id:
                raise AdaptiveLineageContractError(
                    f"oracle selected {survivor_id!r}, absent from judged population"
                )
            survivor = population.judged_by_id[survivor_id]

        bad_record = build_bad_genetic_material_record(
            request=request,
            judged_population=population,
            selection=OracleSelection(
                survivor=survivor,
                bad_genetic_material=selection.bad_genetic_material,
                evidence=selection.evidence,
                oracle_id=selection.oracle_id,
            ),
        )

        memory_writeback: Mapping[str, Any] | None = None
        if survivor is None:
            status = "TERMINATED_VALID"
            stop_reason = "no_survivor"
            lineage_terminal = True
            should_continue = False
        else:
            memory_writeback = self.memory_hooks.write_survivor(
                request=request,
                recall=recall,
                survivor=survivor,
                oracle_evidence=selection.evidence,
                bad_genetic_material=bad_record,
            )
            lineage_terminal = request.generation >= request.max_generations
            should_continue = not lineage_terminal
            status = "TERMINATED_VALID" if lineage_terminal else "ACTIVE"
            stop_reason = (
                "bounded_terminus" if lineage_terminal else "survivor_reproduced"
            )

        receipt = {
            "schema": ENGINE_SCHEMA,
            "status": status,
            "valid_outcome": True,
            "battle_id": request.battle_id,
            "lineage_id": request.lineage_id,
            "run_id": request.run_id,
            "role": request.role,
            "generation": request.generation,
            "population_size": request.population_size,
            "materialize_only": False,
            "oracle": {
                "oracle_id": selection.oracle_id
                or getattr(self.oracle, "oracle_id", "unspecified-oracle"),
                "selection_schema": ORACLE_SELECTION_SCHEMA,
                "survivor_id": survivor_id,
                "evidence": json_safe(selection.evidence),
            },
            "recall": json_safe(recall.receipt),
            "population": {
                "generated_count": len(generated.items),
                "reviewed_count": len(reviewed.items),
                "judged_count": len(judged.items),
                "generated_ids": generated_ids,
                "reviewed_ids": [candidate_id(item) for item in reviewed.items],
                "judged_ids": [candidate_id(item) for item in judged.items],
            },
            "bad_genetic_material": bad_record,
            "survivor": json_safe(survivor) if survivor else None,
            "reproduction": json_safe(memory_writeback)
            if memory_writeback is not None
            else None,
            "lineage_terminal": lineage_terminal,
            "should_continue": should_continue,
            "stop_reason": stop_reason,
            "terminated_reason": stop_reason if lineage_terminal else None,
            "claims": {
                "proves": [
                    "The complete judged population was processed by the injected oracle.",
                    "No-survivor is a valid terminal outcome."
                    if survivor is None
                    else "The survivor, oracle evidence, and isolated bad-material record crossed the /memory HTTP boundary.",
                ],
                "does_not_prove": [
                    "Runnable material is successful material.",
                    "Target contact is oracle success.",
                    "A role-specific oracle beyond the injected adapter is implemented.",
                ],
            },
        }
        return self._persist_receipt(generation_dir, receipt)

    @staticmethod
    def _validate_generated(
        request: GenerationRequest, generated: PopulationStageResult
    ) -> list[str]:
        if len(generated.items) != request.population_size:
            raise AdaptiveLineageContractError(
                f"population primitive materialized {len(generated.items)} candidates; "
                f"expected {request.population_size}"
            )
        generated_ids = [candidate_id(item) for item in generated.items]
        if len(set(generated_ids)) != len(generated_ids):
            raise AdaptiveLineageContractError(
                "population primitive emitted duplicate candidate identities"
            )
        return generated_ids

    def _materialization_receipt(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        generated_ids: list[str],
        generation_dir: Path,
    ) -> dict[str, Any]:
        receipt = {
            "schema": MATERIALIZATION_SCHEMA,
            "status": "MATERIALIZED",
            "valid_outcome": True,
            "battle_id": request.battle_id,
            "lineage_id": request.lineage_id,
            "run_id": request.run_id,
            "role": request.role,
            "generation": request.generation,
            "population_size": request.population_size,
            "materialize_only": True,
            "recall": json_safe(recall.receipt),
            "population": {
                "generated_count": len(generated.items),
                "generated_ids": generated_ids,
                "unjudged_count": len(generated.items),
            },
            "review_skipped": True,
            "judge_skipped": True,
            "oracle_skipped": True,
            "reproduction": None,
            "bad_genetic_material": {
                "status": "NOT_JUDGED",
                "bad_rate": None,
                "items": [],
            },
            "lineage_terminal": False,
            "should_continue": False,
            "stop_reason": "materialize_only",
            "claims": {
                "proves": [
                    f"Exactly {len(generated.items)} specimens were materialized."
                ],
                "does_not_prove": [
                    "Any materialized specimen compiled, ran, or survived an oracle."
                ],
            },
        }
        return self._persist_receipt(generation_dir, receipt)

    @staticmethod
    def _persist_receipt(
        generation_dir: Path, receipt: Mapping[str, Any]
    ) -> dict[str, Any]:
        output = dict(receipt)
        receipt_path = generation_dir / "universal-lineage-generation-receipt.json"
        output["receipt_path"] = str(receipt_path)
        output["receipt_payload_sha256"] = canonical_sha256(output)
        _write_json(receipt_path, output)
        return output
