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
    "attempts",
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
    kwargs: dict[str, Any] = {}
    # Arena-level facts the live primitives require but the engine cannot
    # derive -- manifest, scenario, docker_image, target_identity_sha256 --
    # are injected by the caller through request.context (``--context-json``).
    # Splat them first with raw values so real dicts survive unflattened; the
    # engine-derived identity below always wins over caller-supplied keys.
    if isinstance(request.context, Mapping):
        for context_key, context_value in request.context.items():
            kwargs[str(context_key)] = context_value
    kwargs.update({
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
    })
    return kwargs


_TEAMS = ("red", "blue")


def _is_team_keyed(value: Any) -> bool:
    """True for the live primitives' ``{"red": [...], "blue": [...]}`` shape."""

    if not isinstance(value, Mapping) or not value:
        return False
    if not set(map(str, value)).issubset(set(_TEAMS)):
        return False
    return all(
        isinstance(entry, Sequence) and not isinstance(entry, (str, bytes))
        for entry in value.values()
    )


def _split_team_population(
    value: Mapping[str, Any], *, role: str, stage: str
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Scope a team-keyed population to one role and record its bad material.

    The live primitives interleave good and bad specimens inside each team list
    and distinguish them by ``status`` (``PASS`` survives the stage gate; ``BAD``
    from ``_population_genomes`` and ``BLOCKED`` from ``_review_population`` are
    bad genetic material). The engine is role-scoped, so only ``role``'s team is
    this lineage's population.

    Bad specimens stay IN the population: a generation materializes N specimens
    of which most are expected to be bad genetic material (SKILL.md), so the
    population is all N and badness is recorded alongside it, never subtracted.
    Dropping them here would both break the engine's ``population_size``
    contract and hide the lethality the lineage exists to measure. The live
    ``_review_population`` likewise consumes the full team-keyed genome map and
    gates the bad entries itself.
    """

    items: list[Mapping[str, Any]] = []
    bad: list[Mapping[str, Any]] = []
    for entry in value.get(role, []) or []:
        if not isinstance(entry, Mapping):
            continue
        record = dict(entry)
        items.append(record)
        if str(record.get("status") or "").upper() != "PASS":
            bad.append({**record, "source": str(record.get("source") or stage)})
    return items, bad


_JUDGE_ARENA_TARGET = ("arena", "team-public", "target")


def _require_judge_arena(
    judge_population: Callable[..., Any], generation_dir: Any
) -> None:
    """Fail closed when the generation dir carries no arena for the Judge.

    The live Judge replays each Red x Blue pair against the arena target and
    copies ``<generation_dir>/arena/team-public/target``. The canary's own flow
    runs a generation inside the arena-bearing run directory, so this coupling
    is implicit; when it is unmet the failure surfaces from deep inside
    ``shutil.copytree`` as a bare FileNotFoundError, after every specimen has
    already been compiled in Docker. Name the requirement instead.

    Only the live Judge contract needs this, so the check is gated on the
    primitive's own signature rather than applied to every judge callable.
    """

    if not isinstance(generation_dir, Path):
        return
    parameters = inspect.signature(judge_population).parameters
    if not {"scenario", "docker_image"}.issubset(parameters):
        return
    target = generation_dir.joinpath(*_JUDGE_ARENA_TARGET)
    if target.exists():
        return
    raise AdaptiveLineageContractError(
        "judge stage requires the arena target at "
        f"{target}; the generation directory must carry the battle's arena "
        "(run the generation inside the arena-bearing run directory, or stage "
        "that battle's arena/ tree there before judging)"
    )


def _judge_attempts_by_worker(
    raw: Any, *, role: str
) -> list[Mapping[str, Any]] | None:
    """Collapse the live Judge's pair-keyed attempts into per-worker records.

    The Judge replays every Red x Blue pair and reports attempts keyed
    ``<red_worker>__<blue_worker>``. A lineage's population is per WORKER and
    ``_select_survivor`` selects a worker id, so the judged population handed to
    the oracle must be per worker for this role's team -- otherwise the engine's
    "oracle may only select from the judged population" invariant, which is the
    anti-gaming guarantee, could never be satisfied on live data. Uses the same
    pair_id split the verified helper uses.
    """

    if not isinstance(raw, Mapping):
        return None
    attempts = raw.get("attempts")
    if not isinstance(attempts, Sequence) or isinstance(attempts, (str, bytes)):
        return None

    index = 0 if role == "red" else 1
    records: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            continue
        parts = str(attempt.get("pair_id") or "").split("__")
        if len(parts) <= index:
            continue
        worker_id = parts[index]
        if not worker_id:
            continue
        record = records.setdefault(
            worker_id,
            {
                "worker_id": worker_id,
                "candidate_id": worker_id,
                "team": role,
                "verdicts": [],
                "attempts": [],
            },
        )
        record["verdicts"].append(attempt.get("verdict"))
        record["attempts"].append(json_safe(attempt))
    return list(records.values())


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
        if _is_team_keyed(raw):
            items, bad = _split_team_population(
                raw, role=request.role, stage="population"
            )
            return PopulationStageResult(
                items=tuple(
                    {**item, "_adaptive_stage": "population"} for item in items
                ),
                bad_genetic_material=tuple(bad),
                raw=raw,
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
        # The live _review_population consumes the team-keyed genome map that
        # _population_genomes returned, not a flattened item list.
        if _is_team_keyed(generated.raw):
            kwargs["genomes"] = generated.raw
        raw = _invoke_compatible(self.bundle.review_population, kwargs)
        # Live shape: (reviewed_manifest, per-team pipeline records). That is a
        # payload pair, NOT the (items, bad) pair normalize_stage_result
        # assumes -- reading it as (items, bad) would file every review
        # pipeline record as bad genetic material.
        if (
            isinstance(raw, tuple)
            and len(raw) == 2
            and isinstance(raw[0], Mapping)
            and _is_team_keyed(raw[1])
        ):
            items, bad = _split_team_population(
                raw[1], role=request.role, stage="review"
            )
            return PopulationStageResult(
                items=tuple(
                    {**item, "_adaptive_stage": "review"} for item in items
                ),
                bad_genetic_material=tuple(bad),
                raw=raw,
            )
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
        # _judge_population judges only the review-PASS specimens, so it needs
        # the reviewed manifest and per-specimen pipelines that
        # _review_population returned as its 2-tuple payload.
        if isinstance(reviewed.raw, tuple) and len(reviewed.raw) == 2:
            kwargs["reviewed_manifest"] = reviewed.raw[0]
            kwargs["review_pipelines"] = reviewed.raw[1]
        _require_judge_arena(
            self.bundle.judge_population, kwargs.get("generation_dir")
        )
        raw = _invoke_compatible(self.bundle.judge_population, kwargs)
        live_items = _judge_attempts_by_worker(raw, role=request.role)
        if live_items is not None:
            return PopulationStageResult(
                items=tuple(
                    {**item, "_adaptive_stage": "judge"} for item in live_items
                ),
                raw=raw,
            )
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
        # The live _select_survivor(judge, team) reads the Judge's own verdict
        # payload, which the judge stage preserved verbatim as its raw result.
        if judged_population.judged.raw is not None:
            kwargs["judge"] = judged_population.judged.raw
        raw = _invoke_compatible(self.bundle.select_survivor, kwargs)
        live = self._live_selection(raw, request=request)
        if live is not None:
            return live
        survivor, bad, evidence, oracle_id = self._normalize_selection(
            raw, judged_population
        )
        return OracleSelection(
            survivor=survivor,
            bad_genetic_material=bad,
            evidence=evidence,
            oracle_id=oracle_id,
        )

    _LIVE_SELECTION_KEYS = (
        "selected_survivor",
        "survivor_worker_ids",
        "bad_worker_ids",
        "bad_genetic_material_rate",
    )

    def _live_selection(
        self, raw: Any, *, request: GenerationRequest
    ) -> OracleSelection | None:
        """Read the live ``_select_survivor`` payload on its own terms.

        The verified helper returns worker ids plus the population's bad rate,
        while the Judge payload it summarizes is keyed by PAIR
        (``red-0__blue-0``) -- so the selected worker id is legitimately absent
        from the judged items and must not be resolved against them. A
        ``selected_survivor`` of ``None`` is the common valid terminal: the whole
        generation was bad genetic material and the lineage dies without issue.
        """

        if not isinstance(raw, Mapping):
            return None
        if not any(key in raw for key in self._LIVE_SELECTION_KEYS):
            return None

        outcomes = raw.get("outcomes")
        outcomes = outcomes if isinstance(outcomes, Mapping) else {}
        selected = raw.get("selected_survivor")
        survivor: Mapping[str, Any] | None = None
        if selected not in (None, ""):
            worker_id = str(selected)
            survivor = {
                "worker_id": worker_id,
                "candidate_id": worker_id,
                "team": str(raw.get("team") or request.role),
                "outcomes": json_safe(outcomes.get(worker_id, {})),
            }
        bad_workers = raw.get("bad_worker_ids") or []
        # Every worker the Judge scored as a win is viable. The ones that were
        # not selected are retained runners-up, never bad genetic material:
        # they blocked the exploit (Blue) or landed it (Red).
        runners_up = [
            {
                "worker_id": str(worker),
                "candidate_id": str(worker),
                "team": str(raw.get("team") or request.role),
                "outcomes": json_safe(outcomes.get(str(worker), {})),
            }
            for worker in (raw.get("survivor_worker_ids") or [])
            if str(worker) != str(selected or "")
        ]
        return OracleSelection(
            runners_up=runners_up,
            survivor=survivor,
            bad_genetic_material={
                "schema": "battle.verified_primitive_bad_material.v1",
                "specimens": [
                    {
                        "worker_id": str(worker),
                        "candidate_id": str(worker),
                        "outcomes": json_safe(outcomes.get(str(worker), {})),
                    }
                    for worker in bad_workers
                ],
                "bad_genetic_material_rate": raw.get("bad_genetic_material_rate"),
            },
            evidence={
                "schema": "battle.verified_primitive_selection.v1",
                "selection": json_safe(raw),
            },
            oracle_id=self.oracle_id,
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
