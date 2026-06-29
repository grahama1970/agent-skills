"""Regression tests for the Arena Team target app."""

import unittest

from app import render_search, search_users


class AppTests(unittest.TestCase):
    def test_search_finds_allowed_user(self) -> None:
        self.assertEqual(search_users("ali"), ["alice"])

    def test_entry_point_renders_search_page(self) -> None:
        html = render_search("bob")
        self.assertIn("<h1>Search</h1>", html)
        self.assertIn("<li>bob</li>", html)


if __name__ == "__main__":
    unittest.main()
