"""Battle V16 RelayForge freeze and deterministic RF-A/RF-B/RF-C verticals.

All three real paths, their narrow defenses, regressions, sink isolation,
shortcut denial and reset replay are executable. RF-D, broad quarantine, Memory
and full target qualification remain blocked, so this module never emits a
full-target qualification PASS.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

TARGET_ID = "battle-v16-relayforge-a"
TARGET_SEMANTIC_VERSION = "0.4.0-partial"
GOAL_SHA256 = "26d57f45a1a93e0f000c775530fb5ec543e833e2e7a4a1c189b4b28d13e722c6"

PUBLIC_CONTEXT_SCHEMA = "battle.v16.public_context.v1.schema.json"
PRIVATE_TRUTH_SCHEMA = "battle.v16.private_truth.v1.schema.json"
TARGET_FREEZE_SCHEMA = "battle.v16.target_freeze.v1.schema.json"
JUDGE_OUTCOME_SCHEMA = "battle.v16.judge_outcome.v1.schema.json"
DETERMINISTIC_QUALIFICATION_SCHEMA = (
    "battle.v16.deterministic_qualification.v1.schema.json"
)

IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BASE_IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

ARENA_FREEZE_COMMAND_RECEIPT_SCHEMA = (
    "battle.v16.arena_freeze_command_receipt.v1.schema.json"
)

FREEZE_BLOCKERS = (
    "rf-d-decoy-behavior-unimplemented",
    "rf-d-decoy-validation-unimplemented",
    "broad-quarantine-unimplemented",
    "durable-memory-packets-unimplemented",
    "live-topology-not-qualified",
)


class RelayForgeContractError(RuntimeError):
    """Raised when the RelayForge V16 frozen contract is violated."""


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _target_root(skill_root: Path) -> Path:
    return skill_root / "arena" / "relayforge-v16"


def _schema_root(skill_root: Path) -> Path:
    return skill_root / "schemas"


def _architecture_path(skill_root: Path) -> Path:
    return skill_root / "docs" / "BATTLE_MEMORY_SENSITIVE_ARENA_V16.md"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RelayForgeContractError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RelayForgeContractError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _validate_schema(
    value: Mapping[str, Any], *, schema_name: str, skill_root: Path
) -> None:
    schema_path = _schema_root(skill_root) / schema_name
    schema = _read_json(schema_path)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(dict(value))
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise RelayForgeContractError(
            f"{schema_name} validation failed at {location}: {exc.message}"
        ) from exc


def parse_targets(value: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        targets = tuple(item.strip() for item in value.split(",") if item.strip())
    else:
        targets = tuple(str(item).strip() for item in value if str(item).strip())
    if targets != (TARGET_ID,):
        raise RelayForgeContractError(
            f"Slice 1 supports exactly {TARGET_ID}; received {targets or '<empty>'}"
        )
    return targets


def _require_file(path: Path) -> Path:
    if not path.is_file():
        raise RelayForgeContractError(f"required RelayForge source file missing: {path}")
    return path


def _source_paths(skill_root: Path) -> dict[str, Path]:
    target_root = _target_root(skill_root)
    return {
        "compose.yaml": _require_file(target_root / "compose.yaml"),
        "Dockerfile": _require_file(target_root / "Dockerfile"),
        "service.py": _require_file(target_root / "service.py"),
        "rf_a_reference.py": _require_file(target_root / "rf_a_reference.py"),
        "rf_b_reference.py": _require_file(target_root / "rf_b_reference.py"),
        "rf_c_reference.py": _require_file(target_root / "rf_c_reference.py"),
        "contracts/public-context.json": _require_file(
            target_root / "contracts" / "public-context.json"
        ),
        "contracts/private-truth.json": _require_file(
            target_root / "contracts" / "private-truth.json"
        ),
        "judge/predicates.json": _require_file(
            target_root / "judge" / "predicates.json"
        ),
        "judge/regression-fixtures.json": _require_file(
            target_root / "judge" / "regression-fixtures.json"
        ),
        "judge/judge.py": _require_file(target_root / "judge" / "judge.py"),
    }


def _assert_goal_bound(architecture_path: Path) -> None:
    try:
        text = architecture_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RelayForgeContractError(
            f"frozen architecture is unavailable: {architecture_path}: {exc}"
        ) from exc
    if GOAL_SHA256 not in text:
        raise RelayForgeContractError(
            f"frozen architecture does not contain required goal hash {GOAL_SHA256}"
        )


def _assert_public_private_separation(
    *, public_context: Mapping[str, Any], private_truth: Mapping[str, Any]
) -> None:
    public_text = json.dumps(public_context, sort_keys=True).casefold()
    leaked = sorted(
        identifier
        for identifier in private_truth.get("private_identifiers", [])
        if isinstance(identifier, str) and identifier.casefold() in public_text
    )
    if leaked:
        raise RelayForgeContractError(
            "public context leaks private identifiers: " + ", ".join(leaked)
        )


def _assert_graph_invariants(private_truth: Mapping[str, Any]) -> None:
    sinks = {
        str(item["sink_id"]): item
        for item in private_truth.get("sinks", [])
        if isinstance(item, dict) and "sink_id" in item
    }
    paths = private_truth.get("attack_graph", {}).get("paths", [])
    path_ids = {str(item.get("path_id")) for item in paths if isinstance(item, dict)}
    if path_ids != {"RF-A", "RF-B", "RF-C"}:
        raise RelayForgeContractError(
            f"RelayForge must freeze exactly RF-A/RF-B/RF-C; received {sorted(path_ids)}"
        )
    assigned_sinks = [str(item.get("sink_id")) for item in paths]
    if len(set(assigned_sinks)) != 3 or set(assigned_sinks) != set(sinks):
        raise RelayForgeContractError(
            "RF-A/RF-B/RF-C must map one-to-one to three independent sinks"
        )
    for item in paths:
        path_id = str(item["path_id"])
        expected = path_ids - {path_id}
        actual = {str(value) for value in item.get("independent_from", [])}
        if actual != expected:
            raise RelayForgeContractError(
                f"{path_id} independence set must be {sorted(expected)}, got {sorted(actual)}"
            )
    decoy_sinks = private_truth.get("attack_graph", {}).get("decoy", {}).get(
        "real_sink_ids", ["invalid"]
    )
    if decoy_sinks != []:
        raise RelayForgeContractError("RF-D decoy must have no real sink")


def _validate_image_inputs(*, image_digest: str, base_image_digest: str) -> None:
    if not IMAGE_ID_RE.fullmatch(image_digest):
        raise RelayForgeContractError(
            "--image-digest must be an immutable local image id sha256:<64 lowercase hex>"
        )
    if not BASE_IMAGE_RE.fullmatch(base_image_digest):
        raise RelayForgeContractError(
            "--base-image-digest must be a repository digest name@sha256:<64 lowercase hex>"
        )


def _validate_repository_commit(repository_commit: str) -> None:
    if not COMMIT_RE.fullmatch(repository_commit):
        raise RelayForgeContractError(
            "--repository-commit must be the 40-character commit containing the applied patch"
        )


def _judge_module(skill_root: Path):
    judge_path = _target_root(skill_root) / "judge" / "judge.py"
    spec = importlib.util.spec_from_file_location("battle_relayforge_v16_judge", judge_path)
    if spec is None or spec.loader is None:
        raise RelayForgeContractError(f"cannot load RelayForge Judge module: {judge_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def freeze_relayforge_target(
    *,
    out: Path,
    image_digest: str,
    base_image_digest: str,
    repository_commit: str,
    targets: str | Sequence[str] = TARGET_ID,
    skill_root: Path | None = None,
) -> dict[str, Any]:
    """Freeze the current fail-closed RelayForge target skeleton deterministically."""

    parse_targets(targets)
    _validate_image_inputs(
        image_digest=image_digest, base_image_digest=base_image_digest
    )
    _validate_repository_commit(repository_commit)

    root = (skill_root or _skill_root()).resolve()
    architecture_path = _architecture_path(root)
    _assert_goal_bound(architecture_path)
    source_paths = _source_paths(root)

    public_context = _read_json(source_paths["contracts/public-context.json"])
    private_truth = _read_json(source_paths["contracts/private-truth.json"])
    predicates = _read_json(source_paths["judge/predicates.json"])
    regressions = _read_json(source_paths["judge/regression-fixtures.json"])

    _validate_schema(
        public_context, schema_name=PUBLIC_CONTEXT_SCHEMA, skill_root=root
    )
    _validate_schema(
        private_truth, schema_name=PRIVATE_TRUTH_SCHEMA, skill_root=root
    )
    _assert_public_private_separation(
        public_context=public_context, private_truth=private_truth
    )
    _assert_graph_invariants(private_truth)

    source_hashes = {
        relative: file_sha256(path) for relative, path in sorted(source_paths.items())
    }
    build_context_sha256 = canonical_sha256(source_hashes)
    service_ids = sorted(
        str(item["service_id"])
        for item in private_truth["topology"]["services"]
    )
    image_manifest = {
        "schema": "battle.v16.image_digest_manifest.v1",
        "target_id": TARGET_ID,
        "base_image_digest": base_image_digest,
        "service_image_id": image_digest,
        "build_context_sha256": build_context_sha256,
        "services": {
            service_id: {
                "image_id": image_digest,
                "build_context_sha256": build_context_sha256,
            }
            for service_id in service_ids
        },
        "all_images_immutable": True,
    }

    attack_graph = {
        "schema": "battle.v16.attack_graph.v1",
        "target_id": TARGET_ID,
        **private_truth["attack_graph"],
    }
    defense_graph = {
        "schema": "battle.v16.defense_graph.v1",
        "target_id": TARGET_ID,
        **private_truth["defense_graph"],
    }

    output = out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    public_path = _write_json(output / "public-context-manifest.json", public_context)
    private_path = _write_json(output / "private-truth-manifest.json", private_truth)
    image_path = _write_json(output / "image-digest-manifest.json", image_manifest)
    attack_path = _write_json(output / "attack-graph.json", attack_graph)
    defense_path = _write_json(output / "defense-graph.json", defense_graph)

    reference_contracts = private_truth["reference_contracts"]
    memory_contracts = private_truth["memory_contracts"]
    freeze_manifest = {
        "schema": "battle.v16.target_freeze.v1",
        "status": "FROZEN_NOT_QUALIFIED",
        "target_id": TARGET_ID,
        "semantic_version": TARGET_SEMANTIC_VERSION,
        "repository_commit": repository_commit,
        "architecture_sha256": file_sha256(architecture_path),
        "image_digest_manifest_sha256": canonical_sha256(image_manifest),
        "public_context_sha256": canonical_sha256(public_context),
        "private_truth_sha256": canonical_sha256(private_truth),
        "topology_sha256": canonical_sha256(private_truth["topology"]),
        "attack_graph_sha256": canonical_sha256(attack_graph),
        "defense_graph_sha256": canonical_sha256(defense_graph),
        "public_context_schema_sha256": file_sha256(
            _schema_root(root) / PUBLIC_CONTEXT_SCHEMA
        ),
        "private_truth_schema_sha256": file_sha256(
            _schema_root(root) / PRIVATE_TRUTH_SCHEMA
        ),
        "target_freeze_schema_sha256": file_sha256(
            _schema_root(root) / TARGET_FREEZE_SCHEMA
        ),
        "judge_outcome_schema_sha256": file_sha256(
            _schema_root(root) / JUDGE_OUTCOME_SCHEMA
        ),
        "deterministic_qualification_schema_sha256": file_sha256(
            _schema_root(root) / DETERMINISTIC_QUALIFICATION_SCHEMA
        ),
        "arena_freeze_command_receipt_schema_sha256": file_sha256(
            _schema_root(root) / ARENA_FREEZE_COMMAND_RECEIPT_SCHEMA
        ),
        "judge_predicate_corpus_sha256": canonical_sha256(predicates),
        "regression_corpus_sha256": canonical_sha256(regressions),
        "reference_exploit_contract_sha256": canonical_sha256(
            reference_contracts["red_exploits"]
        ),
        "reference_defense_contract_sha256": canonical_sha256(
            reference_contracts["blue_defenses"]
        ),
        "instance_seed_schedule_sha256": canonical_sha256(
            private_truth["instance_seed_schedule"]
        ),
        "source_memory_contract_sha256": canonical_sha256(memory_contracts),
        "action_schema_sha256": canonical_sha256(public_context["action_schema"]),
        "action_budget_sha256": canonical_sha256(public_context["action_budget"]),
        "source_files": source_hashes,
        "artifacts": {
            "public_context": public_path.name,
            "private_truth": private_path.name,
            "image_digests": image_path.name,
            "attack_graph": attack_path.name,
            "defense_graph": defense_path.name,
        },
        "qualification_eligible": False,
        "blockers": list(FREEZE_BLOCKERS),
        "claims": {
            "may_claim": [
                "The RelayForge contract and RF-A/RF-B/RF-C deterministic verticals are content-addressed"
            ],
            "must_not_claim": [
                "RelayForge is deterministically qualified",
                "RF-D has been behaviorally validated as a decoy",
                "Broad quarantine is implemented",
                "Any V16 Memory packet or uptake chain is implemented",
            ],
        },
    }
    _validate_schema(
        freeze_manifest, schema_name=TARGET_FREEZE_SCHEMA, skill_root=root
    )
    freeze_path = _write_json(output / "arena-freeze-manifest.json", freeze_manifest)
    target_identity_sha256 = canonical_sha256(freeze_manifest)
    identity = {
        "schema": "battle.v16.target_identity.v1",
        "status": "FROZEN_NOT_QUALIFIED",
        "target_id": TARGET_ID,
        "semantic_version": TARGET_SEMANTIC_VERSION,
        "target_identity_sha256": target_identity_sha256,
        "freeze_manifest_sha256": canonical_sha256(freeze_manifest),
        "freeze_manifest_file_sha256": file_sha256(freeze_path),
        "qualification_eligible": False,
        "blockers": list(FREEZE_BLOCKERS),
    }
    identity_path = _write_json(output / "target-identity.json", identity)

    command_receipt = {
        "schema": "battle.v16.arena_freeze_command_receipt.v1",
        "status": "CONTRACT_FROZEN",
        "target_id": TARGET_ID,
        "target_identity_sha256": target_identity_sha256,
        "target_identity_path": str(identity_path),
        "freeze_manifest_path": str(freeze_path),
        "qualification_eligible": False,
        "blockers": list(FREEZE_BLOCKERS),
        "pass_emitted": False,
    }
    _validate_schema(
        command_receipt,
        schema_name=ARENA_FREEZE_COMMAND_RECEIPT_SCHEMA,
        skill_root=root,
    )
    return command_receipt


def run_relayforge_deterministic_qualification(
    *,
    freeze: Path,
    out: Path,
    target: str = TARGET_ID,
    skill_root: Path | None = None,
) -> dict[str, Any]:
    """Run all real-path acceptance proofs while keeping the full target fail closed."""

    if target != TARGET_ID:
        raise RelayForgeContractError(
            f"RF-A/RF-B/RF-C verticals support exactly {TARGET_ID}; received {target}"
        )
    root = (skill_root or _skill_root()).resolve()
    freeze_root = freeze.resolve()
    freeze_manifest = _read_json(freeze_root / "arena-freeze-manifest.json")
    identity = _read_json(freeze_root / "target-identity.json")
    _validate_schema(
        freeze_manifest, schema_name=TARGET_FREEZE_SCHEMA, skill_root=root
    )
    computed_identity = canonical_sha256(freeze_manifest)
    if identity.get("target_identity_sha256") != computed_identity:
        raise RelayForgeContractError(
            "target identity does not match canonical arena-freeze-manifest.json"
        )

    output = out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    judge = _judge_module(root)
    with tempfile.TemporaryDirectory(prefix="relayforge-rf-a-rf-b-rf-c-qualification-") as temporary:
        temporary_root = Path(temporary)
        judge_outcome = judge.evaluate(
            _target_root(root) / "judge",
            state_root=temporary_root / "state",
            sink_root=temporary_root / "sinks",
            artifact_root=output,
        )
    _validate_schema(
        judge_outcome, schema_name=JUDGE_OUTCOME_SCHEMA, skill_root=root
    )

    rf_a = judge_outcome["rf_a_vertical"]
    rf_b = judge_outcome["rf_b_vertical"]
    rf_c = judge_outcome["rf_c_vertical"]
    for label, vertical in (("RF-A", rf_a), ("RF-B", rf_b), ("RF-C", rf_c)):
        for name, expected_sha256 in vertical["artifact_sha256"].items():
            artifact_path = output / name
            if not artifact_path.is_file():
                raise RelayForgeContractError(
                    f"{label} Judge artifact is missing: {artifact_path}"
                )
            actual_sha256 = canonical_sha256(_read_json(artifact_path))
            if actual_sha256 != expected_sha256:
                raise RelayForgeContractError(
                    f"{label} Judge artifact hash drift for {name}: {actual_sha256} != {expected_sha256}"
                )

    judge_path = _write_json(output / "judge-outcome.json", judge_outcome)
    blockers = sorted(
        set(
            [
                *freeze_manifest.get("blockers", []),
                *judge_outcome.get("blockers", []),
            ]
        )
    )
    if rf_a.get("status") != "PASS":
        blockers = sorted({*blockers, "rf_a_vertical_failed"})
    if rf_b.get("status") != "PASS":
        blockers = sorted({*blockers, "rf_b_vertical_failed"})
    if rf_c.get("status") != "PASS":
        blockers = sorted({*blockers, "rf_c_vertical_failed"})
    result = {
        "schema": "battle.v16.deterministic_qualification.v1",
        "status": "BLOCKED",
        "target_id": TARGET_ID,
        "target_identity_sha256": computed_identity,
        "freeze_manifest_sha256": canonical_sha256(freeze_manifest),
        "judge_outcome_sha256": canonical_sha256(judge_outcome),
        "rf_a_vertical_status": rf_a["status"],
        "rf_a_artifact_sha256": dict(rf_a["artifact_sha256"]),
        "rf_b_vertical_status": rf_b["status"],
        "rf_b_artifact_sha256": dict(rf_b["artifact_sha256"]),
        "rf_c_vertical_status": rf_c["status"],
        "rf_c_artifact_sha256": dict(rf_c["artifact_sha256"]),
        "blockers": blockers,
        "pass_emitted": False,
        "claims": {
            "may_claim": [
                item
                for item, passed in (
                    ("RF-A deterministic acceptance passed", rf_a["status"] == "PASS"),
                    ("RF-B deterministic acceptance passed", rf_b["status"] == "PASS"),
                    ("RF-C deterministic acceptance passed", rf_c["status"] == "PASS"),
                )
                if passed
            ],
            "must_not_claim": [
                "RelayForge deterministic qualification passed",
                "RF-D was behaviorally validated as a decoy",
                "Broad quarantine was evaluated",
                "Durable Memory packets or uptake were evaluated",
                "The six-campaign live canary may begin",
            ],
        },
    }
    _validate_schema(
        result, schema_name=DETERMINISTIC_QUALIFICATION_SCHEMA, skill_root=root
    )
    result_path = _write_json(output / "deterministic-qualification.json", result)
    return {
        **result,
        "result_path": str(result_path),
        "judge_outcome_path": str(judge_path),
    }
