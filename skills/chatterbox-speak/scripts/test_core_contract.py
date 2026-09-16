# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic", "httpx"]
# ///
"""Core-import contract check for chatterbox_speak (adversarial, assert-based).

Run directly:  uv run --project .. python test_core_contract.py

Covers the ten hardening fixes on the import surface: model-level plan
invariants, route-from-payload gating (plan/delivery/chunk intensity), pause
compilation honesty, frozen render snapshot + payload digest, receipt reserved
fields, typed receipt, zero-POST proof via a local counting server, and live
render + explicit opt-out through the REAL service. Failure before the core
exists is the expected red baseline.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))


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
    import speak_core as core  # ImportError here = red baseline
    from pydantic import ValidationError

    # -- 1. build_plan: policy inputs -> typed plan --------------------------
    plan = core.build_plan(
        turn_id="core-contract-smoke",
        text="Core contract smoke line.",
        voice="embry",
        tone="neutral_warm",
    )
    assert plan.voice == "embry" and plan.text == "Core contract smoke line."
    digest = core.plan_sha256(plan)
    assert digest.startswith("sha256:") and len(digest) == 71, digest
    assert core.plan_sha256(core.build_plan(turn_id="core-contract-smoke",
                                            text="Core contract smoke line.",
                                            voice="embry", tone="neutral_warm")) == digest

    # -- 2. PLAN_INVARIANTS_IN_MODEL: direct construction is fully constrained
    for kwargs, why in (
        ({"turn_id": "x"}, "no text/chunks"),
        ({"turn_id": "x", "text": "hi", "voice": "nosuch"}, "unknown voice"),
        ({"turn_id": "x", "text": "hi", "intensity": "extreme"}, "bad intensity"),
        ({"turn_id": "x", "text": "hi", "render_chunks": []}, "empty chunks"),
        ({"turn_id": "x", "text": "hi", "render_chunks": [{"text": "a"}]},
         "chunks require caller_plan|compiled source"),
        ({"turn_id": "x", "text": "hi", "pause_strategy": "planned_pauses"},
         "pause strategy requires chunks"),
        ({"turn_id": "x", "text": "hi", "intent_policy_source": "made_up"},
         "closed policy vocabulary"),
    ):
        try:
            core.VoiceDeliveryPlan(**kwargs)
            raise AssertionError(f"model must reject: {why}")
        except (ValidationError, ValueError):
            pass
    # ref_audio rescues an unknown voice name
    ok = core.VoiceDeliveryPlan(turn_id="x", text="hi", voice="nosuch",
                                ref_audio="/data/embry_ref.wav")
    assert ok.ref_audio == "/data/embry_ref.wav"

    # -- 3. GATE_FROM_ACTUAL_RENDER_ROUTE ------------------------------------
    # delivery intensity alone selects base-affect: [sigh] must be gated even
    # though plan.intensity is None (the reviewer's exact bypass).
    stealth = core.build_plan(turn_id="stealth", text="[sigh] hi.", voice="embry",
                              delivery={"intensity": 0.9,
                                        "emotion_realization": "audible"})
    try:
        core.render(stealth)
        raise AssertionError("delivery-intensity route must gate [sigh]")
    except core.UnsupportedTagError as exc:
        assert exc.base_affect_route and exc.route == "base_affect", exc
    # chunk-level backend fields gate too
    chunked = core.build_plan(
        turn_id="chunk-gate", answer_text="a b",
        render_chunks=[{"text": "[sigh] a."}, {"text": "b.", "intensity": 0.9}],
        voice="embry")
    try:
        core.render(chunked)
        raise AssertionError("chunk intensity must select base-affect gating")
    except core.UnsupportedTagError:
        pass
    # and WITHOUT any intensity, known tags stay allowed on the turbo route
    assert core.evaluate_gate(json.loads(core.canonical_plan_json(
        core.build_plan(turn_id="turbo", text="[sigh] fine.", voice="embry")))) == []

    # -- 4. FINAL_TEXT_HAS_NO_UNCOMPILED_PAUSE_MACROS -------------------------
    # layer 1: a caller flag alone cannot unlock pause syntax (model rejects
    # planned_pauses without compiled chunks)
    try:
        core.build_plan(turn_id="forged", text="[pause:weight] hi.",
                        voice="embry", pause_strategy="planned_pauses")
        raise AssertionError("flag alone must not unlock pause syntax")
    except (ValidationError, ValueError):
        pass
    # layer 2: a named macro hiding INSIDE real chunks/text still hits the gate
    forged = core.build_plan(turn_id="forged2", text="[pause:weight] hi.",
                             render_chunks=[{"text": "[pause:weight] hi."}],
                             voice="embry", render_source="caller_plan",
                             pause_strategy="caller_chunks")
    try:
        core.render(forged)
        raise AssertionError("uncompiled named pause must be gated")
    except core.UnsupportedTagError as exc:
        assert "[pause:weight]" in exc.tags, exc
    # numeric shape (the compiler OUTPUT) stays renderable in every mode
    assert core.unsupported_tags("Hold [pause:750ms] there.",
                                 allow_event_tags=True,
                                 allow_named_pauses=False) == []

    # -- 9. ZERO_POST_CORE_PROOF: counting server as transport oracle --------
    server = _Counter()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        counting_url = f"http://127.0.0.1:{server.server_address[1]}"
        bad = core.build_plan(turn_id="zero-post", text="[laughs] no.",
                              voice="embry", tone="neutral_warm")
        try:
            core.render(bad, base_url=counting_url)
            raise AssertionError("gated render must fail")
        except core.UnsupportedTagError:
            pass
        assert server.posts == 0, f"gate leaked {server.posts} POSTs"
        # clean plan attempts exactly 1 POST (count is the oracle, not success)
        clean = core.build_plan(turn_id="one-post", text="counting probe.",
                                voice="embry", tone="neutral_warm")
        try:
            core.render(clean, base_url=counting_url)
            raise AssertionError("counter returns 500; render must fail")
        except core.ServiceCallFailed:
            pass
        assert server.posts == 1, server.posts
    finally:
        server.shutdown()

    # -- 3b. render through the REAL service (no playback) -------------------
    result = core.render(plan)
    assert result.wav_copy.is_file() and result.wav_copy.stat().st_size > 0
    assert result.receipt.live is True and result.receipt.ok is True
    assert result.receipt.mocked is False

    # -- 5/6. FREEZE_RENDER_SNAPSHOT + REQUEST_PAYLOAD_SHA256 ----------------
    frozen_digest = result.plan_sha256
    plan.text = "MUTATED AFTER RENDER"
    if plan.delivery is not None:
        plan.delivery.intensity = 0.9
    assert result.plan_sha256 == frozen_digest, "snapshot mutated!"
    assert result.plan_snapshot["text"] == "Core contract smoke line."
    assert result.request_payload_sha256.startswith("sha256:")
    assert result.payload["text"] == "Core contract smoke line."

    # -- 7/8. typed receipt, reserved fields, digest equality ----------------
    record = core.build_receipt(plan, result,
                                context="core contract", original_text="Core contract smoke line.",
                                spoken_text="Core contract smoke line.").model_dump()
    assert record["plan_sha256"] == frozen_digest, "receipt must carry the frozen digest"
    assert record["request_payload_sha256"] == result.request_payload_sha256
    assert record["live"] is True and record["mocked"] is False
    assert "allow_unknown_tags" in record and "unknown_tags_detected" in record
    assert "backend" in record and record["backend"], record.get("backend")
    assert "tag_handling" in record and "caller_metadata" in record
    try:
        core.build_receipt(plan, result, plan_sha256="fake", live=False)
        raise AssertionError("cli_fields must not override core-owned evidence")
    except ValueError as exc:
        assert "plan_sha256" in str(exc) and "live" in str(exc), exc

    # -- 10. explicit opt-out through the REAL service ------------------------
    optout = core.build_plan(turn_id="optout-contract", text="[laughs] fine.",
                             voice="embry", tone="neutral_warm",
                             allow_unknown_tags=True)
    result2 = core.render(optout)
    rec2 = core.build_receipt(optout, result2).model_dump()
    assert rec2["allow_unknown_tags"] is True
    assert rec2["unknown_tags_detected"] == ["[laughs]"], rec2
    assert rec2["unknown_tag_policy"] == "explicit_operator_opt_out"
    assert rec2["plan_sha256"] == result2.plan_sha256
    assert rec2["live"] is True and result2.wav_copy.is_file()

    # -- 10b. batch/render_chunks render through the core (REAL service) -----
    batch_plan = core.build_plan(
        turn_id="batch-contract", answer_text="Batch contract answer.",
        render_chunks=[{"text": "First chunk.", "tone": "neutral_warm"},
                       {"text": "Second chunk.", "tone": "relieved"}],
        voice="embry", render_source="caller_plan", pause_strategy="caller_chunks")
    batch = core.render(batch_plan)
    assert batch.endpoint == "synthesize-batch"
    assert batch.wav_copy.is_file() and batch.receipt.live is True
    batch_rec = core.build_receipt(batch_plan, batch).model_dump()
    assert batch_rec["plan_sha256"] == batch.plan_sha256
    assert batch_rec["request_payload_sha256"] == batch.request_payload_sha256

    print("PASS_CORE_IMPORT_CONTRACT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
