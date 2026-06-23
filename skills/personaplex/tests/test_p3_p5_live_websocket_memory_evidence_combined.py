from __future__ import annotations

import asyncio
import http.server
import json
import tempfile
import threading
import unittest
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from personaplex_p3_p5_combined_probe import P3P5CombinedProbe
from personaplex_p3_p5_live_services import (
    attempt_evidence_case,
    attempt_memory_upsert,
    build_response_packet,
    deterministic_intent,
    deterministic_recall,
    validate_no_inline_vectors,
)


FIXTURE = {
    "session_id": "p3p5-session",
    "persona_id": "embry",
    "turns": [
        {
            "transcript": "Are any of our internet-facing Ivanti Connect Secure gateways exposed to CVE-2025-0282?",
            "source": "deterministic_transcript_fixture",
            "start_after_ms": 0,
            "route_delay_ms": 180,
            "user_audio_marker": "turn1",
        },
        {
            "transcript": "Focus on the west gateway.",
            "source": "deterministic_transcript_fixture",
            "start_after_ms": 30,
            "route_delay_ms": 0,
            "user_audio_marker": "turn2",
        },
    ],
}


def run(coro):
    return asyncio.run(coro)


class _Handler(http.server.BaseHTTPRequestHandler):
    responses: list[dict] = []
    posts: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.posts.append({"path": self.path, "payload": payload})
        if self.path == "/upsert":
            body = {"ok": True, "collection": payload.get("collection"), "key_count": len(payload.get("documents", []))}
        elif self.path == "/create-evidence-case":
            body = {"ok": True, "can_answer": False, "review_status": "needs_clarification", "evidence_case_key": "case:test"}
        else:
            body = {"ok": False, "error": "unknown"}
        self.__class__.responses.append(body)
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


class P3P5CombinedTests(unittest.TestCase):
    def test_deterministic_fallback_receipt_is_honest_and_safe(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                probe = P3P5CombinedProbe(
                    fixture=FIXTURE,
                    run_root=Path(tmp),
                    memory_url=None,
                    memory_upsert_endpoint="/upsert",
                    evidence_case_url=None,
                    live_websocket_url=None,
                )
                receipt = await probe.run()
                self.assertTrue(receipt["ok"])
                self.assertFalse(receipt["live_websocket"])
                self.assertFalse(receipt["real_deepgram"])
                self.assertFalse(receipt["real_gpu_personaplex"])
                self.assertFalse(receipt["real_memory_upsert"])
                self.assertFalse(receipt["real_create_evidence_case"])
                self.assertEqual(receipt["sealed_turn_keys"], ["conversation:p3p5-session:000002"])
                self.assertEqual(receipt["queue_depth_at_release"], 0)
                self.assertGreaterEqual(receipt["stale_rejection_count"], 1)
        run(scenario())

    def test_no_inline_vectors_validator_rejects_vectors(self):
        validate_no_inline_vectors({"qdrant_pointer_metadata": {"qdrant_point_id": "x"}})
        with self.assertRaises(ValueError):
            validate_no_inline_vectors({"embedding": [0.1] * 10})

    def test_memory_upsert_attempt_records_unavailable_without_claiming_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = {
                "_key": "conversation:test:000001",
                "collection": "conversation_history",
                "retrieval_text": "retrieval friendly text",
                "audio_artifacts": {},
                "qdrant_pointer_metadata": {"semantic_sync_state": "pending"},
            }
            attempt = attempt_memory_upsert(memory_url=None, endpoint="/upsert", record=record, run_root=Path(tmp))
            self.assertFalse(attempt["real_memory_upsert"])
            self.assertEqual(attempt["unavailable_reason"], "memory_url_not_configured")
            self.assertTrue(Path(attempt["local_fallback_path"]).exists())

    def test_configured_memory_and_evidence_http_endpoints_can_succeed(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                record = {
                    "_key": "conversation:test:000001",
                    "collection": "conversation_history",
                    "retrieval_text": "retrieval friendly text",
                    "audio_artifacts": {},
                    "qdrant_pointer_metadata": {"semantic_sync_state": "pending"},
                }
                upsert = attempt_memory_upsert(memory_url=url, endpoint="/upsert", record=record, run_root=Path(tmp))
                self.assertTrue(upsert["real_memory_upsert"])
                intent = deterministic_intent("Focus on the west gateway.", turn_id=1, generation=1, session_id="s", persona_id="embry")
                recall = deterministic_recall("Focus on the west gateway.", intent)
                evidence = attempt_evidence_case(evidence_case_url=f"{url}/create-evidence-case", transcript="Focus on the west gateway.", intent=intent, recall=recall)
                self.assertTrue(evidence["real_create_evidence_case"])
                self.assertFalse(evidence["can_answer"])
                self.assertTrue(evidence["fail_closed"])
        finally:
            server.shutdown()
            server.server_close()

    def test_evidence_case_unavailable_fails_closed_to_clarify(self):
        intent = deterministic_intent("Is Ivanti exposed?", turn_id=1, generation=1, session_id="s", persona_id="embry")
        recall = deterministic_recall("Is Ivanti exposed?", intent)
        evidence = attempt_evidence_case(evidence_case_url=None, transcript="Is Ivanti exposed?", intent=intent, recall=recall)
        self.assertFalse(evidence["real_create_evidence_case"])
        self.assertEqual(evidence["selected_route"], "/memory /clarify")
        self.assertFalse(evidence["substantive_compliance_claim_released"])

    def test_response_packet_is_bounded_and_non_factual_for_fallback(self):
        packet = build_response_packet(
            session_id="s",
            turn_id=2,
            generation=2,
            route_endpoint="/memory /clarify",
            text="I need one more grounded detail.",
            factual_claims_allowed=False,
            source_product_hash="source",
            current_intent_authority_hash="intent",
        )
        self.assertTrue(packet["bounded"])
        self.assertFalse(packet["factual_claims_allowed"])
        self.assertIn("packet_hash", packet)


if __name__ == "__main__":
    unittest.main()
