"""Generate synthetic F36 engineering QRA families from immutable requirements."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Literal

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator

import generator


app = typer.Typer(no_args_is_help=True)
SKILL_DIR = Path(__file__).resolve().parent
PROMPT_DIR = SKILL_DIR / "prompts" / "f36_requirement"
SYSTEM_PROMPT_PATH = PROMPT_DIR / "engineering_qra_family_system.txt"
USER_PROMPT_PATH = PROMPT_DIR / "engineering_qra_family_user.txt"
EXPECTED_RESPONSE_PATH = PROMPT_DIR / "expected_response.json"
TEMPLATE_VERSION = "f36-engineering-question-templates-v2"
PROMPT_KIND = "f36_requirement_engineering_qra_family_v1"
REQUIRED_VARIANTS = (
    ("operator", "simple"),
    ("project_manager", "simple"),
    ("systems_engineer", "medium"),
    ("cybersecurity_compliance_officer", "medium"),
    ("mission_assurance_cybersecurity_reviewer", "advanced"),
)
TYPE_ALIASES = {
    "cybersecurity": "cybersecurity",
    "safety": "safety",
    "interface": "interface",
    "supply_chain": "supply_chain_provenance",
    "human_factors": "human_factors",
    "performance": "performance",
    "environmental": "environmental",
    "verification": "verification_acceptance",
}


class EngineeringIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engineering_obligation_id: str = Field(min_length=1)
    primary_component_family_id: str = Field(min_length=1)
    protected_object_or_interface: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    required_behavior: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)


class CanonicalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=r"^C[0-9]{2}$")
    claim_class: Literal["engineering"]
    text: str = Field(min_length=1)
    source_artifact_ids: list[str]


class EngineeringSemanticCore(BaseModel):
    """The complete model-authored surface. Questions are intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1)
    requirement_revision_id: str = Field(min_length=1)
    requirement_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    canonical_intent: EngineeringIntent
    engineering_rationale: str = Field(min_length=1)
    verification_observable: str = Field(min_length=1)
    canonical_answer: str = Field(min_length=1)
    canonical_claims: list[CanonicalClaim] = Field(min_length=1)
    canonical_evidence_query: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_control_resolution(self) -> "EngineeringSemanticCore":
        surface = "\n".join(
            [
                self.engineering_rationale,
                self.verification_observable,
                self.canonical_answer,
                self.canonical_evidence_query,
                *(item.text for item in self.canonical_claims),
            ]
        )
        forbidden = re.compile(r"\b(?:SPARTA|CM\d{4}|[A-Z]{2}-\d{4}(?:\.\d+)?)\b", re.IGNORECASE)
        if forbidden.search(surface):
            raise ValueError("engineering QRA stage must not introduce SPARTA/control identifiers")
        return self


