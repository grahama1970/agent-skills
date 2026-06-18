from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def _load_kde_spaces():
    path = Path(__file__).resolve().parents[1] / "scripts" / "kde_spaces.py"
    spec = importlib.util.spec_from_file_location("kde_spaces", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["kde_spaces"] = module
    spec.loader.exec_module(module)
    return module


def test_annotate_tabs_uses_helper_when_available(monkeypatch) -> None:
    kde_spaces = _load_kde_spaces()

    def fake_request(path: str, *, payload: Any | None = None, timeout: float = 1.5) -> dict[str, Any] | None:
        assert path == "/annotate-tabs"
        assert payload == [{"id": 123, "windowId": 9}]
        return {
            "schema": "surf.tab_list_with_kde.v1",
            "tabs": [
                {
                    "id": 123,
                    "windowId": 9,
                    "kde": {
                        "desktop_index": 4,
                        "x11_window_id": "0xabc",
                        "window_match_confidence": "title",
                    },
                }
            ],
            "kde": {"schema": "surf.kde_spaces.v1", "source": "helper"},
        }

    monkeypatch.setattr(kde_spaces, "_request_helper", fake_request)

    result = kde_spaces.annotate_tabs([{"id": 123, "windowId": 9}], use_helper=True)

    assert result["source"] == "helper"
    assert result["kde"]["helper_available"] is True
    assert result["tabs"][0]["kde"]["desktop_index"] == 4


def test_annotate_tabs_local_maps_active_chrome_window(monkeypatch) -> None:
    kde_spaces = _load_kde_spaces()

    monkeypatch.setattr(
        kde_spaces,
        "kde_inventory",
        lambda *, use_helper=False: {
            "schema": "surf.kde_spaces.v1",
            "source": "local",
            "windows": [
                {
                    "x11_window_id": "0x123",
                    "desktop_index": 2,
                    "wm_class": "google-chrome.Google-chrome",
                    "title": "ChatGPT - Demo - Google Chrome",
                }
            ],
            "issues": [],
        },
    )

    result = kde_spaces.annotate_tabs(
        [
            {"id": 123, "windowId": 9, "active": True, "title": "ChatGPT - Demo"},
            {"id": 124, "windowId": 9, "active": False, "title": "Other"},
        ],
        use_helper=False,
    )

    assert result["source"] == "local"
    assert result["tabs"][0]["kde"]["desktop_index"] == 2
    assert result["tabs"][1]["kde"]["x11_window_id"] == "0x123"
