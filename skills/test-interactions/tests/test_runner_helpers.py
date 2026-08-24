"""Focused tests for interaction runner helper behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_interactions import _allows_url_guard_escape


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


if __name__ == "__main__":
    unittest.main()
