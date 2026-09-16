#!/usr/bin/env python3
"""Render-gate contract test for the embry-voice-control Chatterbox leg.

Contract under test (see speak_core.py, the single definition this skill
imports via embry_voice_control.chatterbox_gate):

1. An unknown/unsupported bracket tag is REJECTED before any service POST —
   proven here with a counting HTTP server (POST count must stay 0).
2. Known-tag text still routes to the service (gate is not a blanket block).

Runnable directly: ``python3 scripts/test_render_gate_contract.py``
Exits 0 only when both properties hold on the CURRENT code.
"""
from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))


class _Counter(HTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.posts = 0


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        self.server.posts += 1  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b'{"ok": false}')

    def log_message(self, *a: object) -> None:
        pass


def main() -> int:
    from embry_voice_control.embry_chat import (
        DEFAULT_EMBRY_REF_AUDIO,
        synthesize_chatterbox,
    )

    server = _Counter()
    host, port = server.server_address
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://{host}:{port}"

    # -- 1. unknown tag: REJECTED before any service POST -------------------
    status, body, error, audio = synthesize_chatterbox(
        chatterbox_url=url,
        text="[laughs] Well, that is new.",
        ref_audio=DEFAULT_EMBRY_REF_AUDIO,
        label="render-gate-red",
        timeout=5.0,
    )
    assert server.posts == 0, (
        f"gate violated: {server.posts} POST(s) reached the service with an "
        "unsupported tag; expected rejection before any POST")
    assert body.get("ok") is not True, body
    assert body.get("gate_rejected") is True, body
    assert "[laughs]" in str(body.get("tags") or ""), body
    assert "[laughs]" in str(error or ""), error
    assert audio is None and status is None, (status, audio)
    print("PASS_UNKNOWN_TAG_REJECTED_BEFORE_POST")

    # -- 2. known singular tag: still routes to the service ------------------
    status, body, error, audio = synthesize_chatterbox(
        chatterbox_url=url,
        text="All nominal. [happy]",
        ref_audio=DEFAULT_EMBRY_REF_AUDIO,
        label="render-gate-control",
        timeout=5.0,
    )
    assert server.posts == 1, (
        f"gate over-blocked: known-tag text produced {server.posts} POST(s); "
        "expected the request to reach the service")
    assert status is None and audio is None, (status, audio)  # server said 500
    assert body.get("gate_rejected") is not True, body
    print("PASS_KNOWN_TAG_STILL_ROUTES")

    # -- 3. sys.modules collision: a preloaded fake speak_core is REJECTED --
    import types
    from embry_voice_control import chatterbox_gate
    fake = types.ModuleType("speak_core")
    fake.poisoned = True
    sys.modules["speak_core"] = fake  # adversarial preload
    try:
        core = chatterbox_gate.load_speak_core()
        assert getattr(core, "poisoned", False) is not True, (
            "VERIFIED_CORE_LOADER violated: the preloaded fake module was used")
        identity = chatterbox_gate.core_identity()
        assert identity["loaded"] is True and identity["core_sha256"], identity
        assert identity["core_load_mode"] in {"sibling", "container", "explicit_override"}, identity
        assert identity["core_source_path"].endswith("speak_core.py"), identity
    finally:
        sys.modules.pop("speak_core", None)
    print("PASS_FAKE_SYS_MODULES_REJECTED")

    # -- 4. successful path vs live :8018: full evidence chain -------------
    # (TURN_RECEIPT_GATE_BINDING + AUDIO_ARTIFACT_BINDING + the honest policy
    # source, exercised through the same helpers the turn receipt uses)
    import hashlib
    import json as _json
    import tempfile
    from embry_voice_control.embry_chat import DEFAULT_CHATTERBOX_URL
    policy = {"source": "memory.intent", "tone": "calm_precise",
              "emotion_tags": ["[calm]"]}
    status, body, error, audio = synthesize_chatterbox(
        chatterbox_url=DEFAULT_CHATTERBOX_URL,
        text="Gate evidence check. [happy]",
        ref_audio=DEFAULT_EMBRY_REF_AUDIO,
        label="render-gate-success",
        timeout=120.0,
        voice_policy=policy,
    )
    assert status == 200 and audio is not None, (status, error)
    for key in ("plan_sha256", "request_payload_sha256", "render_route",
                "core_sha256", "core_load_mode"):
        assert body.get(key), f"gate body missing {key}: {sorted(body)}"
    assert body["intent_policy_source"] == "memory.intent", body.get("intent_policy_source")
    expected_policy_hash = "sha256:" + hashlib.sha256(
        _json.dumps(policy, sort_keys=True).encode()).hexdigest()
    assert body["memory_intent_policy_sha256"] == expected_policy_hash, body.get("memory_intent_policy_sha256")
    with tempfile.TemporaryDirectory() as tmp:
        final_wav = Path(tmp) / "embry_response.wav"
        final_wav.write_bytes(Path(audio).read_bytes())
        evidence, missing = chatterbox_gate.assemble_render_evidence(
            turn_id="render-gate-success",
            response_body=body,
            generated_wav=Path(audio),
            final_wav=final_wav,
        )
        assert not missing, f"render_evidence incomplete: {missing}"
        assert evidence["plan_sha256"] == body["plan_sha256"]
        assert evidence["render_route"] == body["render_route"]
        assert evidence["audio_sha256"] == evidence["final_audio_sha256"], evidence
        # tamper case: a modified copy must FAIL the binding
        final_wav.write_bytes(final_wav.read_bytes() + b"\x00")
        evidence2, _ = chatterbox_gate.assemble_render_evidence(
            turn_id="render-gate-success", response_body=body,
            generated_wav=Path(audio), final_wav=final_wav)
        assert evidence2["audio_sha256"] != evidence2["final_audio_sha256"], (
            "AUDIO_ARTIFACT_BINDING violated: tampered copy still matched")
    print("PASS_SUCCESSFUL_WIRING_RECEIPT_EVIDENCE")

    print("PASS_RENDER_GATE_CONTRACT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
