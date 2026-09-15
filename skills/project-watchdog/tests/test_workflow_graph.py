"""Guardrails for the editable Watchdog graph source."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "watchdog_graph.py"
SPEC = importlib.util.spec_from_file_location("watchdog_graph", SOURCE)
assert SPEC and SPEC.loader
graph_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = graph_module
SPEC.loader.exec_module(graph_module)


class GraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = deepcopy(graph_module.read_graph("active")[0])

    def add_scout(self) -> None:
        self.graph["nodes"].append({
            "id": "scout", "agent": "reviewer", "access": "read",
            "task": "Inspect the target without editing.", "depends_on": [],
        })
        self.graph["layout"]["scout"] = {"x": 0, "y": 0}
        self.graph["nodes"][0]["depends_on"] = ["scout"]

    def test_read_only_scout_feeds_fixer_and_reviewer(self) -> None:
        self.add_scout()
        ordered = graph_module.validate_graph(self.graph)
        node_ids = [node["id"] for node in ordered]
        self.assertLess(node_ids.index("scout"), node_ids.index("fixer"))
        self.assertLess(node_ids.index("fixer"), node_ids.index("reviewer"))
        script = graph_module.compile_script(
            self.graph,
            {"key": "example#1", "title": "Repair", "body": "Target: marker.txt", "proof_command": "test marker"},
            "test-model",
        )
        self.assertLess(script.index('runs.run("scout"'), script.index('runs.run("fixer"'))
        self.assertIn('String(results["scout"].output ??', script)
        self.assertIn("Unrelated dirty or untracked files may predate this ticket", script)
        self.assertIn("do not revert them", script)

    def test_cycle_fails(self) -> None:
        self.graph["nodes"][0]["depends_on"] = ["reviewer"]
        with self.assertRaisesRegex(graph_module.GraphError, "cycle"):
            graph_module.validate_graph(self.graph)

    def test_second_writer_fails(self) -> None:
        self.add_scout()
        self.graph["nodes"][2]["access"] = "write"
        with self.assertRaisesRegex(graph_module.GraphError, "read-only"):
            graph_module.validate_graph(self.graph)

    def test_dangling_node_fails(self) -> None:
        self.add_scout()
        self.graph["nodes"][0]["depends_on"] = []
        with self.assertRaisesRegex(graph_module.GraphError, "feed into reviewer"):
            graph_module.validate_graph(self.graph)

    def test_revision_conflict_does_not_change_draft(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "draft.json"
            original = graph_module.canonical_bytes(self.graph)
            path.write_bytes(original)
            with patch.object(graph_module, "DRAFT_GRAPH", path), patch.dict(os.environ, {"PROJECT_WATCHDOG_STATE_ROOT": root}):
                changed = deepcopy(self.graph)
                changed["nodes"][0]["task"] += " Check the file."
                with self.assertRaises(graph_module.RevisionConflict):
                    graph_module.save_graph(changed, "wrong-revision")
            self.assertEqual(path.read_bytes(), original)

    def test_promotion_uses_both_revisions(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            active = Path(root) / "active.json"
            draft = Path(root) / "draft.json"
            active.write_bytes(graph_module.canonical_bytes(self.graph))
            changed = deepcopy(self.graph)
            changed["nodes"][0]["task"] += " Check the file."
            draft.write_bytes(graph_module.canonical_bytes(changed))
            with patch.object(graph_module, "ACTIVE_GRAPH", active), patch.object(graph_module, "DRAFT_GRAPH", draft), patch.dict(os.environ, {"PROJECT_WATCHDOG_STATE_ROOT": root}):
                with self.assertRaises(graph_module.RevisionConflict):
                    graph_module.promote_graph(graph_module.revision(draft.read_bytes()), "wrong")
                self.assertEqual(json.loads(active.read_text()), self.graph)
                promoted = graph_module.promote_graph(graph_module.revision(draft.read_bytes()), graph_module.revision(active.read_bytes()))
                self.assertEqual(promoted, graph_module.revision(active.read_bytes()))
                self.assertEqual(json.loads(active.read_text()), changed)


if __name__ == "__main__":
    unittest.main()
