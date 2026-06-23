from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "reviews/personaplex-deepgram/personaplex-interactive-chat.html"
SERVER = ROOT / "reviews/personaplex-deepgram/serve_personaplex_interactive_chat.py"

REQUIRED_FLAGS = [
    "real_personaplex_ws",
    "real_turn_gate",
    "real_memory_intent",
    "real_memory_recall",
    "real_evidence_case",
    "real_gpu_personaplex",
    "real_memory_upsert",
    "real_session_compaction",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_html_has_chatwell_static_parity_surface() -> None:
    html = read(HTML)
    assert "Google Sans" in html
    assert "Material Symbols Rounded" in html
    assert "ppx-chat-shell" in html
    assert "ppx-message-shell ${role}" in html
    assert ".ppx-message-shell.user" in html
    assert "ppx-tool-trace" in html
    assert "PersonaPlex Voice Trace Panel" in html
    assert "data-testid=\"personaplex-chat-well\"" in html


def test_html_has_no_pasted_key_ui_or_committed_secret() -> None:
    html = read(HTML).lower()
    forbidden = [
        'id="dgkey"',
        "paste key",
        "paste a deepgram key",
        "placeholder=\"vite_deepgram_api_key",
    ]
    for term in forbidden:
        assert term not in html
    assert "deepgram_api_key is not injected" in html


def test_html_accepts_window_env_and_has_mic_to_speech_final_flow() -> None:
    html = read(HTML)
    assert "window.__ENV__" in html
    assert "navigator.mediaDevices.getUserMedia" in html
    assert "new WebSocket(deepgramUrl, [\"token\", state.deepgramKey])" in html
    assert "data.speech_final" in html
    assert 'type: "speech_final"' in html
    assert 'topic: "personaplex_tool_trace"' in html


def test_all_required_real_flags_are_rendered() -> None:
    html = read(HTML)
    for flag in REQUIRED_FLAGS:
        assert flag in html


def test_server_injects_env_without_printing_secret(monkeypatch) -> None:
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test-secret")
    spec = importlib.util.spec_from_file_location("serve_personaplex_interactive_chat", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module.load_runtime_env()
    assert payload["DEEPGRAM_API_KEY"] == "dg-test-secret"
    js = module.safe_js_env()
    assert "dg-test-secret" in js
    assert js.startswith("{") and js.endswith("}")


def test_server_default_root_points_to_repo_root() -> None:
    spec = importlib.util.spec_from_file_location("serve_personaplex_interactive_chat", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.default_repo_root() == ROOT