# Compatibility alias retained for existing consumers of the F36 extension.
EngineeringQRAFamilyResponse = EngineeringSemanticCore


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def canonical_json_hash(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def intent_tuple(intent: EngineeringIntent) -> tuple[str, ...]:
    return tuple(normalize_text(str(value)) for value in intent.model_dump().values())


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if data.get("schema") != "f36.synthetic_engineering_qra_generation_manifest.v1":
        raise ValueError(f"unsupported manifest schema: {data.get('schema')}")
    return data


def review_manifest(data: dict[str, Any]) -> dict[str, Any]:
    jobs = data.get("jobs") or []
    families = data.get("families") or []
    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def block(issue_id: str, detail: str) -> None:
        blocking.append({"id": issue_id, "detail": detail})

    if len(jobs) != 3680 or len(families) != 3680:
        block("F36QRA001", f"expected 3680 jobs/families, got {len(jobs)}/{len(families)}")
    job_ids = [item.get("job_id") for item in jobs]
    stable_ids = [item.get("stable_item_id") for item in jobs]
    if len(set(job_ids)) != len(job_ids):
        block("F36QRA002", "duplicate job_id")
    if len(set(stable_ids)) != len(stable_ids):
        block("F36QRA003", "duplicate stable_item_id")
    if any(item.get("job_type") != "engineering_qra_family" for item in jobs):
        block("F36QRA004", "unsupported job_type")
    if any(item.get("prompt_kind") != PROMPT_KIND for item in jobs):
        block("F36QRA005", "unsupported or missing prompt_kind")
    if any(
        tuple((entry.get("role"), entry.get("difficulty")) for entry in item.get("requested_variant_plan") or [])
        != REQUIRED_VARIANTS
        for item in jobs
    ):
        block("F36QRA006", "job variant plan differs from required five-role plan")
    if any(not item.get("required_output", {}).get("sparta_control_resolution_forbidden") for item in jobs):
        block("F36QRA007", "engineering stage must explicitly forbid SPARTA control resolution")
    missing = [str(path) for path in (SYSTEM_PROMPT_PATH, USER_PROMPT_PATH, EXPECTED_RESPONSE_PATH) if not path.exists()]
    if missing:
        block("F36QRA008", f"missing prompt contract files: {missing}")
    else:
        try:
            EngineeringSemanticCore.model_validate(json.loads(EXPECTED_RESPONSE_PATH.read_text()))
        except Exception as exc:
            block("F36QRA009", f"expected response fixture failed schema validation: {exc}")

    declared = data.get("generation_contract") or {}
    if declared.get("backend") != "/v1/scillm/batch/completions":
        block("F36QRA010", "manifest does not declare the SciLLM batch backend")
    if declared.get("model_pool") != "qra-deepseek-pool":
        warnings.append({"id": "F36QRAW01", "detail": "non-default model pool declared"})
    if declared.get("response_format") != {"type": "json_object"}:
        block("F36QRA011", "JSON object response format is required")

    status = "BLOCKED" if blocking else "FULL_RUN_OK"
    return {
        "schema": "create_qras.f36_requirement_manifest_review.v2",
        "verdict": {"status": status},
        "blocking_issues": blocking,
        "warnings": warnings,
        "job_count": len(jobs),
        "family_count": len(families),
        "contract": "semantic_core_plus_deterministic_questions",
        "question_template_version": TEMPLATE_VERSION,
        "prompt_inventory": {
            "system": {"path": str(SYSTEM_PROMPT_PATH), "sha256": sha256_text(SYSTEM_PROMPT_PATH.read_text()) if SYSTEM_PROMPT_PATH.exists() else None},
            "user": {"path": str(USER_PROMPT_PATH), "sha256": sha256_text(USER_PROMPT_PATH.read_text()) if USER_PROMPT_PATH.exists() else None},
            "expected_response": {"path": str(EXPECTED_RESPONSE_PATH), "sha256": sha256_text(EXPECTED_RESPONSE_PATH.read_text()) if EXPECTED_RESPONSE_PATH.exists() else None},
        },
        "execution_gate": ["review", "dry_run", "one_item_canary", "heterogeneous_canary", "reviewed_batches_of_100"],
    }


def render_messages(job: dict[str, Any]) -> list[dict[str, str]]:
    source = job["source_record"]
    user_prompt = USER_PROMPT_PATH.read_text().format(
        engineering_qra_family_id=job["engineering_qra_family_id"],
        engineering_obligation_id=job["engineering_obligation_id"],
        requirement_revision_id=job["requirement_revision_id"],
        requirement_content_hash=job["requirement_content_hash"],
        requirement_id=source["requirement_id"],
        title=source["title"],
        statement=source["statement"],
        rationale=source["rationale"],
        requirement_type=source["requirement_type"],
        major_system_id=source["major_system_id"],
        subsystem_id=source["subsystem_id"],
        primary_component_family_id=source["primary_component_family_id"],
        source_artifact_ids=json.dumps(source.get("source_artifact_ids") or []),
    )
    return [{"role": "system", "content": SYSTEM_PROMPT_PATH.read_text()}, {"role": "user", "content": user_prompt}]


def render_questions(intent: EngineeringIntent) -> tuple[dict[str, str], list[dict[str, str]]]:
    obj = intent.protected_object_or_interface
    condition = intent.condition
    outcome = intent.expected_outcome
    canonical = {
        "question": f"For the condition '{condition}', what must {obj} do, and what outcome must result?",
        "reasoning": "This asks directly for the condition, required behavior, and expected outcome in the immutable engineering obligation.",
    }
    variants = [
        {
            "question": f"For '{condition}', what must {obj} do?",
            "reasoning": "This is the operator-facing form of the same condition and required behavior.",
        },
        {
            "question": f"What behavior and outcome must the {obj} capability deliver for '{condition}'?",
            "reasoning": "This is the delivery-facing form of the same engineering obligation.",
        },
        {
            "question": f"How shall {obj} respond for '{condition}' to achieve '{outcome}'?",
            "reasoning": "This expresses the same condition, behavior, and outcome as a system constraint.",
        },
        {
            "question": f"What engineering behavior and outcome must be traceable for {obj} under '{condition}'?",
            "reasoning": "This asks for traceability of the same engineering obligation without adding a control claim.",
        },
        {
            "question": f"How does the requirement constrain {obj} under '{condition}', and what behavior and outcome must assurance evidence substantiate?",
            "reasoning": "This asks an advanced assurance question about the same bounded engineering intent.",
        },
    ]
    return canonical, variants


def validate_materialized_family(result: dict[str, Any], intent: EngineeringIntent) -> dict[str, Any]:
    canonical, expected_variants = render_questions(intent)
    answer = result["canonical_qra"]["canonical_answer_text"]
    answer_hash = sha256_text(answer)
    intent_hash = canonical_json_hash(intent.model_dump())
    errors: list[str] = []
    if result["canonical_qra"]["question"] != canonical["question"]:
        errors.append("canonical_question_template_mismatch")
    for index, (variant, expected) in enumerate(zip(result["variants"], expected_variants, strict=True), start=1):
        if variant.get("question") != expected["question"]:
            errors.append(f"variant_{index}_question_template_mismatch")
        if variant.get("answer") != answer or variant.get("canonical_answer_hash") != answer_hash:
            errors.append(f"variant_{index}_answer_mismatch")
        if variant.get("intent_hash") != intent_hash:
            errors.append(f"variant_{index}_intent_mismatch")
    questions = [item["question"] for item in result["variants"]]
    if len({normalize_text(item) for item in questions}) != 5:
        errors.append("variant_questions_not_unique")
    return {
        "schema": "create_qras.f36_deterministic_variant_validator.v1",
        "status": "PASS" if not errors else "FAIL",
        "template_version": TEMPLATE_VERSION,
        "canonical_answer_hash": answer_hash,
        "canonical_intent_hash": intent_hash,
        "errors": errors,
        "mocked": False,
        "live": False,
    }


def assemble_family(family: dict[str, Any], core: EngineeringSemanticCore, provider_meta: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(family))
    canonical, variants = render_questions(core.canonical_intent)
    answer_hash = sha256_text(core.canonical_answer)
    intent_hash = canonical_json_hash(core.canonical_intent.model_dump())
    evidence_query = {
        "text": core.canonical_evidence_query,
        "sha256": sha256_text(core.canonical_evidence_query),
        "derivation_version": "f36-requirement-engineering-qra-v2",
        "material_claim_ids": [item.claim_id for item in core.canonical_claims],
    }
    result["canonical_qra"] = {
        "generation_state": "generated_candidate",
        "question": canonical["question"],
        "reasoning": canonical["reasoning"],
        "canonical_answer_text": core.canonical_answer,
        "canonical_answer_hash": answer_hash,
        "canonical_intent": core.canonical_intent.model_dump(),
        "canonical_intent_hash": intent_hash,
        "engineering_rationale": core.engineering_rationale,
        "verification_observable": core.verification_observable,
        "canonical_claims": [item.model_dump() for item in core.canonical_claims],
        "canonical_evidence_query": evidence_query,
    }
    for target, rendered, (role, difficulty) in zip(result["variants"], variants, REQUIRED_VARIANTS, strict=True):
        target.update(
            {
                "role": role,
                "difficulty": difficulty,
                "generation_state": "generated_candidate",
                "question": rendered["question"],
                "reasoning": rendered["reasoning"],
                "answer": core.canonical_answer,
                "canonical_answer_hash": answer_hash,
                "intent_hash": intent_hash,
                "question_template_version": TEMPLATE_VERSION,
            }
        )
    validator = validate_materialized_family(result, core.canonical_intent)
    if validator["status"] != "PASS":
        raise ValueError(f"deterministic variant validation failed: {validator['errors']}")
    validator_id = f"F36B-QRA-VAL-{validator['canonical_intent_hash'].split(':', 1)[1][:20]}"
    validator["validator_receipt_id"] = validator_id
    for target in result["variants"]:
        target["variant_resolution"] = {
            "state": "deterministic_intent_match",
            "canonical_answer_hash_match": True,
            "obligation_match": True,
            "material_entity_set_match": True,
            "new_claim_count": 0,
            "validator_receipt_id": validator_id,
            "available_for_use": True,
        }
    result["variant_validator_receipt"] = validator
    result["claim_support"] = [
        {
            "claim_id": item.claim_id,
            "support_domain": "f36_architecture",
            "source_artifact_ids": item.source_artifact_ids,
            "source_passage_ids": [],
            "evidence_case_id": None,
        }
        for item in core.canonical_claims
    ]
    result["projection_eligibility"]["qra_engineering_inventory"] = True
    result["projection_eligibility"]["reason_codes"] = ["sparta_not_assessed"]
    result["generation_receipt"] = {
        "generator": "skill:create-qras:f36-requirement",
        "contract": "semantic_core_plus_deterministic_questions",
        "prompt_kind": PROMPT_KIND,
        "prompt_hash": provider_meta.get("prompt_hash"),
        "semantic_core_hash": canonical_json_hash(core.model_dump()),
        "provider": provider_meta.get("provider"),
        "model": provider_meta.get("model"),
        "lane": provider_meta.get("lane"),
        "batch_id": provider_meta.get("batch_id"),
        "item_id": provider_meta.get("item_id"),
        "item_receipt_ids": provider_meta.get("item_receipt_ids") or [],
        "generated_at": int(time.time()),
        "mocked": False,
        "live": True,
    }
    return result


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


async def post_batch_with_event_ledger(
    payload: dict[str, Any], event_ledger: Path
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    batch_done = False
    async with generator._get_async_scillm_client() as client:
        async with client.stream("POST", "/v1/scillm/batch/completions/stream", json=payload) as response:
            response.raise_for_status()
            async for event_name, event_data in generator._iter_sse_events(response):
                if event_name in {"item_completed", "item_failed", "item_replayed", "batch_done"}:
                    append_jsonl(
                        event_ledger,
                        {
                            "schema": "create_qras.f36_provider_terminal_event.v1",
                            "recorded_at": int(time.time()),
                            "event": event_name,
                            "batch_id": payload["batch_id"],
                            "data": event_data,
                        },
                    )
                if event_name in {"item_completed", "item_failed", "item_replayed"}:
                    item_id = str(event_data.get("item_id") or event_data.get("id") or "")
                    if item_id:
                        normalized = dict(event_data)
                        normalized["terminal_event"] = event_name
                        if event_name == "item_replayed" and "ok" not in normalized:
                            normalized["ok"] = normalized.get("status") == "ok"
                        results[item_id] = normalized
                elif event_name == "batch_done":
                    batch_done = True
    if not batch_done:
        raise RuntimeError("scillm batch stream ended without batch_done")
    return results


def validate_core_against_job(core: EngineeringSemanticCore, job: dict[str, Any]) -> None:
    source = job["source_record"]
    expected = {
        "requirement_id": source["requirement_id"],
        "requirement_revision_id": job["requirement_revision_id"],
        "requirement_content_hash": job["requirement_content_hash"],
        "engineering_obligation_id": job["engineering_obligation_id"],
        "primary_component_family_id": source["primary_component_family_id"],
    }
    observed = {
        "requirement_id": core.requirement_id,
        "requirement_revision_id": core.requirement_revision_id,
        "requirement_content_hash": core.requirement_content_hash,
        "engineering_obligation_id": core.canonical_intent.engineering_obligation_id,
        "primary_component_family_id": core.canonical_intent.primary_component_family_id,
    }
    if observed != expected:
        raise ValueError(f"immutable identity mismatch: expected {expected}, observed {observed}")
    supplied_sources = set(source.get("source_artifact_ids") or [])
    claimed_sources = {source_id for claim in core.canonical_claims for source_id in claim.source_artifact_ids}
    if not claimed_sources.issubset(supplied_sources):
        raise ValueError(f"claim uses unsupplied source artifact ids: {sorted(claimed_sources - supplied_sources)}")


def validate_source_grounding(core: EngineeringSemanticCore, job: dict[str, Any]) -> dict[str, Any]:
    """Apply source-bounded checks without claiming engineering truth."""
    validate_core_against_job(core, job)
    source = job["source_record"]
    supplied_text = " ".join(str(source.get(field) or "") for field in ("title", "statement", "rationale"))
    generated_text = " ".join(
        [
            core.engineering_rationale,
            core.verification_observable,
            core.canonical_answer,
            core.canonical_evidence_query,
            *core.canonical_intent.model_dump().values(),
            *(claim.text for claim in core.canonical_claims),
        ]
    )
    supplied_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", supplied_text))
    generated_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", generated_text))
    invented_numbers = sorted(generated_numbers - supplied_numbers)
    allowed_components = {
        str(source.get("primary_component_family_id") or ""),
        *(str(item) for item in source.get("affected_component_family_ids") or []),
    }
    generated_components = set(re.findall(r"\bF36B-M\d{2}-S\d{2}-C\d{2}\b", generated_text))
    invented_components = sorted(generated_components - allowed_components)
    if invented_numbers:
        raise ValueError(f"generated text introduces unsupplied numeric values: {invented_numbers}")
    if invented_components:
        raise ValueError(f"generated text introduces unsupplied component ids: {invented_components}")
    return {
        "status": "PASS",
        "identity_match": True,
        "source_artifact_ids_bounded": True,
        "invented_numeric_values": 0,
        "invented_component_ids": 0,
        "sparta_control_ids_introduced": 0,
        "engineering_obligations": 1,
        "claims": {
            "proves": ["immutable identity and selected closed-vocabulary/source-bound checks passed"],
            "does_not_prove": ["engineering correctness, completeness, SPARTA applicability, or evidence sufficiency"],
        },
    }


def select_jobs(
    manifest: dict[str, Any], limit: int, only_item: str | None, heterogeneous_canary: str | None
) -> list[dict[str, Any]]:
    jobs = manifest["jobs"]
    if only_item and heterogeneous_canary:
        raise typer.BadParameter("--only-item and --heterogeneous-canary are mutually exclusive")
    if only_item:
        selected = [job for job in jobs if job["stable_item_id"] == only_item]
        if len(selected) != 1:
            raise typer.BadParameter(f"--only-item matched {len(selected)} jobs, expected exactly one")
        return selected
    if heterogeneous_canary:
        requested = [item.strip() for item in heterogeneous_canary.split(",") if item.strip()]
        unknown = sorted(set(requested) - set(TYPE_ALIASES))
        if unknown:
            raise typer.BadParameter(f"unknown heterogeneous classes: {unknown}")
        selected = []
        for requested_type in requested:
            actual_type = TYPE_ALIASES[requested_type]
            matches = sorted(
                (job for job in jobs if job["source_record"]["requirement_type"] == actual_type),
                key=lambda job: job["stable_item_id"],
            )
            if not matches:
                raise typer.BadParameter(f"no manifest job found for {requested_type} ({actual_type})")
            selected.append(matches[0])
        return selected
    return jobs[: limit or None]


def build_calls(jobs: list[dict[str, Any]], repeat: int) -> tuple[list[dict[str, Any]], dict[str, tuple[dict[str, Any], int]]]:
    items: list[dict[str, Any]] = []
    call_map: dict[str, tuple[dict[str, Any], int]] = {}
    for job in jobs:
        for call_number in range(1, repeat + 1):
            call_id = job["stable_item_id"] if repeat == 1 else f"{job['stable_item_id']}::repeat-{call_number:02d}"
            items.append({"id": call_id, "messages": render_messages(job)})
            call_map[call_id] = (job, call_number)
    return items, call_map


def process_chunk(
    jobs: list[dict[str, Any]],
    families: dict[str, dict[str, Any]],
    parent_batch_id: str,
    chunk_index: int,
    repeat: int,
    lane_offset: int,
    event_ledger: Path,
    item_receipt_ledger: Path,
    quarantine_ledger: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    child_batch_id = f"{parent_batch_id}-chunk-{chunk_index:04d}"
    items, call_map = build_calls(jobs, repeat)
    payload = {
        "model_pool": generator.SCILLM_QRA_MODEL_POOL,
        "batch_id": child_batch_id,
        "lane_offset": lane_offset,
        "spill_to_available_lane": False,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "items": items,
    }
    results = asyncio.run(post_batch_with_event_ledger(payload, event_ledger))
    accepted_by_job: dict[str, list[tuple[EngineeringSemanticCore, dict[str, Any], str]]] = {}
    failures: list[dict[str, Any]] = []
    prompt_hashes = {job["stable_item_id"]: canonical_json_hash(render_messages(job)) for job in jobs}

    for call_id, (job, call_number) in call_map.items():
        event = results.get(call_id)
        receipt_id = f"F36B-QRA-ITEM-{sha256_text(child_batch_id + ':' + call_id).split(':', 1)[1][:20]}"
        receipt: dict[str, Any] = {
            "schema": "create_qras.f36_item_generation_receipt.v1",
            "receipt_id": receipt_id,
            "stable_item_id": job["stable_item_id"],
            "provider_item_id": call_id,
            "call_number": call_number,
            "batch_id": child_batch_id,
            "prompt_hash": prompt_hashes[job["stable_item_id"]],
            "prompt_template_id": PROMPT_KIND,
            "source_requirement_id": job["source_record"]["requirement_id"],
            "source_requirement_revision_id": job["requirement_revision_id"],
            "source_requirement_hash": job["requirement_content_hash"],
            "expected_lane_offset": lane_offset,
            "fallback_used": False,
            "mocked": False,
            "live": True,
        }
        try:
            if event is None:
                raise RuntimeError("missing_scillm_terminal_event")
            if not event.get("ok"):
                raise RuntimeError(str(event.get("error") or "provider_item_failed"))
            raw_content = event.get("content") or ""
            parsed = generator._parse_json_content(raw_content)
            core = EngineeringSemanticCore.model_validate(parsed)
            grounding = validate_source_grounding(core, job)
            receipt.update(
                {
                    "status": "accepted",
                    "provider": event.get("provider"),
                    "model": event.get("model"),
                    "lane": event.get("lane"),
                    "terminal_event": event.get("terminal_event"),
                    "content_length": len(raw_content),
                    "raw_content_sha256": sha256_text(raw_content),
                    "json_parse": "PASS",
                    "closed_schema": "PASS",
                    "unknown_fields": 0,
                    "required_fields_missing": 0,
                    "source_grounding": grounding,
                    "canonical_answer_nonempty": bool(core.canonical_answer.strip()),
                    "normalized_intent_tuple_complete": all(intent_tuple(core.canonical_intent)),
                    "semantic_core_hash": canonical_json_hash(core.model_dump()),
                    "intent_tuple_hash": canonical_json_hash(intent_tuple(core.canonical_intent)),
                }
            )
            accepted_by_job.setdefault(job["stable_item_id"], []).append((core, event, receipt_id))
        except Exception as exc:
            receipt.update({"status": "quarantined", "error": str(exc), "error_type": type(exc).__name__})
            failure = {
                "schema": "create_qras.f36_generation_quarantine.v1",
                "stable_item_id": job["stable_item_id"],
                "engineering_qra_family_id": job["engineering_qra_family_id"],
                "provider_item_id": call_id,
                "batch_id": child_batch_id,
                "state": "runtime_error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "mocked": False,
                "live": True,
            }
            append_jsonl(quarantine_ledger, failure)
            failures.append(failure)
        append_jsonl(item_receipt_ledger, receipt)

    records: list[dict[str, Any]] = []
    for job in jobs:
        accepted = accepted_by_job.get(job["stable_item_id"], [])
        if len(accepted) != repeat:
            continue
        tuple_hashes = {canonical_json_hash(intent_tuple(item[0].canonical_intent)) for item in accepted}
        if len(tuple_hashes) != 1:
            failure = {
                "schema": "create_qras.f36_generation_quarantine.v1",
                "stable_item_id": job["stable_item_id"],
                "engineering_qra_family_id": job["engineering_qra_family_id"],
                "batch_id": child_batch_id,
                "state": "runtime_error",
                "error": "repeated semantic cores changed the normalized engineering intent tuple",
                "error_type": "SemanticCoreDisagreement",
                "mocked": False,
                "live": True,
            }
            append_jsonl(quarantine_ledger, failure)
            failures.append(failure)
            continue
        core, event, _ = accepted[0]
        records.append(
            assemble_family(
                families[job["engineering_qra_family_id"]],
                core,
                {
                    "provider": event.get("provider"),
                    "model": event.get("model"),
                    "lane": event.get("lane"),
                    "batch_id": child_batch_id,
                    "item_id": job["stable_item_id"],
                    "item_receipt_ids": [item[2] for item in accepted],
                    "prompt_hash": prompt_hashes[job["stable_item_id"]],
                },
            )
        )
    return records, failures, len(items)


@app.command("review")
def review_command(manifest_path: Path, output: Path = typer.Option(..., "--output", "-o")) -> None:
    result = review_manifest(load_manifest(manifest_path))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(json.dumps(result, indent=2))
    if result["verdict"]["status"] == "BLOCKED":
        raise typer.Exit(1)


@app.command("manifest")
def manifest_command(
    manifest_path: Path,
    review_path: Path = typer.Option(..., "--review"),
    output_jsonl: Path = typer.Option(..., "--output-jsonl"),
    receipt_path: Path = typer.Option(..., "--receipt"),
    event_ledger: Path | None = typer.Option(None, "--event-ledger"),
    item_receipt_ledger: Path | None = typer.Option(None, "--item-receipt-ledger"),
    quarantine_ledger: Path | None = typer.Option(None, "--quarantine-ledger"),
    limit: int = typer.Option(0, "--limit", min=0),
    only_item: str | None = typer.Option(None, "--only-item"),
    heterogeneous_canary: str | None = typer.Option(None, "--heterogeneous-canary"),
    repeat: int = typer.Option(1, "--repeat", min=1, max=2),
    lane_offset: int = typer.Option(0, "--lane-offset", min=0),
    dry_run: bool = typer.Option(False, "--dry-run"),
    batch_id: str = typer.Option("f36b-engineering-qra-families-r1", "--batch-id"),
) -> None:
    manifest = load_manifest(manifest_path)
    review = json.loads(review_path.read_text())
    if review.get("verdict", {}).get("status") not in {"FULL_RUN_OK", "CANARY_ONLY"}:
        raise typer.BadParameter("review verdict must be FULL_RUN_OK or CANARY_ONLY")
    jobs = select_jobs(manifest, limit, only_item, heterogeneous_canary)
    event_ledger = event_ledger or receipt_path.with_name("provider-events.jsonl")
    item_receipt_ledger = item_receipt_ledger or receipt_path.with_name("item-receipts.jsonl")
    quarantine_ledger = quarantine_ledger or receipt_path.with_name("quarantine.jsonl")
    if dry_run:
        for job in jobs:
            render_messages(job)
        receipt = {
            "schema": "create_qras.f36_requirement_run_receipt.v2",
            "status": "dry_run",
            "manifest_path": str(manifest_path.resolve()),
            "review_path": str(review_path.resolve()),
            "selected_jobs": len(jobs),
            "attempted_calls": 0,
            "batch_id": batch_id,
            "contract": "semantic_core_plus_deterministic_questions",
            "mocked": False,
            "live": False,
            "claims": {
                "proves": ["manifest selection and semantic-core prompt rendering were exercised"],
                "does_not_prove": ["model generation, schema conformance, semantic consistency, or persistence"],
            },
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        typer.echo(json.dumps(receipt, indent=2))
        return

    existing_ids: set[str] = set()
    if output_jsonl.exists():
        existing_ids = {
            json.loads(line)["engineering_qra_family_id"]
            for line in output_jsonl.read_text().splitlines()
            if line.strip()
        }
    pending = [job for job in jobs if job["engineering_qra_family_id"] not in existing_ids]
    families = {item["engineering_qra_family_id"]: item for item in manifest["families"]}
    started = int(time.time())
    generated = 0
    attempted_calls = 0
    failures: list[dict[str, Any]] = []
    for offset in range(0, len(pending), 8):
        chunk = pending[offset : offset + 8]
        chunk_index = offset // 8 + 1
        try:
            records, chunk_failures, chunk_calls = process_chunk(
                chunk,
                families,
                batch_id,
                chunk_index,
                repeat,
                lane_offset,
                event_ledger,
                item_receipt_ledger,
                quarantine_ledger,
            )
            attempted_calls += chunk_calls
            for record in records:
                append_jsonl(output_jsonl, record)
            generated += len(records)
            failures.extend(chunk_failures)
            typer.echo(f"chunk {chunk_index}: accepted {len(records)} families", err=True)
            if chunk_failures:
                break
        except Exception as exc:
            failures.append(
                {
                    "state": "runtime_error",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "generated_before_failure": generated,
                }
            )
            break

    selected_family_ids = {job["engineering_qra_family_id"] for job in jobs}
    quarantined_family_ids = {item.get("engineering_qra_family_id") for item in failures if item.get("engineering_qra_family_id")}
    receipt = {
        "schema": "create_qras.f36_requirement_run_receipt.v2",
        "status": "failed" if failures else "completed",
        "manifest_path": str(manifest_path.resolve()),
        "review_path": str(review_path.resolve()),
        "output_jsonl": str(output_jsonl.resolve()),
        "event_ledger": str(event_ledger.resolve()),
        "item_receipt_ledger": str(item_receipt_ledger.resolve()),
        "quarantine_ledger": str(quarantine_ledger.resolve()),
        "selected_jobs": len(jobs),
        "attempted_calls": attempted_calls,
        "replayed_jobs": len(existing_ids.intersection(selected_family_ids)),
        "accepted_jobs": generated,
        "successful_live_calls": generated * repeat,
        "failed_calls": len(failures),
        "accepted_semantic_cores": generated,
        "emitted_family_records": generated,
        "generated_jobs": generated,
        "quarantined_jobs": len(quarantined_family_ids) if quarantined_family_ids else len(failures),
        "failed_jobs": len(failures),
        "failures": failures,
        "repeat": repeat,
        "lane_offset": lane_offset,
        "batch_id": batch_id,
        "contract": "semantic_core_plus_deterministic_questions",
        "run_state": "complete" if not failures else "failed",
        "started_at": started,
        "finished_at": int(time.time()),
        "mocked": False,
        "live": True,
        "claims": {
            "proves": ["accepted records came from live SciLLM terminal events and passed semantic-core and deterministic-variant validators"],
            "does_not_prove": ["full-corpus generation, SPARTA applicability, evidence resolution, human review, certification, or operational correctness"],
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    typer.echo(json.dumps(receipt, indent=2))
    if failures or generated + receipt["replayed_jobs"] != len(jobs):
        raise typer.Exit(1)


@app.command("validate")
def validate_command(
    families_jsonl: Path,
    receipt_path: Path = typer.Option(..., "--receipt"),
    expected_families: int = typer.Option(..., "--expected-families", min=1),
    expected_variants: int | None = typer.Option(None, "--expected-variants", min=1),
    expected_live_calls: int | None = typer.Option(None, "--expected-live-calls", min=1),
) -> None:
    records = [json.loads(line) for line in families_jsonl.read_text().splitlines() if line.strip()]
    receipt = json.loads(receipt_path.read_text())
    errors: list[str] = []
    if len(records) != expected_families:
        errors.append(f"expected {expected_families} families, observed {len(records)}")
    if receipt.get("status") != "completed" or receipt.get("mocked") or not receipt.get("live"):
        errors.append("run receipt is not a completed non-mocked live run")
    if receipt.get("accepted_jobs") != expected_families or receipt.get("quarantined_jobs") != 0:
        errors.append("receipt family counts do not match the accepted fail-closed contract")
    if expected_live_calls is not None and receipt.get("attempted_calls") != expected_live_calls:
        errors.append(f"expected {expected_live_calls} live calls, observed {receipt.get('attempted_calls')}")
    observed_variants = sum(len(record.get("variants") or []) for record in records)
    if expected_variants is not None and observed_variants != expected_variants:
        errors.append(f"expected {expected_variants} variants, observed {observed_variants}")
    for record in records:
        if record.get("sparta_applicability", {}).get("state") != "not_assessed":
            errors.append(f"{record.get('engineering_qra_family_id')}: SPARTA applicability was mutated")
        if record.get("sparta_resolution", {}).get("state") != "not_run":
            errors.append(f"{record.get('engineering_qra_family_id')}: SPARTA resolution was mutated")
        if record.get("operational_authority") or record.get("certification_authority"):
            errors.append(f"{record.get('engineering_qra_family_id')}: authority flag was promoted")
        validator = record.get("variant_validator_receipt") or {}
        if validator.get("status") != "PASS":
            errors.append(f"{record.get('engineering_qra_family_id')}: deterministic validator did not pass")
    result = {
        "schema": "create_qras.f36_corpus_validation.v1",
        "status": "PASS" if not errors else "FAIL",
        "families": len(records),
        "variants": observed_variants,
        "errors": errors,
        "mocked": False,
        "live": True,
    }
    typer.echo(json.dumps(result, indent=2))
    if errors:
        raise typer.Exit(1)


@app.command("phase-gate")
def phase_gate_command(
    one_item_receipt: Path = typer.Option(..., "--one-item-receipt"),
    heterogeneous_receipt: Path = typer.Option(..., "--heterogeneous-receipt"),
    output: Path = typer.Option(..., "--output"),
) -> None:
    receipts = [json.loads(one_item_receipt.read_text()), json.loads(heterogeneous_receipt.read_text())]
    errors = []
    expected = ((1, 2), (8, 8))
    for receipt, (families, calls) in zip(receipts, expected, strict=True):
        if receipt.get("status") != "completed" or receipt.get("mocked") or not receipt.get("live"):
            errors.append(f"{receipt.get('batch_id')}: receipt is not completed live non-mocked evidence")
        if receipt.get("accepted_jobs") != families or receipt.get("attempted_calls") != calls:
            errors.append(f"{receipt.get('batch_id')}: expected {families} families/{calls} calls")
        if receipt.get("quarantined_jobs") != 0:
            errors.append(f"{receipt.get('batch_id')}: quarantined items present")
    result = {
        "schema": "create_qras.f36_bd_canary_phase_gate.v1",
        "status": "PASS" if not errors else "BLOCKED",
        "mocked": False,
        "live": True,
        "evidence": [str(one_item_receipt.resolve()), str(heterogeneous_receipt.resolve())],
        "errors": errors,
        "claims": {
            "proves": ["the repeated-item and heterogeneous B+D canaries met their receipt contracts"] if not errors else [],
            "does_not_prove": ["3,680-family generation, SPARTA evidence resolution, human approval, certification, or operational authority"],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(json.dumps(result, indent=2))
    if errors:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
