"""RelayForge V16 live durable-Memory uptake qualification.

This module closes one bounded gate only:

measured RelayForge observation -> team-scoped production Memory write -> exact
recall -> live Tau/SciLLM provider use -> changed strategy artifact.

It deliberately does not run a RelayForge campaign and does not claim that the
recalled record improves any Judge outcome.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import httpx
import jsonschema

from . import arena_live_battle_proof as live_battle
from .adaptive_memory_ablation import _scillm_auth_readiness, _tau_runtime_readiness

TARGET_ID = "battle-v16-relayforge-a"
GOAL_HASH = "a359b76d3cd379e6f3c7cdafadfd0115c33b6079252b401423a7fd8350974d7a"
MEMORY_COLLECTION = "battle_experiment_memory"
TEAM = "blue"
EXPECTED_SOURCE_BLOCKERS = {
    "durable-memory-packets-unimplemented",
    "live-topology-not-qualified",
}
REMAINING_BLOCKERS = ["live-topology-not-qualified"]
EXPECTED_REGRESSION_VECTOR = {
    "regular-package-import": True,
    "in-bound-transformed-object": False,
    "tenant-owned-report": True,
    "valid-external-preview": False,
    "safe-report-profile": False,
    "legacy-conversion": True,
}
REQUIRED_DETERMINISTIC_STATUSES = (
    "rf_a_vertical_status",
    "rf_b_vertical_status",
    "rf_c_vertical_status",
    "rf_d_validation_status",
    "broad_quarantine_status",
    "decoy_shutdown_status",
)
SCHEMA_FILES = {
    "source": "battle.v16.memory_chain_source_observation.v1.schema.json",
    "write": "battle.v16.memory_chain_write.v1.schema.json",
    "recall": "battle.v16.memory_chain_recall.v1.schema.json",
    "strategy": "battle.v16.memory_chain_strategy.v1.schema.json",
    "provider_use": "battle.v16.memory_chain_provider_use.v1.schema.json",
    "qualification": "battle.v16.memory_chain_qualification.v1.schema.json",
}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class MemoryChainContractError(RuntimeError):
    """Raised when the V16 Memory-chain gate cannot be proven exactly."""


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _schema_root() -> Path:
    return _skill_root() / "schemas"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        raise MemoryChainContractError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MemoryChainContractError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _validate(value: Mapping[str, Any], schema_key: str) -> None:
    schema_path = _schema_root() / SCHEMA_FILES[schema_key]
    schema = _read_json(schema_path)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(dict(value))
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise MemoryChainContractError(
            f"{schema_path.name} validation failed at {location}: {exc.message}"
        ) from exc


def _require_sha(value: Any, label: str) -> str:
    text = str(value or "")
    if not SHA_RE.fullmatch(text):
        raise MemoryChainContractError(f"{label} is not a lowercase SHA-256")
    return text


def _collect_function_results(value: Any, found: dict[str, bool]) -> None:
    if isinstance(value, dict):
        function_id = value.get("function_id")
        passed = value.get("passed")
        actual = value.get("actual")
        outcome = actual == "PASS" if actual in {"PASS", "FAIL"} else passed
        if isinstance(function_id, str) and isinstance(outcome, bool):
            existing = found.get(function_id)
            if existing is not None and existing is not outcome:
                raise MemoryChainContractError(
                    f"conflicting Judge regression result for {function_id}"
                )
            found[function_id] = outcome
        for child in value.values():
            _collect_function_results(child, found)
    elif isinstance(value, list):
        for child in value:
            _collect_function_results(child, found)


def _select_broad_regression_artifact(
    qualification_root: Path, qualification: Mapping[str, Any]
) -> tuple[Path, dict[str, Any], str]:
    artifact_map = qualification.get("broad_quarantine_artifact_sha256")
    if not isinstance(artifact_map, dict) or not artifact_map:
        raise MemoryChainContractError(
            "deterministic qualification lacks broad quarantine artifact hashes"
        )
    names = sorted(str(name) for name in artifact_map)
    regression_names = [name for name in names if "regression" in name.casefold()]
    candidates = regression_names or names
    for name in candidates:
        path = qualification_root / name
        if not path.is_file():
            continue
        payload = _read_json(path)
        expected = _require_sha(artifact_map[name], f"artifact hash for {name}")
        actual = canonical_sha256(payload)
        if actual != expected:
            raise MemoryChainContractError(
                f"Judge artifact hash drift for {name}: {actual} != {expected}"
            )
        results: dict[str, bool] = {}
        _collect_function_results(payload, results)
        if results == EXPECTED_REGRESSION_VECTOR:
            return path, payload, actual
    raise MemoryChainContractError(
        "no hash-bound broad quarantine artifact contains the exact 3-pass/3-fail regression vector"
    )


def build_source_observation(
    *, deterministic_qualification: Path, out: Path
) -> tuple[dict[str, Any], Path]:
    root = deterministic_qualification.expanduser().resolve()
    qualification_path = root / "deterministic-qualification.json"
    judge_path = root / "judge-outcome.json"
    qualification = _read_json(qualification_path)
    judge = _read_json(judge_path)

    if qualification.get("schema") != "battle.v16.deterministic_qualification.v1":
        raise MemoryChainContractError("unexpected deterministic qualification schema")
    if qualification.get("target_id") != TARGET_ID:
        raise MemoryChainContractError("deterministic qualification target mismatch")
    if qualification.get("status") != "BLOCKED" or qualification.get("pass_emitted") is not False:
        raise MemoryChainContractError(
            "deterministic qualification must be immutable BLOCKED evidence"
        )
    blockers = set(qualification.get("blockers") or [])
    if blockers != EXPECTED_SOURCE_BLOCKERS:
        raise MemoryChainContractError(
            f"unexpected deterministic blocker set: {sorted(blockers)}"
        )
    failed = [
        field
        for field in REQUIRED_DETERMINISTIC_STATUSES
        if qualification.get(field) != "PASS"
    ]
    if failed:
        raise MemoryChainContractError(
            "deterministic security evidence is incomplete: " + ", ".join(failed)
        )
    judge_expected = _require_sha(
        qualification.get("judge_outcome_sha256"), "judge_outcome_sha256"
    )
    judge_actual = canonical_sha256(judge)
    if judge_actual != judge_expected:
        raise MemoryChainContractError(
            f"Judge outcome hash drift: {judge_actual} != {judge_expected}"
        )
    artifact_path, _artifact, artifact_sha = _select_broad_regression_artifact(
        root, qualification
    )
    lesson = {
        "summary": (
            "Judge-measured broad quarantine contained the tested security paths but "
            "broke three required functions; prefer evidence-targeted boundary controls "
            "over global service shutdown."
        ),
        "adopt_method": "evidence-targeted-boundary-control",
        "reject_method": "global-service-quarantine",
        "expected_observation": (
            "contain the evidenced trust boundary while preserving the public functionality contract"
        ),
    }
    receipt = {
        "schema": "battle.v16.memory_chain_source_observation.v1",
        "status": "PASS",
        "target_id": TARGET_ID,
        "team": TEAM,
        "deterministic_qualification_path": str(qualification_path),
        "deterministic_qualification_sha256": file_sha256(qualification_path),
        "deterministic_qualification_canonical_sha256": canonical_sha256(qualification),
        "judge_outcome_path": str(judge_path),
        "judge_outcome_sha256": judge_actual,
        "measured_artifact_path": str(artifact_path),
        "measured_artifact_sha256": artifact_sha,
        "measured_regression_vector": EXPECTED_REGRESSION_VECTOR,
        "measured_regression_vector_sha256": canonical_sha256(
            EXPECTED_REGRESSION_VECTOR
        ),
        "lesson": lesson,
        "lesson_sha256": canonical_sha256(lesson),
        "battle_approval": {
            "status": "APPROVED_FOR_DURABLE_WRITE",
            "policy_id": "battle-v16-measured-evidence-memory-gate-v1",
            "visibility_scope": "blue_only",
            "source_must_be_judge_bound": True,
            "memory_is_not_outcome_authority": True,
        },
        "mocked": False,
        "live": False,
        "fixture_fallback_used": False,
        "outcome_improvement_proven": False,
        "created_at": _now(),
    }
    _validate(receipt, "source")
    path = _write_json(out / "source-observation-receipt.json", receipt)
    return receipt, path


def build_pre_memory_strategy(
    *, source_receipt: Mapping[str, Any], source_receipt_sha256: str, out: Path
) -> tuple[dict[str, Any], Path]:
    strategy = {
        "schema": "battle.v16.memory_chain_strategy.v1",
        "status": "PASS",
        "phase": "PRE_MEMORY",
        "target_id": TARGET_ID,
        "team": TEAM,
        "strategy_id": "relayforge-v16-blue-pre-memory",
        "selected_methods": ["global-service-quarantine"],
        "rejected_methods": ["evidence-targeted-boundary-control"],
        "parameters": {"control_scope": "global", "preserve_functionality": False},
        "mutation_origin": "pre-memory baseline",
        "expected_observation": "all advanced workflows are unavailable",
        "memory_origin_reason": None,
        "memory_citations": {},
        "source_observation_receipt_sha256": source_receipt_sha256,
        "source_lesson_sha256": source_receipt["lesson_sha256"],
        "mocked": False,
        "live": False,
        "outcome_improvement_proven": False,
    }
    _validate(strategy, "strategy")
    path = _write_json(out / "strategy-before-memory.json", strategy)
    return strategy, path


def _memory_document(
    *, source: Mapping[str, Any], source_receipt_sha256: str
) -> dict[str, Any]:
    key = f"{TARGET_ID}:memory-chain:{TEAM}:{source_receipt_sha256[:24]}"
    payload = {
        "kind": "battle_v16_relayforge_measured_strategy_evidence",
        "target_id": TARGET_ID,
        "team": TEAM,
        "visibility_scope": "blue_only",
        "source_observation_receipt_sha256": source_receipt_sha256,
        "deterministic_qualification_sha256": source[
            "deterministic_qualification_sha256"
        ],
        "judge_outcome_sha256": source["judge_outcome_sha256"],
        "measured_artifact_sha256": source["measured_artifact_sha256"],
        "lesson": source["lesson"],
        "memory_is_not_outcome_authority": True,
        "status": "current",
    }
    content_sha = canonical_sha256(payload)
    tags = [
        "battle",
        "relayforge-v16",
        "memory-chain",
        f"target:{TARGET_ID}",
        f"team:{TEAM}",
        f"memory-key:{key}",
        f"source-observation-sha:{source_receipt_sha256}",
        f"content-sha:{content_sha}",
    ]
    solution = json.dumps(
        {
            "summary": source["lesson"]["summary"],
            "strategy": {
                "selected_methods": [source["lesson"]["adopt_method"]],
                "rejected_methods": [source["lesson"]["reject_method"]],
                "parameters": {"control_scope": "measured_trust_boundary"},
                "mutation_origin": "durable_memory",
                "expected_observation": source["lesson"]["expected_observation"],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "_key": key,
        **payload,
        "content_sha256": content_sha,
        "problem": (
            "What measured RelayForge defense lesson should the Blue strategy use "
            "without treating Memory as outcome authority?"
        ),
        "solution": solution,
        "tags": tags,
        "updated_at": _now(),
    }


def _memory_service_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Project the evidence record into the registered Memory source fields."""
    return {
        "_key": document["_key"],
        "kind": document["kind"],
        "battle_id": TARGET_ID,
        "experiment_id": "battle-v16-memory-chain",
        "trial_id": "relayforge-blue-uptake",
        "block_id": "durable-memory-packets",
        "condition_id": "memory-on",
        "team": TEAM,
        "source_memory_sha256": document["content_sha256"],
        "problem": document["problem"],
        "solution": document["solution"],
        "tags": document["tags"],
        "status": document["status"],
    }


