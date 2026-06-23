from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from personaplex_conversation_compaction import run_conversation_compaction  # noqa: E402
from personaplex_deepgram_live import deepgram_websocket_probe, inspect_audio_file, iter_audio_payload_chunks  # noqa: E402
from personaplex_gpu_inference_probe import run_gpu_personaplex_probe, validate_real_gpu_payload  # noqa: E402
from personaplex_p3_p5_combined_probe import run_combined_probe  # noqa: E402
from personaplex_p3_p5_live_services import build_conversation_document, find_inline_vector_paths  # noqa: E402


class CapturingHandler(BaseHTTPRequestHandler):
    captures: ClassVar[list[dict[str, Any]]] = []
    response_status: ClassVar[int] = 200
    response_body: ClassVar[dict[str, Any]] = {"ok": True}

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", errors="replace")}
        self.__class__.captures.append({"path": self.path, "payload": payload})
        body = json.dumps(self.__class__.response_body).encode("utf-8")
        self.send_response(self.__class__.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalHttpServer:
    def __init__(self, response_status: int = 200, response_body: dict[str, Any] | None = None) -> None:
        self.response_status = response_status
        self.response_body = response_body if response_body is not None else {"ok": True}
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "LocalHttpServer":
        CapturingHandler.captures = []
        CapturingHandler.response_status = self.response_status
        CapturingHandler.response_body = self.response_body
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), CapturingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=2)

    @property
    def url(self) -> str:
        assert self.server is not None
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    @property
    def captures(self) -> list[dict[str, Any]]:
        return CapturingHandler.captures


def unused_local_url() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()
    return f"http://{host}:{port}"


def make_test_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        # 100 ms of quiet non-zero PCM so the file is a valid 16k mono linear16 WAV.
        frames = (b"\x01\x00" * 1600)
        wav.writeframes(frames)
    return path


