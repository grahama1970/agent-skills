"""Battle V15 blocked 2x2 durable-memory contribution experiment.

This module intentionally stays narrower than a general experiment framework. It
freezes one Battle-004 source campaign, one Red and one Blue durable-memory
payload, twelve predeclared trials, and a deterministic bounded classifier.

Research basis (design input, not local proof):
- NIST full factorial designs:
  https://www.itl.nist.gov/div898/handbook/pri/section3/pri333.htm
- NIST randomized block designs:
  https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm
- Causal Agent Replay (stochastic counterfactual replay):
  https://arxiv.org/abs/2606.08275
- Causal Intervention-Based Memory Selection:
  https://arxiv.org/abs/2605.17641
- ACL 2026 empirical memory-management study:
  https://aclanthology.org/2026.acl-long.27/

The contract never upgrades three replicates per factorial cell into a broad
causal, population, production, or exploit-success claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

import httpx
import jsonschema

EXPERIMENT_SCHEMA = "battle.memory_ablation_experiment.v1"
TRIAL_SCHEMA = "battle.memory_ablation_trial.v1"
RESULT_SCHEMA = "battle.memory_ablation_result.v1"
PREFLIGHT_SCHEMA = "battle.memory_ablation_preflight_receipt.v1"

CONDITION_ORDER = ("R0B0", "R1B0", "R0B1", "R1B1")
TEAMS = ("red", "blue")
CLASSIFICATIONS = (
    "OBSERVED_BENEFIT",
    "NO_OBSERVED_EFFECT",
    "OBSERVED_REGRESSION",
    "INCONCLUSIVE",
)
INTERACTION_CLASSIFICATIONS = (
    "OBSERVED_INTERACTION",
    "NO_OBSERVED_INTERACTION",
    "INCONCLUSIVE",
)

RED_PERSONA = "battle-red-durable-memory-child"
BLUE_PERSONA = "battle-blue-durable-memory-child"
PROMPT_TEMPLATE = (
    "Create the next {team} artifact for the immutable public Arena target. "
    "An experiment context envelope is supplied. Use any relevant content when "
    "it is useful, but do not cite experiment or memory identifiers merely for "
    "compliance. Produce the strongest artifact and structured strategy_genome "
    "supported by public evidence. Battle and Judge retain outcome authority."
)
JUDGE_POLICY_ID = "battle-reviewed-red-blue-pair-v1"
RANDOMIZATION_ALGORITHM = "sha256-sort-v1"
ATTENTION_POLICY_ID = "battle-memory-ablation-attention-match-v1"
COMPARISON_POLICY_ID = "battle-memory-ablation-team-vector-v1"
FAILURE_POLICY_ID = "battle-memory-ablation-bounded-failure-v1"
MEMORY_COLLECTION = "battle_experiment_memory"


DEFECT_DISPOSITIONS = (
    ("D1", "Treatment must not force citation, method reuse, or artifact change."),
    ("D2", "Citation and reuse are descriptive mediators, not benefit evidence."),
    ("D3", "A genuine attention-matched memory-OFF path is required."),
    ("D4", "All conditions must use identical Red and Blue personas."),
    ("D5", "Red and Blue require separate team-specific Judge outcome vectors."),
    (
        "D6",
        "Security, attempts, duration, tokens, and cost must be captured when emitted.",
    ),
    (
        "D7",
        "Unavailable provider seed, temperature, identity, usage, and cost remain NOT_EMITTED.",
    ),
    ("D8", "Main effects must be contrasted at both opponent-memory levels."),
    (
        "D9",
        "Memory keys must be unique per experiment, block, condition, trial, and team.",
    ),
    (
        "D10",
        "All identifiers must derive from battle_id rather than hard-coded Battle-004 literals.",
    ),
    ("D11", "Team filtering is routing evidence and never a Memory-service ACL claim."),
    (
        "D12",
        "Each trial requires team outcomes, provider execution, pipelines, Judge, and costs when emitted.",
    ),
    (
        "D13",
        "V15 uses strict dedicated schemas instead of the permissive legacy fitness schema.",
    ),
    (
        "D14",
        "Run order, immutable hashes, and systemic failure handling must be frozen before execution.",
    ),
    ("D15", "Three replicates per cell permit bounded observed-effect language only."),
)

RESEARCH_SOURCES = (
    "https://www.itl.nist.gov/div898/handbook/pri/section3/pri333.htm",
    "https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm",
    "https://arxiv.org/abs/2606.08275",
    "https://arxiv.org/abs/2605.17641",
    "https://aclanthology.org/2026.acl-long.27/",
)


class ContractError(RuntimeError):
    """Raised when a V15 artifact violates the frozen contract."""


@dataclass(frozen=True)
class TrialBlocked(Exception):
    """Structured live-trial blocker used by the bounded retry policy."""

    family: str
    detail: str
    retryable: bool = True

    def __str__(self) -> str:
        return f"{self.family}: {self.detail}"


def _schema_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas"


def _schema(name: str) -> dict[str, Any]:
    return _read_json(_schema_dir() / name)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(root: Path) -> str:
    if not root.exists() or not root.is_dir():
        raise ContractError(f"required input tree missing: {root}")
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    if not entries:
        raise ContractError(f"required input tree is empty: {root}")
    return canonical_sha256(entries)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    if not cleaned:
        raise ContractError("identifier normalizes to an empty value")
    return cleaned


def condition_flags(condition_id: str) -> tuple[bool, bool]:
    if condition_id not in CONDITION_ORDER:
        raise ContractError(f"unsupported memory condition: {condition_id}")
    return condition_id[1] == "1", condition_id[3] == "1"


def _randomized_condition_order(seed: str, block_id: str) -> list[str]:
    return sorted(
        CONDITION_ORDER,
        key=lambda condition: hashlib.sha256(
            f"{RANDOMIZATION_ALGORITHM}:{seed}:{block_id}:{condition}".encode("utf-8")
        ).hexdigest(),
    )


def _optional_value(value: Any) -> dict[str, Any]:
    return {
        "status": "EMITTED" if value is not None else "NOT_EMITTED",
        "value": value,
    }


def _memory_tags(
    *,
    battle_id: str,
    experiment_id: str,
    trial_id: str,
    block_id: str,
    condition_id: str,
    team: str,
    source_memory_sha256: str,
) -> list[str]:
    """Return the exact identity tags shared by preflight and live recall."""

    return [
        "battle",
        "memory-ablation-v15",
        f"battle:{battle_id}",
        f"experiment:{experiment_id}",
        f"trial:{trial_id}",
        f"block:{block_id}",
        f"condition:{condition_id}",
        f"team:{team}",
        f"source-memory-sha:{source_memory_sha256}",
    ]


def _items_with_all_tags(
    items: Iterable[Any], required_tags: Iterable[str]
) -> list[dict[str, Any]]:
    required = set(required_tags)
    matches: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        tags = item.get("tags")
        if isinstance(tags, list) and required.issubset(set(tags)):
            matches.append(item)
    return matches


def _matches_memory_document(
    item: Any, document: Mapping[str, Any], required_tags: Iterable[str]
) -> bool:
    return (
        isinstance(item, dict)
        and item.get("_key") == document["_key"]
        and item.get("source_memory_sha256") == document["source_memory_sha256"]
        and item.get("solution") == document["solution"]
        and item.get("battle_id") == document["battle_id"]
        and item.get("experiment_id") == document["experiment_id"]
        and item.get("trial_id") == document["trial_id"]
        and item.get("block_id") == document["block_id"]
        and item.get("condition_id") == document["condition_id"]
        and item.get("team") == document["team"]
        and item.get("tags") == list(required_tags)
    )


def load_source_bindings(
    *, source_root: Path, memory_source_root: Path, battle_id: str
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load immutable V13/V14 source hashes without exposing runtime paths in the plan."""

    from .adaptive_memory_canary import _load_v13_source

    source_root = source_root.resolve()
    memory_source_root = memory_source_root.resolve()
    source = _load_v13_source(battle_id=battle_id, source_root=source_root)
    campaign_path = source_root / "campaign-receipt.json"
    selection_path = source_root / "selection-receipt.json"
    scenario_path = source_root / "generation-1" / "arena" / "scenario.json"
    research_root = source_root / "generation-2" / "arena" / "team-public" / "research"

    source_binding = {
        "source_campaign_run_id": str(source["campaign"]["run_id"]),
        "campaign_receipt_sha256": file_sha256(campaign_path),
        "selection_receipt_sha256": file_sha256(selection_path),
        "target_identity_sha256": str(source["target_identity_sha256"]),
        "scenario_sha256": file_sha256(scenario_path),
        "research_input_sha256": {
            team: _hash_tree(research_root / team) for team in TEAMS
        },
        "parent_genome_sha256": {
            team: str(source["genomes"][team]["sha256"]) for team in TEAMS
        },
        "parent_artifact_sha256": {
            team: str(source["artifacts"][team]["sha256"]) for team in TEAMS
        },
    }

    memory_sources: dict[str, dict[str, Any]] = {}
    for team in TEAMS:
        recall_path = (
            memory_source_root / "memory" / team / "memory-recall-receipt.json"
        )
        recall = _read_json(recall_path)
        document = recall.get("recalled_document")
        if recall.get("status") != "PASS" or not isinstance(document, dict):
            raise ContractError(f"V14 {team} exact recall receipt is not PASS")
        solution = document.get("solution")
        if not isinstance(solution, str) or not solution:
            raise ContractError(
                f"V14 {team} recalled document lacks structured solution"
            )
        try:
            parsed_solution = json.loads(solution)
        except json.JSONDecodeError as exc:
            raise ContractError(
                f"V14 {team} recalled solution is invalid JSON"
            ) from exc
        if not isinstance(parsed_solution, dict):
            raise ContractError(f"V14 {team} recalled solution must be an object")
        content_sha = recall.get("memory_content_sha256")
        if not isinstance(content_sha, str) or not re.fullmatch(
            r"[0-9a-f]{64}", content_sha
        ):
            raise ContractError(f"V14 {team} recall lacks memory content SHA-256")
        memory_sources[team] = {
            "memory_content_sha256": content_sha,
            "solution_sha256": hashlib.sha256(solution.encode("utf-8")).hexdigest(),
            "solution_json": json.dumps(
                parsed_solution, sort_keys=True, separators=(",", ":")
            ),
            "source_recall_receipt_sha256": file_sha256(recall_path),
        }
    return source_binding, memory_sources


def _context_base(
    *,
    experiment_id: str,
    trial_id: str,
    team: str,
    memory_on: bool,
    memory_source: Mapping[str, Any],
    memory_key: str,
) -> dict[str, Any]:
    if memory_on:
        parsed_solution = json.loads(str(memory_source["solution_json"]))
        payload: dict[str, Any] = {
            "summary": parsed_solution.get(
                "summary",
                "Frozen durable evidence is available as optional design input.",
            ),
            "strategy": parsed_solution.get("strategy", {}),
        }
        source_sha: str | None = str(memory_source["memory_content_sha256"])
        context_class = "frozen_durable_memory"
    else:
        payload = {
            "summary": "No durable memory is available in this control trial; use public evidence only.",
            "strategy": {
                "selected_methods": [],
                "rejected_methods": [],
                "parameters": {},
                "expected_observation": "not supplied by the control context",
            },
        }
        source_sha = None
        context_class = "attention_matched_control"
    return {
        "schema": "battle.memory_ablation_context.v1",
        "experiment_id": experiment_id,
        "trial_id": trial_id,
        "team": team,
        "memory_available": memory_on,
        "context_class": context_class,
        "memory_key": memory_key if memory_on else None,
        "source_memory_sha256": source_sha,
        "instructions": (
            "Use relevant supplied context only when useful. Do not cite memory, "
            "control, experiment, or receipt identifiers merely for compliance."
        ),
        "payload": payload,
        "authority": {
            "context_is_design_input_only": True,
            "battle_and_judge_retain_outcome_authority": True,
        },
        "attention_pad": "",
    }


def _pad_context(context: Mapping[str, Any], target_bytes: int) -> dict[str, Any]:
    value = json.loads(json.dumps(context))
    current = len(_canonical_bytes(value))
    if current > target_bytes:
        raise ContractError(
            f"attention context exceeds frozen byte budget: {current}>{target_bytes}"
        )
    value["attention_pad"] = "x" * (target_bytes - current)
    final = len(_canonical_bytes(value))
    if final != target_bytes:
        # The existing empty JSON string contributes the same quotes before and after;
        # ASCII padding therefore should be exact. Fail closed if an encoder changes.
        raise ContractError(f"attention padding failed: {final}!={target_bytes}")
    return value


def build_attention_matched_context(
    *,
    plan: Mapping[str, Any],
    trial: Mapping[str, Any],
    team: str,
    recalled_solution_json: str | None = None,
) -> dict[str, Any]:
    memory_on = bool(trial["condition"][f"{team}_memory"])
    memory_key = str(trial["memory_namespace"][f"{team}_key"])
    memory_source = dict(plan["immutable_inputs"]["memory_sources"][team])
    if recalled_solution_json is not None:
        if not memory_on:
            raise ContractError("OFF context cannot receive a recalled solution")
        if (
            hashlib.sha256(recalled_solution_json.encode("utf-8")).hexdigest()
            != memory_source["solution_sha256"]
        ):
            raise ContractError(
                f"{team} recalled solution differs from the frozen memory source"
            )
        memory_source["solution_json"] = recalled_solution_json
    base = _context_base(
        experiment_id=str(plan["experiment_id"]),
        trial_id=str(trial["trial_id"]),
        team=team,
        memory_on=memory_on,
        memory_source=memory_source,
        memory_key=memory_key,
    )
    padded = _pad_context(base, int(plan["controls"]["context_target_bytes"]))
    return {
        "envelope": padded,
        "sha256": canonical_sha256(padded),
        "bytes": len(_canonical_bytes(padded)),
        "token_match_status": "NOT_VERIFIABLE",
    }


