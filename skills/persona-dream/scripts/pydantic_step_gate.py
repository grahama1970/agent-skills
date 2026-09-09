"""Pydantic first-gate for every persona-dream pipeline step boundary.

Operator directive (2026-09-06): every pipeline step validates its data with
Pydantic as the FIRST deterministic test, no exceptions. This module is the
single enforcement point. `dag_step.py` (the shim every Tau spine step routes
through) calls `validate_artifact` on every consumed JSON artifact BEFORE the
step runs, and on every produced JSON artifact after it runs. A violation
yields Pydantic `errors()` data (`type`, `loc`, `ctx`) as the steering signal
per best-practices-python `correctness-pydantic-steering` — never prose.

Inputs: artifact paths. Outputs: [] on pass, or a list of pydantic error dicts.
Failure modes: unreadable file, malformed JSON/JSONL, missing/unknown schema,
wrong artifact type or cycle, and rejected typed payload. The strict spine gate
never admits an unknown schema using only an envelope. Legacy non-strict callers
retain their documented envelope fallback.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

try:
    from spine_artifact_models import SPINE_ARTIFACT_MODELS
except ImportError:  # producers load this module by file path without scripts/ on sys.path
    import importlib.util as _importlib_util

    _spec = _importlib_util.spec_from_file_location(
        "spine_artifact_models", Path(__file__).with_name("spine_artifact_models.py"))
    _module = _importlib_util.module_from_spec(_spec)
    sys.modules["spine_artifact_models"] = _module
    _spec.loader.exec_module(_module)
    SPINE_ARTIFACT_MODELS = _module.SPINE_ARTIFACT_MODELS


class ArtifactEnvelope(BaseModel):
    """Minimum contract every persona-dream JSON artifact must satisfy."""

    model_config = ConfigDict(extra="allow")

    schema_name: str = Field(alias="schema", min_length=1)


class StoryboardPacket(ArtifactEnvelope):
    schema_name: Literal["persona_dream.storyboard_packet.v1"] = Field(alias="schema")
    accepted: Literal[True]
    status: Literal["PASS_PANEL_REVIEWED"]
    panels: list[dict[str, Any]] = Field(min_length=1)


class TriageError(BaseModel):
    """Typed triage-error classification embedded in blocked step receipts."""

    model_config = ConfigDict(extra="allow")

    code: str = Field(min_length=1)
    cause: str = Field(min_length=1)
    next_command: str = Field(min_length=1)


class ArtifactReference(BaseModel):
    """A declared upstream artifact, not an arbitrary nested dict."""

    model_config = ConfigDict(extra="allow")
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    bytes: int = Field(ge=0, strict=True)


class NodeReceipt(ArtifactEnvelope):
    schema_name: Literal["tau.generic_dag_node_receipt.v1"] = Field(alias="schema")
    node_id: str = Field(min_length=1)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    status: Literal["PASS", "BLOCKED"]
    verdict: Literal["PASS", "BLOCKED"]
    errors: list[str]
    pydantic_errors: list[dict[str, Any]]
    triage_errors: list[TriageError]

    @model_validator(mode="after")
    def blocked_receipts_need_typed_error_data(self) -> "NodeReceipt":
        if self.status != self.verdict:
            raise ValueError("status and verdict must agree")
        if self.status == "PASS" and (self.errors or self.pydantic_errors or self.triage_errors):
            raise ValueError("PASS receipt cannot contain errors")
        if self.status == "BLOCKED" and not (self.pydantic_errors or self.triage_errors):
            raise ValueError("BLOCKED receipt requires pydantic_errors[] or triage_errors[]")
        if self.errors and not self.triage_errors:
            raise ValueError("receipt errors[] require triage_errors[]")
        return self


# schema field value -> strict model. Envelope applies to everything else.
REGISTRY: dict[str, type[ArtifactEnvelope]] = {
    "persona_dream.storyboard_packet.v1": StoryboardPacket,
    "tau.generic_dag_node_receipt.v1": NodeReceipt,
}


_GENERATED_DIR = Path(__file__).resolve().parent / "generated_models"
_generated_registry: dict[str, type[BaseModel]] | None = None
_generated_by_stem: dict[str, type[BaseModel]] = {}
#: stem -> load error. A generated contract that fails to import is a visible
#: fail-closed condition for the schemas it should own, never a silent envelope.
GENERATED_MODEL_LOAD_FAILURES: dict[str, str] = {}


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
        except Exception as exc:  # noqa: BLE001 - recorded, then fail-closed at use sites
            sys.modules.pop(spec.name, None)
            GENERATED_MODEL_LOAD_FAILURES[module_path.stem] = f"{type(exc).__name__}: {exc}"
            continue  # other generated contracts stay usable; this one is fail-closed
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


def _generated_contract_load_error(schema: dict[str, Any]) -> str | None:
    """Return the load failure for the generated model this schema should use."""
    _load_generated_registry()
    const = str((schema.get("properties", {}).get("schema", {}) or {}).get("const", ""))
    schema_id = str(schema.get("$id", ""))
    stems = []
    if schema_id:
        stems.append(Path(schema_id).name.removesuffix(".json").replace(".", "_").replace("-", "_"))
    if const:
        normalized = const.replace("-", "_").replace(".", "_")
        stems.extend([normalized, normalized.removeprefix("persona_dream_") + "_schema"])
    for failed_stem, failure in GENERATED_MODEL_LOAD_FAILURES.items():
        base = failed_stem.removesuffix("_schema")
        if failed_stem in stems or any(stem.endswith(base) for stem in stems):
            return f"{failed_stem}: {failure}"
    return None


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
    unavailable = _generated_contract_load_error(schema)
    if unavailable:
        return [{"type": "generated_model_load_failed", "loc": ["schema"],
                 "msg": f"generated pydantic contract unavailable: {unavailable}"}]
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
    choices: list[Any] = Field(min_length=1)


class ChatterboxSynthesizeResponse(BaseModel):
    """Chatterbox /synthesize-batch response consumed by conversation renders."""

    model_config = ConfigDict(extra="allow")
    finished_response_audio: str = Field(min_length=1)


class JournalReasoningResult(BaseModel):
    """Typed journal LLM output; validated before any entry/persistence logic."""

    model_config = ConfigDict(extra="allow")
    journal: str = Field(min_length=1)
    unresolved_tension: str = Field(min_length=1)
    expanded_understanding: str = Field(min_length=1)
    mood_label: str = Field(min_length=1)
    mood_description: str = Field(min_length=1)


class HorusTurnResult(BaseModel):
    """Typed conversation-turn LLM output; validated before speech or append."""

    model_config = ConfigDict(extra="allow")
    question: str = Field(min_length=1)
    tone: str = Field(min_length=1)


HTTP_RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "memory_generic": GenericJsonObject,
    "embedding": EmbeddingResponse,
    "chat_completion": ChatCompletionResponse,
    "chatterbox_synthesize": ChatterboxSynthesizeResponse,
    "journal_reasoning": JournalReasoningResult,
    "horus_turn": HorusTurnResult,
    "memory_query": MemoryQueryResponse,
    "memory_recall": MemoryRecallResponse,
    "memory_list": MemoryListResponse,
    "memory_store": MemoryStoreResponse,
}


#: memory API path -> response model kind, for the producers' shared post() seam.
MEMORY_PATH_KINDS = {"/list": "memory_list", "/recall": "memory_recall",
                     "/query": "memory_query", "/upsert": "memory_store",
                     "/store": "memory_store"}


def memory_kind_for_path(path: str) -> str:
    return MEMORY_PATH_KINDS.get(str(path).split("?", 1)[0].rstrip("/"), "memory_generic")


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


def _artifact_value_errors(path: Path, raw: Any, require_schema: bool) -> list[dict[str, Any]]:
    """Select by the consumer's filename contract before trusting a discriminator."""
    if not isinstance(raw, dict):
        return [{"type": "artifact_not_object", "loc": [str(path)], "msg": "JSON object required"}]
    try:
        if require_schema or "schema" in raw:
            envelope = ArtifactEnvelope.model_validate(raw)
            declared = envelope.schema_name
            model = SPINE_ARTIFACT_MODELS.get(path.name) if require_schema else None
            model = model or REGISTRY.get(declared) or _load_generated_registry().get(declared)
            if model is None and require_schema:
                detail = f"no typed artifact contract registered for {declared!r}"
                if GENERATED_MODEL_LOAD_FAILURES:
                    detail += f"; generated contract modules failed to load: {GENERATED_MODEL_LOAD_FAILURES}"
                return [{"type": "artifact_schema_unknown", "loc": [str(path), "schema"], "msg": detail}]
            model = model or ArtifactEnvelope
        else:
            stem = path.name.removesuffix(".json").replace(".", "_").replace("-", "_") + "_schema"
            _load_generated_registry()
            model = _generated_by_stem.get(stem, GenericJsonObject)
        model.model_validate(raw)
    except ValidationError as exc:
        # errors() may contain ValueError instances in ctx; JSON serialization
        # preserves the typed steering fields without crashing the blocked receipt.
        return [{**e, "loc": [str(path), *e["loc"]]}
                for e in json.loads(exc.json(include_url=False, include_input=False))]
    if require_schema:
        audio_refs = []
        if path.name == "dynamic_conversation_receipt.v1.json":
            audio_refs = [pair[role] for pair in raw["turn_pairs"] for role in ("horus", "embry")]
        elif path.name == "JOURNAL_AUDIO_RECEIPT.json" or (path.name == "conversation.jsonl" and raw.get("audio")):
            audio_refs = [raw]
        for reference in audio_refs:
            named = Path(reference["audio"])
            audio = (path.parent / named.name).resolve()
            if named.is_absolute() and named.resolve() != audio:
                return [{"type": "artifact_audio_path_mismatch", "loc": [str(path), "audio"],
                         "msg": "audio reference must name a file in this cycle directory"}]
            if not audio.is_relative_to(path.parent.resolve()):
                return [{"type": "artifact_audio_path_mismatch", "loc": [str(path), "audio"],
                         "msg": "audio reference must name a file in this cycle directory"}]
            try:
                data = audio.read_bytes()
            except OSError as exc:
                return [{"type": "artifact_audio_missing", "loc": [str(path), "audio"], "msg": str(exc)}]
            if "sha256:" + hashlib.sha256(data).hexdigest() != reference.get("audio_sha256"):
                return [{"type": "artifact_audio_hash_mismatch", "loc": [str(path), "audio_sha256"],
                         "msg": "referenced local WAV bytes do not match the receipt"}]
            if not data or ("audio_bytes" in reference and len(data) != reference["audio_bytes"]):
                return [{"type": "artifact_audio_size_mismatch", "loc": [str(path), "audio_bytes"],
                         "msg": "referenced local WAV size does not match the receipt"}]
            if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
                return [{"type": "artifact_audio_not_wav", "loc": [str(path), "audio"],
                         "msg": "referenced audio bytes are not a RIFF/WAVE file"}]
        lineage = _lineage_errors(path, raw)
        if lineage:
            return lineage
        field = {"phase14_tom.json": "revision_id", "observation_packet.json": "source_revision_id",
                 "dream_journal.v1.json": "cycle"}.get(path.name)
        if field and raw[field] != path.parent.name:
            return [{"type": "artifact_cycle_mismatch", "loc": [str(path), field],
                     "msg": "artifact does not belong to the active cycle directory"}]
    return []


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _lineage_errors(path: Path, raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Join spoken text, audio and conversation claims to actual cycle bytes.

    Individually valid receipts must not be mutually self-asserted: each digest
    field is bound to the real file it claims to describe (measured live
    relationships from cycle_20260909T130904Z, not invented conventions).
    """
    def err(kind: str, where: str, msg: str) -> list[dict[str, Any]]:
        return [{"type": kind, "loc": [str(path), where], "msg": msg}]

    cycle = path.parent

    def read(name: str) -> bytes | None:
        try:
            return (cycle / name).read_bytes()
        except OSError:
            return None

    if path.name == "JOURNAL_SPOKEN_TEXT_RECEIPT.json":
        if Path(raw["journal_spoken"]).name != "journal_spoken.txt":
            return err("artifact_lineage_target_mismatch", "journal_spoken",
                       "receipt must describe this cycle's journal_spoken.txt")
        spoken = read("journal_spoken.txt")
        if spoken is None:
            return err("artifact_lineage_target_missing", "journal_spoken",
                       "journal_spoken.txt does not exist in this cycle")
        if _sha(spoken.decode("utf-8", "replace").strip().encode()) != raw["spoken_text_sha256"]:
            return err("artifact_lineage_hash_mismatch", "spoken_text_sha256",
                       "digest does not match the actual journal_spoken.txt text")
        source_name = Path(raw["source"]).name
        if source_name not in {"dream_journal.v1.json", "dream_journal.md"}:
            return err("artifact_lineage_target_mismatch", "source", "source must be the cycle journal")
        source = read(source_name)
        if source is None:
            return err("artifact_lineage_target_missing", "source", "named journal source is absent")
        if source_name == "dream_journal.v1.json":
            journal = json.loads(source).get("journal", "")
            if str(journal).strip() != spoken.decode("utf-8", "replace").strip():
                return err("artifact_lineage_text_mismatch", "source",
                           "journal_spoken.txt does not match the journal entry text")

    if path.name == "JOURNAL_AUDIO_RECEIPT.json":
        if Path(raw["audio"]).name != "journal.wav":
            return err("artifact_lineage_target_mismatch", "audio",
                       "journal audio receipt must describe this cycle's journal.wav")
        spoken = read("journal_spoken.txt")
        if spoken is None:
            return err("artifact_lineage_target_missing", "journal_spoken",
                       "journal_spoken.txt does not exist in this cycle")
        stripped = spoken.decode("utf-8", "replace").strip()
        if _sha(stripped.encode()) != raw["source_spoken_text_sha256"]:
            return err("artifact_lineage_hash_mismatch", "source_spoken_text_sha256",
                       "digest does not match the actual journal_spoken.txt text")
        rendered = stripped[: raw["truncated_to"]] if raw.get("truncated_to") else stripped
        if _sha(rendered.encode()) != raw["spoken_text_sha256"]:
            return err("artifact_lineage_hash_mismatch", "spoken_text_sha256",
                       "digest does not match the rendered spoken text")

    if path.name == "dynamic_conversation_receipt.v1.json":
        transcript = read("conversation.jsonl")
        if transcript is None:
            return err("artifact_lineage_target_missing", "conversation.jsonl",
                       "conversation.jsonl does not exist in this cycle")
        try:
            rows = [json.loads(line) for line in transcript.decode("utf-8", "replace").splitlines() if line.strip()]
        except ValueError as exc:
            return err("artifact_lineage_target_unreadable", "conversation.jsonl", str(exc))
        expected = int(raw.get("transcript_base_lines") or 0) + int(raw["turn_count"])
        if len(rows) != expected:
            return err("artifact_lineage_count_mismatch", "turn_count",
                       f"conversation.jsonl has {len(rows)} rows; receipt claims {expected}")
        transcript_hashes = {row.get("audio_sha256") for row in rows}
        claimed = {pair[role]["audio_sha256"] for pair in raw["turn_pairs"] for role in ("horus", "embry")}
        if not claimed <= transcript_hashes:
            return err("artifact_lineage_hash_mismatch", "turn_pairs",
                       "receipt claims voiced turns absent from conversation.jsonl")

    if path.name == "conversation.jsonl" and raw.get("journal_spoken_sha256"):
        spoken = read("journal_spoken.txt")
        if spoken is None:
            return err("artifact_lineage_target_missing", "journal_spoken_sha256",
                       "journal_spoken.txt does not exist in this cycle")
        if _sha(spoken) != raw["journal_spoken_sha256"]:
            return err("artifact_lineage_hash_mismatch", "journal_spoken_sha256",
                       "turn is bound to a different journal_spoken.txt than this cycle's")
    return []


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSON cannot use duplicate keys to overwrite a failed status or lineage."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-standard JSON constant: {value}")


def validate_artifact(path: Path, require_schema: bool = False) -> list[dict[str, Any]]:
    """Validate JSON, or every non-empty JSONL row; [] means typed admission."""
    try:
        text = path.read_text(encoding="utf-8")
        rows = [(i, line) for i, line in enumerate(text.splitlines(), 1) if line.strip()] if path.suffix.lower() == ".jsonl" else [(None, text)]
        if not rows:
            return [{"type": "artifact_empty", "loc": [str(path)], "msg": "empty JSONL artifact"}]
        errors = []
        for line_number, line in rows:
            try:
                raw = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            except ValueError as exc:
                errors.append({"type": "artifact_unreadable", "loc": [str(path), line_number], "msg": str(exc)})
                continue
            row_errors = _artifact_value_errors(path, raw, require_schema)
            if line_number is not None:
                for error in row_errors:
                    error["loc"].insert(1, line_number)
            errors.extend(row_errors)
        return errors
    except FileNotFoundError:
        return [{"type": "artifact_missing", "loc": [str(path)], "msg": "file not found"}]
    except (OSError, UnicodeError) as exc:
        return [{"type": "artifact_unreadable", "loc": [str(path)], "msg": str(exc)}]


def validate_artifacts(
    paths: list[Path], json_only: bool = True, require_schema: bool = False
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for path in paths:
        if json_only and path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        errors.extend(validate_artifact(path, require_schema=require_schema))
    return errors