def _replace_tag(tags: Iterable[str], prefix: str, replacement: str) -> list[str]:
    return [replacement if tag.startswith(prefix) else tag for tag in tags]


def _recall_request(document: Mapping[str, Any], tags: list[str]) -> dict[str, Any]:
    return {
        "q": document["problem"],
        "k": 5,
        "collections": [MEMORY_COLLECTION],
        "tags": tags,
        "threshold": 0.0,
    }


def _documents_from_response(body: Any, label: str) -> list[dict[str, Any]]:
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise MemoryChainContractError(f"{label} response lacks items")
    return [item for item in items if isinstance(item, dict)]


def write_and_recall_memory(
    *,
    source: Mapping[str, Any],
    source_receipt_sha256: str,
    out: Path,
    memory_base_url: str,
    client_factory: Callable[..., httpx.Client] = httpx.Client,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, Path]:
    document = _memory_document(
        source=source, source_receipt_sha256=source_receipt_sha256
    )
    service_document = _memory_service_document(document)
    memory_dir = out / "memory" / TEAM
    try:
        with client_factory(
            base_url=memory_base_url,
            timeout=httpx.Timeout(30.0, connect=3.0),
        ) as client:
            health = client.get("/health")
            health.raise_for_status()
            health_body = health.json()
            _write_json(out / "memory-health.json", health_body)

            existing_response = client.post(
                "/list",
                json={
                    "collection": MEMORY_COLLECTION,
                    "limit": 10,
                    "filters": {"_key": document["_key"]},
                },
            )
            existing_response.raise_for_status()
            existing_body = existing_response.json()
            existing = (
                existing_body.get("documents")
                if isinstance(existing_body, dict)
                else None
            )
            if not isinstance(existing, list):
                raise MemoryChainContractError("Memory list response lacks documents")
            mismatched = [
                item
                for item in existing
                if isinstance(item, dict)
                and canonical_sha256(item) != canonical_sha256(service_document)
            ]
            if mismatched:
                raise MemoryChainContractError(
                    "the exact V16 Memory key already exists with different content"
                )

            write_response = client.post(
                "/upsert",
                json={"collection": MEMORY_COLLECTION, "documents": [service_document]},
            )
            write_response.raise_for_status()
            write_body = write_response.json()
            write_receipt = {
                "schema": "battle.v16.memory_chain_write.v1",
                "status": "PASS",
                "target_id": TARGET_ID,
                "team": TEAM,
                "collection": MEMORY_COLLECTION,
                "memory_key": document["_key"],
                "memory_content_sha256": document["content_sha256"],
                "source_observation_receipt_sha256": source_receipt_sha256,
                "request_document_sha256": canonical_sha256(service_document),
                "service_response_sha256": canonical_sha256(write_body),
                "mocked": False,
                "live": True,
                "fixture_fallback_used": False,
                "created_at": _now(),
            }
            _validate(write_receipt, "write")
            write_path = _write_json(
                memory_dir / "memory-write-receipt.json", write_receipt
            )
            write_receipt_sha = file_sha256(write_path)

            exact_body: dict[str, Any] | None = None
            exact_items: list[dict[str, Any]] = []
            for attempt in range(10):
                response = client.post(
                    "/recall", json=_recall_request(document, list(document["tags"]))
                )
                response.raise_for_status()
                body = response.json()
                items = _documents_from_response(body, "exact recall")
                exact_items = [
                    item
                    for item in items
                    if item.get("_key") == document["_key"]
                    and item.get("team") == TEAM
                    and item.get("battle_id") == TARGET_ID
                    and item.get("source_memory_sha256")
                    == document["content_sha256"]
                    and item.get("solution") == document["solution"]
                    and item.get("tags") == document["tags"]
                ]
                exact_body = body if isinstance(body, dict) else None
                if len(exact_items) == 1:
                    break
                if attempt < 9:
                    time.sleep(1)
            if len(exact_items) != 1 or exact_body is None:
                raise MemoryChainContractError(
                    "exact production Memory recall did not converge to one record"
                )

            negative_requests = {
                "cross_team": _recall_request(
                    document,
                    _replace_tag(list(document["tags"]), "team:", "team:red"),
                ),
                "wrong_key": _recall_request(
                    document,
                    _replace_tag(
                        list(document["tags"]),
                        "memory-key:",
                        f"memory-key:{document['_key']}:wrong",
                    ),
                ),
                "wrong_source_hash": _recall_request(
                    document,
                    _replace_tag(
                        list(document["tags"]),
                        "source-observation-sha:",
                        "source-observation-sha:" + ("0" * 64),
                    ),
                ),
            }
            negative_counts: dict[str, int] = {}
            negative_hashes: dict[str, str] = {}
            for name, request in negative_requests.items():
                response = client.post("/recall", json=request)
                response.raise_for_status()
                body = response.json()
                items = _documents_from_response(body, name)
                negative_counts[name] = len(items)
                negative_hashes[name] = canonical_sha256(body)
                if items:
                    raise MemoryChainContractError(
                        f"Memory isolation failure: {name} recall returned records"
                    )
    except httpx.HTTPError as exc:
        raise MemoryChainContractError(f"production Memory request failed: {exc}") from exc

    recalled_document = exact_items[0]
    recall_receipt = {
        "schema": "battle.v16.memory_chain_recall.v1",
        "status": "PASS",
        "target_id": TARGET_ID,
        "team": TEAM,
        "collection": MEMORY_COLLECTION,
        "memory_key": document["_key"],
        "memory_content_sha256": document["content_sha256"],
        "source_observation_receipt_sha256": source_receipt_sha256,
        "memory_write_receipt_sha256": write_receipt_sha,
        "query_sha256": hashlib.sha256(document["problem"].encode("utf-8")).hexdigest(),
        "exact_match_count": 1,
        "recalled_document_sha256": canonical_sha256(recalled_document),
        "recalled_solution_sha256": hashlib.sha256(
            document["solution"].encode("utf-8")
        ).hexdigest(),
        "service_response_sha256": canonical_sha256(exact_body),
        "negative_item_counts": negative_counts,
        "negative_response_sha256": negative_hashes,
        "cross_team_items_absent": negative_counts["cross_team"] == 0,
        "wrong_key_items_absent": negative_counts["wrong_key"] == 0,
        "wrong_source_hash_items_absent": negative_counts["wrong_source_hash"] == 0,
        "mocked": False,
        "live": True,
        "fixture_fallback_used": False,
        "created_at": _now(),
    }
    _validate(recall_receipt, "recall")
    recall_path = _write_json(
        memory_dir / "memory-recall-receipt.json", recall_receipt
    )
    return document, write_receipt, recall_receipt, write_path, recall_path


