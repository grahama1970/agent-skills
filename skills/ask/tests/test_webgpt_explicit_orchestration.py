"""Explicit $ask webgpt must not auto-draft implementation DAGs."""

from __future__ import annotations

import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ask.model_aliases import resolve_model_alias_route


def test_webgpt_alias_sets_backend():
    route = resolve_model_alias_route(
        ["webgpt", "product design only: collab skill?"],
        scillm_base_url="http://localhost:4001",
        scillm_api_key="sk-dev-proxy-123",
    )
    assert route is not None
    assert route.oracle_backend == "webgpt"
