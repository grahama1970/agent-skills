"""Conformance test for the skill's token-boundary guard.

The guard exists twice -- here and in
memory/src/graph_memory/entity_helpers.py::_is_fragment_of_larger_token -- with
nothing structural keeping them in sync. Both repos run their implementation
against the SAME canonical fixture (kept in the memory repo); drift between
the copies fails tests on whichever side changed instead of silently
diverging. If the fixture is absent on this machine the test skips loudly
rather than passing vacuously.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

FIXTURE = Path.home() / "workspace/experiments/memory/tests/fixtures/entity_boundary_conformance.json"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entity_match_policy import is_fragment_of_larger_token  # noqa: E402


@pytest.mark.skipif(not FIXTURE.exists(), reason=f"canonical fixture not present at {FIXTURE}")
def test_skill_guard_matches_conformance_fixture() -> None:
    cases = json.loads(FIXTURE.read_text())["cases"]
    failures = []
    for case in cases:
        text, token = case["text"], case["token"]
        start = text.index(token)
        got = is_fragment_of_larger_token(text, start, start + len(token))
        if got != case["expect_fragment"]:
            failures.append(f"{case['name']}: expected {case['expect_fragment']}, got {got}")
    assert not failures, "; ".join(failures)
