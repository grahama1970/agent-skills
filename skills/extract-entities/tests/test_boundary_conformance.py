"""Conformance test for the skill's token-boundary guard.

The guard exists twice -- here and in
memory/src/graph_memory/entity_helpers.py::_is_fragment_of_larger_token -- with
nothing structural keeping them in sync. Both repos run their implementation
against the SAME canonical fixture (kept in the memory repo, versioned and
checksum-pinned); drift between the copies fails tests on whichever side
changed instead of silently diverging.

Enforcement per the 2026-08-12 external review: a missing or version-drifted
fixture is a HARD FAILURE, not a skip -- "a visible skip is diagnostic, but it
is not enforcement." Green CI must mean cross-repository conformance actually
ran. For genuinely isolated developer environments only, set
EXTRACT_ENTITIES_CONFORMANCE_OPTIONAL=1 to downgrade absence to a skip;
checksum mismatch still fails because that means the copies are being tested
against different contracts.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

FIXTURE = Path.home() / "workspace/experiments/memory/tests/fixtures/entity_boundary_conformance.json"
PINNED_VERSION = 1
PINNED_SHA256 = "46130040bf8c4ee62add64304aab96985e1d366cf814ef9029ede7c124c1c004"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entity_match_policy import is_fragment_of_larger_token  # noqa: E402


def _load_fixture() -> dict:
    if not FIXTURE.exists():
        if os.environ.get("EXTRACT_ENTITIES_CONFORMANCE_OPTIONAL") == "1":
            pytest.skip(f"canonical fixture absent at {FIXTURE} (explicitly allowed by env)")
        pytest.fail(
            f"canonical conformance fixture missing at {FIXTURE}; conformance did not run. "
            "This is enforcement, not diagnostics -- clone the memory repo or set "
            "EXTRACT_ENTITIES_CONFORMANCE_OPTIONAL=1 only for isolated dev environments."
        )
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    data = json.loads(FIXTURE.read_text())
    if data.get("version") != PINNED_VERSION or digest != PINNED_SHA256:
        pytest.fail(
            f"conformance fixture drift: version={data.get('version')} sha256={digest[:16]}..., "
            f"pinned version={PINNED_VERSION} sha256={PINNED_SHA256[:16]}.... The two guard "
            "copies are being tested against different contracts; update BOTH repos' pins "
            "together with the fixture change."
        )
    return data


def test_skill_guard_matches_conformance_fixture() -> None:
    cases = _load_fixture()["cases"]
    failures = []
    for case in cases:
        text, token = case["text"], case["token"]
        start = text.index(token)
        got = is_fragment_of_larger_token(text, start, start + len(token))
        if got != case["expect_fragment"]:
            failures.append(f"{case['name']}: expected {case['expect_fragment']}, got {got}")
    assert not failures, "; ".join(failures)
