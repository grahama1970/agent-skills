"""Adapters for Battle's four already-verified adaptive-lineage primitives.

This module is intentionally tolerant at the call boundary because the verified
helpers pre-date the universal engine and carry role-specific argument names.
It is strict after the call: outputs are normalized to complete population-stage
records, and a survivor may only resolve to a judged candidate.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .adaptive_lineage_engine import (
    AdaptiveLineageContractError,
    GenerationRequest,
    JudgedPopulation,
    OracleSelection,
    PopulationStageResult,
    RecallResult,
    candidate_id,
    json_safe,
)


@dataclass(frozen=True)
class PrimitiveBundle:
    population_genomes: Callable[..., Any]
    review_population: Callable[..., Any]
    judge_population: Callable[..., Any]
    select_survivor: Callable[..., Any]


def load_verified_primitive_bundle(
    module_name: str = "battle_skill.adaptive_red_blue_lineage_canary",
) -> PrimitiveBundle:
    module = importlib.import_module(module_name)
    names = {
        "population_genomes": "_population_genomes",
        "review_population": "_review_population",
        "judge_population": "_judge_population",
        "select_survivor": "_select_survivor",
    }
    loaded: dict[str, Callable[..., Any]] = {}
    missing: list[str] = []
    for field_name, attribute in names.items():
        value = getattr(module, attribute, None)
        if not callable(value):
            missing.append(attribute)
        else:
            loaded[field_name] = value
    if missing:
        raise AdaptiveLineageContractError(
            f"{module_name} is missing verified primitives: {', '.join(missing)}"
        )
    return PrimitiveBundle(**loaded)


def _invoke_compatible(function: Callable[..., Any], kwargs: Mapping[str, Any]) -> Any:
    """Call a legacy primitive with only the keyword names it accepts."""

    signature = inspect.signature(function)
    parameters = signature.parameters
    has_var_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    accepted = dict(kwargs) if has_var_kwargs else {
        name: value for name, value in kwargs.items() if name in parameters
    }
    missing = [
        name
        for name, parameter in parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        and name not in accepted
    ]
    if missing:
        raise AdaptiveLineageContractError(
            f"verified primitive {function.__module__}.{function.__name__} requires "
            f"unsupported arguments: {missing}"
        )
    return function(**accepted)


_ITEM_KEYS = (
    "items",
    "population",
    "population_records",
    "genomes",
    "genome_records",
    "specimens",
    "candidates",
    "reviews",
    "review_records",
    "reviewed_population",
    "judgments",
    "judge_attempts",
    "judge_records",
    "judged_population",
    "verdicts",
)
_BAD_KEYS = (
    "bad_genetic_material",
    "bad_records",
    "rejections",
    "failures",
    "errors",
)


def _mapping_values_as_items(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    ignored = set(_BAD_KEYS) | {
        "status",
        "schema",
        "receipt",
        "summary",
        "evidence",
        "survivor",
        "selected",
        "winner",
    }
    entries: list[Mapping[str, Any]] = []
    for key, item in value.items():
        if key in ignored or not isinstance(item, Mapping):
            continue
        candidate = dict(item)
        if not any(
            candidate.get(identity) not in (None, "")
            for identity in (
                "specimen_id",
                "candidate_id",
                "genome_id",
                "worker_id",
                "id",
                "_key",
            )
        ):
            candidate["candidate_id"] = str(key)
        entries.append(candidate)
    return entries


def _as_mapping_items(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        identity_keys = {
            "specimen_id",
            "candidate_id",
            "genome_id",
            "worker_id",
            "id",
            "_key",
        }
        if identity_keys.intersection(value):
            return [dict(value)]
        mapped = _mapping_values_as_items(value)
        if mapped:
            return mapped
        return [dict(value)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _as_bad_items(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("specimens", "items", "records", "failures", "rejections"):
            if key in value:
                nested = _as_mapping_items(value.get(key))
                if nested or value.get(key) == []:
                    return nested
        return [dict(value)]
    return _as_mapping_items(value)


def normalize_stage_result(raw: Any, *, stage: str) -> PopulationStageResult:
    items: list[Mapping[str, Any]] = []
    bad: list[Mapping[str, Any]] = []

    if isinstance(raw, tuple) and len(raw) == 2:
        items = _as_mapping_items(raw[0])
        bad = _as_mapping_items(raw[1])
    elif isinstance(raw, Mapping):
        for key in _ITEM_KEYS:
            if key in raw:
                items = _as_mapping_items(raw.get(key))
                if items or raw.get(key) == []:
                    break
        if not items:
            items = _mapping_values_as_items(raw)
        for key in _BAD_KEYS:
            bad.extend(_as_bad_items(raw.get(key)))
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        items = _as_mapping_items(raw)
    else:
        raise AdaptiveLineageContractError(
            f"{stage} primitive returned unsupported type {type(raw)!r}"
        )

    normalized_items = tuple(
        {**dict(item), "_adaptive_stage": stage} for item in items
    )
    normalized_bad = tuple(
        {**dict(item), "source": str(item.get("source") or stage)} for item in bad
    )
    return PopulationStageResult(
        items=normalized_items,
        bad_genetic_material=normalized_bad,
        raw=raw,
    )


def _base_kwargs(
    request: GenerationRequest,
    recall: RecallResult,
) -> dict[str, Any]:
    generation_dir = request.out_dir.resolve() / f"generation-{request.generation:04d}"
    return {
        "battle_id": request.battle_id,
        "lineage_id": request.lineage_id,
        "run_id": request.run_id,
        "role": request.role,
        "team": request.role,
        "generation": request.generation,
        "population_size": request.population_size,
        "n": request.population_size,
        "worker_count": request.population_size,
        "red_workers": request.population_size if request.role == "red" else 0,
        "blue_workers": request.population_size if request.role == "blue" else 0,
        "materialize_only": request.materialize_only,
        "max_generations": request.max_generations,
        "out_dir": generation_dir,
        "generation_dir": generation_dir,
        "recall": recall.as_context(),
        "memory_recall": recall.as_context(),
        "inherited_knowledge": recall.as_context(),
        "subgraph_scope": json_safe(request.subgraph_scope),
        "context": json_safe(request.context),
    }


class VerifiedPopulationHooks:
    """Plug the four live-proven helpers into the universal engine."""

    def __init__(self, bundle: PrimitiveBundle | None = None) -> None:
        self.bundle = bundle or load_verified_primitive_bundle()

    def synthesize(
        self, *, request: GenerationRequest, recall: RecallResult
    ) -> PopulationStageResult:
        raw = _invoke_compatible(
            self.bundle.population_genomes,
            _base_kwargs(request, recall),
        )
        return normalize_stage_result(raw, stage="population")

    def review(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
    ) -> PopulationStageResult:
        kwargs = _base_kwargs(request, recall)
        kwargs.update(
            {
                "population": list(generated.items),
                "genomes": list(generated.items),
                "specimens": list(generated.items),
                "generated_population": list(generated.items),
                "bad_genetic_material": list(generated.bad_genetic_material),
            }
        )
        raw = _invoke_compatible(self.bundle.review_population, kwargs)
        return normalize_stage_result(raw, stage="review")

    def judge(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        reviewed: PopulationStageResult,
    ) -> PopulationStageResult:
        kwargs = _base_kwargs(request, recall)
        kwargs.update(
            {
                "population": list(generated.items),
                "genomes": list(generated.items),
                "specimens": list(generated.items),
                "reviewed": list(reviewed.items),
                "reviews": list(reviewed.items),
                "reviewed_population": list(reviewed.items),
                "bad_genetic_material": [
                    *generated.bad_genetic_material,
                    *reviewed.bad_genetic_material,
                ],
            }
        )
        raw = _invoke_compatible(self.bundle.judge_population, kwargs)
        return normalize_stage_result(raw, stage="judge")


class PrimitiveBackedOracle:
    """Oracle adapter whose decision is the verified ``_select_survivor`` helper."""

    oracle_id = "primitive-backed-select-survivor"

    def __init__(self, bundle: PrimitiveBundle | None = None) -> None:
        self.bundle = bundle or load_verified_primitive_bundle()

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection:
        kwargs = _base_kwargs(request, recall)
        payload = judged_population.as_oracle_payload()
        kwargs.update(
            {
                "judged_population": list(judged_population.judged.items),
                "judgments": list(judged_population.judged.items),
                "verdicts": list(judged_population.judged.items),
                "population": list(judged_population.generated.items),
                "reviews": list(judged_population.reviewed.items),
                "bad_genetic_material": list(
                    judged_population.bad_genetic_material
                ),
                "population_record": payload,
            }
        )
        raw = _invoke_compatible(self.bundle.select_survivor, kwargs)
        survivor, bad, evidence, oracle_id = self._normalize_selection(
            raw, judged_population
        )
        return OracleSelection(
            survivor=survivor,
            bad_genetic_material=bad,
            evidence=evidence,
            oracle_id=oracle_id,
        )

    def _normalize_selection(
        self,
        raw: Any,
        judged_population: JudgedPopulation,
    ) -> tuple[
        Mapping[str, Any] | None,
        Mapping[str, Any],
        Mapping[str, Any],
        str,
    ]:
        survivor_raw: Any = None
        bad: Mapping[str, Any] = {
            "schema": "battle.verified_primitive_bad_material.v1",
            "specimens": [],
        }
        evidence: Mapping[str, Any] = {}
        oracle_id = self.oracle_id

        if raw is None:
            pass
        elif isinstance(raw, tuple) and len(raw) == 2:
            survivor_raw, bad_raw = raw
            if isinstance(bad_raw, Mapping):
                bad = dict(bad_raw)
            else:
                bad = {"specimens": _as_mapping_items(bad_raw)}
        elif isinstance(raw, Mapping):
            identity_keys = {
                "specimen_id",
                "candidate_id",
                "genome_id",
                "worker_id",
                "id",
                "_key",
            }
            survivor_keys = (
                "survivor",
                "selected_survivor",
                "selected",
                "winner",
                "winner_specimen",
            )
            is_wrapper = not identity_keys.intersection(raw) and (
                any(key in raw for key in survivor_keys)
                or "bad_genetic_material" in raw
                or "bad_records" in raw
                or "oracle_id" in raw
            )
            if is_wrapper:
                survivor_raw = next(
                    (raw.get(key) for key in survivor_keys if raw.get(key) is not None),
                    None,
                )
                bad_raw = raw.get("bad_genetic_material")
                if bad_raw is None:
                    bad_raw = raw.get("bad_records")
                if isinstance(bad_raw, Mapping):
                    bad = dict(bad_raw)
                elif bad_raw is not None:
                    bad = {"specimens": _as_bad_items(bad_raw)}
                evidence_raw = raw.get("evidence") or raw.get("oracle_evidence") or {}
                evidence = (
                    dict(evidence_raw)
                    if isinstance(evidence_raw, Mapping)
                    else {"value": json_safe(evidence_raw)}
                )
                oracle_id = str(raw.get("oracle_id") or self.oracle_id)
            else:
                survivor_raw = raw
        elif isinstance(raw, str):
            survivor_raw = raw
        else:
            raise AdaptiveLineageContractError(
                f"_select_survivor returned unsupported type {type(raw)!r}"
            )

        survivor = self._resolve_survivor(survivor_raw, judged_population)
        return survivor, bad, evidence, oracle_id

    @staticmethod
    def _resolve_survivor(
        survivor_raw: Any,
        judged_population: JudgedPopulation,
    ) -> Mapping[str, Any] | None:
        if survivor_raw is None:
            return None
        judged = judged_population.judged_by_id
        if isinstance(survivor_raw, str):
            selected_id = survivor_raw
        elif isinstance(survivor_raw, Mapping):
            selected_id = candidate_id(survivor_raw)
        else:
            raise AdaptiveLineageContractError(
                f"survivor has unsupported type {type(survivor_raw)!r}"
            )
        if selected_id not in judged:
            raise AdaptiveLineageContractError(
                f"_select_survivor selected {selected_id!r}, absent from judged population"
            )
        return judged[selected_id]


# Backward-compatible name from the round-one patch.
VerifiedSelectSurvivorOracle = PrimitiveBackedOracle
