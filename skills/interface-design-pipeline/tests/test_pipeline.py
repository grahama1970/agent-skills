from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location("interface_pipeline", SCRIPT)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sparta-chat.json"


class PipelineTests(unittest.TestCase):
    def test_example_manifest_is_valid(self) -> None:
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual([], pipeline.validate_manifest(manifest))

    def test_duplicate_competitor_ids_are_rejected(self) -> None:
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["mockups"]["competitors"][1]["id"] = manifest["mockups"]["competitors"][0]["id"]
        errors = pipeline.validate_manifest(manifest)
        self.assertTrue(any("duplicate competitor" in error for error in errors))

    def test_plan_writes_phase_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            result = pipeline.plan_pipeline(EXAMPLE, output)
            self.assertEqual("PLANNED", result["status"])
            self.assertEqual(6, result["research_lanes"])
            self.assertEqual(3, result["mockup_competitors"])
            self.assertEqual(3, result["implementation_competitors"])
            for relative in (
                "status.json",
                "pipeline-receipt.json",
                "phases/01-research/plan.json",
                "phases/02-reference-adjudication/agent-task.json",
                "phases/03-mockup-tournament/plan.json",
                "phases/04-component-inventory/agent-task.json",
                "phases/05-implementation-tournament/plan.json",
                "phases/06-final-adjudication/agent-task.json",
                "phases/07-human-promotion/gate.json",
            ):
                self.assertTrue((output / relative).is_file(), relative)
            mockup_nodes = list((output / "phases/03-mockup-tournament/nodes").glob("*.json"))
            implementation_nodes = list((output / "phases/05-implementation-tournament/node-templates").glob("*.json"))
            self.assertEqual(3, len(mockup_nodes))
            self.assertEqual(3, len(implementation_nodes))


if __name__ == "__main__":
    unittest.main()
