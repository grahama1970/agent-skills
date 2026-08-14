"""Shared test fixtures for /ask."""

from __future__ import annotations

import os

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


@pytest.fixture(autouse=True, scope="session")
def _isolate_browser_window_registry(tmp_path_factory):
    """No test may append to the user's real browser-window ledger.

    The tau_dag suite writes synthetic window ids (901, 902, 1002...) through
    the normal registration path. Those went into ~/.ask/browser-windows.jsonl
    on every run, and the timer-driven reaper would then be handed ids that
    belong to no window Ask ever opened.
    """
    os.environ["ASK_BROWSER_WINDOW_REGISTRY"] = str(
        tmp_path_factory.mktemp("ask-window-registry") / "browser-windows.jsonl"
    )
    yield
    os.environ.pop("ASK_BROWSER_WINDOW_REGISTRY", None)
