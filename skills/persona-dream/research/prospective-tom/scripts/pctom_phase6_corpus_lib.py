"""Deterministic Phase 6 compute-matched corpus helpers."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


SCHEMA_PREFIX = "persona_dream.research.prospective_tom"
REQUIRED_CONDITIONS = ("MEMORY", "FREE_CD", "STRUCTURED_CD", "FUNCTIONAL_TOM")
FORBIDDEN_INPUT_KEYS = {
    "actual_next_action",
    "hidden_world_state",
    "ground_truth_tom_labels",
    "outcome",
    "outcome_reveal",
    "observed_outcome",
    "revealed_outcome",
    "score",
    "scoring_receipt",
}
COMPUTE_BUDGET = {
    "model_call_slots": 0,
    "tau_call_slots": 0,
    "provider_call_slots": 0,
    "memory_write_slots": 0,
    "max_prompt_tokens": 512,
    "max_output_tokens": 256,
    "visible_evidence_slots": 3,
    "condition_artifact_slots": 2,
}


def default_phase6_paths(root: Path) -> dict[str, Path]:
    return {
        "source_corpus": root / "fixtures/gate1/development/social_episode_corpus.v1.json",
        "corpus": root / "fixtures/phase6/compute_matched_corpora/pctom-compute-matched-corpus.v1.json",
    }


def visible_refs(episode: dict[str, Any]) -> list[dict[str, str]]:
    episode_id = episode["episode_id"]
    refs = [{"scope": "social_episode_access", "source_id": f"{episode_id}:information_access_by_agent"}]
    history = episode.get("observable_history") or []
    for index, item in enumerate(history[:2]):
        if isinstance(item, dict):
            refs.append({"scope": "social_episode_observation", "source_id": f"{episode_id}:observable_history:{index}"})
    return sorted(refs, key=lambda row: (row["scope"], row["source_id"]))


def condition_artifacts(episode: dict[str, Any], condition: str) -> list[dict[str, Any]]:
    episode_id = episode["episode_id"]
    refs = visible_refs(episode)
    if condition == "MEMORY":
        artifacts = [
            {
                "artifact_id": f"{episode_id}:memory:evidence_packet",
                "artifact_type": "memory_only_retrieval_packet",
                "synthetic": False,
                "counterfactual": False,
                "uses_do_operator": False,
                "evidence_refs": refs,
            },
            {
                "artifact_id": f"{episode_id}:memory:literal_prior",
                "artifact_type": "literal_memory_prior",
                "synthetic": False,
                "counterfactual": False,
                "uses_do_operator": False,
                "evidence_refs": refs,
            },
        ]
    elif condition == "FREE_CD":
        artifacts = [
            {
                "artifact_id": f"{episode_id}:free_cd:branch_free_text",
                "artifact_type": "free_counterfactual_dream_branch",
                "synthetic": True,
                "counterfactual": True,
                "uses_do_operator": False,
                "evidence_refs": refs,
                "branch_text": "Imagine the counterpart chooses a different next move while visible evidence stays fixed.",
            },
            {
                "artifact_id": f"{episode_id}:free_cd:comparison_note",
                "artifact_type": "free_form_branch_comparison",
                "synthetic": True,
                "counterfactual": True,
                "uses_do_operator": False,
                "evidence_refs": refs,
            },
        ]
    elif condition == "STRUCTURED_CD":
        artifacts = [
            {
                "artifact_id": f"{episode_id}:structured_cd:do_policy_alternative",
                "artifact_type": "structured_do_counterfactual_branch",
                "synthetic": True,
                "counterfactual": True,
                "uses_do_operator": True,
                "intervened_variable": "counterpart_policy.expected_actual_next_action",
                "held_fixed": ["observable_history", "information_access_by_agent", "counterpart_goals"],
                "evidence_refs": refs,
            },
            {
                "artifact_id": f"{episode_id}:structured_cd:branch_delta",
                "artifact_type": "structured_counterfactual_delta",
                "synthetic": True,
                "counterfactual": True,
                "uses_do_operator": True,
                "evidence_refs": refs,
            },
        ]
    elif condition == "FUNCTIONAL_TOM":
        artifacts = [
            {
                "artifact_id": f"{episode_id}:functional_tom:bdi_state",
                "artifact_type": "functional_tom_bdi_state",
                "synthetic": False,
                "counterfactual": False,
                "uses_do_operator": False,
                "subject_model": "counterpart_belief_goal_policy",
                "state_variables": ["belief", "goal", "preference_or_commitment", "information_access"],
                "evidence_refs": refs,
            },
            {
                "artifact_id": f"{episode_id}:functional_tom:policy_rule",
                "artifact_type": "functional_tom_policy_rule",
                "synthetic": False,
                "counterfactual": False,
                "uses_do_operator": False,
                "action_policy": {
                    "policy_source": "deterministic_simulator_config",
                    "allowed_action_count": len(episode.get("allowed_next_actions") or []),
                    "chosen_action_hidden_until_reveal": True,
                },
                "evidence_refs": refs,
            },
        ]
    else:
        raise ValueError(f"unknown_condition:{condition}")
    return artifacts


def build_corpus(root: Path, output_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    source_path = default_phase6_paths(root)["source_corpus"]
    source = load_json(source_path, errors, "source_social_episode_corpus")
    if not isinstance(source, dict):
        raise SystemExit(f"cannot build corpus: {errors}")
    episodes = [episode for episode in source.get("episodes") or [] if isinstance(episode, dict)]
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            continue
        visible = visible_refs(episode)
        for condition in REQUIRED_CONDITIONS:
            artifacts = condition_artifacts(episode, condition)
            rows.append({
                "row_id": f"{episode_id}:{condition}",
                "episode_id": episode_id,
                "scenario_family": episode.get("scenario_family"),
                "condition": condition,
                "compute_budget": COMPUTE_BUDGET,
                "visible_evidence_refs": visible,
                "condition_artifacts": artifacts,
                "input_packet": {
                    "episode_id": episode_id,
                    "scenario_family": episode.get("scenario_family"),
                    "observable_history": episode.get("observable_history"),
                    "information_access_by_agent": episode.get("information_access_by_agent"),
                    "allowed_next_actions": episode.get("allowed_next_actions"),
                    "condition": condition,
                    "outcome_visible": False,
                },
                "replay": {
                    "source_episode_sha256": stable_json_sha256(episode),
                    "visible_refs_sha256": stable_json_sha256(visible),
                    "condition_artifacts_sha256": stable_json_sha256(artifacts),
                },
                "mocked": False,
                "live": False,
                "fixture_backed": True,
                "human_content_judgment_used": False,
                "llm_judge_used": False,
                "provider_call_attempts": 0,
                "memory_write_attempts": 0,
            })
    counts = {
        "episodes": len(episodes),
        "conditions": len(REQUIRED_CONDITIONS),
        "rows": len(rows),
        "rows_per_condition": {
            condition: sum(1 for row in rows if row["condition"] == condition)
            for condition in REQUIRED_CONDITIONS
        },
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
    }
    corpus = {
        "schema": f"{SCHEMA_PREFIX}.pctom_compute_matched_corpus.v1",
        "created_at": now_iso(),
        "status": "COMPUTE_MATCHED_CORPUS_BUILT",
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "source_corpus_path": rel(root, source_path),
        "source_corpus_sha256": file_sha256(source_path),
        "source_corpus_episodes_sha256": source.get("episodes_sha256"),
        "conditions": list(REQUIRED_CONDITIONS),
        "compute_budget": COMPUTE_BUDGET,
        "rows": rows,
        "counts": counts,
        "claims": {
            "proves": [
                "deterministic Memory, free-CD, structured-CD, and functional-ToM corpus rows are derived from the same source social episodes",
                "all four corpus conditions carry equal declared compute budgets and hash-bound visible evidence refs",
                "functional-ToM rows include explicit BDI state and policy-rule artifacts without revealing outcomes",
            ],
            "does_not_prove": [
                "live Memory recall",
                "Tau execution",
                "prediction benefit",
                "semantic dream quality",
                "paid provider execution",
                "production Phase 01-16 runtime execution",
            ],
        },
    }
    write_json(output_path, corpus)
    return corpus


def collect_forbidden_paths(value: Any, prefix: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_INPUT_KEYS:
                paths.append(child_path)
            paths.extend(collect_forbidden_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(collect_forbidden_paths(child, f"{prefix}[{index}]"))
    return paths


def audit_corpus_data(root: Path, corpus: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if corpus.get("schema") != f"{SCHEMA_PREFIX}.pctom_compute_matched_corpus.v1":
        errors.append(f"invalid_corpus_schema:{corpus.get('schema')}")
    if corpus.get("mocked") is not False or corpus.get("live") is not False or corpus.get("fixture_backed") is not True:
        errors.append(f"invalid_evidence_mode:{corpus.get('mocked')}:{corpus.get('live')}:{corpus.get('fixture_backed')}")
    source_path_value = corpus.get("source_corpus_path")
    if not isinstance(source_path_value, str) or not source_path_value:
        errors.append("source_corpus_path_missing")
        source = {}
    else:
        source_path = root / source_path_value
        source = load_json(source_path, errors, "source_corpus")
        if source_path.exists() and corpus.get("source_corpus_sha256") != file_sha256(source_path):
            errors.append("source_hash_mismatch:source_corpus_sha256")
    if not isinstance(source, dict):
        source = {}
    source_episodes = {
        episode.get("episode_id"): episode
        for episode in source.get("episodes") or []
        if isinstance(episode, dict) and isinstance(episode.get("episode_id"), str)
    }
    rows = corpus.get("rows")
    if not isinstance(rows, list):
        errors.append("rows_not_list")
        rows = []
    by_condition: dict[str, list[dict[str, Any]]] = {condition: [] for condition in REQUIRED_CONDITIONS}
    by_episode: dict[str, set[str]] = {}
    budget_by_condition: dict[str, Any] = {}
    hidden_paths = 0
    functional_missing = 0
    judgment_rows = 0
    replay_mismatches = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row_{index}_not_object")
            continue
        condition = row.get("condition")
        episode_id = row.get("episode_id")
        if condition not in REQUIRED_CONDITIONS:
            errors.append(f"condition_invalid:{index}:{condition}")
            continue
        by_condition[condition].append(row)
        if isinstance(episode_id, str):
            by_episode.setdefault(episode_id, set()).add(condition)
        budget = row.get("compute_budget")
        budget_by_condition.setdefault(condition, budget)
        if budget != COMPUTE_BUDGET:
            errors.append(f"compute_budget_mismatch:{row.get('row_id')}:{budget}")
        input_packet = row.get("input_packet")
        forbidden = collect_forbidden_paths(input_packet)
        hidden_paths += len(forbidden)
        for path in forbidden:
            errors.append(f"outcome_leakage:{row.get('row_id')}:{path}")
        if row.get("human_content_judgment_used") is not False or row.get("llm_judge_used") is not False:
            judgment_rows += 1
            errors.append(f"judgment_used:{row.get('row_id')}:{row.get('human_content_judgment_used')}:{row.get('llm_judge_used')}")
        if row.get("provider_call_attempts") != 0 or row.get("memory_write_attempts") != 0:
            errors.append(f"side_effect_counter_nonzero:{row.get('row_id')}")
        artifacts = row.get("condition_artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != COMPUTE_BUDGET["condition_artifact_slots"]:
            errors.append(f"condition_artifact_count_mismatch:{row.get('row_id')}")
            artifacts = []
        if condition == "FUNCTIONAL_TOM":
            has_bdi = any(isinstance(artifact, dict) and artifact.get("artifact_type") == "functional_tom_bdi_state" for artifact in artifacts)
            has_policy = any(isinstance(artifact, dict) and artifact.get("artifact_type") == "functional_tom_policy_rule" and isinstance(artifact.get("action_policy"), dict) for artifact in artifacts)
            if not has_bdi or not has_policy:
                functional_missing += 1
                errors.append(f"functional_tom_missing:{row.get('row_id')}:{has_bdi}:{has_policy}")
        if condition == "STRUCTURED_CD" and not all(isinstance(artifact, dict) and artifact.get("uses_do_operator") is True for artifact in artifacts):
            errors.append(f"structured_cd_missing_do_operator:{row.get('row_id')}")
        if condition == "FREE_CD" and not all(isinstance(artifact, dict) and artifact.get("counterfactual") is True for artifact in artifacts):
            errors.append(f"free_cd_missing_counterfactual:{row.get('row_id')}")
        if condition == "MEMORY" and any(isinstance(artifact, dict) and artifact.get("counterfactual") is True for artifact in artifacts):
            errors.append(f"memory_condition_contains_counterfactual:{row.get('row_id')}")
        source_episode = source_episodes.get(episode_id)
        replay = row.get("replay") if isinstance(row.get("replay"), dict) else {}
        if source_episode and replay.get("source_episode_sha256") != stable_json_sha256(source_episode):
            replay_mismatches += 1
            errors.append(f"replay_source_episode_hash_mismatch:{row.get('row_id')}")
        visible = row.get("visible_evidence_refs")
        if source_episode and visible != visible_refs(source_episode):
            replay_mismatches += 1
            errors.append(f"visible_refs_replay_mismatch:{row.get('row_id')}")
        if replay.get("visible_refs_sha256") != stable_json_sha256(visible):
            replay_mismatches += 1
            errors.append(f"visible_refs_hash_mismatch:{row.get('row_id')}")
        if replay.get("condition_artifacts_sha256") != stable_json_sha256(artifacts):
            replay_mismatches += 1
            errors.append(f"condition_artifacts_hash_mismatch:{row.get('row_id')}")
    source_episode_ids = set(source_episodes)
    condition_missing = 0
    for condition in REQUIRED_CONDITIONS:
        if not by_condition[condition]:
            condition_missing += 1
            errors.append(f"condition_missing:{condition}")
    for episode_id in sorted(source_episode_ids):
        conditions = by_episode.get(episode_id, set())
        missing = set(REQUIRED_CONDITIONS) - conditions
        if missing:
            condition_missing += len(missing)
            errors.append(f"episode_condition_missing:{episode_id}:{sorted(missing)}")
    budget_values = list(budget_by_condition.values())
    compute_budget_mismatches = sum(1 for value in budget_values if value != COMPUTE_BUDGET)
    counts = {
        "source_episodes": len(source_episode_ids),
        "conditions": len(REQUIRED_CONDITIONS),
        "rows": len(rows),
        "rows_per_condition": {condition: len(by_condition[condition]) for condition in REQUIRED_CONDITIONS},
        "condition_missing": condition_missing,
        "compute_budget_mismatches": compute_budget_mismatches,
        "outcome_leakage_rows": hidden_paths,
        "functional_tom_missing_rows": functional_missing,
        "source_hash_mismatches": sum(1 for error in errors if error.startswith("source_hash_mismatch:")),
        "replay_mismatches": replay_mismatches,
        "human_or_llm_judgment_rows": judgment_rows,
    }
    return errors, counts


def mutation_status(errors: list[str]) -> str:
    if any(error.startswith("compute_budget_mismatch:") for error in errors):
        return "BLOCKED_PCTOM_COMPUTE_BUDGET_MISMATCH"
    if any(error.startswith("condition_missing:") or error.startswith("episode_condition_missing:") for error in errors):
        return "BLOCKED_PCTOM_CORPUS_CONDITION_MISSING"
    if any(error.startswith("outcome_leakage:") for error in errors):
        return "BLOCKED_PCTOM_CORPUS_OUTCOME_LEAKAGE"
    if any(error.startswith("functional_tom_missing:") for error in errors):
        return "BLOCKED_PCTOM_FUNCTIONAL_TOM_MISSING"
    if any(error.startswith("source_hash_mismatch:") or error.startswith("replay_") or error.startswith("visible_refs_") or error.startswith("condition_artifacts_hash_mismatch:") for error in errors):
        return "BLOCKED_PCTOM_CORPUS_SOURCE_HASH_MISMATCH"
    if any(error.startswith("judgment_used:") for error in errors):
        return "BLOCKED_PCTOM_CORPUS_JUDGMENT_USED"
    return "PASS_PCTOM_COMPUTE_MATCHED_CORPUS_CASE"


def negative_cases(corpus: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    cases: list[tuple[str, str, dict[str, Any]]] = []
    budget = deepcopy(corpus)
    budget["rows"][0]["compute_budget"]["max_prompt_tokens"] = 1024
    cases.append(("compute-budget-mismatch", "BLOCKED_PCTOM_COMPUTE_BUDGET_MISMATCH", budget))

    missing = deepcopy(corpus)
    missing["rows"] = [row for row in missing["rows"] if row.get("condition") != "FREE_CD"]
    cases.append(("condition-missing", "BLOCKED_PCTOM_CORPUS_CONDITION_MISSING", missing))

    leakage = deepcopy(corpus)
    leakage["rows"][0]["input_packet"]["actual_next_action"] = "LEAKED_ACTION"
    cases.append(("outcome-leakage", "BLOCKED_PCTOM_CORPUS_OUTCOME_LEAKAGE", leakage))

    functional = deepcopy(corpus)
    for row in functional["rows"]:
        if row.get("condition") == "FUNCTIONAL_TOM":
            row["condition_artifacts"] = row["condition_artifacts"][:1]
            break
    cases.append(("functional-tom-missing", "BLOCKED_PCTOM_FUNCTIONAL_TOM_MISSING", functional))

    source = deepcopy(corpus)
    source["source_corpus_sha256"] = "sha256:" + "0" * 64
    cases.append(("source-hash-mismatch", "BLOCKED_PCTOM_CORPUS_SOURCE_HASH_MISMATCH", source))

    judgment = deepcopy(corpus)
    judgment["rows"][0]["llm_judge_used"] = True
    cases.append(("judgment-used", "BLOCKED_PCTOM_CORPUS_JUDGMENT_USED", judgment))
    return cases