def _minimum_context_target(
    *, experiment_id: str, memory_sources: Mapping[str, Mapping[str, Any]], minimum: int
) -> int:
    sizes: list[int] = []
    for team in TEAMS:
        for enabled in (False, True):
            sample = _context_base(
                experiment_id=experiment_id,
                trial_id="sample-trial",
                team=team,
                memory_on=enabled,
                memory_source=memory_sources[team],
                memory_key=f"sample:{team}",
            )
            sizes.append(len(_canonical_bytes(sample)))
    return max(minimum, max(sizes) + 512)


def _trial_binding_basis(
    *,
    battle_id: str,
    experiment_id: str,
    block_id: str,
    order_index: int,
    condition_id: str,
    red_memory: bool,
    blue_memory: bool,
    source_binding: Mapping[str, Any],
    memory_sources: Mapping[str, Mapping[str, Any]],
    personas: Mapping[str, str],
    prompt_hashes: Mapping[str, str],
    model: str,
    scillm_route_sha256: str,
    docker_image_identity: str,
    memory_namespace: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "battle_id": battle_id,
        "experiment_id": experiment_id,
        "block_id": block_id,
        "order_index": order_index,
        "condition_id": condition_id,
        "red_memory": red_memory,
        "blue_memory": blue_memory,
        "source_binding": dict(source_binding),
        "memory_source_sha256": {
            team: memory_sources[team]["memory_content_sha256"] for team in TEAMS
        },
        "personas": dict(personas),
        "prompt_template_sha256": dict(prompt_hashes),
        "model": model,
        "scillm_route_sha256": scillm_route_sha256,
        "docker_image_identity": docker_image_identity,
        "judge_policy_sha256": hashlib.sha256(
            JUDGE_POLICY_ID.encode("utf-8")
        ).hexdigest(),
        "memory_namespace": dict(memory_namespace),
    }


def build_experiment_plan(
    *,
    battle_id: str,
    experiment_id: str,
    source_binding: Mapping[str, Any],
    memory_sources: Mapping[str, Mapping[str, Any]],
    randomization_seed: str,
    docker_image: str,
    docker_image_identity: str,
    model: str,
    scillm_base_url: str,
    timeout_s: float,
    memory_collection: str | None = None,
    generated_at: str | None = None,
    context_minimum_bytes: int = 8192,
) -> dict[str, Any]:
    """Build one immutable, randomized-blocked 2x2x3 experiment plan."""

    if set(memory_sources) != set(TEAMS):
        raise ContractError("memory sources must contain exactly Red and Blue")
    experiment_id = _safe_id(experiment_id)
    if memory_collection is not None and memory_collection != MEMORY_COLLECTION:
        raise ContractError(
            f"Battle V15 memory collection must be exactly {MEMORY_COLLECTION}"
        )
    collection = MEMORY_COLLECTION
    context_target = _minimum_context_target(
        experiment_id=experiment_id,
        memory_sources=memory_sources,
        minimum=context_minimum_bytes,
    )
    personas = {
        "red": RED_PERSONA,
        "blue": BLUE_PERSONA,
    }
    prompt_hashes = {
        team: hashlib.sha256(
            PROMPT_TEMPLATE.format(team=team).encode("utf-8")
        ).hexdigest()
        for team in TEAMS
    }

    trials: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    for block_number in range(1, 4):
        block_id = f"block-{block_number:02d}"
        order = _randomized_condition_order(randomization_seed, block_id)
        block_trial_ids: list[str] = []
        for order_index, condition_id in enumerate(order, start=1):
            red_memory, blue_memory = condition_flags(condition_id)
            trial_id = f"{experiment_id}-b{block_number:02d}-o{order_index:02d}-{condition_id.lower()}"
            memory_namespace = {
                "collection": collection,
                "red_key": f"{battle_id}:{experiment_id}:{block_id}:{condition_id}:{trial_id}:red",
                "blue_key": f"{battle_id}:{experiment_id}:{block_id}:{condition_id}:{trial_id}:blue",
            }
            binding_basis = _trial_binding_basis(
                battle_id=battle_id,
                experiment_id=experiment_id,
                block_id=block_id,
                order_index=order_index,
                condition_id=condition_id,
                red_memory=red_memory,
                blue_memory=blue_memory,
                source_binding=source_binding,
                memory_sources=memory_sources,
                personas=personas,
                prompt_hashes=prompt_hashes,
                model=model,
                scillm_route_sha256=hashlib.sha256(
                    scillm_base_url.encode("utf-8")
                ).hexdigest(),
                docker_image_identity=docker_image_identity,
                memory_namespace=memory_namespace,
            )
            trial = {
                "trial_id": trial_id,
                "block_id": block_id,
                "replicate": block_number,
                "order_index": order_index,
                "condition_id": condition_id,
                "condition": {
                    "red_memory": red_memory,
                    "blue_memory": blue_memory,
                },
                "output_relpath": f"trials/{trial_id}",
                "memory_namespace": memory_namespace,
                "trial_input_binding_sha256": canonical_sha256(binding_basis),
            }
            trials.append(trial)
            block_trial_ids.append(trial_id)
        blocks.append(
            {
                "block_id": block_id,
                "replicate": block_number,
                "condition_order": order,
                "trial_ids": block_trial_ids,
            }
        )

    plan = {
        "schema": EXPERIMENT_SCHEMA,
        "status": "CONTRACT_VALIDATED",
        "experiment_id": experiment_id,
        "battle_id": battle_id,
        "generated_at": generated_at or _now(),
        "phase": "experiment_contract_review",
        "defect_dispositions": [
            {"defect_id": defect_id, "verdict": "CONFIRMED", "resolution": resolution}
            for defect_id, resolution in DEFECT_DISPOSITIONS
        ],
        "design": {
            "design_type": "blocked_full_factorial_2x2",
            "factors": ["red_memory", "blue_memory"],
            "factor_levels": ["OFF", "ON"],
            "block_count": 3,
            "trials_per_block": 4,
            "total_trials": 12,
            "condition_ids": list(CONDITION_ORDER),
        },
        "randomization": {
            "algorithm": RANDOMIZATION_ALGORITHM,
            "seed": randomization_seed,
            "blocks": blocks,
        },
        "immutable_inputs": {
            **dict(source_binding),
            "memory_sources": {team: dict(memory_sources[team]) for team in TEAMS},
            "personas": {
                team: {
                    "id": personas[team],
                    "sha256": hashlib.sha256(
                        personas[team].encode("utf-8")
                    ).hexdigest(),
                }
                for team in TEAMS
            },
            "prompt_template_sha256": prompt_hashes,
            "research_inputs_are_identical_across_conditions": True,
            "docker_image": docker_image,
            "docker_image_identity": docker_image_identity,
            "model": model,
            "scillm_route_sha256": hashlib.sha256(
                scillm_base_url.encode("utf-8")
            ).hexdigest(),
            "judge_policy_id": JUDGE_POLICY_ID,
            "judge_policy_sha256": hashlib.sha256(
                JUDGE_POLICY_ID.encode("utf-8")
            ).hexdigest(),
            "requested_seed": _optional_value(None),
            "requested_temperature": _optional_value(None),
            "timeout_s": timeout_s,
        },
        "controls": {
            "policy_id": ATTENTION_POLICY_ID,
            "same_personas": True,
            "same_prompt_shape": True,
            "same_public_context": True,
            "same_research_inputs": True,
            "same_model_request_shape": True,
            "same_docker_and_judge": True,
            "context_target_bytes": context_target,
            "token_match_status": "NOT_VERIFIABLE",
            "on_use_is_optional": True,
            "off_service_calls_after_preflight": 0,
        },
        "provider_matching": {
            "visible_request_fields_bound": True,
            "seed_matching": "NOT_VERIFIABLE",
            "temperature_matching": "NOT_VERIFIABLE",
            "provider_identity_required": False,
            "missing_fields_are_not_emitted": True,
            "repeated_calls_are_not_deterministic": True,
        },
        "failure_policy": {
            "policy_id": FAILURE_POLICY_ID,
            "max_attempts_per_trial_blocker": 2,
            "max_identical_failures_per_family": 3,
            "systemic_failure_action": "stop_family_mark_remaining_blocked_continue_independent_families",
            "valid_but_poor_output_is_not_retryable": True,
            "replacement_trials_forbidden": True,
        },
        "aggregation_policy": {
            "policy_id": COMPARISON_POLICY_ID,
            "security_outcomes_precede_efficiency": True,
            "duration_tie_fraction": 0.10,
            "benefit_min_positive_contrasts": 4,
            "regression_min_negative_contrasts": 4,
            "required_contrasts_per_team": 6,
            "interaction_reversal_blocks_required": 2,
            "classifications": list(CLASSIFICATIONS),
            "interaction_classifications": list(INTERACTION_CLASSIFICATIONS),
        },
        "trials": trials,
        "claims": {
            "may_claim": [
                "bounded observed memory contribution for one immutable Battle-004 arena",
                "separate Red and Blue classifications under the frozen comparison policy",
            ],
            "must_not_claim": [
                "population-scale causal effect",
                "general memory improvement",
                "production readiness",
                "exploit success beyond the exact Judge receipts",
                "deterministic provider replay",
                "Memory service ACL enforcement",
            ],
        },
        "research_sources": list(RESEARCH_SOURCES),
    }
    validate_experiment_plan(plan)
    return plan


def validate_experiment_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    try:
        jsonschema.validate(
            plan, _schema("battle.memory_ablation_experiment.v1.schema.json")
        )
    except jsonschema.ValidationError as exc:
        raise ContractError(
            f"experiment schema validation failed: {exc.message}"
        ) from exc
    errors: list[str] = []
    trials = list(plan.get("trials", []))
    if len(trials) != 12:
        errors.append("experiment must contain exactly 12 predeclared trials")
    if len({trial["trial_id"] for trial in trials}) != len(trials):
        errors.append("trial ids must be unique")
    if len({trial["output_relpath"] for trial in trials}) != len(trials):
        errors.append("trial output paths must be unique")
    conditions = {condition: 0 for condition in CONDITION_ORDER}
    key_values: set[str] = set()
    immutable = plan["immutable_inputs"]
    personas = {team: immutable["personas"][team]["id"] for team in TEAMS}
    prompt_hashes = immutable["prompt_template_sha256"]
    source_binding = {
        key: immutable[key]
        for key in (
            "source_campaign_run_id",
            "campaign_receipt_sha256",
            "selection_receipt_sha256",
            "target_identity_sha256",
            "scenario_sha256",
            "research_input_sha256",
            "parent_genome_sha256",
            "parent_artifact_sha256",
        )
    }
    for trial in trials:
        condition_id = trial["condition_id"]
        conditions[condition_id] = conditions.get(condition_id, 0) + 1
        expected_red, expected_blue = condition_flags(condition_id)
        if trial["condition"] != {
            "red_memory": expected_red,
            "blue_memory": expected_blue,
        }:
            errors.append(f"trial {trial['trial_id']} condition flags disagree with id")
        expected_basis = _trial_binding_basis(
            battle_id=str(plan["battle_id"]),
            experiment_id=str(plan["experiment_id"]),
            block_id=str(trial["block_id"]),
            order_index=int(trial["order_index"]),
            condition_id=str(condition_id),
            red_memory=expected_red,
            blue_memory=expected_blue,
            source_binding=source_binding,
            memory_sources=immutable["memory_sources"],
            personas=personas,
            prompt_hashes=prompt_hashes,
            model=str(immutable["model"]),
            scillm_route_sha256=str(immutable["scillm_route_sha256"]),
            docker_image_identity=str(immutable["docker_image_identity"]),
            memory_namespace=trial["memory_namespace"],
        )
        if trial["trial_input_binding_sha256"] != canonical_sha256(expected_basis):
            errors.append(f"trial {trial['trial_id']} input binding hash mismatch")
        if trial["memory_namespace"]["collection"] != MEMORY_COLLECTION:
            errors.append(
                f"trial {trial['trial_id']} memory collection must be exactly "
                f"{MEMORY_COLLECTION}"
            )
        expected_prefix = f"{plan['battle_id']}:{plan['experiment_id']}:"
        for key_name in ("red_key", "blue_key"):
            key = trial["memory_namespace"][key_name]
            if key in key_values:
                errors.append(f"memory key reused across trials: {key}")
            if not str(key).startswith(expected_prefix):
                errors.append(
                    f"trial {trial['trial_id']} memory key is outside experiment namespace"
                )
            key_values.add(key)
    if conditions != {condition: 3 for condition in CONDITION_ORDER}:
        errors.append("each 2x2 condition must appear exactly three times")

    blocks = plan["randomization"]["blocks"]
    if len(blocks) != 3:
        errors.append("experiment must contain exactly three matched blocks")
    for block in blocks:
        expected_order = _randomized_condition_order(
            str(plan["randomization"]["seed"]), str(block["block_id"])
        )
        if block["condition_order"] != expected_order:
            errors.append(
                f"block {block['block_id']} order differs from frozen randomization"
            )
        if sorted(block["condition_order"]) != sorted(CONDITION_ORDER):
            errors.append(
                f"block {block['block_id']} is not a complete 2x2 permutation"
            )
        block_trials = [
            trial for trial in trials if trial["block_id"] == block["block_id"]
        ]
        if len(block_trials) != 4:
            errors.append(f"block {block['block_id']} must contain four trials")
        ordered = [
            trial["condition_id"]
            for trial in sorted(block_trials, key=lambda item: item["order_index"])
        ]
        if ordered != block["condition_order"]:
            errors.append(f"block {block['block_id']} order disagrees with trials")

    if immutable["docker_image_identity"] in {"", "NOT_EMITTED", None}:
        errors.append("live approval requires an immutable Docker image identity")
    for team in TEAMS:
        source = immutable["memory_sources"][team]
        try:
            solution = str(source["solution_json"])
            json.loads(solution)
        except (KeyError, json.JSONDecodeError):
            errors.append(f"{team} frozen memory solution is invalid")
            continue
        if (
            hashlib.sha256(solution.encode("utf-8")).hexdigest()
            != source["solution_sha256"]
        ):
            errors.append(f"{team} frozen memory solution hash mismatch")
    dispositions = plan.get("defect_dispositions")
    expected_dispositions = [
        {"defect_id": defect_id, "verdict": "CONFIRMED", "resolution": resolution}
        for defect_id, resolution in DEFECT_DISPOSITIONS
    ]
    if dispositions != expected_dispositions:
        errors.append("D1-D15 defect dispositions differ from the frozen review")
    forbidden_claims = " ".join(plan["claims"]["may_claim"]).lower()
    if any(
        term in forbidden_claims
        for term in ("population", "general improvement", "production ready")
    ):
        errors.append("plan may_claim exceeds the bounded Battle-004 experiment")
    if errors:
        raise ContractError("\n".join(errors))
    return {
        "schema": "battle.memory_ablation_experiment_validation.v1",
        "status": "PASS",
        "approval": "CONTRACT_VALIDATED",
        "experiment_id": plan["experiment_id"],
        "trial_count": 12,
        "condition_counts": conditions,
        "plan_sha256": canonical_sha256(plan),
    }


