"""Deterministic WebGPT export/import for synthetic F36 engineering QRA families.

This module intentionally performs no live-provider calls.  It exports immutable
F36 requirements for a separately proven WebGPT transport and imports only a
closed, fail-closed complete-family artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Literal

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


app = typer.Typer(no_args_is_help=True)
SKILL_DIR = Path(__file__).resolve().parent
PROMPT_DIR = SKILL_DIR / "prompts" / "f36_requirement"
WEBGPT_CONTRACT_PATH = PROMPT_DIR / "webgpt_complete_family_contract.md"
WEBGPT_EXPECTED_BATCH_PATH = PROMPT_DIR / "webgpt_expected_batch.json"

MANIFEST_SCHEMA = "f36.synthetic_engineering_qra_generation_manifest.v1"
EXPORT_SCHEMA = "f36.webgpt_complete_family_export.v1"
EXPORT_REQUIREMENT_SCHEMA = "f36.webgpt_export_requirement.v1"
OUTPUT_BATCH_SCHEMA = "f36.webgpt_complete_family_batch.v1"
OUTPUT_FAMILY_SCHEMA = "f36.webgpt_complete_family.v1"
IMPORTED_BATCH_SCHEMA = "f36.webgpt_imported_family_batch.v1"
QUARANTINE_SCHEMA = "f36.webgpt_import_quarantine.v1"
TRANSPORT_RECEIPT_SCHEMA = "create_qras.webgpt_transport_receipt.v1"
CONTRACT_VERSION = "f36-webgpt-complete-family-v1"

REQUIRED_VARIANTS: tuple[tuple[str, str], ...] = (
    ("operator", "simple"),
    ("project_manager", "simple"),
    ("systems_engineer", "medium"),
    ("cybersecurity_compliance_officer", "medium"),
    ("mission_assurance_cybersecurity_reviewer", "advanced"),
)

CONTROL_ID_PATTERN = re.compile(
    r"\b(?:SPARTA|CWE-\d+|CAPEC-\d+|CM\d{4}|ST\d{4}|"
    r"(?:REC|RD|IA|EX|PER|DE|LM|EXF|IMP)-\d{4}(?:\.\d+)?|"
    r"[A-Z]{2}-\d+(?:\(\d+\))?|T\d{4}(?:\.\d+)?|d3f:[A-Za-z0-9_]+)\b",
    re.IGNORECASE,
)
COMPONENT_ID_PATTERN = re.compile(r"\bF36B-M\d{2}-S\d{2}-C\d{2}\b")
NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")
UNSUPPORTED_PROOF_PATTERN = re.compile(
    r"\b(?:certified|approved|accepted|operationally proven|test results (?:show|prove|demonstrate)|"
    r"evidence (?:shows|proves|demonstrates)|has been (?:verified|validated|tested))\b",
    re.IGNORECASE,
)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does", "for",
    "from", "how", "if", "in", "into", "is", "it", "must", "of", "on", "or", "shall", "should",
    "that", "the", "their", "then", "this", "to", "under", "what", "when", "where", "which", "while",
    "who", "why", "will", "with", "without", "would", "requirement", "system", "engineering", "outcome",
    "behavior", "behaviour", "condition", "interface", "component", "capability", "ensure", "required",
}
GENERIC_SEMANTIC_TOKENS = {
    "operator", "project", "manager", "management", "delivery", "systems", "engineer", "cybersecurity",
    "compliance", "officer", "mission", "assurance", "review", "reviewer", "simple", "medium", "advanced",
    "ask", "asks", "answer", "answers", "explain", "explains", "describe", "describes", "identify", "identifies",
    "state", "states", "perform", "performs", "preserve", "preserves", "achieve", "achieves", "result", "results",
    "respond", "responds", "response", "function", "functions", "action", "actions", "applies", "applicable",
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", value.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> dict[str, Any]:
    data = read_json(path)
    if data.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported manifest schema: {data.get('schema')}")
    return data


class SourceFragments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protected_object_or_interface: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    required_behavior: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)


class CompleteIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engineering_obligation_id: str = Field(min_length=1)
    primary_component_family_id: str = Field(min_length=1)
    protected_object_or_interface: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    required_behavior: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)
    source_fragments: SourceFragments

    @model_validator(mode="after")
    def fragments_equal_intent(self) -> "CompleteIntent":
        for field_name in (
            "protected_object_or_interface",
            "condition",
            "required_behavior",
            "expected_outcome",
        ):
            if normalize_text(getattr(self, field_name)) != normalize_text(
                getattr(self.source_fragments, field_name)
            ):
                raise ValueError(f"{field_name} must match its source fragment")
        return self


class CompleteVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str = Field(min_length=1)
    role: Literal[
        "operator",
        "project_manager",
        "systems_engineer",
        "cybersecurity_compliance_officer",
        "mission_assurance_cybersecurity_reviewer",
    ]
    difficulty: Literal["simple", "medium", "advanced"]
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    intent_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class CompleteFamily(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal[OUTPUT_FAMILY_SCHEMA] = Field(alias="schema")
    stable_item_id: str = Field(min_length=1)
    engineering_qra_family_id: str = Field(min_length=1)
    engineering_obligation_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    requirement_revision_id: str = Field(min_length=1)
    requirement_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    primary_component_family_id: str = Field(min_length=1)
    canonical_question: str = Field(min_length=1)
    canonical_answer: str = Field(min_length=1)
    canonical_intent: CompleteIntent
    variants: list[CompleteVariant] = Field(min_length=5, max_length=5)
    synthetic: Literal[True]
    operational_authority: Literal[False]
    certification_authority: Literal[False]
    engineering_qra_state: Literal["generated_candidate"]
    sparta_applicability: Literal["not_assessed"]
    sparta_resolution: Literal["not_run"]
    resolved_control_ids: list[str]
    crosswalk_chain_ids: list[str]
    evidence_case_id: None

    @model_validator(mode="after")
    def fail_closed_fields(self) -> "CompleteFamily":
        if self.resolved_control_ids:
            raise ValueError("resolved_control_ids must be empty")
        if self.crosswalk_chain_ids:
            raise ValueError("crosswalk_chain_ids must be empty")
        return self


class CompleteBatchEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal[OUTPUT_BATCH_SCHEMA] = Field(alias="schema")
    export_id: str = Field(min_length=1)
    canonical_input_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    synthetic: Literal[True]
    operational_authority: Literal[False]
    certification_authority: Literal[False]
    families: list[dict[str, Any]]


class WebGPTTransportReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal[TRANSPORT_RECEIPT_SCHEMA] = Field(alias="schema")
    status: Literal["completed"]
    export_id: str = Field(min_length=1)
    canonical_input_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    mocked: Literal[False]
    live: Literal[True]


def _variant_ids_for_family(family: dict[str, Any]) -> list[str]:
    variants = family.get("variants") or []
    ids = [str(item.get("variant_id") or "") for item in variants]
    if len(ids) != 5 or any(not item for item in ids) or len(set(ids)) != 5:
        raise ValueError(f"family {family.get('engineering_qra_family_id')} does not have five unique variant IDs")
    return ids


def review_manifest(data: dict[str, Any]) -> dict[str, Any]:
    jobs = data.get("jobs") or []
    families = data.get("families") or []
    blocking: list[dict[str, str]] = []

    def block(issue_id: str, detail: str) -> None:
        blocking.append({"id": issue_id, "detail": detail})

    if len(jobs) != 3680 or len(families) != 3680:
        block("F36W001", f"expected 3680 jobs/families, got {len(jobs)}/{len(families)}")
    job_ids = [item.get("job_id") for item in jobs]
    stable_ids = [item.get("stable_item_id") for item in jobs]
    family_ids = [item.get("engineering_qra_family_id") for item in families]
    if len(set(job_ids)) != len(job_ids):
        block("F36W002", "duplicate job_id")
    if len(set(stable_ids)) != len(stable_ids):
        block("F36W003", "duplicate stable_item_id")
    if len(set(family_ids)) != len(family_ids):
        block("F36W004", "duplicate engineering_qra_family_id")
    if any(item.get("job_type") != "engineering_qra_family" for item in jobs):
        block("F36W005", "unsupported job_type")
    if any(
        tuple((entry.get("role"), entry.get("difficulty")) for entry in item.get("requested_variant_plan") or [])
        != REQUIRED_VARIANTS
        for item in jobs
    ):
        block("F36W006", "job variant plan differs from required order")

    family_map = {str(item.get("engineering_qra_family_id")): item for item in families}
    for job in jobs:
        family = family_map.get(str(job.get("engineering_qra_family_id")))
        if family is None:
            block("F36W007", f"missing family for {job.get('engineering_qra_family_id')}")
            break
        try:
            _variant_ids_for_family(family)
        except ValueError as exc:
            block("F36W008", str(exc))
            break

    for required_path in (WEBGPT_CONTRACT_PATH, WEBGPT_EXPECTED_BATCH_PATH):
        if not required_path.exists():
            block("F36W009", f"missing WebGPT contract artifact: {required_path}")
    if WEBGPT_EXPECTED_BATCH_PATH.exists():
        try:
            raw_fixture = read_json(WEBGPT_EXPECTED_BATCH_PATH)
            envelope = CompleteBatchEnvelope.model_validate(raw_fixture)
            for raw_family in envelope.families:
                CompleteFamily.model_validate(raw_family)
        except Exception as exc:  # pragma: no cover - exercised by manifest review users
            block("F36W010", f"expected WebGPT fixture failed closed-schema validation: {exc}")

    status = "BLOCKED" if blocking else "FULL_RUN_OK"
    return {
        "schema": "create_qras.f36_webgpt_manifest_review.v1",
        "verdict": {"status": status},
        "blocking_issues": blocking,
        "job_count": len(jobs),
        "family_count": len(families),
        "contract": CONTRACT_VERSION,
        "execution_surface": "deterministic_webgpt_export_import",
        "provider_calls": False,
        "prompt_inventory": {
            "contract": {
                "path": str(WEBGPT_CONTRACT_PATH),
                "sha256": sha256_file(WEBGPT_CONTRACT_PATH) if WEBGPT_CONTRACT_PATH.exists() else None,
            },
            "expected_batch": {
                "path": str(WEBGPT_EXPECTED_BATCH_PATH),
                "sha256": sha256_file(WEBGPT_EXPECTED_BATCH_PATH) if WEBGPT_EXPECTED_BATCH_PATH.exists() else None,
            },
        },
        "mocked": False,
        "live": False,
        "claims": {
            "proves": ["manifest cardinality, stable IDs, variant-plan order, and local contract fixtures were checked"],
            "does_not_prove": ["WebGPT transport, engineering correctness, SPARTA applicability, evidence grounding, certification, or operational correctness"],
        },
    }


EXPORT_TOP_LEVEL_FIELDS = {
    "schema",
    "contract_version",
    "manifest_schema",
    "batch_ordinal",
    "batch_size",
    "batch_start_index",
    "requirement_count",
    "expected_family_count",
    "expected_variant_count",
    "variant_order",
    "synthetic",
    "operational_authority",
    "certification_authority",
    "requirements",
    "export_id",
    "canonical_input_sha256",
}
EXPORT_REQUIREMENT_FIELDS = {
    "schema",
    "batch_item_ordinal",
    "stable_item_id",
    "engineering_qra_family_id",
    "engineering_obligation_id",
    "requirement_id",
    "requirement_revision_id",
    "requirement_content_hash",
    "primary_component_family_id",
    "source_record",
    "variants",
}
EXPORT_VARIANT_FIELDS = {"variant_id", "role", "difficulty"}


def validate_export_bundle(exported: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown = sorted(set(exported) - EXPORT_TOP_LEVEL_FIELDS)
    missing = sorted(EXPORT_TOP_LEVEL_FIELDS - set(exported))
    if unknown:
        errors.append("requirements_export_unknown_fields:" + ",".join(unknown))
    if missing:
        errors.append("requirements_export_missing_fields:" + ",".join(missing))
    if exported.get("schema") != EXPORT_SCHEMA:
        errors.append("requirements_export_schema_invalid")
    if exported.get("contract_version") != CONTRACT_VERSION:
        errors.append("requirements_export_contract_version_invalid")
    if exported.get("manifest_schema") != MANIFEST_SCHEMA:
        errors.append("requirements_export_manifest_schema_invalid")
    if exported.get("synthetic") is not True or exported.get("operational_authority") is not False or exported.get("certification_authority") is not False:
        errors.append("requirements_export_authority_flags_invalid")

    canonical_input = {
        key: value
        for key, value in exported.items()
        if key not in {"export_id", "canonical_input_sha256"}
    }
    recomputed = canonical_json_hash(canonical_input)
    if exported.get("canonical_input_sha256") != recomputed:
        errors.append("requirements_export_canonical_input_hash_mismatch")
    expected_export_id = f"F36B-WEBGPT-EXPORT-{recomputed.split(':', 1)[1][:20]}"
    if exported.get("export_id") != expected_export_id:
        errors.append("requirements_export_id_mismatch")

    requirements = exported.get("requirements")
    if not isinstance(requirements, list):
        return sorted(set(errors + ["requirements_export_requirements_not_list"]))
    if exported.get("requirement_count") != len(requirements):
        errors.append("requirements_export_requirement_count_mismatch")
    if exported.get("expected_family_count") != len(requirements):
        errors.append("requirements_export_expected_family_count_mismatch")
    if exported.get("expected_variant_count") != len(requirements) * 5:
        errors.append("requirements_export_expected_variant_count_mismatch")
    if exported.get("variant_order") != [
        {"position": position, "role": role, "difficulty": difficulty}
        for position, (role, difficulty) in enumerate(REQUIRED_VARIANTS, start=1)
    ]:
        errors.append("requirements_export_variant_order_invalid")

    stable_ids: list[str] = []
    family_ids: list[str] = []
    requirement_ids: list[str] = []
    for index, item in enumerate(requirements):
        if not isinstance(item, dict):
            errors.append(f"requirements_export_item_{index}_not_object")
            continue
        item_unknown = sorted(set(item) - EXPORT_REQUIREMENT_FIELDS)
        item_missing = sorted(EXPORT_REQUIREMENT_FIELDS - set(item))
        if item_unknown:
            errors.append(f"requirements_export_item_{index}_unknown_fields:" + ",".join(item_unknown))
        if item_missing:
            errors.append(f"requirements_export_item_{index}_missing_fields:" + ",".join(item_missing))
        if item.get("schema") != EXPORT_REQUIREMENT_SCHEMA:
            errors.append(f"requirements_export_item_{index}_schema_invalid")
        if item.get("batch_item_ordinal") != exported.get("batch_start_index", 0) + index + 1:
            errors.append(f"requirements_export_item_{index}_ordinal_invalid")
        source = item.get("source_record")
        if not isinstance(source, dict):
            errors.append(f"requirements_export_item_{index}_source_record_invalid")
        else:
            if item.get("requirement_id") != source.get("requirement_id"):
                errors.append(f"requirements_export_item_{index}_source_requirement_id_mismatch")
            if item.get("primary_component_family_id") != source.get("primary_component_family_id"):
                errors.append(f"requirements_export_item_{index}_source_component_owner_mismatch")
        variants = item.get("variants")
        if not isinstance(variants, list) or len(variants) != 5:
            errors.append(f"requirements_export_item_{index}_variant_count_invalid")
        else:
            triples = []
            for variant_index, variant in enumerate(variants):
                if not isinstance(variant, dict):
                    errors.append(f"requirements_export_item_{index}_variant_{variant_index}_not_object")
                    continue
                if set(variant) != EXPORT_VARIANT_FIELDS:
                    errors.append(f"requirements_export_item_{index}_variant_{variant_index}_fields_invalid")
                triples.append((variant.get("role"), variant.get("difficulty")))
            if tuple(triples) != REQUIRED_VARIANTS:
                errors.append(f"requirements_export_item_{index}_variant_order_invalid")
            variant_ids = [str(variant.get("variant_id") or "") for variant in variants if isinstance(variant, dict)]
            if len(variant_ids) != 5 or any(not value for value in variant_ids) or len(set(variant_ids)) != 5:
                errors.append(f"requirements_export_item_{index}_variant_ids_invalid")
        stable_ids.append(str(item.get("stable_item_id") or ""))
        family_ids.append(str(item.get("engineering_qra_family_id") or ""))
        requirement_ids.append(str(item.get("requirement_id") or ""))
    if len(set(stable_ids)) != len(stable_ids) or any(not item for item in stable_ids):
        errors.append("requirements_export_stable_ids_invalid")
    if len(set(family_ids)) != len(family_ids) or any(not item for item in family_ids):
        errors.append("requirements_export_family_ids_invalid")
    if len(set(requirement_ids)) != len(requirement_ids) or any(not item for item in requirement_ids):
        errors.append("requirements_export_requirement_ids_invalid")
    return sorted(set(errors))


def _export_requirement(job: dict[str, Any], family: dict[str, Any], ordinal: int) -> dict[str, Any]:
    source = job.get("source_record")
    if not isinstance(source, dict):
        raise ValueError(f"job {job.get('stable_item_id')} has no source_record")
    required_job_fields = (
        "stable_item_id",
        "engineering_qra_family_id",
        "engineering_obligation_id",
        "requirement_revision_id",
        "requirement_content_hash",
    )
    missing = [field for field in required_job_fields if not job.get(field)]
    if missing:
        raise ValueError(f"job {job.get('stable_item_id')} missing fields: {missing}")
    for field in ("requirement_id", "primary_component_family_id"):
        if not source.get(field):
            raise ValueError(f"job {job.get('stable_item_id')} source_record missing {field}")
    variant_ids = _variant_ids_for_family(family)
    variants = [
        {"variant_id": variant_id, "role": role, "difficulty": difficulty}
        for variant_id, (role, difficulty) in zip(variant_ids, REQUIRED_VARIANTS, strict=True)
    ]
    return {
        "schema": EXPORT_REQUIREMENT_SCHEMA,
        "batch_item_ordinal": ordinal,
        "stable_item_id": job["stable_item_id"],
        "engineering_qra_family_id": job["engineering_qra_family_id"],
        "engineering_obligation_id": job["engineering_obligation_id"],
        "requirement_id": source["requirement_id"],
        "requirement_revision_id": job["requirement_revision_id"],
        "requirement_content_hash": job["requirement_content_hash"],
        "primary_component_family_id": source["primary_component_family_id"],
        "source_record": source,
        "variants": variants,
    }


def build_export_bundle(manifest: dict[str, Any], batch_ordinal: int, batch_size: int) -> dict[str, Any]:
    if batch_ordinal < 1:
        raise ValueError("batch_ordinal must be at least 1")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    jobs = manifest.get("jobs") or []
    families = manifest.get("families") or []
    family_map = {str(item.get("engineering_qra_family_id")): item for item in families}
    start = (batch_ordinal - 1) * batch_size
    selected = jobs[start : start + batch_size]
    if not selected:
        raise ValueError(f"batch ordinal {batch_ordinal} selects no manifest jobs")
    requirements = []
    for index, job in enumerate(selected, start=start + 1):
        family_id = str(job.get("engineering_qra_family_id") or "")
        family = family_map.get(family_id)
        if family is None:
            raise ValueError(f"manifest family missing for job {job.get('stable_item_id')}")
        requirements.append(_export_requirement(job, family, index))

    canonical_input = {
        "schema": EXPORT_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "manifest_schema": manifest.get("schema"),
        "batch_ordinal": batch_ordinal,
        "batch_size": batch_size,
        "batch_start_index": start,
        "requirement_count": len(requirements),
        "expected_family_count": len(requirements),
        "expected_variant_count": len(requirements) * 5,
        "variant_order": [
            {"position": position, "role": role, "difficulty": difficulty}
            for position, (role, difficulty) in enumerate(REQUIRED_VARIANTS, start=1)
        ],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "requirements": requirements,
    }
    canonical_input_sha256 = canonical_json_hash(canonical_input)
    export_id = f"F36B-WEBGPT-EXPORT-{canonical_input_sha256.split(':', 1)[1][:20]}"
    return {
        **canonical_input,
        "export_id": export_id,
        "canonical_input_sha256": canonical_input_sha256,
    }


def render_request(export_bundle: dict[str, Any]) -> str:
    contract = WEBGPT_CONTRACT_PATH.read_text(encoding="utf-8")
    metadata = {
        "export_id": export_bundle["export_id"],
        "canonical_input_sha256": export_bundle["canonical_input_sha256"],
        "batch_ordinal": export_bundle["batch_ordinal"],
        "requirement_count": export_bundle["requirement_count"],
        "expected_family_count": export_bundle["expected_family_count"],
        "expected_variant_count": export_bundle["expected_variant_count"],
        "requirements_file": "requirements.json",
    }
    return (
        "# F36B WebGPT Complete-Family Request\n\n"
        "## Export metadata\n\n"
        "```json\n"
        + json.dumps(metadata, indent=2, ensure_ascii=False)
        + "\n```\n\n"
        + contract.rstrip()
        + "\n"
    )


def export_webgpt_batch(manifest_path: Path, batch_ordinal: int, batch_size: int, output_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    bundle = build_export_bundle(manifest, batch_ordinal, batch_size)
    output_dir.mkdir(parents=True, exist_ok=True)
    requirements_path = output_dir / "requirements.json"
    request_path = output_dir / "request.md"
    receipt_path = output_dir / "export-receipt.json"
    write_json(requirements_path, bundle)
    request_path.write_text(render_request(bundle), encoding="utf-8")
    requirements = bundle["requirements"]
    receipt = {
        "schema": "create_qras.f36_webgpt_export_receipt.v1",
        "status": "completed",
        "contract_version": CONTRACT_VERSION,
        "export_id": bundle["export_id"],
        "canonical_input_sha256": bundle["canonical_input_sha256"],
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "requirements_path": str(requirements_path.resolve()),
        "requirements_sha256": sha256_file(requirements_path),
        "request_path": str(request_path.resolve()),
        "request_sha256": sha256_file(request_path),
        "batch_ordinal": batch_ordinal,
        "batch_size": batch_size,
        "requirement_count": len(requirements),
        "expected_family_count": len(requirements),
        "expected_variant_count": len(requirements) * 5,
        "expected_families": len(requirements),
        "expected_variants": len(requirements) * 5,
        "first_stable_item_id": requirements[0]["stable_item_id"],
        "last_stable_item_id": requirements[-1]["stable_item_id"],
        "first_family_id": requirements[0]["engineering_qra_family_id"],
        "last_family_id": requirements[-1]["engineering_qra_family_id"],
        "mocked": False,
        "live": False,
        "claims": {
            "proves": ["stable manifest selection and deterministic WebGPT request export"],
            "does_not_prove": ["WebGPT transport, family generation, engineering correctness, SPARTA applicability, evidence grounding, certification, or operational correctness"],
        },
    }
    write_json(receipt_path, receipt)
    return receipt


def _source_text(exported: dict[str, Any]) -> str:
    source = exported.get("source_record") or {}
    return "\n".join(str(source.get(field) or "") for field in ("title", "statement", "rationale"))


def _semantic_surface(family: CompleteFamily) -> str:
    return "\n".join(
        [
            family.canonical_question,
            family.canonical_answer,
            family.canonical_intent.protected_object_or_interface,
            family.canonical_intent.condition,
            family.canonical_intent.required_behavior,
            family.canonical_intent.expected_outcome,
            *(variant.question for variant in family.variants),
            *(variant.answer for variant in family.variants),
        ]
    )


def validate_family_against_export(family: CompleteFamily, exported: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    exact_fields = (
        "stable_item_id",
        "engineering_qra_family_id",
        "engineering_obligation_id",
        "requirement_id",
        "requirement_revision_id",
        "requirement_content_hash",
        "primary_component_family_id",
    )
    observed = family.model_dump()
    for field in exact_fields:
        if observed.get(field) != exported.get(field):
            errors.append(f"{field}_mismatch")

    intent = family.canonical_intent
    if intent.engineering_obligation_id != exported.get("engineering_obligation_id"):
        errors.append("canonical_intent_obligation_id_mismatch")
    if intent.primary_component_family_id != exported.get("primary_component_family_id"):
        errors.append("canonical_intent_component_owner_mismatch")

    expected_variants = exported.get("variants") or []
    actual_variant_triples = [(item.variant_id, item.role, item.difficulty) for item in family.variants]
    expected_variant_triples = [
        (str(item.get("variant_id") or ""), item.get("role"), item.get("difficulty"))
        for item in expected_variants
    ]
    if actual_variant_triples != expected_variant_triples:
        errors.append("variant_ids_or_order_mismatch")

    questions = [family.canonical_question, *(item.question for item in family.variants)]
    if any(not item.strip().endswith("?") for item in questions):
        errors.append("question_not_grammatical_question")
    if len({normalize_text(item) for item in questions}) != 6:
        errors.append("canonical_or_variant_questions_not_unique")

    answer = family.canonical_answer
    answer_hash = sha256_text(answer)
    intent_hash = canonical_json_hash(intent.model_dump())
    for index, variant in enumerate(family.variants, start=1):
        if variant.answer != answer:
            errors.append(f"variant_{index}_answer_not_byte_identical")
        if variant.intent_hash != intent_hash:
            errors.append(f"variant_{index}_intent_hash_mismatch")
    if not answer.strip():
        errors.append("canonical_answer_empty")

    source_text = _source_text(exported)
    normalized_source = normalize_text(source_text)
    fragments = intent.source_fragments.model_dump()
    for field_name, fragment in fragments.items():
        if normalize_text(fragment) not in normalized_source:
            errors.append(f"{field_name}_source_fragment_not_found")
        fragment_tokens = meaningful_tokens(fragment)
        if not fragment_tokens:
            errors.append(f"{field_name}_source_fragment_has_no_anchor")
            continue
        if not fragment_tokens.intersection(meaningful_tokens(answer)):
            errors.append(f"canonical_answer_missing_{field_name}_anchor")
        for index, question in enumerate(questions, start=0):
            if not fragment_tokens.intersection(meaningful_tokens(question)):
                label = "canonical" if index == 0 else f"variant_{index}"
                errors.append(f"{label}_missing_{field_name}_anchor")

    semantic_surface = _semantic_surface(family)
    allowed_semantic_tokens = meaningful_tokens(source_text) | GENERIC_SEMANTIC_TOKENS
    expanded_tokens = sorted(meaningful_tokens(semantic_surface) - allowed_semantic_tokens)
    if expanded_tokens:
        errors.append("semantic_expansion_tokens:" + ",".join(expanded_tokens))
    if CONTROL_ID_PATTERN.search(semantic_surface):
        errors.append("sparta_or_control_id_introduced")
    if UNSUPPORTED_PROOF_PATTERN.search(semantic_surface):
        errors.append("unsupported_evidence_or_acceptance_claim")

    source_numbers = set(NUMBER_PATTERN.findall(source_text))
    generated_numbers = set(NUMBER_PATTERN.findall(semantic_surface))
    invented_numbers = sorted(generated_numbers - source_numbers)
    if invented_numbers:
        errors.append("invented_numeric_values:" + ",".join(invented_numbers))

    source_record = exported.get("source_record") or {}
    allowed_components = {
        str(exported.get("primary_component_family_id") or ""),
        *(str(item) for item in source_record.get("affected_component_family_ids") or []),
    }
    generated_components = set(COMPONENT_ID_PATTERN.findall(semantic_surface))
    if generated_components - allowed_components:
        errors.append("invented_component_ids:" + ",".join(sorted(generated_components - allowed_components)))

    # The generated surface may use connective prose, but every intent dimension is
    # extractive and every question/answer must carry anchors from all four source
    # fragments.  This is intentionally a bounded lexical gate, not an engineering
    # correctness claim.
    return sorted(set(errors))


def _transport_state(
    transport_receipt_path: Path | None,
    exported: dict[str, Any],
    request_sha256: str | None,
    output_path: Path,
) -> tuple[bool, str, list[str]]:
    if transport_receipt_path is None:
        return False, "not_provided", []
    errors: list[str] = []
    try:
        receipt = WebGPTTransportReceipt.model_validate(read_json(transport_receipt_path))
    except Exception as exc:
        return False, "invalid", [f"transport_receipt_invalid:{exc}"]
    if receipt.export_id != exported.get("export_id"):
        errors.append("transport_export_id_mismatch")
    if receipt.canonical_input_sha256 != exported.get("canonical_input_sha256"):
        errors.append("transport_canonical_input_hash_mismatch")
    if request_sha256 is None or receipt.request_sha256 != request_sha256:
        errors.append("transport_request_hash_mismatch")
    if receipt.output_sha256 != sha256_file(output_path):
        errors.append("transport_output_hash_mismatch")
    return (not errors), ("verified" if not errors else "invalid"), errors


def _error_record(
    family_id: str,
    requirement_id: str | None,
    reasons: list[str],
    source_index: int | None = None,
    observed_variant_count: int = 0,
) -> dict[str, Any]:
    return {
        "engineering_qra_family_id": family_id,
        "requirement_id": requirement_id,
        "source_index": source_index,
        "observed_variant_count": observed_variant_count,
        "reasons": sorted(set(reasons)),
    }


def import_webgpt_batch(
    requirements_path: Path,
    complete_family_path: Path,
    accepted_output: Path,
    quarantine_output: Path,
    receipt_path: Path,
    transport_receipt_path: Path | None = None,
) -> dict[str, Any]:
    exported = read_json(requirements_path)
    batch_errors: list[str] = validate_export_bundle(exported)
    expected_requirements = exported.get("requirements") or []
    expected_map = {
        str(item.get("engineering_qra_family_id") or ""): item
        for item in expected_requirements
        if isinstance(item, dict)
    }
    if len(expected_map) != len(expected_requirements):
        batch_errors.append("requirements_export_family_ids_invalid")

    try:
        raw_output = read_json(complete_family_path)
    except Exception as exc:
        raw_output = {}
        batch_errors.append(f"output_json_invalid:{exc}")

    top_level_allowed = {
        "schema",
        "export_id",
        "canonical_input_sha256",
        "synthetic",
        "operational_authority",
        "certification_authority",
        "families",
    }
    if raw_output:
        unknown_top = sorted(set(raw_output) - top_level_allowed)
        missing_top = sorted(top_level_allowed - set(raw_output))
        if unknown_top:
            batch_errors.append("unknown_top_level_fields:" + ",".join(unknown_top))
        if missing_top:
            batch_errors.append("missing_top_level_fields:" + ",".join(missing_top))
    try:
        envelope = CompleteBatchEnvelope.model_validate(raw_output) if raw_output else None
    except ValidationError as exc:
        envelope = None
        batch_errors.append("output_envelope_invalid:" + exc.errors()[0]["msg"])

    if envelope is not None:
        if envelope.export_id != exported.get("export_id"):
            batch_errors.append("output_export_id_mismatch")
        if envelope.canonical_input_sha256 != exported.get("canonical_input_sha256"):
            batch_errors.append("output_canonical_input_hash_mismatch")

    request_path = requirements_path.with_name("request.md")
    request_sha256 = sha256_file(request_path) if request_path.exists() else None
    transport_verified, transport_state, transport_errors = _transport_state(
        transport_receipt_path, exported, request_sha256, complete_family_path
    )
    batch_errors.extend(transport_errors)

    raw_families = raw_output.get("families") if isinstance(raw_output.get("families"), list) else []
    parsed_by_id: dict[str, tuple[CompleteFamily, int]] = {}
    per_family_errors: dict[str, list[str]] = {}
    unknown_records: list[dict[str, Any]] = []
    duplicate_ids: set[str] = set()

    for index, raw_family in enumerate(raw_families):
        if not isinstance(raw_family, dict):
            unknown_records.append(_error_record(f"__index_{index}", None, ["family_not_object"], index, 0))
            continue
        family_id = str(raw_family.get("engineering_qra_family_id") or f"__index_{index}")
        if family_id in parsed_by_id or family_id in per_family_errors:
            duplicate_ids.add(family_id)
            per_family_errors.setdefault(family_id, []).append("duplicate_family_id")
            continue
        try:
            family = CompleteFamily.model_validate(raw_family)
        except ValidationError as exc:
            per_family_errors[family_id] = [
                "closed_schema_invalid:" + ";".join(
                    f"{'.'.join(str(part) for part in item['loc'])}:{item['msg']}" for item in exc.errors()
                )
            ]
            continue
        if family_id not in expected_map:
            unknown_records.append(
                _error_record(family_id, family.requirement_id, ["unknown_family_id"], index, len(family.variants))
            )
            continue
        errors = validate_family_against_export(family, expected_map[family_id])
        if errors:
            per_family_errors[family_id] = errors
        else:
            parsed_by_id[family_id] = (family, index)

    if duplicate_ids:
        batch_errors.append("duplicate_family_ids_present")
    for family_id, exported_requirement in expected_map.items():
        if family_id not in parsed_by_id and family_id not in per_family_errors:
            per_family_errors[family_id] = ["missing_family"]
    if len(raw_families) != len(expected_requirements):
        batch_errors.append(
            f"family_count_mismatch:expected={len(expected_requirements)},observed={len(raw_families)}"
        )

    atomic_failure = bool(batch_errors or per_family_errors or unknown_records)
    quarantine_records: list[dict[str, Any]] = []
    if atomic_failure:
        for family_id, exported_requirement in expected_map.items():
            reasons = list(per_family_errors.get(family_id) or [])
            if not reasons:
                reasons.append("atomic_batch_withheld")
            quarantine_records.append(
                _error_record(family_id, str(exported_requirement.get("requirement_id") or ""), reasons, observed_variant_count=5)
            )
        quarantine_records.extend(unknown_records)
        accepted_families: list[dict[str, Any]] = []
    else:
        accepted_families = [
            parsed_by_id[family_id][0].model_dump(mode="json", by_alias=True) for family_id in expected_map
        ]

    accepted_payload = {
        "schema": IMPORTED_BATCH_SCHEMA,
        "status": "accepted" if not atomic_failure else "rejected",
        "usable": not atomic_failure,
        "contract_version": CONTRACT_VERSION,
        "export_id": exported.get("export_id"),
        "canonical_input_sha256": exported.get("canonical_input_sha256"),
        "transport_state": transport_state,
        "mocked": False,
        "live": transport_verified,
        "families": accepted_families,
    }
    quarantine_payload = {
        "schema": QUARANTINE_SCHEMA,
        "status": "clear" if not atomic_failure else "quarantined",
        "export_id": exported.get("export_id"),
        "batch_errors": sorted(set(batch_errors)),
        "records": quarantine_records,
        "mocked": False,
        "live": transport_verified,
    }
    write_json(accepted_output, accepted_payload)
    write_json(quarantine_output, quarantine_payload)

    accepted_family_count = len(accepted_families)
    accepted_variant_count = sum(len(item.get("variants") or []) for item in accepted_families)
    quarantined_expected = len(quarantine_records) if atomic_failure else 0
    quarantined_variant_count = sum(int(item.get("observed_variant_count") or 0) for item in quarantine_records)
    receipt = {
        "schema": "create_qras.f36_webgpt_import_receipt.v1",
        "status": "completed" if not atomic_failure else "rejected",
        "usable_batch": not atomic_failure,
        "contract_version": CONTRACT_VERSION,
        "export_id": exported.get("export_id"),
        "canonical_input_sha256": exported.get("canonical_input_sha256"),
        "requirements_path": str(requirements_path.resolve()),
        "requirements_sha256": sha256_file(requirements_path),
        "output_path": str(complete_family_path.resolve()),
        "output_sha256": sha256_file(complete_family_path),
        "accepted_output": str(accepted_output.resolve()),
        "accepted_output_sha256": sha256_file(accepted_output),
        "quarantine_output": str(quarantine_output.resolve()),
        "quarantine_output_sha256": sha256_file(quarantine_output),
        "transport_receipt": str(transport_receipt_path.resolve()) if transport_receipt_path else None,
        "transport_state": transport_state,
        "accepted_family_count": accepted_family_count,
        "accepted_variant_count": accepted_variant_count,
        "quarantined_family_count": quarantined_expected,
        "quarantined_variant_count": quarantined_variant_count,
        "unknown_output_family_count": len(unknown_records),
        "batch_error_count": len(set(batch_errors)),
        "mocked": False,
        "live": transport_verified,
        "generated_at": int(time.time()),
        "claims": {
            "proves": [
                "closed-schema, immutable identity, cardinality, byte-identical answer, fail-closed authority, and bounded lexical/source checks"
            ],
            "does_not_prove": [
                "engineering correctness",
                "SPARTA applicability or control resolution",
                "evidence grounding",
                "certification",
                "operational correctness",
            ],
        },
    }
    write_json(receipt_path, receipt)
    return receipt


@app.command("review")
def review_command(manifest_path: Path, output: Path = typer.Option(..., "--output", "-o")) -> None:
    result = review_manifest(load_manifest(manifest_path))
    write_json(output, result)
    typer.echo(json.dumps(result, indent=2))
    if result["verdict"]["status"] == "BLOCKED":
        raise typer.Exit(1)


@app.command("webgpt-export")
def webgpt_export_command(
    manifest_path: Path,
    batch_ordinal: int = typer.Option(..., "--batch-ordinal", min=1),
    batch_size: int = typer.Option(..., "--batch-size", min=1),
    output_dir: Path = typer.Option(..., "--output-dir"),
) -> None:
    try:
        receipt = export_webgpt_batch(manifest_path, batch_ordinal, batch_size, output_dir)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(receipt, indent=2))


@app.command("webgpt-import")
def webgpt_import_command(
    requirements_json: Path,
    complete_family_json: Path,
    accepted_output: Path = typer.Option(..., "--accepted-output"),
    quarantine_output: Path = typer.Option(..., "--quarantine-output"),
    receipt: Path = typer.Option(..., "--receipt"),
    transport_receipt: Path | None = typer.Option(None, "--transport-receipt"),
) -> None:
    result = import_webgpt_batch(
        requirements_json,
        complete_family_json,
        accepted_output,
        quarantine_output,
        receipt,
        transport_receipt,
    )
    typer.echo(json.dumps(result, indent=2))
    if result["status"] != "completed":
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
