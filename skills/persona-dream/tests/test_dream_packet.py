from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_dream_packet import validate_dream_packet  # noqa: E402


PNG_BYTES = b"\x89PNG\r\n\x1a\nfixture"


def _write_packet(path: Path, **overrides: object) -> None:
    packet = {
        "schema": "persona_dream.packet.v1",
        "run_id": "fixture-dream",
        "mode": "static_dream",
        "created_at": "2026-06-28T20:00:00Z",
        "persona": {"id": "horus", "display_name": "Horus"},
        "secondary_persona": None,
        "synthetic_content_notice": "Synthetic fixture.",
        "residue_items": [{"source_id": "fixture-memory-1", "text": "Tea under a void-world sky."}],
        "contradictions": [],
        "dream_prompt": "Dream of a tea table under a void-world sky.",
        "frame_prompts": [{"frame_id": "frame_001", "prompt": "A cinematic patio tea scene."}],
        "contact_sheet": "contact_sheet.png",
        "reflection": "The dream maps collaboration to a shared table.",
        "downstream_routes": {},
    }
    packet.update(overrides)
    path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")


class TestDreamPacket(unittest.TestCase):
    def test_valid_dream_packet_passes_local_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "contact_sheet.png").write_bytes(PNG_BYTES)
            packet = run_root / "dream_packet.json"
            _write_packet(packet)

            result = validate_dream_packet(packet, run_root=run_root)

        self.assertEqual(result["status"], "PASS_DREAM_PACKET")
        self.assertIsNone(result["first_blocker"])
        self.assertEqual(result["frame_prompt_count"], 1)
        self.assertEqual(result["live"], "no")

    def test_dream_packet_blocks_on_wrong_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "contact_sheet.png").write_bytes(PNG_BYTES)
            packet = run_root / "dream_packet.json"
            _write_packet(packet, schema="persona_dream.response.v1")

            result = validate_dream_packet(packet, run_root=run_root)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["reason"], "wrong_schema:persona_dream.response.v1")

    def test_dream_packet_blocks_on_missing_residue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "contact_sheet.png").write_bytes(PNG_BYTES)
            packet = run_root / "dream_packet.json"
            _write_packet(packet, residue_items=[])

            result = validate_dream_packet(packet, run_root=run_root)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["reason"], "missing_residue_items")

    def test_dream_packet_blocks_on_non_png_contact_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "contact_sheet.png").write_text("not png", encoding="utf-8")
            packet = run_root / "dream_packet.json"
            _write_packet(packet)

            result = validate_dream_packet(packet, run_root=run_root)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["phase"], "dream_packet_contact_sheet")
        self.assertEqual(result["first_blocker"]["reason"], "contact_sheet_not_png")


if __name__ == "__main__":
    unittest.main()