class P8P9P10RemainingGapsTests(unittest.TestCase):
    def test_p8_missing_key_uses_deterministic_fallback_with_real_audio_metadata(self) -> None:
        old_key = os.environ.pop("DEEPGRAM_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                wav = make_test_wav(Path(td) / "assets" / "test" / "input_assistant.wav")
                receipt = deepgram_websocket_probe(audio_path=wav, api_key="", out_dir=td)
                self.assertFalse(receipt["real_deepgram"])
                self.assertFalse(receipt["attempted"])
                self.assertEqual(receipt["unavailable_reason"], "missing_deepgram_api_key")
                self.assertEqual(receipt["audio_metadata"]["sample_rate_hz"], 16000)
                self.assertEqual(receipt["audio_metadata"]["channels"], 1)
                self.assertTrue(Path(receipt["fixture_path"]).exists())
        finally:
            if old_key is not None:
                os.environ["DEEPGRAM_API_KEY"] = old_key

    def test_p8_wav_payload_iterator_strips_riff_header(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            wav = make_test_wav(Path(td) / "input.wav")
            meta = inspect_audio_file(wav)
            payload = b"".join(iter_audio_payload_chunks(wav))
            self.assertEqual(meta["matches_deepgram_url_encoding"], True)
            self.assertNotIn(b"RIFF", payload[:16])
            self.assertEqual(len(payload), 3200)

    def test_p9_compaction_hits_expected_collections_and_omits_inline_vectors(self) -> None:
        with tempfile.TemporaryDirectory() as td, LocalHttpServer(response_body={"ok": True}) as server:
            wav = make_test_wav(Path(td) / "input.wav")
            turns = [
                build_conversation_document(
                    session_id="s",
                    turn_id=1,
                    persona_id="embry",
                    transcript="Focus on the west gateway.",
                    audio_metadata={"path": str(wav), "turn_id": 1},
                )
            ]
            receipt = run_conversation_compaction(
                turn_documents=turns,
                session_id="s",
                persona_id="embry",
                memory_url=server.url,
                out_dir=td,
                audio_artifacts=[{"path": str(wav), "turn_id": 1}],
                timeout=1,
            )

            self.assertTrue(receipt["real_conversation_compaction"])
            self.assertTrue(receipt["cas_update_applied"])
            self.assertEqual(receipt["new_generation"], 1)
            collections = [capture["payload"]["collection"] for capture in server.captures]
            self.assertIn("conversation_history", collections)
            self.assertIn("conversation_history_summaries", collections)
            self.assertIn("personaplex_sessions", collections)
            self.assertIn("conversation_audio_artifacts", collections)
            self.assertIn("personaplex_turns", collections)
            for capture in server.captures:
                self.assertEqual(find_inline_vector_paths(capture["payload"]), [])
            session_payload = next(c["payload"] for c in server.captures if c["payload"]["collection"] == "personaplex_sessions")
            self.assertTrue(session_payload["skip_embedding"])
            session_doc = session_payload["documents"][0]
            self.assertEqual(session_doc["cas"]["expected_previous_generation"], 0)
            self.assertFalse(session_doc["cas"]["daemon_enforced"])
            audio_payload = next(c["payload"] for c in server.captures if c["payload"]["collection"] == "conversation_audio_artifacts")
            audio_doc = audio_payload["documents"][0]
            self.assertIn("sha256", audio_doc["metadata"])
            self.assertNotIn("raw_audio", json.dumps(audio_doc))

    def test_p9_compaction_falls_back_when_memory_daemon_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            turns = [build_conversation_document(session_id="s", turn_id=1, transcript="Focus on the west gateway.")]
            receipt = run_conversation_compaction(
                turn_documents=turns,
                session_id="s",
                persona_id="embry",
                memory_url=unused_local_url(),
                out_dir=td,
                timeout=0.2,
            )
            self.assertFalse(receipt["real_conversation_compaction"])
            self.assertTrue(receipt["fallback_used"])
            attempts = receipt["memory_upsert_attempts"]
            self.assertGreaterEqual(len(attempts), 3)
            self.assertTrue(any(a.get("local_fallback_paths") for a in attempts))

    def test_p9_cas_mismatch_fails_closed_before_http_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as td, LocalHttpServer() as server:
            turns = [build_conversation_document(session_id="s", turn_id=1, transcript="Focus on the west gateway.")]
            receipt = run_conversation_compaction(
                turn_documents=turns,
                session_id="s",
                persona_id="embry",
                memory_url=server.url,
                out_dir=td,
                previous_head={"_key": "session:s", "generation": 3},
                expected_previous_generation=2,
            )
            self.assertFalse(receipt["ok"])
            self.assertEqual(receipt["unavailable_reason"], "cas_generation_mismatch")
            self.assertEqual(server.captures, [])

    def test_p9_inline_vectors_fail_closed_before_http_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as td, LocalHttpServer() as server:
            turn = build_conversation_document(session_id="s", turn_id=1, transcript="bad vector")
            turn["embedding"] = [0.1, 0.2]
            receipt = run_conversation_compaction(
                turn_documents=[turn],
                session_id="s",
                persona_id="embry",
                memory_url=server.url,
                out_dir=td,
            )
            self.assertFalse(receipt["ok"])
            self.assertEqual(receipt["unavailable_reason"], "inline_vectors_rejected")
            self.assertEqual(server.captures, [])

    def test_p10_fake_golden_state_hook_records_real_gpu_personaplex(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            server = Path(td) / "personaplex_golden_state_server.py"
            server.write_text(
                "def probe_lmgen_step(out_dir=None, personaplex_root=None, timeout=None, max_steps=1):\n"
                "    return {\n"
                "        'real_gpu_personaplex': True,\n"
                "        'lmgen_step_called': True,\n"
                "        'device': 'cuda:0',\n"
                "        'output_token_id': 42,\n"
                "        'max_steps': max_steps,\n"
                "    }\n",
                encoding="utf-8",
            )
            receipt = run_gpu_personaplex_probe(out_dir=td, server_path=server, timeout=1)
            self.assertTrue(receipt["real_gpu_personaplex"])
            self.assertTrue(receipt["lmgen_step_called"])
            self.assertFalse(receipt["fallback_used"])
            self.assertIn("module_hook", receipt["probe_mode"])

    def test_p10_payload_validation_rejects_unbounded_or_cpu_claims(self) -> None:
        ok, missing = validate_real_gpu_payload({"real_gpu_personaplex": True, "lmgen_step_called": True, "device": "cpu"})
        self.assertFalse(ok)
        self.assertIn("gpu_device_or_cuda_available", missing)
        self.assertIn("bounded_step_output", missing)

    def test_p10_missing_server_uses_honest_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            receipt = run_gpu_personaplex_probe(out_dir=td, server_path=Path(td) / "missing.py", timeout=0.2)
            self.assertFalse(receipt["real_gpu_personaplex"])
            self.assertTrue(receipt["fallback_used"])
            self.assertEqual(receipt["unavailable_reason"], "golden_state_server_not_found")

    def test_combined_probe_records_false_flags_for_unavailable_live_targets(self) -> None:
        old_key = os.environ.pop("DEEPGRAM_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                receipt = run_combined_probe(
                    out_dir=td,
                    memory_url=unused_local_url(),
                    evidence_case_url=unused_local_url(),
                    skip_deepgram=True,
                    skip_gpu=True,
                    timeout=0.2,
                )
                self.assertTrue(receipt["ok"])
                self.assertFalse(receipt["real_deepgram"])
                self.assertFalse(receipt["real_conversation_compaction"])
                self.assertFalse(receipt["real_gpu_personaplex"])
                self.assertTrue(Path(receipt["final_receipt_path"]).exists())
                self.assertEqual(receipt["stale_rejection_count"], 1)
        finally:
            if old_key is not None:
                os.environ["DEEPGRAM_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main(verbosity=2)
