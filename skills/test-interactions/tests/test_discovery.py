"""Focused tests for deterministic live-DOM discovery helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery import _build_manifest, _events_to_findings, _manifest_coverage, _manifest_selector_for_qid, _should_assert_visible_after_click, state_fingerprint


class DiscoveryHelperTests(unittest.TestCase):
    def test_state_fingerprint_changes_when_visible_qids_change(self):
        a = {
            "url": "http://example.test",
            "bodyText": "ready",
            "interactives": [{"qid": "a:b", "visible": True, "enabled": True, "ariaExpanded": "", "text": "Open"}],
            "dialogs": [],
        }
        b = {
            "url": "http://example.test",
            "bodyText": "ready dialog",
            "interactives": [
                {"qid": "a:b", "visible": True, "enabled": True, "ariaExpanded": "", "text": "Open"},
                {"qid": "a:dialog:button", "visible": True, "enabled": True, "ariaExpanded": "", "text": "OK"},
            ],
            "dialogs": [{"qid": "a:dialog"}],
        }
        self.assertNotEqual(state_fingerprint(a), state_fingerprint(b))

    def test_generated_manifest_uses_only_data_qid_selectors(self):
        manifest = _build_manifest("http://127.0.0.1:8775/discovery_defects.html", [{
            "title": "fixture",
            "interactives": [
                {"qid": "fixture:ok", "visible": True, "enabled": True, "title": "OK", "qsAction": "OK"},
                {"qid": "", "visible": True, "enabled": True, "title": "", "qsAction": ""},
            ],
        }])
        interactions = [
            interaction
            for surface in manifest["surfaces"]
            for element in surface["elements"]
            for interaction in element["interactions"]
        ]
        self.assertEqual(len(interactions), 1)
        self.assertEqual(interactions[0]["target"], "[data-qid='fixture:ok']")
        self.assertNotIn("nth-child", str(manifest))
        self.assertNotIn(".missing", str(manifest))

    def test_manifest_selector_for_qid_uses_qid_target(self):
        self.assertEqual(_manifest_selector_for_qid("fixture:ok"), "[data-qid='fixture:ok']")

    def test_generated_manifest_does_not_assert_visibility_after_close(self):
        self.assertFalse(_should_assert_visible_after_click({"qid": "fixture:close-dialog", "text": "Close"}))
        self.assertTrue(_should_assert_visible_after_click({"qid": "fixture:open-dialog", "text": "Open"}))

    def test_manifest_coverage_reads_qid_targets_only(self):
        manifest = {
            "surfaces": [{
                "elements": [{
                    "interactions": [
                        {"target": "[data-qid='fixture:covered']"},
                        {"target": ".class-fallback"},
                    ]
                }]
            }]
        }
        self.assertEqual(_manifest_coverage(manifest), {"[data-qid='fixture:covered']"})

    def test_console_and_network_events_become_findings(self):
        findings = _events_to_findings("run-1", [
            {"method": "Runtime.exceptionThrown", "params": {"exceptionDetails": {"text": "Uncaught"}}},
            {"method": "Network.responseReceived", "params": {"response": {"status": 404, "url": "http://example.test/missing"}}},
        ], {"qid": "fixture:throws", "selector": "[data-qid='fixture:throws']", "tag": "button"}, "state-1")
        self.assertEqual([item["finding_kind"] for item in findings], ["console_exception", "network_failure"])


if __name__ == "__main__":
    unittest.main()