def write_experiment_plan(*, plan: Mapping[str, Any], out: Path) -> dict[str, Any]:
    validate = validate_experiment_plan(plan)
    plan_path = _write_json(out / "memory-ablation-experiment.json", plan)
    validate = {**validate, "plan_file_sha256": file_sha256(plan_path)}
    _write_json(out / "memory-ablation-experiment.validation.json", validate)
    return validate


def _request_envelope(
    *,
    plan: Mapping[str, Any],
    trial: Mapping[str, Any],
    team: str,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    immutable = plan["immutable_inputs"]
    envelope = {
        "trial_id": trial["trial_id"],
        "team": team,
        "condition_id": trial["condition_id"],
        "persona_id": immutable["personas"][team]["id"],
        "persona_sha256": immutable["personas"][team]["sha256"],
        "prompt_template_sha256": immutable["prompt_template_sha256"][team],
        "public_context_sha256": immutable["scenario_sha256"],
        "research_input_sha256": immutable["research_input_sha256"][team],
        "experiment_context_sha256": context["sha256"],
        "model": immutable["model"],
        "scillm_route_sha256": immutable["scillm_route_sha256"],
        "timeout_s": immutable["timeout_s"],
        "requested_seed": immutable["requested_seed"],
        "requested_temperature": immutable["requested_temperature"],
    }
    return {"envelope": envelope, "sha256": canonical_sha256(envelope)}


def build_trial_input_binding(
    *,
    plan: Mapping[str, Any],
    trial: Mapping[str, Any],
    recalled_solutions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    recalled_solutions = recalled_solutions or {}
    contexts = {
        team: build_attention_matched_context(
            plan=plan,
            trial=trial,
            team=team,
            recalled_solution_json=recalled_solutions.get(team),
        )
        for team in TEAMS
    }
    requests = {
        team: _request_envelope(
            plan=plan, trial=trial, team=team, context=contexts[team]
        )
        for team in TEAMS
    }
    binding = {
        "experiment_plan_sha256": canonical_sha256(plan),
        "trial_input_binding_sha256": trial["trial_input_binding_sha256"],
        "immutable_inputs": {
            key: plan["immutable_inputs"][key]
            for key in (
                "campaign_receipt_sha256",
                "selection_receipt_sha256",
                "target_identity_sha256",
                "scenario_sha256",
                "research_input_sha256",
                "parent_genome_sha256",
                "parent_artifact_sha256",
                "docker_image_identity",
                "judge_policy_sha256",
            )
        },
        "contexts": contexts,
        "request_envelopes": requests,
    }
    return binding


def resolve_docker_image_identity(image: str) -> str:
    """Return the local immutable Docker image id used by the live experiment."""

    completed = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    identity = completed.stdout.strip()
    if completed.returncode != 0 or not identity:
        detail = completed.stderr.strip() or "Docker image identity unavailable"
        raise ContractError(detail)
    return identity


def _validate_source_root_against_plan(
    *, plan: Mapping[str, Any], source_root: Path
) -> None:
    from .adaptive_memory_canary import _load_v13_source

    source_root = source_root.resolve()
    source = _load_v13_source(battle_id=str(plan["battle_id"]), source_root=source_root)
    immutable = plan["immutable_inputs"]
    checks = {
        "campaign_receipt_sha256": file_sha256(source_root / "campaign-receipt.json"),
        "selection_receipt_sha256": file_sha256(source_root / "selection-receipt.json"),
        "target_identity_sha256": str(source["target_identity_sha256"]),
        "scenario_sha256": file_sha256(
            source_root / "generation-1" / "arena" / "scenario.json"
        ),
    }
    for key, actual in checks.items():
        if immutable[key] != actual:
            raise ContractError(f"live source binding mismatch for {key}")
    research_root = source_root / "generation-2" / "arena" / "team-public" / "research"
    for team in TEAMS:
        if immutable["research_input_sha256"][team] != _hash_tree(research_root / team):
            raise ContractError(f"live source research binding mismatch for {team}")
        if immutable["parent_genome_sha256"][team] != source["genomes"][team]["sha256"]:
            raise ContractError(f"live source genome binding mismatch for {team}")
        if (
            immutable["parent_artifact_sha256"][team]
            != source["artifacts"][team]["sha256"]
        ):
            raise ContractError(f"live source artifact binding mismatch for {team}")


def _json_command(*, command: list[str], cwd: Path, label: str) -> dict[str, Any]:
    environment = os.environ.copy()
    # Battle and Tau require different Python versions. Never let a nested Tau
    # uv process repurpose Battle's active project environment in place.
    environment.pop("UV_PROJECT_ENVIRONMENT", None)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise ContractError(f"{label} failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError(f"{label} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{label} did not return a JSON object")
    return payload


def _tau_runtime_readiness(*, tau_root: Path) -> dict[str, Any]:
    root = tau_root.expanduser().resolve()
    if not (root / "pyproject.toml").is_file():
        raise ContractError(f"Tau root is not a Tau checkout: {root}")
    doctor = _json_command(
        command=["uv", "run", "tau", "doctor"], cwd=root, label="Tau doctor"
    )
    lanes = doctor.get("lanes") if isinstance(doctor.get("lanes"), dict) else {}
    if (
        doctor.get("schema") != "tau.doctor.v1"
        or doctor.get("status") != "PASS"
        or doctor.get("ok") is not True
        or doctor.get("mocked") is not False
        or doctor.get("live") is not True
        or lanes.get("local_cli", {}).get("ready") is not True
        or lanes.get("local_sanity", {}).get("ready") is not True
    ):
        raise ContractError("Tau doctor did not establish local runtime readiness")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit.stdout.strip()):
        raise ContractError("Tau Git identity is unavailable")
    return {
        "status": "PASS",
        "schema": doctor["schema"],
        "receipt_sha256": canonical_sha256(doctor),
        "tau_git_commit": commit.stdout.strip(),
        "local_cli_ready": True,
        "local_sanity_ready": True,
        "mocked": False,
        "live": True,
    }


def _scillm_auth_readiness(
    *, tau_root: Path, scillm_base_url: str, model: str
) -> dict[str, Any]:
    script = (
        "import json,sys; "
        "from tau_coding.battle_scillm import preflight_battle_scillm_auth; "
        "print(json.dumps(preflight_battle_scillm_auth("
        "scillm_base_url=sys.argv[1], model=sys.argv[2], allow_repair=False), "
        "sort_keys=True))"
    )
    auth = _json_command(
        command=["uv", "run", "python", "-c", script, scillm_base_url, model],
        cwd=tau_root.expanduser().resolve(),
        label="SciLLM auth preflight",
    )
    if (
        auth.get("schema") != "tau.battle_scillm_auth_preflight.v1"
        or auth.get("status") != "PASS"
        or auth.get("ok") is not True
        or auth.get("mocked") is not False
        or auth.get("live") is not True
    ):
        raise ContractError(
            f"SciLLM endpoint/auth readiness failed: {auth.get('errors') or auth.get('reason')}"
        )
    return {
        "status": "PASS",
        "schema": auth["schema"],
        "receipt_sha256": canonical_sha256(auth),
        "base_url_sha256": hashlib.sha256(
            scillm_base_url.rstrip("/").encode("utf-8")
        ).hexdigest(),
        "model": model,
        "http_status": auth.get("status_code"),
        "api_key_present": auth.get("api_key_present") is True,
        "repair_attempted": auth.get("repair_attempted") is True,
        "mocked": False,
        "live": True,
    }


def _judge_readiness(*, plan: Mapping[str, Any]) -> dict[str, Any]:
    from .adaptive_red_blue_lineage_canary import _judge_reviewed_generation
    from .arena_live_battle_proof import _judge_tau_artifacts

    policy_sha256 = hashlib.sha256(JUDGE_POLICY_ID.encode("utf-8")).hexdigest()
    if plan["immutable_inputs"]["judge_policy_id"] != JUDGE_POLICY_ID:
        raise ContractError("Judge policy id differs from the executable policy")
    if plan["immutable_inputs"]["judge_policy_sha256"] != policy_sha256:
        raise ContractError("Judge policy hash differs from the executable policy")
    if not callable(_judge_reviewed_generation) or not callable(_judge_tau_artifacts):
        raise ContractError("Judge runtime entry points are not callable")
    files = {
        "reviewed_pair": Path(__file__).with_name("adaptive_red_blue_lineage_canary.py"),
        "judge_runtime": Path(__file__).with_name("arena_live_battle_proof.py"),
        "judge_core": Path(__file__).with_name("judge.py"),
    }
    if not all(path.is_file() for path in files.values()):
        raise ContractError("Judge executable source is incomplete")
    return {
        "status": "PASS",
        "policy_id": JUDGE_POLICY_ID,
        "policy_sha256": policy_sha256,
        "executable_sha256": {
            name: file_sha256(path) for name, path in files.items()
        },
        "reviewed_pair_entrypoint_ready": True,
        "judge_runtime_entrypoint_ready": True,
    }


def _expected_trial_output_paths(
    *, plan: Mapping[str, Any], experiment_root: Path
) -> dict[Path, Mapping[str, Any]]:
    root = experiment_root.expanduser().resolve()
    expected = {
        root / str(trial["output_relpath"]): trial for trial in plan["trials"]
    }
    unknown_paths: list[str] = []
    for parent in {path.parent for path in expected}:
        if not parent.exists():
            continue
        if parent.is_symlink() or not parent.is_dir():
            raise ContractError(f"trial output parent is not a directory: {parent}")
        for child in parent.iterdir():
            if child.is_symlink() or child not in expected:
                unknown_paths.append(str(child.relative_to(root)))
    if unknown_paths:
        raise ContractError(
            f"unknown trial output paths exist: {sorted(unknown_paths)}"
        )
    return expected


def _assert_unused_trial_outputs(
    *,
    plan: Mapping[str, Any],
    experiment_root: Path,
    reusable_trial_ids: Iterable[str] = (),
) -> dict[str, Any]:
    root = experiment_root.expanduser().resolve()
    _expected_trial_output_paths(plan=plan, experiment_root=root)
    reusable = set(reusable_trial_ids)
    used = {
        str(trial["trial_id"]): str(trial["output_relpath"])
        for trial in plan["trials"]
        if (root / str(trial["output_relpath"])).exists()
    }
    unexpected = [
        output_relpath
        for trial_id, output_relpath in used.items()
        if trial_id not in reusable
    ]
    if unexpected:
        raise ContractError(
            f"predeclared trial output paths are already used: {unexpected}"
        )
    return {
        "status": "PASS",
        "checked_count": len(plan["trials"]),
        "used": sorted(used.values()),
    }


def _existing_memory_keys(
    *, client: httpx.Client, collection: str, keys: Iterable[str]
) -> list[str]:
    existing: list[str] = []
    for key in keys:
        response = client.post(
            "/list",
            json={"collection": collection, "limit": 2, "filters": {"_key": key}},
        )
        response.raise_for_status()
        body = response.json()
        documents = body.get("documents") if isinstance(body, dict) else None
        if isinstance(documents, list) and any(
            isinstance(item, dict) and item.get("_key") == key for item in documents
        ):
            existing.append(key)
    return existing


def _load_public_research_context(*, source_root: Path, team: str) -> dict[str, Any]:
    root = source_root / "generation-2" / "arena" / "team-public" / "research" / team
    receipts: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(root.rglob("*.json")):
        total_bytes += path.stat().st_size
        if len(receipts) >= 64 or total_bytes > 2_000_000:
            raise ContractError(
                f"{team} public research context exceeds bounded limits"
            )
        receipts.append(
            {
                "artifact_label": path.relative_to(root).as_posix(),
                "sha256": file_sha256(path),
                "payload": _read_json(path),
            }
        )
    if not receipts:
        raise ContractError(f"{team} public research context is empty")
    return {
        "tree_sha256": _hash_tree(root),
        "receipt_count": len(receipts),
        "receipts": receipts,
    }


def preflight_experiment(
    *,
    plan: Mapping[str, Any],
    source_root: Path,
    memory_base_url: str,
    scillm_base_url: str,
    tau_root: Path,
    experiment_root: Path,
    plan_file_sha256: str | None = None,
    reusable_trial_ids: Iterable[str] = (),
    reusable_memory_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """Fail closed until every dependency for the frozen live trial set is ready."""

    validate_experiment_plan(plan)
    _validate_source_root_against_plan(plan=plan, source_root=source_root)
    actual_docker_identity = resolve_docker_image_identity(
        str(plan["immutable_inputs"]["docker_image"])
    )
    if actual_docker_identity != plan["immutable_inputs"]["docker_image_identity"]:
        raise ContractError("Docker image identity differs from the frozen plan")
    expected_route = plan["immutable_inputs"]["scillm_route_sha256"]
    actual_route = hashlib.sha256(scillm_base_url.encode("utf-8")).hexdigest()
    if actual_route != expected_route:
        raise ContractError("SciLLM route differs from the frozen experiment plan")

    output_readiness = _assert_unused_trial_outputs(
        plan=plan,
        experiment_root=experiment_root,
        reusable_trial_ids=reusable_trial_ids,
    )
    tau_readiness = _tau_runtime_readiness(tau_root=tau_root)
    scillm_readiness = _scillm_auth_readiness(
        tau_root=tau_root,
        scillm_base_url=scillm_base_url,
        model=str(plan["immutable_inputs"]["model"]),
    )
    judge_readiness = _judge_readiness(plan=plan)

    collection = MEMORY_COLLECTION
    probe_trial_id = f"{plan['experiment_id']}-preflight"
    probe_block_id = "preflight"
    probe_condition_id = "preflight"
    probe_team = "red"
    probe_key = (
        f"{plan['battle_id']}:{plan['experiment_id']}:{probe_block_id}:"
        f"{probe_condition_id}:{probe_trial_id}:{probe_team}"
    )
    probe_solution = json.dumps(
        {
            "kind": "memory-ablation-preflight",
            "battle_id": plan["battle_id"],
            "experiment_id": plan["experiment_id"],
            "trial_id": probe_trial_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    probe_source_sha256 = hashlib.sha256(probe_solution.encode("utf-8")).hexdigest()
    probe_tags = _memory_tags(
        battle_id=str(plan["battle_id"]),
        experiment_id=str(plan["experiment_id"]),
        trial_id=probe_trial_id,
        block_id=probe_block_id,
        condition_id=probe_condition_id,
        team=probe_team,
        source_memory_sha256=probe_source_sha256,
    )
    document = {
        "_key": probe_key,
        "kind": "battle_memory_ablation_preflight",
        "battle_id": plan["battle_id"],
        "experiment_id": plan["experiment_id"],
        "trial_id": probe_trial_id,
        "block_id": probe_block_id,
        "condition_id": probe_condition_id,
        "team": probe_team,
        "source_memory_sha256": probe_source_sha256,
        "problem": "Battle V15 memory service exact-recall preflight",
        "solution": probe_solution,
        "tags": probe_tags,
        "status": "preflight_probe",
    }
    try:
        with httpx.Client(
            base_url=memory_base_url, timeout=httpx.Timeout(30.0, connect=3.0)
        ) as client:
            health = client.get("/health")
            health.raise_for_status()
            planned_keys = [
                str(trial["memory_namespace"][f"{team}_key"])
                for trial in plan["trials"]
                for team in TEAMS
            ]
            existing_keys = _existing_memory_keys(
                client=client, collection=collection, keys=planned_keys
            )
            reusable_keys = set(reusable_memory_keys)
            unexpected_existing_keys = sorted(set(existing_keys) - reusable_keys)
            if unexpected_existing_keys:
                raise ContractError(
                    "Memory trial namespace contains keys that are not bound to "
                    f"validated resumed trials: {unexpected_existing_keys}"
                )
            write = client.post(
                "/upsert", json={"collection": collection, "documents": [document]}
            )
            write.raise_for_status()
            write_body = write.json()
            write_errors = (
                write_body.get("errors") if isinstance(write_body, dict) else None
            )
            write_count = (
                int(write_body.get("inserted", 0) or 0)
                + int(write_body.get("updated", 0) or 0)
                if isinstance(write_body, dict)
                else 0
            )
            if write_errors or write_count != 1:
                raise ContractError(
                    "Memory preflight probe upsert did not write exactly one record"
                )
            recalled: dict[str, Any] | None = None
            for attempt in range(10):
                response = client.post(
                    "/recall",
                    json={
                        "q": document["problem"],
                        "k": 3,
                        "collections": [collection],
                        "tags": probe_tags,
                        "threshold": 0.0,
                    },
                )
                response.raise_for_status()
                body = response.json()
                items = body.get("items") if isinstance(body, dict) else None
                if isinstance(items, list):
                    matches = [
                        item
                        for item in items
                        if isinstance(item, dict)
                        and item.get("_key") == probe_key
                        and item.get("solution") == probe_solution
                        and item.get("battle_id") == plan["battle_id"]
                        and item.get("experiment_id") == plan["experiment_id"]
                        and item.get("trial_id") == probe_trial_id
                        and item.get("block_id") == probe_block_id
                        and item.get("condition_id") == probe_condition_id
                        and item.get("team") == probe_team
                        and item.get("source_memory_sha256") == probe_source_sha256
                        and item.get("tags") == probe_tags
                    ]
                    if len(matches) == 1:
                        recalled = matches[0]
                        break
                if attempt < 9:
                    time.sleep(1)

            opposite_team_tags = [
                tag for tag in probe_tags if not tag.startswith("team:")
            ] + ["team:blue"]
            opposite_team_response = client.post(
                "/recall",
                json={
                    "q": document["problem"],
                    "k": 3,
                    "collections": [collection],
                    "tags": opposite_team_tags,
                    "threshold": 0.0,
                },
            )
            opposite_team_response.raise_for_status()
            opposite_team_body = opposite_team_response.json()
            opposite_team_items = (
                opposite_team_body.get("items")
                if isinstance(opposite_team_body, dict)
                else None
            )
            if not isinstance(opposite_team_items, list):
                raise ContractError(
                    "Memory preflight opposite-team recall response lacks items"
                )
            opposite_team_matches = _items_with_all_tags(
                opposite_team_items, opposite_team_tags
            )
            if opposite_team_matches:
                raise ContractError(
                    "Memory preflight opposite-team isolation returned records"
                )

            other_trial_tags = [
                tag for tag in probe_tags if not tag.startswith("trial:")
            ] + [f"trial:{probe_trial_id}-other"]
            other_trial_response = client.post(
                "/recall",
                json={
                    "q": document["problem"],
                    "k": 3,
                    "collections": [collection],
                    "tags": other_trial_tags,
                    "threshold": 0.0,
                },
            )
            other_trial_response.raise_for_status()
            other_trial_body = other_trial_response.json()
            other_trial_items = (
                other_trial_body.get("items")
                if isinstance(other_trial_body, dict)
                else None
            )
            if not isinstance(other_trial_items, list):
                raise ContractError(
                    "Memory preflight other-trial recall response lacks items"
                )
            other_trial_matches = _items_with_all_tags(
                other_trial_items, other_trial_tags
            )
            if other_trial_matches:
                raise ContractError(
                    "Memory preflight other-trial isolation returned records"
                )
    except httpx.HTTPError as exc:
        raise ContractError(f"Memory preflight failed: {exc}") from exc
    if recalled is None:
        raise ContractError("Memory preflight exact recall did not converge")
    source_binding = {
        key: plan["immutable_inputs"][key]
        for key in (
            "campaign_receipt_sha256",
            "selection_receipt_sha256",
            "target_identity_sha256",
            "scenario_sha256",
            "research_input_sha256",
            "parent_genome_sha256",
            "parent_artifact_sha256",
        )
    }
    return {
        "schema": PREFLIGHT_SCHEMA,
        "status": "PASS",
        "approval": "APPROVED_FOR_LIVE",
        "experiment_id": plan["experiment_id"],
        "experiment_plan_sha256": canonical_sha256(plan),
        "experiment_plan_file_sha256": plan_file_sha256,
        "source_binding": {"status": "PASS", "immutable": source_binding},
        "docker_image_identity": actual_docker_identity,
        "tau_readiness": tau_readiness,
        "scillm_readiness": scillm_readiness,
        "judge_readiness": judge_readiness,
        "output_readiness": output_readiness,
        "memory_readiness": {
            "status": "PASS",
            "base_url_sha256": hashlib.sha256(memory_base_url.encode("utf-8")).hexdigest(),
            "health_response_sha256": canonical_sha256(health.json()),
            "collection": collection,
            "planned_key_count": len(planned_keys),
            "existing_planned_key_count": len(existing_keys),
            "namespace_clean": True,
            "probe_key_sha256": hashlib.sha256(probe_key.encode("utf-8")).hexdigest(),
            "probe_document_sha256": canonical_sha256(document),
            "probe_write_response_sha256": canonical_sha256(write_body),
            "probe_recalled_sha256": canonical_sha256(recalled),
            "exact_write_recall_passed": True,
            "opposite_team_item_count": len(opposite_team_matches),
            "other_trial_item_count": len(other_trial_matches),
            "exact_isolation_passed": True,
        },
        "credentials_exposed": False,
        "created_at": _now(),
    }


def _memory_document(
    *, plan: Mapping[str, Any], trial: Mapping[str, Any], team: str
) -> dict[str, Any]:
    source = plan["immutable_inputs"]["memory_sources"][team]
    key = trial["memory_namespace"][f"{team}_key"]
    solution = str(source["solution_json"])
    return {
        "_key": key,
        "kind": "battle_memory_ablation_frozen_source",
        "battle_id": plan["battle_id"],
        "experiment_id": plan["experiment_id"],
        "trial_id": trial["trial_id"],
        "block_id": trial["block_id"],
        "condition_id": trial["condition_id"],
        "team": team,
        "source_memory_sha256": source["memory_content_sha256"],
        "problem": "What frozen selected evidence is available for this bounded memory ablation trial?",
        "solution": solution,
        "tags": _memory_tags(
            battle_id=str(plan["battle_id"]),
            experiment_id=str(plan["experiment_id"]),
            trial_id=str(trial["trial_id"]),
            block_id=str(trial["block_id"]),
            condition_id=str(trial["condition_id"]),
            team=team,
            source_memory_sha256=str(source["memory_content_sha256"]),
        ),
        "status": "current",
    }


def _write_and_recall_memory(
    *,
    client: httpx.Client,
    collection: str,
    plan: Mapping[str, Any],
    trial: Mapping[str, Any],
    team: str,
    out_dir: Path,
) -> dict[str, Any]:
    document = _memory_document(plan=plan, trial=trial, team=team)
    write_response = client.post(
        "/upsert", json={"collection": collection, "documents": [document]}
    )
    write_response.raise_for_status()
    write_body = write_response.json()
    write_receipt = {
        "schema": "battle.memory_ablation_write_receipt.v1",
        "status": "PASS",
        "team": team,
        "collection": collection,
        "memory_key": document["_key"],
        "source_memory_sha256": document["source_memory_sha256"],
        "request_document_sha256": canonical_sha256(document),
        "service_response_sha256": canonical_sha256(write_body),
        "mocked": False,
        "live": True,
        "created_at": _now(),
    }
    write_path = _write_json(out_dir / f"{team}-memory-write.json", write_receipt)
    write_receipt["receipt_sha256"] = file_sha256(write_path)

    exact: list[dict[str, Any]] = []
    recall_body: Any = None
    recall_request_count = 0
    exact_lookup_request_count = 0
    recall_tags = list(document["tags"])
    for attempt in range(10):
        recall_request_count += 1
        response = client.post(
            "/recall",
            json={
                "q": document["problem"],
                "k": 5,
                "collections": [collection],
                "tags": recall_tags,
                "threshold": 0.0,
            },
        )
        response.raise_for_status()
        recall_body = response.json()
        items = recall_body.get("items") if isinstance(recall_body, dict) else None
        if not isinstance(items, list):
            raise TrialBlocked("memory_service", "recall response lacks items")
        exact = [
            item
            for item in items
            if _matches_memory_document(item, document, recall_tags)
        ]
        if len(exact) == 1:
            break
        if attempt < 9:
            time.sleep(1)
    exact_match_source = "recall"
    exact_lookup_body: Any = None
    if len(exact) != 1:
        exact_lookup_request_count += 1
        lookup_response = client.post(
            "/list",
            json={
                "collection": collection,
                "limit": 2,
                "filters": {"_key": document["_key"]},
            },
        )
        lookup_response.raise_for_status()
        exact_lookup_body = lookup_response.json()
        documents = (
            exact_lookup_body.get("documents")
            if isinstance(exact_lookup_body, dict)
            else None
        )
        if not isinstance(documents, list):
            raise TrialBlocked("memory_service", "exact lookup response lacks documents")
        exact = [
            item
            for item in documents
            if _matches_memory_document(item, document, recall_tags)
        ]
        if len(exact) == 1:
            exact_match_source = "exact_key_lookup"
    if len(exact) != 1:
        raise TrialBlocked("memory_service", f"exact {team} recall did not converge")

    opposite_team = "blue" if team == "red" else "red"
    opposite_team_tags = [
        tag for tag in recall_tags if not tag.startswith("team:")
    ] + [f"team:{opposite_team}"]
    other_trial_tags = [
        tag for tag in recall_tags if not tag.startswith("trial:")
    ] + [f"trial:{trial['trial_id']}-other"]
    negative_responses: dict[str, Any] = {}
    for isolation_kind, isolation_tags in (
        ("opposite_team", opposite_team_tags),
        ("other_trial", other_trial_tags),
    ):
        recall_request_count += 1
        response = client.post(
            "/recall",
            json={
                "q": document["problem"],
                "k": 5,
                "collections": [collection],
                "tags": isolation_tags,
                "threshold": 0.0,
            },
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list):
            raise TrialBlocked(
                "memory_service",
                f"{isolation_kind} recall response lacks items",
            )
        matches = _items_with_all_tags(items, isolation_tags)
        if matches:
            raise TrialBlocked(
                "memory_isolation",
                f"{isolation_kind} recall returned records",
                retryable=False,
            )
        negative_responses[isolation_kind] = {**body, "matching_items": matches}

    recall_receipt = {
        "schema": "battle.memory_ablation_recall_receipt.v1",
        "status": "PASS",
        "team": team,
        "collection": collection,
        "memory_key": document["_key"],
        "source_memory_sha256": document["source_memory_sha256"],
        "write_receipt_sha256": write_receipt["receipt_sha256"],
        "query_sha256": hashlib.sha256(document["problem"].encode("utf-8")).hexdigest(),
        "exact_match_count": 1,
        "cross_team_items_absent": True,
        "cross_trial_items_absent": True,
        "opposite_team_item_count": 0,
        "other_trial_item_count": 0,
        "opposite_team_response_sha256": canonical_sha256(
            negative_responses["opposite_team"]
        ),
        "other_trial_response_sha256": canonical_sha256(
            negative_responses["other_trial"]
        ),
        "recalled_solution_sha256": hashlib.sha256(
            str(exact[0]["solution"]).encode("utf-8")
        ).hexdigest(),
        "service_response_sha256": canonical_sha256(recall_body),
        "exact_match_source": exact_match_source,
        "exact_lookup_response_sha256": (
            canonical_sha256(exact_lookup_body)
            if exact_lookup_body is not None
            else None
        ),
        "mocked": False,
        "live": True,
        "created_at": _now(),
    }
    recall_path = _write_json(out_dir / f"{team}-memory-recall.json", recall_receipt)
    recall_receipt["receipt_sha256"] = file_sha256(recall_path)
    return {
        "mode": "ON",
        "service_request_count": 1 + recall_request_count + exact_lookup_request_count,
        "write": write_receipt,
        "recall": recall_receipt,
        "document": document,
        "recalled_solution_json": str(exact[0]["solution"]),
    }


def _control_memory_receipt(
    *, plan: Mapping[str, Any], trial: Mapping[str, Any], team: str, out_dir: Path
) -> dict[str, Any]:
    receipt = {
        "schema": "battle.memory_ablation_control_receipt.v1",
        "status": "PASS",
        "team": team,
        "mode": "OFF",
        "trial_id": trial["trial_id"],
        "attention_policy_id": ATTENTION_POLICY_ID,
        "service_request_count": 0,
        "memory_key": None,
        "source_memory_sha256": None,
        "claims": {
            "proves": [
                "This trial path did not issue a post-preflight Memory request."
            ],
            "does_not_prove": [
                "The Memory service was unreachable or disabled globally."
            ],
        },
        "created_at": _now(),
    }
    path = _write_json(out_dir / f"{team}-memory-control.json", receipt)
    receipt["receipt_sha256"] = file_sha256(path)
    return {
        "mode": "OFF",
        "service_request_count": 0,
        "control": receipt,
        "document": None,
    }


def _provider_field(call: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    value: Any = call
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            return _optional_value(None)
        value = value[key]
    return _optional_value(value)


def _provider_execution(
    *, entry: Mapping[str, Any], request: Mapping[str, Any], wall_time_seconds: float
) -> dict[str, Any]:
    call_path = Path(str(entry["scillm_call"]))
    handoff_path = Path(str(entry["handoff"]))
    subagent_path = Path(str(entry["subagent_receipt"]))
    call = _read_json(call_path)
    parsed = call.get("parsed_json")
    provider_text = (
        json.dumps(parsed, sort_keys=True) if isinstance(parsed, dict) else ""
    )
    attempts = call.get("attempts") if isinstance(call.get("attempts"), list) else []
    call_status = (
        "PASS"
        if call.get("live") is True
        and call.get("mocked") is False
        and call.get("parse_status") == "PASS"
        and call.get("http_status") == 200
        else "BLOCKED"
    )
    return {
        "status": call_status,
        "live": call.get("live") is True,
        "mocked": call.get("mocked") is True,
        "request_envelope_sha256": request["sha256"],
        "scillm_call_receipt_sha256": file_sha256(call_path),
        "tau_handoff_receipt_sha256": file_sha256(handoff_path),
        "tau_subagent_receipt_sha256": file_sha256(subagent_path),
        "materialized_artifact_sha256": str(entry["materialized"]["artifact_sha256"]),
        "strategy_genome_sha256": str(entry["materialized"]["strategy_genome_sha256"]),
        "provider_identity": _provider_field(call, "provider"),
        "model": _provider_field(call, "model"),
        "persona": _provider_field(call, "persona"),
        "surface": _provider_field(entry, "surface"),
        "provider_request_sha256": _provider_field(call, "request_sha256"),
        "seed": _provider_field(call, "seed"),
        "temperature": _provider_field(call, "temperature"),
        "input_tokens": _provider_field(call, "usage", "input_tokens"),
        "output_tokens": _provider_field(call, "usage", "output_tokens"),
        "total_tokens": _provider_field(call, "usage", "total_tokens"),
        "cost_usd": _provider_field(call, "usage", "cost_usd"),
        "duration_seconds": _provider_field(call, "duration_seconds"),
        "trial_wall_time_seconds": wall_time_seconds,
        "provider_attempt_count": len(attempts),
        "repair_used": call.get("repair_used") is True,
        "memory_identifier_citation_count": sum(
            provider_text.count(token)
            for token in ("memory_key", "source_memory_sha256", "memory_recall")
        ),
    }


def _bool_measurement(value: Any) -> bool | Literal["NOT_EMITTED"]:
    return value if isinstance(value, bool) else "NOT_EMITTED"


def _number_measurement(value: Any) -> float | int | Literal["NOT_EMITTED"]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return "NOT_EMITTED"


def build_team_outcome_vector(
    *,
    team: str,
    judge: Mapping[str, Any],
    pipeline: Mapping[str, Any],
    provider_execution: Mapping[str, Any],
    artifact_changed: bool,
) -> dict[str, Any]:
    """Project one team-specific vector without replacing it with pair verdict rank."""

    attempt = (judge.get("attempts") or [{}])[0]
    if not isinstance(attempt, Mapping):
        attempt = {}
    common = {
        "pair_verdict": judge.get("verdict", "NOT_EMITTED"),
        "pipeline_status": pipeline.get("status", "NOT_EMITTED"),
        "runtime_evaluated": bool(int(judge.get("judged_pair_count") or 0)),
        "target_contact": attempt.get("target_contact", "NOT_EMITTED"),
        "known_parent_failure_avoided": "NOT_EMITTED",
        "provider_attempt_count": provider_execution["provider_attempt_count"],
        "repair_attempt_count": 1 if provider_execution["repair_used"] else 0,
        "provider_duration_seconds": provider_execution["duration_seconds"],
        "trial_wall_time_seconds": provider_execution["trial_wall_time_seconds"],
        "input_tokens": provider_execution["input_tokens"],
        "output_tokens": provider_execution["output_tokens"],
        "total_tokens": provider_execution["total_tokens"],
        "cost_usd": provider_execution["cost_usd"],
        "artifact_changed_from_parent": artifact_changed,
    }
    if team == "red":
        security = {
            "exploit_confirmed_before_patch": _bool_measurement(
                attempt.get("exploit_confirmed_before_patch")
            ),
            "target_contact": common["target_contact"],
            "pipeline_status": common["pipeline_status"],
            "runtime_evaluated": common["runtime_evaluated"],
            "known_parent_failure_avoided": common["known_parent_failure_avoided"],
        }
    elif team == "blue":
        security = {
            "exploit_blocked_after_patch": _bool_measurement(
                attempt.get("exploit_blocked_after_patch")
            ),
            "functionality_preserved": _bool_measurement(
                attempt.get("functionality_preserved")
            ),
            "pipeline_status": common["pipeline_status"],
            "runtime_evaluated": common["runtime_evaluated"],
            "known_parent_failure_avoided": common["known_parent_failure_avoided"],
        }
    else:
        raise ContractError(f"unsupported team: {team}")
    efficiency = {
        "provider_attempt_count": common["provider_attempt_count"],
        "repair_attempt_count": common["repair_attempt_count"],
        "provider_duration_seconds": common["provider_duration_seconds"],
        "trial_wall_time_seconds": common["trial_wall_time_seconds"],
        "input_tokens": common["input_tokens"],
        "output_tokens": common["output_tokens"],
        "total_tokens": common["total_tokens"],
        "cost_usd": common["cost_usd"],
    }
    return {
        "team": team,
        "security": security,
        "efficiency": efficiency,
        "descriptive": {
            "pair_verdict": common["pair_verdict"],
            "artifact_changed_from_parent": common["artifact_changed_from_parent"],
        },
    }


def _objective(team: str) -> str:
    return PROMPT_TEMPLATE.format(team=team)


def _execute_live_trial(
    *,
    plan: Mapping[str, Any],
    trial: Mapping[str, Any],
    source_root: Path,
    trial_dir: Path,
    memory_base_url: str,
    scillm_base_url: str,
    plan_file_sha256: str,
) -> dict[str, Any]:
    from .adaptive_memory_canary import _load_v13_source
    from .adaptive_red_blue_lineage_canary import (
        _copy_public_arena,
        _judge_reviewed_generation,
        _provider_genomes,
        _read_json as read_battle_json,
        _reviewed_manifest,
        _run_tau_harness,
        _write_tau_public_context,
    )
    from .arena_battle_proof import _write_json as write_battle_json

    started = time.perf_counter()
    trial_dir = trial_dir.resolve()
    source = _load_v13_source(battle_id=str(plan["battle_id"]), source_root=source_root)

    memory_dir = trial_dir / "memory"
    memory_results: dict[str, dict[str, Any]] = {}
    any_memory = any(bool(trial["condition"][f"{team}_memory"]) for team in TEAMS)
    client: httpx.Client | None = None
    try:
        if any_memory:
            client = httpx.Client(
                base_url=memory_base_url,
                timeout=httpx.Timeout(30.0, connect=3.0),
            )
            health = client.get("/health")
            health.raise_for_status()
            _write_json(
                trial_dir / "memory-health.json",
                {
                    "status": "PASS",
                    "response_sha256": canonical_sha256(health.json()),
                    "created_at": _now(),
                },
            )
        for team in TEAMS:
            if trial["condition"][f"{team}_memory"]:
                if client is None:
                    raise TrialBlocked("memory_service", "Memory client unavailable")
                memory_results[team] = _write_and_recall_memory(
                    client=client,
                    collection=trial["memory_namespace"]["collection"],
                    plan=plan,
                    trial=trial,
                    team=team,
                    out_dir=memory_dir,
                )
            else:
                memory_results[team] = _control_memory_receipt(
                    plan=plan,
                    trial=trial,
                    team=team,
                    out_dir=memory_dir,
                )
    except httpx.HTTPError as exc:
        raise TrialBlocked("memory_service", str(exc)) from exc
    finally:
        if client is not None:
            client.close()

    recalled_solutions = {
        team: str(memory_results[team]["recalled_solution_json"])
        for team in TEAMS
        if memory_results[team]["mode"] == "ON"
    }
    binding = build_trial_input_binding(
        plan=plan,
        trial=trial,
        recalled_solutions=recalled_solutions,
    )
    binding_path = _write_json(trial_dir / "trial-input-binding.json", binding)

    generation_dir = trial_dir / "generation-3"
    _copy_public_arena(source_root / "generation-1", generation_dir)
    scenario = source["scenario"]
    run_id = str(trial["trial_id"])
    context_path = _write_tau_public_context(
        out_dir=generation_dir,
        battle_id=str(plan["battle_id"]),
        run_id=run_id,
        scenario=scenario,
        red_workers=1,
        blue_workers=1,
    )
    context = read_battle_json(context_path)
    context["summary"]["generation"] = 3
    context["summary"]["external_research"] = {
        team: _load_public_research_context(source_root=source_root, team=team)
        for team in TEAMS
    }
    context["summary"]["memory_ablation"] = {
        "experiment_id": plan["experiment_id"],
        "trial_id": trial["trial_id"],
        "condition_id": trial["condition_id"],
        "attention_policy_id": ATTENTION_POLICY_ID,
    }
    context["team_contexts"] = {
        team: {
            "team": team,
            "memory_ablation_context": binding["contexts"][team]["envelope"],
            "memory_recall_binding": {
                "mode": memory_results[team]["mode"],
                "recall_receipt_sha256": memory_results[team]
                .get("recall", {})
                .get("receipt_sha256"),
                "source_memory_sha256": plan["immutable_inputs"]["memory_sources"][
                    team
                ]["memory_content_sha256"]
                if memory_results[team]["mode"] == "ON"
                else None,
            },
            "request_envelope_sha256": binding["request_envelopes"][team]["sha256"],
            "authority": {
                "memory_is_optional_design_input": True,
                "battle_and_judge_retain_outcome_authority": True,
            },
        }
        for team in TEAMS
    }
    for team in TEAMS:
        context["summary"]["teams"][team]["objective"] = _objective(team)
    write_battle_json(context_path, context)

    try:
        manifest_path = _run_tau_harness(
            out_dir=generation_dir,
            battle_id=str(plan["battle_id"]),
            run_id=run_id,
            scenario_id=scenario["scenario_id"],
            context_path=context_path,
            red_persona=RED_PERSONA,
            blue_persona=BLUE_PERSONA,
            model=plan["immutable_inputs"]["model"],
            scillm_base_url=scillm_base_url,
            timeout_s=float(plan["immutable_inputs"]["timeout_s"]),
            red_workers=1,
            blue_workers=1,
        )
    except Exception as exc:  # external Tau/SciLLM process boundary
        raise TrialBlocked("tau_scillm", str(exc)) from exc

    manifest = read_battle_json(manifest_path)
    parent_genomes = source["genomes"]
    try:
        genomes = _provider_genomes(
            battle_id=str(plan["battle_id"]),
            run_id=run_id,
            generation=3,
            generation_dir=generation_dir,
            manifest=manifest,
            parent_genomes=parent_genomes,
        )
        reviewed_manifest, pipelines = _reviewed_manifest(
            battle_id=str(plan["battle_id"]),
            run_id=run_id,
            generation=3,
            generation_dir=generation_dir,
            manifest=manifest,
            target_identity_sha256=str(
                plan["immutable_inputs"]["target_identity_sha256"]
            ),
            docker_image=str(plan["immutable_inputs"]["docker_image"]),
            genomes=genomes,
        )
    except Exception as exc:
        raise TrialBlocked("artifact_pipeline", str(exc), retryable=False) from exc
    try:
        judge = _judge_reviewed_generation(
            generation_dir=generation_dir,
            scenario=scenario,
            docker_image=str(plan["immutable_inputs"]["docker_image"]),
            reviewed_manifest=reviewed_manifest,
            pipelines=pipelines,
            target_identity_sha256=str(
                plan["immutable_inputs"]["target_identity_sha256"]
            ),
        )
    except Exception as exc:
        raise TrialBlocked("judge", str(exc)) from exc
    judge_path = write_battle_json(
        generation_dir / "judge" / "judge-receipt.json", judge
    )
    judge["receipt_sha256"] = file_sha256(judge_path)

    wall_time = time.perf_counter() - started
    provider_execution: dict[str, dict[str, Any]] = {}
    outcomes: dict[str, dict[str, Any]] = {}
    for team in TEAMS:
        entry = next(item for item in manifest["teams"] if item["team"] == team)
        provider_execution[team] = _provider_execution(
            entry=entry,
            request=binding["request_envelopes"][team],
            wall_time_seconds=wall_time,
        )
        artifact_sha = str(entry["materialized"]["artifact_sha256"])
        outcomes[team] = build_team_outcome_vector(
            team=team,
            judge=judge,
            pipeline=pipelines[team],
            provider_execution=provider_execution[team],
            artifact_changed=artifact_sha
            != plan["immutable_inputs"]["parent_artifact_sha256"][team],
        )

    live_route_pass = (
        manifest.get("status") == "PASS"
        and all(provider_execution[team].get("status") == "PASS" for team in TEAMS)
        and all(pipelines[team].get("status") == "PASS" for team in TEAMS)
        and judge.get("status") == "PASS"
        and int(judge.get("judged_pair_count") or 0) == 1
    )
    if not live_route_pass:
        raise TrialBlocked(
            "incomplete_live_route",
            "Tau/SciLLM, both artifact pipelines, and Judge did not all PASS",
            retryable=False,
        )

    receipt = {
        "schema": TRIAL_SCHEMA,
        "status": "PASS",
        "trial_id": trial["trial_id"],
        "experiment_id": plan["experiment_id"],
        "experiment_plan_sha256": canonical_sha256(plan),
        "experiment_plan_file_sha256": plan_file_sha256,
        "battle_id": plan["battle_id"],
        "block_id": trial["block_id"],
        "replicate": trial["replicate"],
        "order_index": trial["order_index"],
        "condition_id": trial["condition_id"],
        "condition": trial["condition"],
        "mocked": False,
        "live": True,
        "fixture_fallback_used": False,
        "input_binding": {
            **binding,
            "receipt_sha256": file_sha256(binding_path),
        },
        "memory": {
            team: {
                "mode": memory_results[team]["mode"],
                "service_request_count": memory_results[team]["service_request_count"],
                "memory_key": trial["memory_namespace"][f"{team}_key"]
                if trial["condition"][f"{team}_memory"]
                else None,
                "source_memory_sha256": plan["immutable_inputs"]["memory_sources"][
                    team
                ]["memory_content_sha256"]
                if trial["condition"][f"{team}_memory"]
                else None,
                "write_receipt_sha256": memory_results[team]
                .get("write", {})
                .get("receipt_sha256"),
                "recall_receipt_sha256": memory_results[team]
                .get("recall", {})
                .get("receipt_sha256"),
                "control_receipt_sha256": memory_results[team]
                .get("control", {})
                .get("receipt_sha256"),
                "use_was_optional": True,
            }
            for team in TEAMS
        },
        "provider_execution": provider_execution,
        "pipelines": {
            team: {
                "status": pipelines[team]["status"],
                "selected_artifact_sha256": pipelines[team]["selected_artifact_sha256"],
                "compile_receipt_sha256": pipelines[team].get("compile_receipt_sha256"),
                "review_receipt_sha256": pipelines[team].get("review_receipt_sha256"),
                "handoff_sha256": file_sha256(Path(pipelines[team]["handoff_path"])),
            }
            for team in TEAMS
        },
        "judge": {
            "status": judge.get("status"),
            "verdict": judge.get("verdict"),
            "judged_pair_count": judge.get("judged_pair_count"),
            "receipt_sha256": judge["receipt_sha256"],
        },
        "outcomes": outcomes,
        "failure": None,
        "claims": {
            "may_claim": [
                "one predeclared non-mocked Tau/SciLLM-Docker-Judge ablation trial completed"
            ],
            "must_not_claim": [
                "memory caused improvement",
                "population-scale effect",
                "exploit success beyond the Judge receipt",
                "provider determinism",
            ],
        },
        "created_at": _now(),
    }
    validate_trial_receipt(receipt)
    return receipt


def _blocked_trial_receipt(
    *,
    plan: Mapping[str, Any],
    trial: Mapping[str, Any],
    attempts: list[dict[str, Any]],
    family: str,
    detail: str,
    blocked_by_systemic_failure: bool,
    plan_file_sha256: str | None = None,
) -> dict[str, Any]:
    receipt = {
        "schema": TRIAL_SCHEMA,
        "status": "BLOCKED",
        "trial_id": trial["trial_id"],
        "experiment_id": plan["experiment_id"],
        "experiment_plan_sha256": canonical_sha256(plan),
        "experiment_plan_file_sha256": plan_file_sha256 or canonical_sha256(plan),
        "battle_id": plan["battle_id"],
        "block_id": trial["block_id"],
        "replicate": trial["replicate"],
        "order_index": trial["order_index"],
        "condition_id": trial["condition_id"],
        "condition": trial["condition"],
        "mocked": False,
        "live": any(bool(item.get("live_started")) for item in attempts),
        "fixture_fallback_used": False,
        "input_binding": build_trial_input_binding(plan=plan, trial=trial),
        "memory": {
            team: {
                "mode": "ON" if trial["condition"][f"{team}_memory"] else "OFF",
                "service_request_count": (
                    "NOT_EMITTED"
                    if attempts and trial["condition"][f"{team}_memory"]
                    else 0
                ),
                "memory_key": trial["memory_namespace"][f"{team}_key"]
                if trial["condition"][f"{team}_memory"]
                else None,
                "source_memory_sha256": plan["immutable_inputs"]["memory_sources"][
                    team
                ]["memory_content_sha256"]
                if trial["condition"][f"{team}_memory"]
                else None,
                "write_receipt_sha256": None,
                "recall_receipt_sha256": None,
                "control_receipt_sha256": None,
                "use_was_optional": True,
            }
            for team in TEAMS
        },
        "provider_execution": None,
        "pipelines": None,
        "judge": None,
        "outcomes": None,
        "failure": {
            "family": family,
            "signature": hashlib.sha256(
                f"{family}:{detail}".encode("utf-8")
            ).hexdigest(),
            "detail": detail,
            "blocked_by_systemic_failure": blocked_by_systemic_failure,
            "attempts": attempts,
        },
        "claims": {
            "may_claim": ["the predeclared trial was preserved as blocked evidence"],
            "must_not_claim": [
                "a favorable replacement trial",
                "memory benefit or regression",
                "population-scale effect",
            ],
        },
        "created_at": _now(),
    }
    validate_trial_receipt(receipt)
    return receipt


def _family_applies_to_trial(*, family: str, trial: Mapping[str, Any]) -> bool:
    if family == "memory:red":
        return bool(trial["condition"]["red_memory"])
    if family == "memory:blue":
        return bool(trial["condition"]["blue_memory"])
    if family == "memory:any":
        return bool(
            trial["condition"]["red_memory"] or trial["condition"]["blue_memory"]
        )
    return True


def _ordered_experiment_trials(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (dict(trial) for trial in plan["trials"]),
        key=lambda item: (item["replicate"], item["order_index"]),
    )


def _validate_resumable_trial_receipt(
    *,
    plan: Mapping[str, Any],
    trial: Mapping[str, Any],
    receipt: Mapping[str, Any],
    plan_file_sha256: str,
) -> None:
    validate_trial_receipt(receipt)
    expected_plan_sha256 = canonical_sha256(plan)
    exact_bindings = {
        "experiment_id": plan["experiment_id"],
        "battle_id": plan["battle_id"],
        "experiment_plan_sha256": expected_plan_sha256,
        "experiment_plan_file_sha256": plan_file_sha256,
        "trial_id": trial["trial_id"],
        "block_id": trial["block_id"],
        "replicate": trial["replicate"],
        "order_index": trial["order_index"],
        "condition_id": trial["condition_id"],
        "condition": trial["condition"],
    }
    for field, expected in exact_bindings.items():
        if receipt.get(field) != expected:
            raise ContractError(
                f"resumed trial {trial['trial_id']} has mismatched {field}"
            )
    if receipt.get("mocked") is not False or receipt.get("live") is not True:
        raise ContractError(
            f"resumed trial {trial['trial_id']} must be live and non-mocked"
        )
    if receipt.get("fixture_fallback_used") is not False:
        raise ContractError(
            f"resumed trial {trial['trial_id']} used fixture fallback"
        )
    status = receipt.get("status")
    if status not in {"PASS", "BLOCKED"}:
        raise ContractError(
            f"resumed trial {trial['trial_id']} is not terminal"
        )
    attempts = receipt.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ContractError(
            f"resumed trial {trial['trial_id']} lacks live terminal attempts"
        )
    if not any(bool(attempt.get("live_started")) for attempt in attempts):
        raise ContractError(
            f"resumed trial {trial['trial_id']} lacks a live-started attempt"
        )
    if status == "PASS":
        if attempts[-1].get("status") != "PASS":
            raise ContractError(
                f"resumed PASS trial {trial['trial_id']} lacks a terminal PASS attempt"
            )
    else:
        failure = receipt.get("failure")
        if not isinstance(failure, Mapping):
            raise ContractError(
                f"resumed BLOCKED trial {trial['trial_id']} lacks terminal failure evidence"
            )
        if failure.get("attempts") != attempts:
            raise ContractError(
                f"resumed BLOCKED trial {trial['trial_id']} attempt history disagrees"
            )
        if any(attempt.get("status") != "BLOCKED" for attempt in attempts):
            raise ContractError(
                f"resumed BLOCKED trial {trial['trial_id']} has a non-blocked attempt"
            )


def _load_resumable_trial_receipts(
    *,
    plan: Mapping[str, Any],
    experiment_root: Path,
    plan_file_sha256: str,
) -> dict[str, dict[str, Any]]:
    root = experiment_root.expanduser().resolve()
    ordered_trials = _ordered_experiment_trials(plan)
    _expected_trial_output_paths(plan=plan, experiment_root=root)

    receipts: dict[str, dict[str, Any]] = {}
    missing_seen = False
    for trial in ordered_trials:
        trial_dir = root / str(trial["output_relpath"])
        if not trial_dir.exists():
            missing_seen = True
            continue
        if missing_seen:
            raise ContractError(
                "existing resumed trial outputs are not a contiguous frozen-order prefix"
            )
        if trial_dir.is_symlink() or not trial_dir.is_dir():
            raise ContractError(
                f"trial output path is not a normal directory: {trial['output_relpath']}"
            )
        receipt_path = trial_dir / "trial-receipt.json"
        if not receipt_path.is_file():
            raise ContractError(
                f"partial trial output lacks terminal receipt: {trial['trial_id']}"
            )
        try:
            receipt = _read_json(receipt_path)
        except ContractError as exc:
            raise ContractError(
                f"trial receipt is malformed: {trial['trial_id']}"
            ) from exc
        _validate_resumable_trial_receipt(
            plan=plan,
            trial=trial,
            receipt=receipt,
            plan_file_sha256=plan_file_sha256,
        )
        receipt["receipt_sha256"] = file_sha256(receipt_path)
        receipts[str(trial["trial_id"])] = receipt
    return receipts


def _resumed_memory_keys(
    *,
    plan: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    trials = {str(trial["trial_id"]): trial for trial in plan["trials"]}
    keys: set[str] = set()
    for trial_id, receipt in receipts.items():
        if receipt.get("status") != "PASS":
            continue
        trial = trials[trial_id]
        for team in TEAMS:
            if not trial["condition"][f"{team}_memory"]:
                continue
            expected_key = str(trial["memory_namespace"][f"{team}_key"])
            memory = receipt["memory"][team]
            if (
                memory.get("memory_key") != expected_key
                or not memory.get("write_receipt_sha256")
                or not memory.get("recall_receipt_sha256")
            ):
                raise ContractError(
                    f"resumed trial {trial_id} lacks exact {team} Memory binding"
                )
            keys.add(expected_key)
    return keys


def _restore_failure_policy_state(
    *,
    receipt: Mapping[str, Any],
    failure_signature_counts: dict[str, int],
    systemic_families: set[str],
    max_identical_failures_per_family: int,
) -> None:
    if receipt.get("status") != "BLOCKED":
        return
    failure = receipt.get("failure")
    if not isinstance(failure, Mapping):
        raise ContractError("resumed BLOCKED trial lacks failure state")
    family = str(failure["family"])
    if bool(failure.get("blocked_by_systemic_failure")):
        systemic_families.add(family)
        return
    signature = str(failure["signature"])
    failure_signature_counts[signature] = (
        failure_signature_counts.get(signature, 0) + 1
    )
    if failure_signature_counts[signature] >= max_identical_failures_per_family:
        systemic_families.add(family)


def run_experiment(
    *,
    plan_path: Path,
    source_root: Path,
    out_dir: Path,
    memory_base_url: str,
    scillm_base_url: str | None = None,
    tau_root: Path | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Run exactly the twelve predeclared trials; never add favorable replacements."""

    plan = _read_json(plan_path)
    validation = validate_experiment_plan(plan)
    plan_sha = file_sha256(plan_path)
    if validation["approval"] != "CONTRACT_VALIDATED":
        raise ContractError("experiment plan contract is not validated")
    # Bind the current route without changing the frozen hash semantics. The plan
    # stores a route hash; the live caller supplies the actual URL.
    if scillm_base_url:
        expected = plan["immutable_inputs"]["scillm_route_sha256"]
        actual = hashlib.sha256(scillm_base_url.encode("utf-8")).hexdigest()
        if actual != expected:
            raise ContractError("SciLLM route differs from the frozen experiment plan")

    out_dir.mkdir(parents=True, exist_ok=True)
    resumed_receipts = (
        _load_resumable_trial_receipts(
            plan=plan,
            experiment_root=out_dir,
            plan_file_sha256=plan_sha,
        )
        if resume
        else {}
    )
    reusable_memory_keys = _resumed_memory_keys(
        plan=plan, receipts=resumed_receipts
    )
    preflight = preflight_experiment(
        plan=plan,
        source_root=source_root,
        memory_base_url=memory_base_url,
        scillm_base_url=scillm_base_url or "http://localhost:4001",
        tau_root=tau_root
        or Path(os.environ.get("BATTLE_TAU_ROOT", "/home/graham/workspace/experiments/tau")),
        experiment_root=out_dir,
        plan_file_sha256=plan_sha,
        reusable_trial_ids=resumed_receipts.keys(),
        reusable_memory_keys=reusable_memory_keys,
    )
    if preflight.get("approval") != "APPROVED_FOR_LIVE":
        raise ContractError("experiment preflight did not approve live execution")
    _write_json(out_dir / "memory-ablation-preflight-receipt.json", preflight)
    failure_signature_counts: dict[str, int] = {}
    systemic_families: set[str] = set()
    trial_receipts: list[dict[str, Any]] = []
    ordered_trials = _ordered_experiment_trials(plan)
    max_identical_failures = int(
        plan["failure_policy"]["max_identical_failures_per_family"]
    )
    for trial in ordered_trials:
        resumed = resumed_receipts.get(str(trial["trial_id"]))
        if resumed is not None:
            trial_receipts.append(resumed)
            _restore_failure_policy_state(
                receipt=resumed,
                failure_signature_counts=failure_signature_counts,
                systemic_families=systemic_families,
                max_identical_failures_per_family=max_identical_failures,
            )
            continue
        blocking_family = next(
            (
                family
                for family in sorted(systemic_families)
                if _family_applies_to_trial(family=family, trial=trial)
            ),
            None,
        )
        trial_dir = out_dir / trial["output_relpath"]
        if blocking_family:
            receipt = _blocked_trial_receipt(
                plan=plan,
                trial=trial,
                attempts=[],
                family=blocking_family,
                detail="blocked by previously established systemic failure",
                blocked_by_systemic_failure=True,
                plan_file_sha256=plan_sha,
            )
            path = _write_json(trial_dir / "trial-receipt.json", receipt)
            receipt["receipt_sha256"] = file_sha256(path)
            trial_receipts.append(receipt)
            continue

        attempts: list[dict[str, Any]] = []
        receipt: dict[str, Any] | None = None
        last_blocker: TrialBlocked | None = None
        for attempt_number in range(1, 3):
            attempt_started = _now()
            try:
                receipt = _execute_live_trial(
                    plan=plan,
                    trial=trial,
                    source_root=source_root,
                    trial_dir=trial_dir / f"attempt-{attempt_number:02d}",
                    memory_base_url=memory_base_url,
                    scillm_base_url=scillm_base_url or "http://localhost:4001",
                    plan_file_sha256=plan_sha,
                )
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "status": "PASS",
                        "live_started": True,
                        "started_at": attempt_started,
                    }
                )
                break
            except TrialBlocked as exc:
                last_blocker = exc
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "status": "BLOCKED",
                        "family": exc.family,
                        "signature": hashlib.sha256(
                            str(exc).encode("utf-8")
                        ).hexdigest(),
                        "detail": exc.detail,
                        "live_started": True,
                        "started_at": attempt_started,
                    }
                )
                if not exc.retryable:
                    break
        if receipt is None:
            assert last_blocker is not None
            family = last_blocker.family
            if family == "memory_service":
                red_on = bool(trial["condition"]["red_memory"])
                blue_on = bool(trial["condition"]["blue_memory"])
                if red_on and not blue_on:
                    family = "memory:red"
                elif blue_on and not red_on:
                    family = "memory:blue"
                else:
                    family = "memory:any"
            failure_signature = hashlib.sha256(
                f"{family}:{last_blocker.detail}".encode("utf-8")
            ).hexdigest()
            failure_signature_counts[failure_signature] = (
                failure_signature_counts.get(failure_signature, 0) + 1
            )
            if failure_signature_counts[failure_signature] >= max_identical_failures:
                systemic_families.add(family)
            receipt = _blocked_trial_receipt(
                plan=plan,
                trial=trial,
                attempts=attempts,
                family=family,
                detail=last_blocker.detail,
                blocked_by_systemic_failure=False,
                plan_file_sha256=plan_sha,
            )
        receipt["attempts"] = attempts
        path = _write_json(trial_dir / "trial-receipt.json", receipt)
        receipt["receipt_sha256"] = file_sha256(path)
        trial_receipts.append(receipt)

    if len(trial_receipts) != 12:
        raise ContractError(
            f"experiment run did not aggregate exactly 12 trial receipts: {len(trial_receipts)}"
        )
    summary = {
        "schema": "battle.memory_ablation_run_summary.v1",
        "status": "PASS"
        if len(trial_receipts) == 12
        and all(item["status"] == "PASS" for item in trial_receipts)
        else "BLOCKED",
        "experiment_id": plan["experiment_id"],
        "experiment_plan_sha256": plan_sha,
        "trial_receipts": [
            {
                "trial_id": item["trial_id"],
                "status": item["status"],
                "receipt_sha256": item["receipt_sha256"],
            }
            for item in trial_receipts
        ],
        "systemic_failure_families": sorted(systemic_families),
        "created_at": _now(),
    }
    _write_json(out_dir / "memory-ablation-run-summary.json", summary)
    return summary


def validate_trial_receipt(receipt: Mapping[str, Any]) -> None:
    try:
        jsonschema.validate(
            receipt, _schema("battle.memory_ablation_trial.v1.schema.json")
        )
    except jsonschema.ValidationError as exc:
        raise ContractError(f"trial schema validation failed: {exc.message}") from exc
    if receipt["fixture_fallback_used"] is not False or receipt["mocked"] is not False:
        raise ContractError("V15 trials must be non-mocked with no fixture fallback")
    if (
        receipt["input_binding"]["experiment_plan_sha256"]
        != receipt["experiment_plan_sha256"]
    ):
        raise ContractError(
            "trial input binding disagrees with canonical experiment plan hash"
        )
    context_bytes = {
        receipt["input_binding"]["contexts"][team]["bytes"] for team in TEAMS
    }
    if len(context_bytes) != 1:
        raise ContractError(
            "Red and Blue trial contexts must share the frozen byte budget"
        )
    if receipt["status"] == "PASS":
        if receipt["live"] is not True:
            raise ContractError("PASS trial must be live")
        if (
            receipt["provider_execution"] is None
            or receipt["pipelines"] is None
            or receipt["judge"] is None
            or receipt["outcomes"] is None
        ):
            raise ContractError(
                "PASS trial lacks provider, pipeline, Judge, or outcome evidence"
            )
        if (
            receipt["judge"]["status"] != "PASS"
            or int(receipt["judge"]["judged_pair_count"]) != 1
        ):
            raise ContractError("PASS trial lacks one evaluated Judge pair")
        for team in TEAMS:
            provider = receipt["provider_execution"][team]
            request = receipt["input_binding"]["request_envelopes"][team]
            if (
                provider["status"] != "PASS"
                or provider["live"] is not True
                or provider["mocked"] is not False
            ):
                raise ContractError(
                    f"PASS trial lacks live non-mocked {team} provider evidence"
                )
            if provider["request_envelope_sha256"] != request["sha256"]:
                raise ContractError(f"{team} provider request binding mismatch")
            if (
                provider["model"]["status"] != "EMITTED"
                or provider["model"]["value"] != request["envelope"]["model"]
            ):
                raise ContractError(
                    f"{team} provider model differs from the frozen request"
                )
            if receipt["pipelines"][team]["status"] != "PASS":
                raise ContractError(f"PASS trial lacks {team} pipeline PASS")
            memory = receipt["memory"][team]
            memory_on = bool(receipt["condition"][f"{team}_memory"])
            if memory_on:
                if (
                    memory["mode"] != "ON"
                    or not isinstance(memory["service_request_count"], int)
                    or memory["service_request_count"] < 2
                    or not memory["write_receipt_sha256"]
                    or not memory["recall_receipt_sha256"]
                    or memory["control_receipt_sha256"] is not None
                ):
                    raise ContractError(
                        f"{team} ON trial lacks exact live Memory evidence"
                    )
            elif (
                memory["mode"] != "OFF"
                or memory["service_request_count"] != 0
                or not memory["control_receipt_sha256"]
                or memory["write_receipt_sha256"] is not None
                or memory["recall_receipt_sha256"] is not None
            ):
                raise ContractError(
                    f"{team} OFF trial issued or claimed Memory service work"
                )
        red_security = receipt["outcomes"]["red"]["security"]
        blue_security = receipt["outcomes"]["blue"]["security"]
        if not isinstance(red_security.get("exploit_confirmed_before_patch"), bool):
            raise ContractError("Red outcome lacks exploit-before-patch measurement")
        if not isinstance(blue_security.get("exploit_blocked_after_patch"), bool):
            raise ContractError("Blue outcome lacks block-after-patch measurement")
        if not isinstance(blue_security.get("functionality_preserved"), bool):
            raise ContractError("Blue outcome lacks functionality measurement")
    elif receipt["failure"] is None:
        raise ContractError("BLOCKED trial lacks a failure receipt")


def _emitted_value(field: Mapping[str, Any]) -> Any | None:
    return field.get("value") if field.get("status") == "EMITTED" else None


def _bool_rank(value: Any) -> int | None:
    if value is True:
        return 1
    if value is False:
        return 0
    return None


def _target_contact_rank(value: Any) -> int | None:
    if isinstance(value, bool):
        return 1 if value else 0
    if not isinstance(value, str):
        return None
    normalized = value.upper()
    mapping = {
        "CONFIRMED": 2,
        "TARGET_CONTACT": 2,
        "UNPROVEN": 1,
        "TARGET_CONTACT_UNPROVEN": 1,
        "NOT_RUN": 0,
        "NONE": 0,
        "FALSE": 0,
        "TRUE": 2,
    }
    return mapping.get(normalized)


def _pipeline_rank(value: Any) -> int | None:
    if value == "PASS":
        return 1
    if value in {"BLOCKED", "FAIL", "NOT_RUN"}:
        return 0
    return None


def _compare_numeric_lower(
    left: Any, right: Any, *, relative_tie: float | None = None
) -> int | None:
    if not isinstance(left, (int, float)) or isinstance(left, bool):
        return None
    if not isinstance(right, (int, float)) or isinstance(right, bool):
        return None
    if relative_tie is not None:
        baseline = max(abs(float(left)), abs(float(right)), 1e-9)
        if abs(float(left) - float(right)) / baseline < relative_tie:
            return 0
    return 1 if left < right else -1 if left > right else 0


def compare_team_outcomes(
    *,
    team: str,
    treatment: Mapping[str, Any],
    control: Mapping[str, Any],
    duration_tie_fraction: float = 0.10,
) -> dict[str, Any]:
    """Return +1/0/-1 or unavailable using the frozen lexicographic policy."""

    if team == "red":
        security_fields = (
            ("exploit_confirmed_before_patch", _bool_rank),
            ("target_contact", _target_contact_rank),
            ("pipeline_status", _pipeline_rank),
            ("runtime_evaluated", _bool_rank),
            ("known_parent_failure_avoided", _bool_rank),
        )
    elif team == "blue":
        security_fields = (
            ("exploit_blocked_after_patch", _bool_rank),
            ("functionality_preserved", _bool_rank),
            ("pipeline_status", _pipeline_rank),
            ("runtime_evaluated", _bool_rank),
            ("known_parent_failure_avoided", _bool_rank),
        )
    else:
        raise ContractError(f"unsupported team: {team}")

    for field, ranker in security_fields:
        left = ranker(treatment["security"].get(field))
        right = ranker(control["security"].get(field))
        if left is None or right is None:
            if (
                treatment["security"].get(field)
                == control["security"].get(field)
                == "NOT_EMITTED"
            ):
                continue
            return {
                "available": False,
                "sign": None,
                "deciding_component": field,
                "reason": "required security component is not comparable",
            }
        if left != right:
            return {
                "available": True,
                "sign": 1 if left > right else -1,
                "deciding_component": field,
                "reason": f"security component {field} differs",
            }

    efficiency_fields = (
        ("provider_attempt_count", None),
        ("repair_attempt_count", None),
        ("provider_duration_seconds", duration_tie_fraction),
        ("trial_wall_time_seconds", duration_tie_fraction),
        ("total_tokens", None),
        ("cost_usd", None),
    )
    for field, tie in efficiency_fields:
        left_raw = treatment["efficiency"].get(field)
        right_raw = control["efficiency"].get(field)
        left = _emitted_value(left_raw) if isinstance(left_raw, Mapping) else left_raw
        right = (
            _emitted_value(right_raw) if isinstance(right_raw, Mapping) else right_raw
        )
        if left is None or right is None:
            continue
        comparison = _compare_numeric_lower(left, right, relative_tie=tie)
        if comparison:
            return {
                "available": True,
                "sign": comparison,
                "deciding_component": field,
                "reason": f"security tied; lower {field} wins",
            }
    return {
        "available": True,
        "sign": 0,
        "deciding_component": "all_components",
        "reason": "all comparable security and efficiency components tie",
    }


def _trial_by_condition(
    receipts: Iterable[Mapping[str, Any]], *, block_id: str, condition_id: str
) -> Mapping[str, Any] | None:
    return next(
        (
            receipt
            for receipt in receipts
            if receipt["block_id"] == block_id
            and receipt["condition_id"] == condition_id
        ),
        None,
    )


def _classification(contrasts: list[Mapping[str, Any]]) -> str:
    if len(contrasts) != 6 or any(not contrast["available"] for contrast in contrasts):
        return "INCONCLUSIVE"
    signs = [int(contrast["sign"]) for contrast in contrasts]
    opponent_levels = {False: [], True: []}
    for contrast in contrasts:
        opponent_levels[bool(contrast["opponent_memory_on"])].append(
            int(contrast["sign"])
        )
    positives = signs.count(1)
    negatives = signs.count(-1)
    if (
        positives >= 4
        and negatives == 0
        and all(
            any(sign == 1 for sign in values) for values in opponent_levels.values()
        )
    ):
        return "OBSERVED_BENEFIT"
    if (
        negatives >= 4
        and positives == 0
        and all(
            any(sign == -1 for sign in values) for values in opponent_levels.values()
        )
    ):
        return "OBSERVED_REGRESSION"
    if all(sign == 0 for sign in signs):
        return "NO_OBSERVED_EFFECT"
    return "INCONCLUSIVE"


def _interaction(contrasts: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_block: dict[str, dict[bool, int | None]] = {}
    for contrast in contrasts:
        by_block.setdefault(str(contrast["block_id"]), {})[
            bool(contrast["opponent_memory_on"])
        ] = contrast["sign"] if contrast["available"] else None
    reversals = 0
    unresolved = 0
    for values in by_block.values():
        off = values.get(False)
        on = values.get(True)
        if off is None or on is None:
            unresolved += 1
        elif off != 0 and on != 0 and off == -on:
            reversals += 1
    if unresolved:
        label = "INCONCLUSIVE"
    elif reversals >= 2:
        label = "OBSERVED_INTERACTION"
    else:
        label = "NO_OBSERVED_INTERACTION"
    return {
        "classification": label,
        "opposite_sign_reversal_blocks": reversals,
        "unresolved_blocks": unresolved,
    }


def aggregate_experiment(
    *, plan_path: Path, experiment_root: Path, out_path: Path | None = None
) -> dict[str, Any]:
    plan = _read_json(plan_path)
    validate_experiment_plan(plan)
    receipts: list[dict[str, Any]] = []
    trial_refs: list[dict[str, Any]] = []
    for trial in plan["trials"]:
        path = experiment_root / trial["output_relpath"] / "trial-receipt.json"
        receipt = _read_json(path)
        validate_trial_receipt(receipt)
        if receipt["experiment_plan_sha256"] != canonical_sha256(plan):
            raise ContractError(
                f"trial {trial['trial_id']} canonical plan hash mismatch"
            )
        if receipt["experiment_plan_file_sha256"] != file_sha256(plan_path):
            raise ContractError(f"trial {trial['trial_id']} plan file hash mismatch")
        if (
            receipt["trial_id"] != trial["trial_id"]
            or receipt["condition_id"] != trial["condition_id"]
            or receipt["block_id"] != trial["block_id"]
        ):
            raise ContractError(
                f"trial {trial['trial_id']} identity differs from the frozen plan"
            )
        sha = file_sha256(path)
        receipts.append(receipt)
        trial_refs.append(
            {
                "trial_id": trial["trial_id"],
                "condition_id": trial["condition_id"],
                "block_id": trial["block_id"],
                "status": receipt["status"],
                "sha256": sha,
            }
        )

    team_contrasts: dict[str, list[dict[str, Any]]] = {team: [] for team in TEAMS}
    for block_number in range(1, 4):
        block_id = f"block-{block_number:02d}"
        for opponent_on in (False, True):
            red_control = _trial_by_condition(
                receipts,
                block_id=block_id,
                condition_id="R0B1" if opponent_on else "R0B0",
            )
            red_treatment = _trial_by_condition(
                receipts,
                block_id=block_id,
                condition_id="R1B1" if opponent_on else "R1B0",
            )
            team_contrasts["red"].append(
                _contrast_record(
                    team="red",
                    block_id=block_id,
                    opponent_memory_on=opponent_on,
                    control=red_control,
                    treatment=red_treatment,
                    duration_tie_fraction=float(
                        plan["aggregation_policy"]["duration_tie_fraction"]
                    ),
                )
            )
            blue_control = _trial_by_condition(
                receipts,
                block_id=block_id,
                condition_id="R1B0" if opponent_on else "R0B0",
            )
            blue_treatment = _trial_by_condition(
                receipts,
                block_id=block_id,
                condition_id="R1B1" if opponent_on else "R0B1",
            )
            team_contrasts["blue"].append(
                _contrast_record(
                    team="blue",
                    block_id=block_id,
                    opponent_memory_on=opponent_on,
                    control=blue_control,
                    treatment=blue_treatment,
                    duration_tie_fraction=float(
                        plan["aggregation_policy"]["duration_tie_fraction"]
                    ),
                )
            )

    classifications = {team: _classification(team_contrasts[team]) for team in TEAMS}
    blocked = [reference for reference in trial_refs if reference["status"] != "PASS"]
    status = "PASS" if not blocked and len(trial_refs) == 12 else "BLOCKED"
    result = {
        "schema": RESULT_SCHEMA,
        "status": status,
        "experiment_id": plan["experiment_id"],
        "battle_id": plan["battle_id"],
        "experiment_plan_sha256": file_sha256(plan_path),
        "experiment_plan_canonical_sha256": canonical_sha256(plan),
        "trial_set_sha256": canonical_sha256(trial_refs),
        "aggregation_policy_sha256": canonical_sha256(plan["aggregation_policy"]),
        "trial_receipts": trial_refs,
        "blocked_trials": blocked,
        "contrasts": team_contrasts,
        "classifications": classifications,
        "interaction": {
            "red_memory_by_blue_memory": _interaction(team_contrasts["red"]),
            "blue_memory_by_red_memory": _interaction(team_contrasts["blue"]),
        },
        "live_proof": {
            "required_trial_count": 12,
            "completed_live_trial_count": sum(
                1
                for receipt in receipts
                if receipt["status"] == "PASS"
                and receipt["live"] is True
                and receipt["mocked"] is False
                and receipt["fixture_fallback_used"] is False
            ),
            "all_trials_crossed_tau_docker_judge": status == "PASS",
        },
        "claims": {
            "may_claim": [
                f"In this bounded twelve-trial {plan['battle_id']} experiment, Red memory was classified as {classifications['red']} under the predeclared policy.",
                f"In this bounded twelve-trial {plan['battle_id']} experiment, Blue memory was classified as {classifications['blue']} under the predeclared policy.",
            ],
            "must_not_claim": [
                "memory caused general improvement",
                "population-scale causal effect",
                "production readiness",
                "provider determinism",
                "exploit success beyond the exact Judge receipts",
            ],
        },
        "research_sources": list(RESEARCH_SOURCES),
        "created_at": _now(),
    }
    validate_result(result)
    if out_path is not None:
        _write_json(out_path, result)
    return result


def _contrast_record(
    *,
    team: str,
    block_id: str,
    opponent_memory_on: bool,
    control: Mapping[str, Any] | None,
    treatment: Mapping[str, Any] | None,
    duration_tie_fraction: float,
) -> dict[str, Any]:
    base = {
        "team": team,
        "block_id": block_id,
        "opponent_memory_on": opponent_memory_on,
        "control_trial_id": control["trial_id"] if control else None,
        "treatment_trial_id": treatment["trial_id"] if treatment else None,
    }
    if (
        not control
        or not treatment
        or control["status"] != "PASS"
        or treatment["status"] != "PASS"
    ):
        return {
            **base,
            "available": False,
            "sign": None,
            "deciding_component": "trial_status",
            "reason": "control or treatment trial is unavailable or blocked",
        }
    comparison = compare_team_outcomes(
        team=team,
        treatment=treatment["outcomes"][team],
        control=control["outcomes"][team],
        duration_tie_fraction=duration_tie_fraction,
    )
    return {**base, **comparison}


def validate_result(result: Mapping[str, Any]) -> None:
    try:
        jsonschema.validate(
            result, _schema("battle.memory_ablation_result.v1.schema.json")
        )
    except jsonschema.ValidationError as exc:
        raise ContractError(f"result schema validation failed: {exc.message}") from exc
    if len(result["trial_receipts"]) != 12:
        raise ContractError("aggregate must bind exactly twelve trial receipts")
    if result["trial_set_sha256"] != canonical_sha256(result["trial_receipts"]):
        raise ContractError("aggregate trial-set hash mismatch")
    if set(result["classifications"]) != set(TEAMS):
        raise ContractError("aggregate must classify Red and Blue separately")
    if any(
        value not in CLASSIFICATIONS for value in result["classifications"].values()
    ):
        raise ContractError("aggregate contains an unsupported team classification")
    if result["status"] == "PASS" and result["blocked_trials"]:
        raise ContractError("PASS aggregate cannot contain blocked trials")
    may_claim = " ".join(result["claims"]["may_claim"]).lower()
    if "caused" in may_claim or "population" in may_claim or "production" in may_claim:
        raise ContractError(
            "aggregate language exceeds the bounded observed-effect contract"
        )


__all__ = [
    "CLASSIFICATIONS",
    "DEFECT_DISPOSITIONS",
    "CONDITION_ORDER",
    "ContractError",
    "MEMORY_COLLECTION",
    "aggregate_experiment",
    "build_attention_matched_context",
    "build_experiment_plan",
    "build_team_outcome_vector",
    "build_trial_input_binding",
    "canonical_sha256",
    "compare_team_outcomes",
    "condition_flags",
    "file_sha256",
    "load_source_bindings",
    "preflight_experiment",
    "resolve_docker_image_identity",
    "run_experiment",
    "validate_experiment_plan",
    "validate_result",
    "validate_trial_receipt",
    "write_experiment_plan",
]
