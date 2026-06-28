"""Regression tests for the Battle fixture document reader.

Inputs are the fixture files under ``docs``. Output is a unittest pass/fail
result proving allowed document reads still work after the deterministic patch.
"""

import unittest

from app import read_doc


class AppTests(unittest.TestCase):
    def test_reads_allowed_doc(self) -> None:
        self.assertIn("approved", read_doc("approved.txt"))


if __name__ == "__main__":
    unittest.main()
