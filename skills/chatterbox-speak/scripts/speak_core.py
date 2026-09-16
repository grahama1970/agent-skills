# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pydantic"]
# ///
"""Importable core for chatterbox-speak: plan -> gated render -> receipt.

Trust model (hardened after adversarial review):

- The MODEL is the trust boundary: every security-relevant constraint lives in
  ``VoiceDeliveryPlan`` validators, so direct construction is exactly as
  constrained as ``build_plan()`` (convenience only).
- Delivery/chunk structures are typed envelopes; backend-affecting fields
  (intensity) are explicit, never buried in free-form dicts.
- The render route is derived from the EXACT payload inputs (explicit intensity
  OR delivery intensity OR per-chunk intensity) — never from one convenience
  field — by ONE function used by both the gate and payload construction.
- ``render()`` freezes a canonical deep snapshot of the plan, hashes it, gates
  THE SNAPSHOT, builds a deep-copied payload, and hashes that exact HTTP body.
  Post-render mutation of the caller's plan cannot alter recorded evidence.
- Named pause macros ([pause:<name>]) are rejected in every core route: the
  CLI resolves them via the pause compiler BEFORE building a plan, so a plan
  that still contains one is uncompiled and would be spoken literally. A
  caller flag alone never unlocks pause syntax. Numeric [pause:<n>ms] is the
  compiler's output shape and is natively consumed by the service.
- ``build_receipt`` returns a typed ``VoiceRenderReceipt``; caller metadata can
  never overwrite core-owned evidence fields.

Policy that belongs to callers (session mood, memory intent, arcs, playback,
analyzer) stays OUT of this module. Data-driven helpers (pauses, pronounce)
are imported, never duplicated.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import wave
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

BASE_URL = os.environ.get("CHATTERBOX_SPEAK_BASE_URL", "http://127.0.0.1:8018")
OUT_DIR = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs")
# Container /out is host chatterbox/logs (see docker inspect chatterbox-fork-agent-server)
CONTAINER_OUT = "/out"
HOST_OUT = Path(os.environ.get(
    "CHATTERBOX_SPEAK_HOST_OUT", str(Path.home() / "workspace/experiments/chatterbox/logs")))

VOICES = {
    "embry": "/data/embry_ref.wav",
}
INTENSITY = {"low": 0.3, "medium": 0.6, "high": 0.9}

# Turbo-safe singular event tag vocabulary (SKILL.md "Tag vocabulary gotcha").
# Plural forms ([laughs] [chuckles] [sighs]) are ElevenLabs-v3-only and are NOT
# renderable by the backends this skill routes to; an unknown or plural tag sent
# to the service is synthesized AS LITERAL SPOKEN TEXT. Fail closed before the POST.
_KNOWN_EVENT_TAGS = frozenset(
    t.lower() for t in (
        "[clear throat]", "[sigh]", "[shush]", "[cough]", "[groan]",
        "[sniff]", "[gasp]", "[chuckle]", "[laugh]", "[happy]",
        "[surprised]", "[angry]", "[sarcastic]",
    )
)
_TAG_RE = __import__("re").compile(r"\[[^\]\n]{1,40}\]")
# Exact supported pause-token shapes: numeric `[pause:750ms]` (the pause
# compiler's output shape, natively consumed by the service). Named
# `[pause:<name>]` macros exist only BEFORE compilation; the CLI resolves them
# via the pause compiler BEFORE building a plan, so a plan that still contains
# one is uncompiled and is rejected in every core route.
_PAUSE_NUMERIC_RE = __import__("re").compile(r"\[pause:\d+ms\]", __import__("re").IGNORECASE)
_PAUSE_NAMED_RE = __import__("re").compile(r"\[pause:[a-z_]+\]", __import__("re").IGNORECASE)

RENDER_SOURCES = ("single", "caller_plan", "compiled")
PAUSE_STRATEGIES = ("none", "planned_pauses", "caller_chunks")
INTENT_POLICY_SOURCES = ("cli.direct", "memory.intent", "caller.explicit")


def unsupported_tags(text: str, *, allow_event_tags: bool, allow_named_pauses: bool) -> list[str]:
    """Bracket tags in `text` the EFFECTIVE backend cannot render as tags.

    - allow_event_tags: False when the effective route is base-affect, which
      speaks even known event tags as literal words; then the whole event
      vocabulary is unsupported.
    - allow_named_pauses: kept for the CLI's pre-compilation pre-gate. The CORE
      gate always passes False: by plan time compilation must already have
      consumed named macros (see module docstring).
    - Only the exact numeric pause shape passes otherwise; `[pause nonsense]`
      or `[pauseevil]` fail closed like unknown tags.
    """
    out = []
    for tag in _TAG_RE.findall(text or ""):
        low = tag.lower()
        if allow_event_tags and low in _KNOWN_EVENT_TAGS:
            continue
        if _PAUSE_NUMERIC_RE.fullmatch(low):
            continue
        if allow_named_pauses and _PAUSE_NAMED_RE.fullmatch(low):
            continue
        if tag not in out:
            out.append(tag)
    return out


class UnsupportedTagError(Exception):
    """Gate violation: render refused BEFORE any service POST."""

    def __init__(self, tags: list[str], *, base_affect_route: bool, route: str = "base_affect"):
        self.tags = tags
        self.base_affect_route = base_affect_route
        self.route = route
        super().__init__(f"unsupported bracket tag(s) {tags} for the {route} route")


class UnknownVoiceError(ValueError):
    pass


class DeliverySpec(BaseModel):
    """Typed caller-blended voice delivery; the backend-affecting field is
    `intensity` — its presence routes the render to base-affect."""

    model_config = ConfigDict(extra="forbid")
    intensity: float | None = Field(default=None, ge=0.0, le=1.0)
    emotion_realization: str | None = None
    tone: str | None = None
    pace: str | None = None


class RenderChunk(BaseModel):
    """Typed render chunk. `text` is required; `intensity`/`delivery` are the
    backend-affecting fields and gate like the plan-level ones. Extension
    fields (e.g. sfx_after) are allowed but never gate-relevant."""

    model_config = ConfigDict(extra="allow")
    text: str
    intensity: float | str | None = None
    delivery: DeliverySpec | None = None
    tone: str | None = None


def _has_intensity(obj: Any) -> bool:
    """True when a dict-shaped delivery/chunk carries a backend-affecting intensity."""
    if not isinstance(obj, dict):
        return False
    if obj.get("intensity") is not None:
        return True
    inner = obj.get("delivery")
    return isinstance(inner, dict) and inner.get("intensity") is not None


def effective_route(snapshot: dict[str, Any]) -> tuple[str, bool]:
    """GATE_FROM_ACTUAL_RENDER_ROUTE — the ONE route derivation.

    Derives (route_name, allow_event_tags) from the exact normalized payload
    inputs: explicit plan intensity, delivery intensity, or per-chunk
    intensity/delivery. Used by both the gate and payload construction so the
    two can never disagree.
    """
    base_affect = snapshot.get("intensity") is not None
    base_affect = base_affect or _has_intensity({"delivery": snapshot.get("delivery")})
    for chunk in snapshot.get("render_chunks") or []:
        base_affect = base_affect or _has_intensity(chunk)
    return ("base_affect", False) if base_affect else ("turbo_native", True)


class VoiceDeliveryPlan(BaseModel):
    """Typed delivery plan: everything the renderer needs, nothing else.

    PLAN_INVARIANTS_IN_MODEL: the security-relevant constraints live HERE, so
    direct construction is exactly as constrained as build_plan().
    """

    model_config = ConfigDict(extra="forbid")
    turn_id: str
    text: str | None = None
    answer_text: str | None = None
    render_chunks: list[RenderChunk] | None = None
    voice: str = "embry"
    ref_audio: str | None = None
    tone: str | None = None
    intensity: str | None = None
    delivery: DeliverySpec | None = None
    pace: str | None = None
    temperature: float | None = None
    allow_unknown_tags: bool = False
    intent_policy_source: str = "cli.direct"
    render_source: str = "single"  # single | caller_plan | compiled
    pause_strategy: str = "none"  # none | planned_pauses | caller_chunks

    @model_validator(mode="after")
    def _invariants(self) -> "VoiceDeliveryPlan":
        # voice/ref: known voice, or explicit reference audio
        if not self.ref_audio:
            if self.voice in VOICES:
                self.ref_audio = VOICES[self.voice]
            else:
                raise ValueError(
                    f"unknown voice '{self.voice}'; known: {sorted(VOICES)} "
                    "(or pass ref_audio)")
        # intensity vocabulary
        if self.intensity is not None and self.intensity not in INTENSITY:
            raise ValueError(f"intensity must be one of {sorted(INTENSITY)}")
        # content: chunks xor single text; chunks must be non-empty
        if self.render_chunks is not None and not self.render_chunks:
            raise ValueError("render_chunks requires a non-empty list")
        if not self.render_chunks and not (self.text and self.text.strip()):
            raise ValueError("plan needs non-empty text or non-empty render_chunks")
        # coherent render_source / pause_strategy
        if self.render_source not in RENDER_SOURCES:
            raise ValueError(f"render_source must be one of {RENDER_SOURCES}")
        if self.pause_strategy not in PAUSE_STRATEGIES:
            raise ValueError(f"pause_strategy must be one of {PAUSE_STRATEGIES}")
        if self.render_chunks is not None:
            if self.render_source == "single":
                raise ValueError("render_chunks requires render_source caller_plan|compiled")
        else:
            if self.render_source != "single":
                raise ValueError("render_source caller_plan|compiled requires render_chunks")
            if self.pause_strategy != "none":
                raise ValueError("pause_strategy requires render_chunks (compilation happens before the plan)")
        if self.intent_policy_source not in INTENT_POLICY_SOURCES:
            raise ValueError(
                f"intent_policy_source must be one of {INTENT_POLICY_SOURCES}")
        return self


def canonical_plan_json(plan: VoiceDeliveryPlan) -> str:
    return json.dumps(plan.model_dump(), sort_keys=True, separators=(",", ":"))


def plan_sha256(plan: VoiceDeliveryPlan) -> str:
    return "sha256:" + hashlib.sha256(canonical_plan_json(plan).encode()).hexdigest()


def build_plan(
    *,
    turn_id: str,
    text: str | None = None,
    answer_text: str | None = None,
    render_chunks: list[dict[str, Any]] | None = None,
    voice: str = "embry",
    ref_audio: str | None = None,
    tone: str | None = None,
    intensity: str | None = None,
    delivery: dict[str, Any] | None = None,
    pace: str | None = None,
    temperature: float | None = None,
    allow_unknown_tags: bool = False,
    intent_policy_source: str = "cli.direct",
    render_source: str | None = None,
    pause_strategy: str | None = None,
) -> VoiceDeliveryPlan:
    """Convenience construction of a validated plan.

    PLAN_INVARIANTS_IN_MODEL: every constraint enforced here is ALSO enforced
    by the model validators; direct VoiceDeliveryPlan(...) is exactly as
    constrained. Raises UnknownVoiceError / ValueError before any gate or POST.
    Caller passes the FINAL text (pronunciation normalization and pause
    compilation are caller policy and must already be applied).
    """
    resolved_ref = ref_audio or VOICES.get(voice)
    if not resolved_ref:
        raise UnknownVoiceError(f"unknown voice '{voice}'; known: {sorted(VOICES)}")
    if render_source is None:
        render_source = "caller_plan" if render_chunks else "single"
    if pause_strategy is None:
        pause_strategy = "caller_chunks" if render_chunks else "none"
    return VoiceDeliveryPlan(
        turn_id=turn_id, text=text, answer_text=answer_text,
        render_chunks=render_chunks, voice=voice, ref_audio=resolved_ref,
        tone=tone, intensity=intensity, delivery=delivery, pace=pace,
        temperature=temperature, allow_unknown_tags=allow_unknown_tags,
        intent_policy_source=intent_policy_source, render_source=render_source,
        pause_strategy=pause_strategy,
    )


def evaluate_gate(snapshot: dict[str, Any]) -> list[str]:
    """Unsupported tags across every text the SNAPSHOT will render.

    Takes the frozen snapshot dict (see render): the gate must judge exactly
    what will be POSTed, and the route comes from effective_route().
    Named pause macros are always unsupported here (compilation happened
    before the plan existed; a caller flag never unlocks them).
    """
    _, allow_event_tags = effective_route(snapshot)
    texts = [snapshot.get("text") or "", snapshot.get("answer_text") or ""]
    texts += [c.get("text", "") for c in (snapshot.get("render_chunks") or [])
              if isinstance(c, dict)]
    found: list[str] = []
    for t in texts:
        for tag in unsupported_tags(t, allow_event_tags=allow_event_tags,
                                    allow_named_pauses=False):
            if tag not in found:
                found.append(tag)
    return found


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


class RenderResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)
    endpoint: str
    payload: dict[str, Any]
    service_json: dict[str, Any]
    receipt: Any  # ServiceReceipt
    host_wav: Path
    wav_copy: Path
    duration_seconds: float
    # FREEZE_RENDER_SNAPSHOT / REQUEST_PAYLOAD_SHA256: immutable evidence,
    # computed inside render() before gate and POST.
    plan_sha256: str
    plan_snapshot: dict[str, Any]
    request_payload_sha256: str


class ServiceReceipt(BaseModel):
    """Minimal typed view of the service response; extra fields kept via model_extra."""

    model_config = ConfigDict(extra="allow")
    ok: bool
    live: bool
    mocked: bool
    audio: str
    duration_seconds: float
    tone: str | None = None


class BatchReceipt(BaseModel):
    # Projection of the owning service contract; original bytes remain in the receipt.
    model_config = ConfigDict(extra="allow", strict=True)
    ok: bool
    live: bool
    mocked: bool
    finished_response_audio: str


class ServiceCallFailed(Exception):
    pass


class ServiceResponseInvalid(Exception):
    pass


def render(plan: VoiceDeliveryPlan, *, base_url: str | None = None) -> RenderResult:
    """Freeze snapshot -> gate SNAPSHOT -> payload -> hash body -> POST.

    Raises UnsupportedTagError BEFORE any POST when the gate fails and the
    plan does not explicitly allow unknown tags. No playback happens here.
    The caller's plan object is never referenced after freezing: nested
    mutation after render() cannot alter the recorded evidence.
    """
    base = base_url or BASE_URL

    # FREEZE_RENDER_SNAPSHOT: canonical deep snapshot (JSON-safe deep copy).
    snapshot = json.loads(canonical_plan_json(plan))
    digest = _sha256_text(canonical_json(snapshot))

    # Gate THE SNAPSHOT, with the route derived from the snapshot itself.
    found = evaluate_gate(snapshot)
    route, _allow = effective_route(snapshot)
    if found and not snapshot.get("allow_unknown_tags"):
        raise UnsupportedTagError(found, base_affect_route=route == "base_affect",
                                  route=route)

    label = f"chatterbox-speak-{uuid4().hex}"
    delivery = snapshot.get("delivery")
    if snapshot.get("render_chunks"):
        endpoint = "synthesize-batch"
        payload: dict[str, Any] = {
            "answer_text": snapshot.get("answer_text") or snapshot.get("text") or "",
            "render_chunks": snapshot["render_chunks"],
            "label": label, "ref_audio": snapshot.get("ref_audio"),
            "crossfade_ms": 0, "use_blessed_qra_cache": False, "asr_verify": False,
            "voice_delivery": {"tone": snapshot.get("tone") or "neutral_warm",
                               **(delivery or {})},
        }
    else:
        endpoint = "synthesize"
        payload = {
            "text": snapshot.get("text") or "", "ref_audio": snapshot.get("ref_audio"),
            "tone": snapshot.get("tone"),
            "voice_delivery": delivery,
            "label": label,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
    if snapshot.get("temperature") is not None:
        payload["temperature"] = snapshot["temperature"]

    # REQUEST_PAYLOAD_SHA256: bind the exact HTTP body, independent of the plan.
    request_payload_sha256 = _sha256_text(canonical_json(payload))

    try:
        resp = httpx.post(f"{base}/{endpoint}", json=payload, timeout=300)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        raise ServiceCallFailed(
            f"chatterbox service call failed: {exc} {detail[:500]}") from exc

    try:
        if endpoint == "synthesize-batch":
            batch = BatchReceipt.model_validate(resp.json())
            host_audio = HOST_OUT / Path(batch.finished_response_audio).relative_to(CONTAINER_OUT)
            with wave.open(str(host_audio), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            receipt = ServiceReceipt(ok=batch.ok, live=batch.live, mocked=batch.mocked,
                                     audio=batch.finished_response_audio,
                                     duration_seconds=duration, tone=snapshot.get("tone"))
        else:
            receipt = ServiceReceipt.model_validate(resp.json())
    except ValidationError as exc:
        raise ServiceResponseInvalid(
            f"service response failed typed validation: {exc.json()}") from exc
    if not (receipt.ok and receipt.live) or receipt.mocked:
        raise ServiceCallFailed(
            f"render not live/ok: ok={receipt.ok} live={receipt.live} mocked={receipt.mocked}")

    host_wav = HOST_OUT / Path(receipt.audio).relative_to(CONTAINER_OUT)
    if not host_wav.is_file() or host_wav.stat().st_size == 0:
        raise ServiceCallFailed(f"rendered WAV missing/empty on host: {host_wav}")

    out = OUT_DIR / f"{int(__import__('time').time())}-{label}"
    out.mkdir(parents=True, exist_ok=True)
    wav_copy = out / host_wav.name
    shutil.copy2(host_wav, wav_copy)

    return RenderResult(endpoint=endpoint, payload=payload,
                        service_json=resp.json(), receipt=receipt,
                        host_wav=host_wav, wav_copy=wav_copy,
                        duration_seconds=receipt.duration_seconds,
                        plan_sha256=digest, plan_snapshot=snapshot,
                        request_payload_sha256=request_payload_sha256)


# RECEIPT_RESERVED_FIELDS: core-owned evidence a caller may never override.
RESERVED_RECEIPT_FIELDS = frozenset({
    "schema", "turn_id", "plan_sha256", "request_payload_sha256",
    "intent_policy_source", "voice", "context", "original_text", "spoken_text",
    "pronunciation_normalized", "requested_intensity", "speaking_to", "session",
    "memory_context", "voice_delivery", "request", "chatterbox_pause_plan",
    "render_source", "temperature", "wav", "duration_seconds", "mocked", "live",
    "tag_handling", "affect_effect", "backend", "service_receipt",
    "allow_unknown_tags", "unknown_tags_detected", "unknown_tag_policy",
    "caller_metadata",
})


class VoiceRenderReceipt(BaseModel):
    """TYPED_VOICE_RENDER_RECEIPT: validated core-owned evidence + caller_metadata."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    schema: str = "chatterbox_speak.receipt.v1"
    turn_id: str
    plan_sha256: str
    request_payload_sha256: str
    intent_policy_source: str
    voice: str
    context: str = ""
    original_text: str | None = None
    spoken_text: str | None = None
    pronunciation_normalized: bool = True
    requested_intensity: str | None = None
    speaking_to: str | None = None
    session: dict[str, Any] | None = None
    memory_context: dict[str, Any] | None = None
    voice_delivery: dict[str, Any]
    request: dict[str, Any]
    chatterbox_pause_plan: list[Any] | None = None
    render_source: str
    temperature: float | None = None
    wav: str
    duration_seconds: float
    mocked: bool
    live: bool
    tag_handling: Any = None
    affect_effect: Any = None
    backend: Any = None
    service_receipt: dict[str, Any]
    allow_unknown_tags: bool
    unknown_tags_detected: list[str]
    unknown_tag_policy: str | None = None
    caller_metadata: dict[str, Any] = {}


