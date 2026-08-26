"""Focused tests for interaction runner helper behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_interactions import _allows_url_guard_escape
from assertions import run_assertions
from cdp_client import CDPClient


class RunnerHelperTests(unittest.TestCase):
    def test_external_href_can_escape_url_guard(self):
        self.assertTrue(
            _allows_url_guard_escape(
                {"allow_external_navigation": True},
                "https://github.com/grahama1970/agent-skills",
                "https://grahama.co",
            )
        )
        self.assertTrue(
            _allows_url_guard_escape(
                {},
                "mailto:graham@grahama.co",
                "https://grahama.co",
            )
        )
        self.assertFalse(
            _allows_url_guard_escape(
                {},
                "/resume",
                "https://grahama.co",
            )
        )

    def test_assert_js_supports_truthy_equals_and_contains(self):
        class FakeCDP:
            def evaluate(self, script):
                return {
                    "truthy-script": True,
                    "equals-script": "ok",
                    "contains-script": "github.com/grahama1970/memory-public",
                }[script]

        results = run_assertions(
            FakeCDP(),
            {
                "assert_js": [
                    {"label": "truthy check", "script": "truthy-script", "truthy": True},
                    {"label": "equals check", "script": "equals-script", "equals": "ok"},
                    {"label": "contains check", "script": "contains-script", "contains": "memory-public"},
                ]
            },
            wait_ms=0,
        )
        self.assertEqual([item["status"] for item in results], ["PASS", "PASS", "PASS"])
        self.assertEqual([item["check"] for item in results], ["truthy check", "equals check", "contains check"])

    def test_click_selector_dispatches_real_pointer_click_for_svg_targets(self):
        client = CDPClient(port=65534)
        dispatched = []

        def fake_evaluate(script):
            self.assertIn("getBoundingClientRect", script)
            return {
                "ok": True,
                "found": True,
                "tag": "a",
                "text": "t'au",
                "x": 120,
                "y": 80,
                "width": 40,
                "height": 40,
            }

        def fake_send(method, params=None):
            dispatched.append((method, params or {}))
            return {}

        client.evaluate = fake_evaluate
        client.send = fake_send

        result = client.click_selector("[data-qid='constellation:jump:tau']")

        self.assertTrue(result["ok"])
        self.assertEqual(
            [params["type"] for method, params in dispatched if method == "Input.dispatchMouseEvent"],
            ["mouseMoved", "mousePressed", "mouseReleased"],
        )
        self.assertEqual(dispatched[1][1]["button"], "left")
        self.assertEqual(dispatched[2][1]["button"], "left")


if __name__ == "__main__":
    unittest.main()
