from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SCHEMA = "schemas/paid_call_approval_receipt.schema.json"
P0_SCHEMA = "schemas/pipeline_paid_call_approval_receipt.schema.json"
ONE_SCENE_SCHEMA = "schemas/one_scene_kling_call_contract.schema.json"
KLING_SCENE_PACKET_SCHEMA = "schemas/kling_scene_packet.schema.json"

sys.path.insert(0, str(ROOT / "scripts"))
from validate_pipeline_spine import validate_run  # noqa: E402


class TestPipelineSpine(unittest.TestCase):
    def test_manifest_omits_legacy_paid_call_schema_path(self) -> None:
        manifest = json.loads((ROOT / "MANIFEST.json").read_text())
        paths = {entry["path"] for entry in manifest["files"]}
        self.assertNotIn(LEGACY_SCHEMA, paths)
        self.assertIn(P0_SCHEMA, paths)
        self.assertIn(ONE_SCENE_SCHEMA, paths)
        self.assertIn(KLING_SCENE_PACKET_SCHEMA, paths)

    def test_all_schemas_parse(self) -> None:
        manifest = json.loads((ROOT / "MANIFEST.json").read_text())
        schema_paths = [
            ROOT / entry["path"]
            for entry in manifest["files"]
            if entry["path"].startswith("schemas/") and entry["path"].endswith(".schema.json")
        ]
        self.assertEqual(len(schema_paths), 8)
        for schema_path in sorted(schema_paths):
            schema = json.loads(schema_path.read_text())
            jsonschema.Draft202012Validator.check_schema(schema)
            self.assertEqual(schema.get("type"), "object")

    def test_blocked_missing_input_fixture_returns_blocked(self) -> None:
        result = validate_run(ROOT / "fixtures/blocked_missing_input", ROOT)
        self.assertEqual(result["status"], "BLOCKED_MISSING_INPUT")
        self.assertEqual(result["paid_call_schema"], P0_SCHEMA)

    def test_provider_ready_dry_run_fixture_returns_not_live_submittable(self) -> None:
        result = validate_run(ROOT / "fixtures/provider_ready_dry_run", ROOT)
        self.assertEqual(result["status"], "DRY_RUN_NOT_LIVE_SUBMITTABLE")
        self.assertEqual(result["paid_call_schema"], P0_SCHEMA)
        self.assertFalse(result["one_scene_call_ready"])

    def test_one_scene_kling_dry_run_works_back_from_terminal_call(self) -> None:
        result = validate_run(ROOT / "fixtures/one_scene_kling_dry_run", ROOT)
        self.assertEqual(result["status"], "DRY_RUN_NOT_LIVE_SUBMITTABLE")
        self.assertEqual(result["terminal_gate"], "kling_submit")
        self.assertEqual(result["paid_call_schema"], P0_SCHEMA)
        self.assertTrue(result["one_scene_call_ready"])
        self.assertFalse(result["live_provider_call_made"])

    def test_fixture_documents_validate_against_declared_schemas(self) -> None:
        cases = [
            (
                "blocked stage",
                "schemas/stage_receipt.schema.json",
                "fixtures/blocked_missing_input/receipts/stage_receipt.json",
            ),
            (
                "blocked paid approval",
                P0_SCHEMA,
                "fixtures/blocked_missing_input/receipts/pipeline_paid_call_approval_receipt.json",
            ),
            (
                "blocked terminal",
                "schemas/pipeline_terminal_report.schema.json",
                "fixtures/blocked_missing_input/receipts/pipeline_terminal_report.json",
            ),
            (
                "dry-run stage",
                "schemas/stage_receipt.schema.json",
                "fixtures/provider_ready_dry_run/receipts/stage_receipt.json",
            ),
            (
                "dry-run paid approval",
                P0_SCHEMA,
                "fixtures/provider_ready_dry_run/receipts/pipeline_paid_call_approval_receipt.json",
            ),
            (
                "dry-run kling gate",
                "schemas/kling_submit_gate_receipt.schema.json",
                "fixtures/provider_ready_dry_run/receipts/kling_submit_gate_receipt.json",
            ),
            (
                "one-scene Kling scene packet",
                KLING_SCENE_PACKET_SCHEMA,
                "fixtures/one_scene_kling_dry_run/receipts/kling_scene_packet.json",
            ),
            (
                "one-scene Kling call contract",
                ONE_SCENE_SCHEMA,
                "fixtures/one_scene_kling_dry_run/receipts/one_scene_kling_call_contract.json",
            ),
            (
                "one-scene terminal",
                "schemas/pipeline_terminal_report.schema.json",
                "fixtures/one_scene_kling_dry_run/receipts/pipeline_terminal_report.json",
            ),
        ]
        for name, schema_rel, doc_rel in cases:
            with self.subTest(name=name):
                schema = json.loads((ROOT / schema_rel).read_text())
                doc = json.loads((ROOT / doc_rel).read_text())
                jsonschema.Draft202012Validator(schema).validate(doc)