def build_receipt(plan: VoiceDeliveryPlan, result: RenderResult,
                  *, context: str = "", original_text: str | None = None,
                  spoken_text: str | None = None,
                  pronunciation_normalized: bool = True,
                  requested_intensity: str | None = None,
                  speaking_to: str | None = None, session: dict | None = None,
                  memory_context: dict | None = None,
                  pause_plan_chunks: list | None = None,
                  analysis: dict | None = None, **cli_fields: Any) -> VoiceRenderReceipt:
    """Assemble the typed receipt from FROZEN render evidence.

    plan_sha256 / request_payload_sha256 come from ``result`` (frozen inside
    render()); they are never recomputed from the caller-owned plan object.
    Caller extras land under ``caller_metadata``; collisions with core-owned
    evidence fields raise ValueError.
    """
    collide = sorted(RESERVED_RECEIPT_FIELDS & set(cli_fields))
    if collide:
        raise ValueError(
            f"cli_fields collide with core-owned receipt evidence: {collide}; "
            "pass caller-owned fields under explicit names or use caller_metadata")
    record: dict[str, Any] = {
        "schema": "chatterbox_speak.receipt.v1",
        "turn_id": plan.turn_id,
        "plan_sha256": result.plan_sha256,
        "request_payload_sha256": result.request_payload_sha256,
        "intent_policy_source": plan.intent_policy_source,
        "voice": plan.voice,
        "context": context,
        "original_text": original_text if original_text is not None else plan.text,
        "spoken_text": spoken_text if spoken_text is not None else plan.text,
        "pronunciation_normalized": pronunciation_normalized,
        "requested_intensity": requested_intensity,
        "speaking_to": speaking_to,
        "session": session,
        "memory_context": memory_context,
        "voice_delivery": {
            "tone": plan.tone or "neutral_warm",
            **(plan.delivery.model_dump() if plan.delivery else {})},
        "request": result.payload,
        "chatterbox_pause_plan": pause_plan_chunks,
        "render_source": plan.render_source,
        "temperature": plan.temperature,
        "wav": str(result.wav_copy),
        "duration_seconds": result.duration_seconds,
        "mocked": result.receipt.mocked,
        "live": result.receipt.live,
        "tag_handling": result.service_json.get("tag_handling"),
        "affect_effect": result.service_json.get("affect_effect"),
        "backend": result.service_json.get("backend"),
        "service_receipt": result.service_json,
        # RECORD_TAG_OPT_OUT_ALWAYS: the policy switch itself is evidence,
        # computed from the frozen snapshot.
        "allow_unknown_tags": bool(result.plan_snapshot.get("allow_unknown_tags")),
        "unknown_tags_detected": evaluate_gate(result.plan_snapshot),
    }
    if record["allow_unknown_tags"] and record["unknown_tags_detected"]:
        record["unknown_tag_policy"] = "explicit_operator_opt_out"
    if analysis is not None:
        cli_fields["analysis"] = analysis
    record["caller_metadata"] = dict(cli_fields)
    return VoiceRenderReceipt.model_validate(record)