def _provider_public_files(
    *,
    provider_root: Path,
    source_receipt_sha256: str,
    pre_strategy: Mapping[str, Any],
) -> dict[str, Any]:
    arena_root = provider_root / "arena" / "team-public"
    target_path = arena_root / "target" / "app.py"
    brief_path = arena_root / "scenario-brief.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        "\"\"\"Public bounded package-import contract for strategy qualification.\"\"\"\n"
        "from pathlib import Path\n"
        "from zipfile import ZipFile\n\n"
        "def import_zip(zip_path: str, destination: str) -> list[str]:\n"
        "    root = Path(destination)\n"
        "    root.mkdir(parents=True, exist_ok=True)\n"
        "    written: list[str] = []\n"
        "    with ZipFile(zip_path) as archive:\n"
        "        for member in archive.infolist():\n"
        "            if member.is_dir():\n"
        "                continue\n"
        "            target = root / member.filename\n"
        "            target.parent.mkdir(parents=True, exist_ok=True)\n"
        "            target.write_bytes(archive.read(member))\n"
        "            written.append(str(target))\n"
        "    return written\n\n"
        + "BASELINE_STRATEGY = "
        + repr(
            {
                "selected_methods": pre_strategy["selected_methods"],
                "parameters": pre_strategy["parameters"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    brief = {
        "schema": "battle.v16.memory_chain_public_brief.v1",
        "target_id": TARGET_ID,
        "public_entrypoint": "strategy-only",
        "source_observation_receipt_sha256": source_receipt_sha256,
        "task": "Produce one Blue strategy mutation from the supplied recalled evidence.",
        "private_truth_included": False,
        "outcome_authority": "Battle and Judge retain outcome authority.",
    }
    _write_json(brief_path, brief)
    return {
        "scenario_id": "relayforge-v16-memory-chain-blue-uptake",
        "public_entrypoint": "strategy-only",
        "brief_path": brief_path,
        "target_path": target_path,
    }


def _provider_entry(manifest: Mapping[str, Any], team: str) -> dict[str, Any]:
    teams = manifest.get("teams")
    if not isinstance(teams, list):
        raise MemoryChainContractError("Tau manifest lacks teams")
    matches = [item for item in teams if isinstance(item, dict) and item.get("team") == team]
    if len(matches) != 1:
        raise MemoryChainContractError(f"Tau manifest must contain exactly one {team} entry")
    return matches[0]


def validate_provider_strategy(
    *,
    parsed: Mapping[str, Any],
    provider_call: Mapping[str, Any],
    manifest: Mapping[str, Any],
    document: Mapping[str, Any],
    recall_receipt_sha256: str,
    source_receipt_sha256: str,
    pre_strategy: Mapping[str, Any],
    pre_strategy_sha256: str,
    memory_write_receipt_sha256: str,
    provider_call_sha256: str,
    tau_manifest_sha256: str,
    provider_call_path: Path | None = None,
    tau_manifest_path: Path | None = None,
    context_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if provider_call.get("live") is not True or provider_call.get("mocked") is not False:
        raise MemoryChainContractError("provider call is not live and non-mocked")
    if provider_call.get("parse_status") != "PASS" or provider_call.get("http_status") != 200:
        raise MemoryChainContractError("provider call did not return parsed HTTP 200 evidence")
    if provider_call.get("fixture_fallback_used") is True or manifest.get(
        "fixture_fallback_used"
    ) is True:
        raise MemoryChainContractError("provider or Tau manifest used fixture fallback")
    strategy = parsed.get("strategy_genome")
    if not isinstance(strategy, dict):
        raise MemoryChainContractError("provider response lacks strategy_genome")
    selected = strategy.get("selected_methods")
    rejected = strategy.get("rejected_methods")
    parameters = strategy.get("parameters")
    mutation_origin = strategy.get("mutation_origin")
    expected_observation = strategy.get("expected_observation")
    if not isinstance(selected, list) or not all(isinstance(item, str) for item in selected):
        raise MemoryChainContractError("strategy_genome.selected_methods is invalid")
    if not isinstance(rejected, list) or not all(isinstance(item, str) for item in rejected):
        raise MemoryChainContractError("strategy_genome.rejected_methods is invalid")
    if not isinstance(parameters, dict):
        raise MemoryChainContractError("strategy_genome.parameters is invalid")
    if not isinstance(mutation_origin, str) or not mutation_origin:
        raise MemoryChainContractError("strategy_genome.mutation_origin is absent")
    if not isinstance(expected_observation, str) or not expected_observation:
        raise MemoryChainContractError("strategy_genome.expected_observation is absent")
    memory_origin_reason = parsed.get("memory_origin_reason") or strategy.get(
        "memory_origin_reason"
    )
    if not isinstance(memory_origin_reason, str) or not memory_origin_reason.strip():
        raise MemoryChainContractError("provider response lacks memory_origin_reason")
    response_text = json.dumps(parsed, sort_keys=True)
    required_tokens = {
        "memory_key": document["_key"],
        "memory_content_sha256": document["content_sha256"],
        "memory_recall_receipt_sha256": recall_receipt_sha256,
        "source_observation_receipt_sha256": source_receipt_sha256,
    }
    citations = {name: token in response_text for name, token in required_tokens.items()}
    if not all(citations.values()):
        missing = [name for name, present in citations.items() if not present]
        raise MemoryChainContractError(
            "provider response lacks exact Memory provenance citations: "
            + ", ".join(missing)
        )
    if "evidence-targeted-boundary-control" not in selected:
        raise MemoryChainContractError("provider did not adopt the recalled method")
    if "global-service-quarantine" not in rejected:
        raise MemoryChainContractError("provider did not reject the baseline broad method")
    if document["_key"] not in mutation_origin and source_receipt_sha256 not in mutation_origin:
        raise MemoryChainContractError(
            "strategy mutation_origin does not identify the recalled record"
        )
    post_strategy = {
        "schema": "battle.v16.memory_chain_strategy.v1",
        "status": "PASS",
        "phase": "POST_MEMORY",
        "target_id": TARGET_ID,
        "team": TEAM,
        "strategy_id": "relayforge-v16-blue-post-memory",
        "selected_methods": selected,
        "rejected_methods": rejected,
        "parameters": parameters,
        "mutation_origin": mutation_origin,
        "expected_observation": expected_observation,
        "memory_origin_reason": memory_origin_reason.strip(),
        "memory_citations": required_tokens,
        "source_observation_receipt_sha256": source_receipt_sha256,
        "source_lesson_sha256": document["lesson"] and canonical_sha256(document["lesson"]),
        "mocked": False,
        "live": True,
        "outcome_improvement_proven": False,
    }
    _validate(post_strategy, "strategy")
    post_sha = canonical_sha256(post_strategy)
    if post_sha == canonical_sha256(pre_strategy):
        raise MemoryChainContractError("provider strategy artifact is unchanged")
    changed_fields = sorted(
        key
        for key in (
            "selected_methods",
            "rejected_methods",
            "parameters",
            "mutation_origin",
            "expected_observation",
        )
        if post_strategy.get(key) != pre_strategy.get(key)
    )
    if not changed_fields:
        raise MemoryChainContractError("provider changed no strategy decision field")
    if not any(field in memory_origin_reason for field in changed_fields):
        raise MemoryChainContractError(
            "memory_origin_reason does not name a changed strategy field"
        )
    use_receipt = {
        "schema": "battle.v16.memory_chain_provider_use.v1",
        "status": "PASS",
        "target_id": TARGET_ID,
        "team": TEAM,
        "memory_key": document["_key"],
        "memory_content_sha256": document["content_sha256"],
        "memory_write_receipt_sha256": memory_write_receipt_sha256,
        "memory_recall_receipt_sha256": recall_receipt_sha256,
        "source_observation_receipt_sha256": source_receipt_sha256,
        "provider_call_receipt_sha256": provider_call_sha256,
        "tau_manifest_sha256": tau_manifest_sha256,
        "provider_call_path": str(provider_call_path.resolve()) if provider_call_path else "NOT_EMITTED_IN_UNIT_VALIDATION",
        "tau_manifest_path": str(tau_manifest_path.resolve()) if tau_manifest_path else "NOT_EMITTED_IN_UNIT_VALIDATION",
        "context_path": str(context_path.resolve()) if context_path else "NOT_EMITTED_IN_UNIT_VALIDATION",
        "provider_citations": citations,
        "memory_origin_reason": memory_origin_reason.strip(),
        "changed_strategy_fields": changed_fields,
        "pre_strategy_sha256": pre_strategy_sha256,
        "post_strategy_canonical_sha256": post_sha,
        "adopted_methods": ["evidence-targeted-boundary-control"],
        "rejected_methods": ["global-service-quarantine"],
        "mocked": False,
        "live": True,
        "fixture_fallback_used": False,
        "outcome_improvement_proven": False,
        "claims": {
            "proves": [
                "The live provider cited the exact recalled record and changed a strategy artifact for an explicit Memory-origin reason."
            ],
            "does_not_prove": [
                "The changed strategy improved any RelayForge Judge outcome."
            ],
        },
        "created_at": _now(),
    }
    return post_strategy, use_receipt


def run_live_provider_use(
    *,
    out: Path,
    document: Mapping[str, Any],
    recall_receipt: Mapping[str, Any],
    recall_path: Path,
    source_path: Path,
    pre_strategy: Mapping[str, Any],
    pre_strategy_path: Path,
    tau_root: Path,
    scillm_base_url: str,
    model: str,
    timeout_s: float,
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    try:
        tau_readiness = _tau_runtime_readiness(tau_root=tau_root)
        scillm_readiness = _scillm_auth_readiness(
            tau_root=tau_root, scillm_base_url=scillm_base_url, model=model
        )
    except Exception as exc:  # external Tau/SciLLM readiness boundary
        raise MemoryChainContractError(f"Tau/SciLLM readiness failed: {exc}") from exc
    if tau_readiness.get("status") != "PASS" or scillm_readiness.get("status") != "PASS":
        raise MemoryChainContractError("Tau or SciLLM readiness did not PASS")

    provider_root = out / "provider"
    provider_root.mkdir(parents=True, exist_ok=True)
    source_sha = file_sha256(source_path)
    public = _provider_public_files(
        provider_root=provider_root,
        source_receipt_sha256=source_sha,
        pre_strategy=pre_strategy,
    )
    scenario = {
        "scenario_id": public["scenario_id"],
        "public_entrypoint": public["public_entrypoint"],
    }
    context_path = live_battle._write_tau_public_context(
        out_dir=provider_root,
        battle_id=TARGET_ID,
        run_id="relayforge-v16-memory-chain",
        scenario=scenario,
        red_workers=1,
        blue_workers=1,
    )
    context = _read_json(context_path)
    recall_sha = file_sha256(recall_path)
    context["summary"]["mode"] = "v16_memory_chain_qualification"
    context["summary"]["teams"]["red"]["objective"] = (
        "Return a bounded public-only audit artifact without using durable Memory. "
        "Do not claim any security outcome."
    )
    context["summary"]["teams"]["blue"]["objective"] = (
        "Produce a changed Blue strategy artifact from the exact recalled record. "
        f"In rationale and strategy_genome.mutation_origin cite memory_key={document['_key']}, "
        f"memory_content_sha256={document['content_sha256']}, "
        f"memory_recall_receipt_sha256={recall_sha}, and "
        f"source_observation_receipt_sha256={source_sha}. "
        "Return memory_origin_reason that names each changed strategy field. "
        "strategy_genome must contain selected_methods, rejected_methods, parameters, "
        "mutation_origin, expected_observation, and memory_origin_reason. "
        "Adopt exact selected method evidence-targeted-boundary-control and reject exact "
        "method global-service-quarantine. Memory is design input only and does not prove improvement."
    )
    context["team_contexts"] = {
        "red": {
            "team": "red",
            "durable_memory_recall": None,
            "pre_memory_strategy": None,
            "authority": {
                "memory_available": False,
                "memory_is_design_input_only": True,
                "outcome_improvement_proven": False,
            },
        },
        "blue": {
            "team": TEAM,
            "durable_memory_recall": {
                "memory_key": document["_key"],
                "memory_content_sha256": document["content_sha256"],
                "memory_recall_receipt_sha256": recall_sha,
                "source_observation_receipt_sha256": source_sha,
                "summary": document["lesson"]["summary"],
                "strategy": json.loads(document["solution"])["strategy"],
            },
            "pre_memory_strategy": dict(pre_strategy),
            "authority": {
                "memory_is_design_input_only": True,
                "outcome_improvement_proven": False,
            },
        }
    }
    _write_json(context_path, context)

    original_tau_repo = live_battle.TAU_REPO
    live_battle.TAU_REPO = tau_root.expanduser().resolve()
    try:
        manifest_path = live_battle._run_tau_harness(
            out_dir=provider_root,
            battle_id=TARGET_ID,
            run_id="relayforge-v16-memory-chain",
            scenario_id=scenario["scenario_id"],
            context_path=context_path,
            red_persona="battle-red-public-auditor",
            blue_persona="battle-blue-durable-memory-child",
            model=model,
            scillm_base_url=scillm_base_url,
            timeout_s=timeout_s,
            red_workers=1,
            blue_workers=1,
        )
    except Exception as exc:  # external Tau/provider process boundary
        raise MemoryChainContractError(f"live Tau/provider handoff failed: {exc}") from exc
    finally:
        live_battle.TAU_REPO = original_tau_repo

    manifest = _read_json(manifest_path)
    if manifest.get("status") != "PASS":
        raise MemoryChainContractError(
            f"Tau live handoff did not PASS: {manifest.get('reason')}"
        )
    if manifest.get("mocked") is not False or manifest.get("live") is not True:
        raise MemoryChainContractError("Tau manifest is not live and non-mocked")
    entry = _provider_entry(manifest, TEAM)
    materialized = entry.get("materialized")
    if entry.get("status") != "PASS" or not isinstance(materialized, dict) or materialized.get("status") != "PASS":
        raise MemoryChainContractError("Blue Tau lane did not materialize a PASS artifact")
    call_path = Path(str(entry.get("scillm_call") or ""))
    if not call_path.is_file():
        raise MemoryChainContractError("Blue provider call receipt is missing")
    provider_call = _read_json(call_path)
    parsed = provider_call.get("parsed_json")
    if not isinstance(parsed, dict):
        raise MemoryChainContractError("Blue provider response is not parsed JSON")
    post_strategy, use_receipt = validate_provider_strategy(
        parsed=parsed,
        provider_call=provider_call,
        manifest=manifest,
        document=document,
        recall_receipt_sha256=recall_sha,
        source_receipt_sha256=source_sha,
        pre_strategy=pre_strategy,
        pre_strategy_sha256=file_sha256(pre_strategy_path),
        memory_write_receipt_sha256=str(recall_receipt["memory_write_receipt_sha256"]),
        provider_call_sha256=file_sha256(call_path),
        tau_manifest_sha256=file_sha256(manifest_path),
        provider_call_path=call_path,
        tau_manifest_path=manifest_path,
        context_path=context_path,
    )
    strategy_path = _write_json(out / "strategy-after-memory.json", post_strategy)
    use_receipt = {
        **use_receipt,
        "post_strategy_artifact_sha256": file_sha256(strategy_path),
    }
    _validate(use_receipt, "provider_use")
    use_path = _write_json(out / "memory-use-acknowledgement.json", use_receipt)
    return post_strategy, use_receipt, strategy_path, use_path


def _artifact_entry(path: Path, out: Path) -> dict[str, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(out.resolve()).as_posix()
    except ValueError:
        relative = "EXTERNAL_SOURCE/" + resolved.name
    return {
        "absolute_path": str(resolved),
        "relative_path": relative,
        "sha256": file_sha256(resolved),
    }


def run_relayforge_v16_memory_chain(
    *,
    target: str,
    deterministic_qualification: Path,
    out: Path,
    memory_base_url: str = "http://127.0.0.1:8601",
    tau_root: Path = Path("/home/graham/workspace/experiments/tau"),
    scillm_base_url: str = "http://localhost:4001",
    model: str = "gpt-5.5",
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Execute the one live V16 durable-Memory qualification chain."""

    if target != TARGET_ID:
        raise MemoryChainContractError(
            f"this gate supports exactly {TARGET_ID}; received {target}"
        )
    output = out.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    source, source_path = build_source_observation(
        deterministic_qualification=deterministic_qualification, out=output
    )
    source_sha = file_sha256(source_path)
    pre_strategy, pre_strategy_path = build_pre_memory_strategy(
        source_receipt=source,
        source_receipt_sha256=source_sha,
        out=output,
    )

    document, write, recall, write_path, recall_path = write_and_recall_memory(
        source=source,
        source_receipt_sha256=source_sha,
        out=output,
        memory_base_url=memory_base_url,
    )
    _, provider_use, strategy_path, use_path = run_live_provider_use(
        out=output,
        document=document,
        recall_receipt=recall,
        recall_path=recall_path,
        source_path=source_path,
        pre_strategy=pre_strategy,
        pre_strategy_path=pre_strategy_path,
        tau_root=tau_root,
        scillm_base_url=scillm_base_url,
        model=model,
        timeout_s=timeout_s,
    )

    artifact_paths = {
        "source_observation": _artifact_entry(source_path, output),
        "strategy_before_memory": _artifact_entry(pre_strategy_path, output),
        "memory_write": _artifact_entry(write_path, output),
        "memory_recall": _artifact_entry(recall_path, output),
        "provider_context": _artifact_entry(Path(provider_use["context_path"]), output),
        "tau_manifest": _artifact_entry(Path(provider_use["tau_manifest_path"]), output),
        "provider_call": _artifact_entry(Path(provider_use["provider_call_path"]), output),
        "strategy_after_memory": _artifact_entry(strategy_path, output),
        "provider_use": _artifact_entry(use_path, output),
    }
    receipt = {
        "schema": "battle.v16.memory_chain_qualification.v1",
        "status": "PASS",
        "target_id": TARGET_ID,
        "goal_hash": GOAL_HASH,
        "team": TEAM,
        "collection": MEMORY_COLLECTION,
        "mocked": False,
        "live": True,
        "fixture_fallback_used": False,
        "source_observation_receipt_sha256": source_sha,
        "memory_write_receipt_sha256": file_sha256(write_path),
        "memory_recall_receipt_sha256": file_sha256(recall_path),
        "provider_use_receipt_sha256": file_sha256(use_path),
        "pre_strategy_artifact_sha256": file_sha256(pre_strategy_path),
        "post_strategy_artifact_sha256": file_sha256(strategy_path),
        "memory_key": document["_key"],
        "memory_content_sha256": document["content_sha256"],
        "closed_blocker": "durable-memory-packets-unimplemented",
        "remaining_blockers": REMAINING_BLOCKERS,
        "artifact_paths": artifact_paths,
        "outcome_improvement_proven": False,
        "claims": {
            "proves": [
                "Battle wrote and exactly recalled one team-scoped measured RelayForge record through the production Memory API.",
                "A live Tau/SciLLM provider cited and used that exact record to change a strategy artifact for an explicit Memory-origin reason.",
            ],
            "does_not_prove": [
                "The changed strategy improves any Red or Blue Judge outcome.",
                "The RelayForge live bounded campaign or topology is qualified.",
                "The Memory service enforces authorization beyond the demonstrated exact filters.",
            ],
        },
        "created_at": _now(),
    }
    # Re-read and re-hash every linked artifact immediately before PASS.
    for name, entry in artifact_paths.items():
        path = Path(entry["absolute_path"])
        if not path.is_file() or file_sha256(path) != entry["sha256"]:
            raise MemoryChainContractError(f"final artifact hash drift: {name}")
    if provider_use.get("status") != "PASS" or write.get("status") != "PASS" or recall.get("status") != "PASS":
        raise MemoryChainContractError("one live Memory-chain receipt is not PASS")
    _validate(receipt, "qualification")
    result_path = _write_json(output / "memory-chain-qualification.json", receipt)
    return {**receipt, "result_path": str(result_path)}


def runtime_defaults() -> dict[str, Any]:
    """Resolve optional live service settings without adding mandatory CLI flags."""

    return {
        "memory_base_url": os.environ.get(
            "BATTLE_MEMORY_BASE_URL", "http://127.0.0.1:8601"
        ),
        "tau_root": Path(
            os.environ.get(
                "BATTLE_TAU_PROJECT_ROOT", "/home/graham/workspace/experiments/tau"
            )
        ),
        "scillm_base_url": os.environ.get("SCILLM_BASE_URL", "http://localhost:4001"),
        "model": os.environ.get("BATTLE_MODEL", "gpt-5.5"),
        "timeout_s": float(os.environ.get("BATTLE_MEMORY_CHAIN_TIMEOUT_S", "300")),
    }
