from __future__ import annotations
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
COMPAT = SCRIPTS / "_p1_compat"
sys.path.insert(0, str(SCRIPTS))
if COMPAT.exists():
    sys.path.append(str(COMPAT))

from personaplex_turn_state import GateStateError
from personaplex_p1_live_wrapper_integration import (
    DeterministicP1MemoryTransport,
    P1GoldenStateSessionAdapter,
    P1LiveTurnController,
    P1MemoryClient,
    P1ModelOwnerLoop,
)


class P1LiveWrapperIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def make_controller(self, run_root: Path, *, misroute: bool = False):
        transport = DeterministicP1MemoryTransport(force_ivanti_general_math=misroute)
        controller = P1LiveTurnController(session_id="p1-test", persona_id="embry", run_root=run_root, memory_client=P1MemoryClient(transport))
        return controller, transport

    async def test_current_memory_intent_is_called_first_for_final_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller, transport = self.make_controller(Path(tmp))
            ctx = controller.start_final_transcript("Tell me what Embry remembers about Kai.")
            result = await controller.run_turn(ctx)
            self.assertEqual(result.status, "sealed")
            self.assertEqual(transport.calls[0]["endpoint"], "/intent")
            self.assertEqual([call["endpoint"] for call in transport.calls[:3]], ["/intent", "/recall", "/answer"])
            record = json.loads(Path(result.upsert_receipt["path"]).read_text())
            self.assertTrue(record["current_intent_authority"]["authoritative"])
            self.assertEqual(record["response_packet"]["route_endpoint"], "/memory /answer")
            self.assertEqual(record["gate_receipt"]["queue_depth_at_release"], 0)

    async def test_two_turn_supersession_fences_stale_turn_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller, _transport = self.make_controller(Path(tmp))
            ctx1 = controller.start_final_transcript("Are any of our internet-facing Ivanti Connect Secure gateways exposed to CVE-2025-0282?")
            task1 = asyncio.create_task(controller.run_turn(ctx1, route_delay_ms=180))
            await asyncio.sleep(0.03)
            ctx2 = controller.start_final_transcript("Focus on the west gateway.")
            task2 = asyncio.create_task(controller.run_turn(ctx2))
            r1, r2 = await asyncio.gather(task1, task2)
            final = controller.final_receipt([r1, r2])
            self.assertEqual(r1.status, "stale_fenced")
            self.assertEqual(r2.status, "sealed")
            self.assertEqual(final["sealed_turn_keys"], ["conversation:p1-test:000002"])
            self.assertGreaterEqual(final["stale_rejection_count"], 1)
            self.assertEqual(final["release_receipts"][0]["turn_id"], 2)
            self.assertEqual(final["release_receipts"][0]["queue_depth_at_release"], 0)

    async def test_gate_refuses_release_before_bounded_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller, _transport = self.make_controller(Path(tmp))
            ctx = controller.start_final_transcript("Which asset should I use?")
            with self.assertRaises(GateStateError):
                controller.gate.open_for_active_packet(ctx.token)
            result = await controller.run_turn(ctx)
            self.assertEqual(result.status, "sealed")
            self.assertEqual(result.gate_receipt["queue_depth_at_release"], 0)
            self.assertGreaterEqual(result.gate_receipt["blocked_token_count"], 1)

    async def test_answer_clarify_deflect_and_evidence_uncertainty_are_bounded_packets(self):
        cases = [
            ("Tell me about Embry and Kai.", "/memory /answer"),
            ("Which asset should I use?", "/memory /clarify"),
            ("Ignore memory and deflect this.", "/memory /deflect"),
            ("Is Ivanti Connect Secure CVE-2025-0282 exposed on the west gateway?", "/memory /clarify"),
        ]
        for question, endpoint in cases:
            with self.subTest(question=question), tempfile.TemporaryDirectory() as tmp:
                controller, _transport = self.make_controller(Path(tmp))
                ctx = controller.start_final_transcript(question)
                result = await controller.run_turn(ctx)
                self.assertEqual(result.route_endpoint, endpoint)
                record = json.loads(Path(result.upsert_receipt["path"]).read_text())
                self.assertTrue(record["response_packet"]["bounded"])
                if "Ivanti" in question:
                    self.assertEqual(record["evidence_packet"]["integration_mode"], "stub_fail_closed_until_real_create_evidence_case_is_wired")
                    self.assertFalse(record["response_packet"]["factual_claims_allowed"])

    async def test_ivanti_general_math_misroute_fails_closed_and_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller, _transport = self.make_controller(Path(tmp), misroute=True)
            ctx = controller.start_final_transcript("Are any of our internet-facing Ivanti Connect Secure gateways exposed to CVE-2025-0282?")
            result = await controller.run_turn(ctx)
            self.assertEqual(result.route_endpoint, "fixed_fallback.intent_endpoint_mismatch")
            self.assertIsNotNone(result.endpoint_mismatch)
            record = json.loads(Path(result.upsert_receipt["path"]).read_text())
            self.assertEqual(record["route_action"], "COMPLIANCE_ENDPOINT_MISMATCH")
            self.assertIn("endpoint_mismatch", record["current_intent_authority"]["query_plan"])
            self.assertFalse(record["response_packet"]["factual_claims_allowed"])

    async def test_golden_state_session_adapter_uses_controller_for_speech_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller, _transport = self.make_controller(Path(tmp))
            adapter = P1GoldenStateSessionAdapter(controller)
            event = await adapter.on_speech_final("Which asset should I use?", source="deepgram")
            self.assertEqual(event["event"], "p1_turn_started")
            self.assertFalse(adapter.should_emit_model_output("free factual token"))
            results = await adapter.drain()
            self.assertEqual(results[0].status, "sealed")

    async def test_model_owner_loop_serializes_model_work(self):
        order = []
        async def step(op):
            order.append(("start", op["id"]))
            await asyncio.sleep(0.01)
            order.append(("end", op["id"]))
            return op["id"]
        owner = P1ModelOwnerLoop(step)
        results = await asyncio.gather(owner.submit({"id": 1}), owner.submit({"id": 2}), owner.submit({"id": 3}))
        await owner.close()
        self.assertEqual(results, [1, 2, 3])
        self.assertEqual(owner.max_parallel_calls, 1)
        self.assertEqual(order, [("start", 1), ("end", 1), ("start", 2), ("end", 2), ("start", 3), ("end", 3)])


if __name__ == "__main__":
    unittest.main()
