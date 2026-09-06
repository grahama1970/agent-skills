"""Pydantic first-gate for every persona-dream pipeline step boundary.

Operator directive (2026-09-06): every pipeline step validates its data with
Pydantic as the FIRST deterministic test, no exceptions. This module is the
single enforcement point. `dag_step.py` (the shim every Tau spine step routes
through) calls `validate_artifact` on every consumed JSON artifact BEFORE the
step runs, and on every produced JSON artifact after it runs. A violation
yields Pydantic `errors()` data (`type`, `loc`, `ctx`) as the steering signal
per best-practices-python `correctness-pydantic-steering` — never prose.

Inputs: artifact paths. Outputs: [] on pass, or a list of pydantic error dicts.
Failure modes: unreadable file, non-object JSON, missing/blank `schema` field,
or a registered per-schema model rejecting the payload. Fail-closed: unknown
schemas still must satisfy the envelope; registered schemas get the strict
model. Extend the REGISTRY as schemas migrate off jsonschema (ticket tracks
the full migration).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ArtifactEnvelope(BaseModel):
    """Minimum contract every persona-dream JSON artifact must satisfy."""

    model_config = ConfigDict(extra="allow")

    schema_name: str = Field(alias="schema", min_length=1)


class StoryboardPacket(ArtifactEnvelope):
    schema_name: Literal["persona_dream.storyboard_packet.v1"] = Field(alias="schema")
    accepted: Literal[True]
    status: Literal["PASS_PANEL_REVIEWED"]
    panels: list[dict[str, Any]] = Field(min_length=1)


class NodeReceipt(ArtifactEnvelope):
    schema_name: Literal["tau.generic_dag_node_receipt.v1"] = Field(alias="schema")
    node_id: str = Field(min_length=1)
    status: Literal["PASS", "BLOCKED"]
    verdict: Literal["PASS", "BLOCKED"]
    errors: list[str]


# schema field value -> strict model. Envelope applies to everything else.
REGISTRY: dict[str, type[ArtifactEnvelope]] = {
    "persona_dream.storyboard_packet.v1": StoryboardPacket,
    "tau.generic_dag_node_receipt.v1": NodeReceipt,
}


_GENERATED_DIR = Path(__file__).resolve().parent / "generated_models"
_generated_registry: dict[str, type[BaseModel]] | None = None
_generated_by_stem: dict[str, type[BaseModel]] = {}


def _load_generated_registry() -> dict[str, type[BaseModel]]:
    """Map schema-const values -> generated pydantic models (lazy, cached)."""
    global _generated_registry
    if _generated_registry is not None:
        return _generated_registry
    import importlib.util
    from typing import get_args, get_type_hints

    registry: dict[str, type[BaseModel]] = {}
    for module_path in sorted(_GENERATED_DIR.glob("*.py")):
        if module_path.name == "__init__.py":
            continue
        spec = importlib.util.spec_from_file_location(
            f"persona_dream_generated.{module_path.stem}", module_path
        )
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # required so get_type_hints resolves ForwardRefs
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(spec.name, None)
            continue  # a broken generated module must not break the gate for others
        last_model = None
        for obj in vars(module).values():
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == spec.name:
                last_model = obj
        if last_model is not None:
            _generated_by_stem[module_path.stem] = last_model
        for obj in vars(module).values():
            if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
                continue
            name = "schema" if "schema" in obj.model_fields else (
                "schema_" if "schema_" in obj.model_fields else None
            )
            if name is None:
                continue
            field = obj.model_fields[name]
            try:
                hints = get_type_hints(obj)  # resolves ForwardRef from future annotations
                annotation = hints.get(name, field.annotation)
            except Exception:
                annotation = field.annotation
            const = get_args(annotation) or (
                (field.default,) if isinstance(field.default, str) else ()
            )
            for value in const:
                if isinstance(value, str) and value:
                    registry.setdefault(value, obj)
    _generated_registry = registry
    return registry


def _resolve_model(schema: dict[str, Any], value: Any) -> type[BaseModel] | None:
    """Resolve the generated model for a loaded JSON Schema dict.

    Order: schema-const discriminator -> $id filename stem -> envelope when the
    schema itself declares a `schema` property. Returns None only when the
    contract has no discriminator at all (jsonschema still enforces it).
    """
    registry = _load_generated_registry()
    const = (schema.get("properties", {}).get("schema", {}) or {}).get("const", "")
    if const and const in registry:
        return registry[const]
    schema_id = str(schema.get("$id", ""))
    if schema_id:
        stem = Path(schema_id).name.removesuffix(".json").replace(".", "_").replace("-", "_")
        if stem in _generated_by_stem:
            return _generated_by_stem[stem]
    if "schema" in schema.get("properties", {}):
        if isinstance(value, dict):
            return REGISTRY.get(value.get("schema", ""), ArtifactEnvelope)
        return ArtifactEnvelope
    return None


def validate_payload(schema: dict[str, Any], value: Any) -> list[dict[str, Any]]:
    """Pydantic-first validation of a payload against a loaded JSON Schema dict.

    Resolves the generated pydantic model via the schema's declared const
    discriminator and validates with it FIRST. jsonschema then runs as a
    secondary depth check for constraints codegen cannot express. Returns
    pydantic-style error dicts; empty list means PASS.
    """
    errors: list[dict[str, Any]] = []
    model = _resolve_model(schema, value)
    if model is not None:
        try:
            model.model_validate(value)
        except ValidationError as exc:
            errors.extend(exc.errors(include_url=False, include_input=False))
    import jsonschema  # pinned dependency; secondary depth check only

    for err in jsonschema.Draft202012Validator(schema).iter_errors(value):
        errors.append({
            "type": "json_schema_constraint",
            "loc": list(err.path),
            "msg": err.message,
        })
    return errors


def validate_payload_messages(schema: dict[str, Any], value: Any) -> list[str]:
    """Drop-in for `sorted(e.message for e in Draft202012Validator(s).iter_errors(v))`."""
    return sorted(
        f"{e['type']} at {list(e['loc'])}: {e.get('msg', '')}" for e in validate_payload(schema, value)
    )


def validate_payload_or_raise(schema: dict[str, Any], value: Any) -> None:
    """Drop-in for `Draft202012Validator(schema).validate(value)` (raises on failure)."""
    errors = validate_payload(schema, value)
    if errors:
        raise ValueError("; ".join(validate_payload_messages(schema, value)))


class MemoryQueryResponse(BaseModel):
    """POST /query response: documents or result list."""

    model_config = ConfigDict(extra="allow")
    documents: list[Any] | None = None
    result: list[Any] | None = None


class MemoryRecallResponse(BaseModel):
    """POST /recall response: items/results list."""

    model_config = ConfigDict(extra="allow")
    items: list[Any] | None = None
    results: list[Any] | None = None


class MemoryListResponse(BaseModel):
    """POST /list response: total or count."""

    model_config = ConfigDict(extra="allow")
    total: int | None = None
    count: int | None = None


class MemoryStoreResponse(BaseModel):
    """POST /store response: documents/items written."""

    model_config = ConfigDict(extra="allow")
    documents: list[Any] | None = None
    items: list[Any] | None = None
    stored: bool | None = None


class GenericJsonObject(BaseModel):
    """Any JSON-object response; rejects non-object roots."""

    model_config = ConfigDict(extra="allow")


class EmbeddingResponse(BaseModel):
    """Embedding service response."""

    model_config = ConfigDict(extra="allow")
    embedding: list[float]


class ChatCompletionResponse(BaseModel):
    """OpenAI-style chat completion response."""

    model_config = ConfigDict(extra="allow")
    choices: list[Any]


HTTP_RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "memory_generic": GenericJsonObject,
    "embedding": EmbeddingResponse,
    "chat_completion": ChatCompletionResponse,
    "memory_query": MemoryQueryResponse,
    "memory_recall": MemoryRecallResponse,
    "memory_list": MemoryListResponse,
    "memory_store": MemoryStoreResponse,
}


def validate_http_json(kind: str, payload: Any) -> dict[str, Any]:
    """Pydantic-first gate for HTTP JSON responses at model/memory call seams.

    Returns the payload dict on pass; raises ValueError carrying pydantic
    errors() data on failure. A response that is not a JSON object fails.
    """
    model = HTTP_RESPONSE_MODELS.get(kind)
    if model is None:
        raise ValueError(f"unknown http response kind: {kind}")
    try:
        model.model_validate(payload)
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_input=False)
        raise ValueError(f"http_response_invalid kind={kind}: {errors}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"http_response_invalid kind={kind}: JSON object required")
    return payload


def pydantic_error_messages(schema: dict[str, Any], value: Any) -> list[str]:
    """Pure-pydantic error messages (no jsonschema); [] means the model accepts."""
    model = _resolve_model(schema, value)
    if model is None:
        return []
    try:
        model.model_validate(value)
    except ValidationError as exc:
        return [
            f"pydantic {e['type']} at {list(e['loc'])}: {e['msg']}"
            for e in exc.errors(include_url=False, include_input=False)
        ]
    return []


def pydantic_first_check(schema: dict[str, Any], value: Any) -> None:
    """Pydantic-first gate that raises jsonschema.ValidationError for drop-in use.

    Call immediately before an existing `Draft202012Validator(schema).validate(x)`
    so pydantic is the first deterministic test without changing the exception
    type existing callers handle.
    """
    messages = pydantic_error_messages(schema, value)
    if messages:
        import jsonschema

        raise jsonschema.exceptions.ValidationError("; ".join(messages))


def validate_artifact(path: Path) -> list[dict[str, Any]]:
    """Return pydantic-style error dicts; empty list means PASS."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [{"type": "artifact_missing", "loc": [str(path)], "msg": "file not found"}]
    except (OSError, json.JSONDecodeError) as exc:
        return [{"type": "artifact_unreadable", "loc": [str(path)], "msg": str(exc)}]
    if not isinstance(raw, dict):
        return [{"type": "artifact_not_object", "loc": [str(path)], "msg": "JSON object required"}]
    model = REGISTRY.get(raw.get("schema", ""), ArtifactEnvelope)
    try:
        model.model_validate(raw)
    except ValidationError as exc:
        return [
            {**e, "loc": [str(path), *e["loc"]]}
            for e in exc.errors(include_url=False, include_input=False)
        ]
    return []


def validate_artifacts(paths: list[Path], json_only: bool = True) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for path in paths:
        if json_only and path.suffix != ".json":
            continue
        errors.extend(validate_artifact(path))
    return errors
