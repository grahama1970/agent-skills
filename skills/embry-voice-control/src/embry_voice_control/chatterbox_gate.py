"""Chatterbox gate seam: the ONLY route from this skill to the Chatterbox
service, wired through the hardened chatterbox-speak core.

IMPORT MECHANISM (VERIFIED_CORE_LOADER): dynamic import of the single
canonical ``speak_core.py`` definition via importlib, with content
verification. Search order (first existing file wins):

1. ``CHATTERBOX_SPEAK_CORE_PATH`` env override (deployment knob;
   ``core_load_mode = "explicit_override"``);
2. the sibling skill checkout
   ``<agent-skills>/skills/chatterbox-speak/scripts/speak_core.py``
   (``core_load_mode = "sibling"``);
3. ``/opt/chatterbox-speak/speak_core.py`` (container build —
   ``deploy/Dockerfile.voice-control`` COPYs the file from the
   ``chatterbox-speak`` compose additional context and bakes its digest to
   ``/opt/chatterbox-speak/speak_core.py.sha256``;
   ``core_load_mode = "container"``).

HARDENING (review round 2):
- an arbitrary preloaded ``sys.modules["speak_core"]`` is NEVER trusted —
  the loader reads bytes, hashes them, and imports under the private module
  name ``_evc_speak_core``; only the verified module is cached;
- if ``CHATTERBOX_SPEAK_CORE_SHA256`` is set, a digest mismatch fails closed;
- in container mode the baked digest file is the expected digest and the
  loader records ``digest_match`` (exposed via ``core_identity()`` and the
  service ``/readiness`` endpoint);
- every render carries ``core_sha256`` + ``core_load_mode`` so receipts can
  prove WHICH gate definition produced them.

``speak_core`` needs only pydantic + httpx, both already dependencies here.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()

_CANDIDATES = (
    (os.environ.get("CHATTERBOX_SPEAK_CORE_PATH", "") or None, "explicit_override"),
    (str(_HERE.parents[3] / "chatterbox-speak" / "scripts" / "speak_core.py"), "sibling"),
    ("/opt/chatterbox-speak/speak_core.py", "container"),
)

_BAKED_DIGEST_FILE = "/opt/chatterbox-speak/speak_core.py.sha256"
_PRIVATE_MODULE_NAME = "_evc_speak_core"

_CORE_CACHE: dict[str, Any] | None = None


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _expected_digest(load_mode: str, core_path: Path) -> str | None:
    """Expected core digest, when one is knowable for this load mode."""
    env_expected = os.environ.get("CHATTERBOX_SPEAK_CORE_SHA256", "")
    if env_expected:
        return env_expected
    if load_mode == "container" and Path(_BAKED_DIGEST_FILE).is_file():
        # baked by the Dockerfile: "<hex>  /opt/chatterbox-speak/speak_core.py"
        hexdigest = Path(_BAKED_DIGEST_FILE).read_text().split()[0]
        return "sha256:" + hexdigest
    return None


def load_speak_core() -> Any:
    """Import the canonical, content-verified speak_core module.

    NEVER reuses an arbitrary ``sys.modules["speak_core"]`` — that would let
    any earlier import silently replace the safety gate. The verified module
    is imported under the private name ``_evc_speak_core`` and cached here.
    """
    global _CORE_CACHE
    if _CORE_CACHE is not None:
        return _CORE_CACHE["module"]

    strict = bool(os.environ.get("CHATTERBOX_SPEAK_CORE_SHA256", ""))
    last: str | None = None
    for cand, load_mode in _CANDIDATES:
        if not cand:
            continue
        path = Path(cand)
        if not path.is_file():
            last = cand
            continue
        data = path.read_bytes()
        digest = _sha256_bytes(data)
        expected = _expected_digest(load_mode, path)
        if strict and expected is not None and digest != expected:
            raise ImportError(
                "VERIFIED_CORE_LOADER: CHATTERBOX_SPEAK_CORE_SHA256 is set and "
                f"the resolved core digest {digest} != expected {expected} "
                f"({load_mode} path {path}); failing closed")
        spec = importlib.util.spec_from_file_location(_PRIVATE_MODULE_NAME, path)
        if spec is None or spec.loader is None:  # pragma: no cover
            last = cand
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PRIVATE_MODULE_NAME] = module
        spec.loader.exec_module(module)
        _CORE_CACHE = {
            "module": module,
            "core_sha256": digest,
            "core_load_mode": load_mode,
            "core_source_path": str(path),
            "expected_sha256": expected,
            "digest_match": (expected is None or digest == expected),
        }
        return module
    raise ImportError(
        "speak_core not found; set CHATTERBOX_SPEAK_CORE_PATH or deploy via "
        f"deploy/Dockerfile.voice-control (tried: {[c for c, _ in _CANDIDATES if c]}; "
        f"last missing: {last})"
    )


def core_identity() -> dict[str, Any]:
    """Identity of the loaded core: digest, load mode, expected, match.

    Returned with ``loaded=False`` values when the core has not been loaded
    yet; callers that need the module should call :func:`load_speak_core`
    first. Used by the service ``/readiness`` endpoint so the deployed
    container can prove WHICH gate bytes it is running.
    """
    if _CORE_CACHE is None:
        return {"loaded": False, "core_sha256": None, "core_load_mode": None,
                "core_source_path": None, "expected_sha256": None,
                "digest_match": None}
    return {
        "loaded": True,
        "core_sha256": _CORE_CACHE["core_sha256"],
        "core_load_mode": _CORE_CACHE["core_load_mode"],
        "core_source_path": _CORE_CACHE["core_source_path"],
        "expected_sha256": _CORE_CACHE["expected_sha256"],
        "digest_match": _CORE_CACHE["digest_match"],
    }


def reset_core_cache() -> None:
    """Test hook: forget the verified module so a later load re-verifies."""
    global _CORE_CACHE
    _CORE_CACHE = None
    sys.modules.pop(_PRIVATE_MODULE_NAME, None)


def _honest_policy_source(voice_policy: dict[str, Any] | None) -> str:
    """Closed vocabulary: never claim memory.intent without the policy."""
    if voice_policy and voice_policy.get("source") == "memory.intent":
        return "memory.intent"
    if voice_policy:
        return "caller.explicit"
    return "cli.direct"


def _policy_hash(voice_policy: dict[str, Any] | None) -> str | None:
    if not voice_policy:
        return None
    return "sha256:" + hashlib.sha256(
        json.dumps(voice_policy, sort_keys=True).encode()).hexdigest()


def assemble_render_evidence(
    *,
    turn_id: str,
    response_body: dict[str, Any],
    generated_wav: Path | None,
    final_wav: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    """TURN_RECEIPT_GATE_BINDING + AUDIO_ARTIFACT_BINDING.

    Build the required ``render_evidence`` object from the gate body and the
    actual audio artifacts, and name any missing bindings. Returns
    ``(evidence, missing_fields)``; ``audio_sha256`` binds the core-rendered
    WAV, ``final_audio_sha256`` the copied turn artifact — they must match
    (checked by the caller's acceptance gate ``render_audio_copy_binding``).
    """
    evidence: dict[str, Any] = {
        "turn_id": turn_id,
        "plan_sha256": response_body.get("plan_sha256"),
        "request_payload_sha256": response_body.get("request_payload_sha256"),
        "render_route": response_body.get("render_route"),
        "core_sha256": response_body.get("core_sha256"),
        "core_load_mode": response_body.get("core_load_mode"),
        "intent_policy_source": response_body.get("intent_policy_source"),
        "memory_intent_policy_sha256": response_body.get("memory_intent_policy_sha256"),
        "audio_sha256": _sha256_bytes(generated_wav.read_bytes()) if generated_wav and Path(generated_wav).is_file() else None,
        "final_audio_sha256": _sha256_bytes(final_wav.read_bytes()) if final_wav and Path(final_wav).is_file() else None,
        "final_audio_copy": str(final_wav) if final_wav else None,
    }
    required = ("turn_id", "plan_sha256", "request_payload_sha256",
                "render_route", "core_sha256", "audio_sha256",
                "final_audio_sha256")
    missing = [k for k in required if not evidence.get(k)]
    return evidence, missing


def render_chatterbox(
    *,
    chatterbox_url: str,
    text: str,
    ref_audio_container: str,
    label: str,
    tone: str | None = None,
    temperature: float | None = 0.7,
    voice_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render ONE Chatterbox request through the core gate.

    Returns the legacy ``synthesize_chatterbox`` tuple shape:
    ``(status, body, error, audio_path)`` plus gate evidence keys in ``body``.

    - UnsupportedTagError  -> ``(None, {ok: False, gate_rejected: True, ...},
      error, None)`` with ZERO service POSTs (the core raises before POST).
    - ServiceCallFailed / ServiceResponseInvalid -> ``(None, {}, error, None)``
      (post_json's own error semantics for transport failures).
    - success -> ``(200, service_json + plan/request/route/core hashes,
      None, host_wav)``.

    BIND_MEMORY_INTENT_POLICY: ``intent_policy_source`` is honest — it claims
    ``memory.intent`` only when the caller actually passed the voice policy
    that memory intent produced (its content hash is bound into the body);
    otherwise the closed vocabulary ``caller.explicit`` / ``cli.direct`` is
    used.
    """
    core = load_speak_core()
    identity = core_identity()
    plan = core.build_plan(
        turn_id=label,
        text=text,
        voice="embry",
        ref_audio=ref_audio_container,
        tone=tone,
        temperature=temperature,
        intent_policy_source=_honest_policy_source(voice_policy),
    )
    try:
        result = core.render(plan, base_url=chatterbox_url)
    except core.UnsupportedTagError as exc:
        return (
            None,
            {
                "ok": False,
                "gate_rejected": True,
                "tags": exc.tags,
                "route": exc.route,
                "reason": str(exc),
                "core_sha256": identity["core_sha256"],
                "core_load_mode": identity["core_load_mode"],
            },
            f"{exc} (rejected before any service POST)",
            None,
        )
    except (core.ServiceCallFailed, core.ServiceResponseInvalid) as exc:
        return None, {}, str(exc), None
    body = dict(result.service_json)
    body["plan_sha256"] = result.plan_sha256
    body["request_payload_sha256"] = result.request_payload_sha256
    # ROUTE_FROM_RENDER_RESULT: copy the route selected at render time.
    body["render_route"] = result.render_route
    body["core_sha256"] = identity["core_sha256"]
    body["core_load_mode"] = identity["core_load_mode"]
    body["intent_policy_source"] = plan.intent_policy_source
    body["memory_intent_policy_sha256"] = _policy_hash(voice_policy)
    return 200, body, None, result.host_wav
