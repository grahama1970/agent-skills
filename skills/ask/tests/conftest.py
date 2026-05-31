"""Shared test fixtures for /ask."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_selected_lane_preflight_available(monkeypatch):
    """Keep CLI unit tests deterministic; live preflight is covered explicitly."""
    import ask.ask as ask_module

    monkeypatch.setattr(
        ask_module,
        "probe_selected_oracle_lane",
        lambda backend: {
            "lane": str(backend),
            "state": "available",
            "detail": "test preflight available",
            "safe_default": "requires_live_artifact_before_readiness_claim",
        },
    )
