from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "probe_browser_provider_availability.py"
SPEC = importlib.util.spec_from_file_location("probe_browser_provider_availability", SCRIPT_PATH)
assert SPEC and SPEC.loader
probe_browser_provider_availability = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe_browser_provider_availability
SPEC.loader.exec_module(probe_browser_provider_availability)


def test_probe_run_timeout_kills_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "child-survived.txt"
    child_code = (
        "import pathlib, time; "
        "time.sleep(2); "
        f"pathlib.Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(10)"
    )

    result = probe_browser_provider_availability._run(
        [sys.executable, "-c", parent_code],
        timeout=1,
    )

    assert result.returncode == 124
    assert "killed process group" in result.stderr
    time.sleep(2.5)
    assert not marker.exists()


def test_probe_detects_webgpt_too_many_requests_without_submission(tmp_path: Path) -> None:
    surf = _fake_surf(
        tmp_path,
        tabs=[
            {"id": 111, "windowId": 1, "title": "ChatGPT", "url": "https://chatgpt.com/", "active": True},
            {"id": 222, "windowId": 1, "title": "Kimi", "url": "https://www.kimi.com/", "active": True},
        ],
        tab_text={
            "111": "Too many requests\nYou're making requests too quickly. Please wait a few minutes.",
            "222": "Kimi ready",
        },
    )

    report = probe_browser_provider_availability.probe(
        providers=["webgpt", "webkimi"],
        surf_run=surf,
        max_tabs_per_provider=1,
        explicit_tabs={},
    )

    assert report["status"] == "NEEDS_ATTENTION"
    assert report["mocked"] is False
    assert report["live"] is True
    assert report["providers"]["webgpt"]["provider_limited"] is True
    assert report["providers"]["webkimi"]["provider_limited"] is False
    assert "chatgpt" not in (tmp_path / "surf-calls.log").read_text(encoding="utf-8")


def test_probe_uses_only_explicit_provider_tab_when_stale_same_provider_tab_exists(tmp_path: Path) -> None:
    surf = _fake_surf(
        tmp_path,
        tabs=[
            {"id": 837367444, "windowId": 1, "title": "ChatGPT healthy", "url": "https://chatgpt.com/c/current", "active": True},
            {"id": 837367147, "windowId": 2, "title": "ChatGPT stale", "url": "https://chatgpt.com/c/stale", "active": False},
        ],
        tab_text={
            "837367444": "Battle backend review tab ready\nAsk anything",
            "837367147": "Too many requests\nYou're making requests too quickly. Please wait a few minutes.",
        },
    )

    report = probe_browser_provider_availability.probe(
        providers=["webgpt"],
        surf_run=surf,
        max_tabs_per_provider=2,
        explicit_tabs={"webgpt": ["837367444"]},
    )

    webgpt = report["providers"]["webgpt"]
    assert report["status"] == "AVAILABLE_PREFLIGHT"
    assert webgpt["provider_limited"] is False
    assert webgpt["explicit_tabs_only"] is True
    assert webgpt["explicit_tab_ids"] == ["837367444"]
    assert [item["tab_id"] for item in webgpt["checked_tabs"]] == ["837367444"]
    assert "--tab-id 837367147" not in (tmp_path / "surf-calls.log").read_text(encoding="utf-8")


def test_probe_reports_available_when_checked_tabs_have_no_limit_text(tmp_path: Path) -> None:
    surf = _fake_surf(
        tmp_path,
        tabs=[
            {"id": 333, "windowId": 2, "title": "Claude", "url": "https://claude.ai/new", "active": True},
            {"id": 444, "windowId": 2, "title": "Gemini", "url": "https://gemini.google.com/app", "active": True},
        ],
        tab_text={
            "333": "Claude prompt ready",
            "444": "Gemini prompt ready",
        },
    )

    report = probe_browser_provider_availability.probe(
        providers=["webclaude", "webgemini"],
        surf_run=surf,
        max_tabs_per_provider=1,
        explicit_tabs={},
    )

    assert report["status"] == "AVAILABLE_PREFLIGHT"
    assert not report["providers"]["webclaude"]["provider_limited"]
    assert not report["providers"]["webgemini"]["provider_limited"]


def test_probe_does_not_flag_generic_try_again_later_text_as_gemini_limit(tmp_path: Path) -> None:
    surf = _fake_surf(
        tmp_path,
        tabs=[
            {"id": 445, "windowId": 2, "title": "Gemini", "url": "https://gemini.google.com/app", "active": True},
        ],
        tab_text={
            "445": "A project note says the user may try again later after checking local tests.",
        },
    )

    report = probe_browser_provider_availability.probe(
        providers=["webgemini"],
        surf_run=surf,
        max_tabs_per_provider=1,
        explicit_tabs={},
    )

    assert report["status"] == "AVAILABLE_PREFLIGHT"
    assert report["providers"]["webgemini"]["provider_limited"] is False


def test_probe_degrades_but_does_not_block_when_one_provider_tab_reads_cleanly(monkeypatch, tmp_path: Path) -> None:
    surf = tmp_path / "surf-run.sh"
    surf.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    surf.chmod(0o755)

    def fake_run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        if "tab.list" in command:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps(
                    [
                        {"id": 777, "windowId": 1, "title": "Kimi ready", "url": "https://www.kimi.com/", "active": True},
                        {"id": 666, "windowId": 1, "title": "Kimi stale", "url": "https://www.kimi.com/chat/old", "active": False},
                    ]
                ),
                stderr="",
            )
        if "--tab-id" in command and command[command.index("--tab-id") + 1] == "777":
            payload = {
                "href": "https://www.kimi.com/",
                "title": "Kimi ready",
                "text_excerpt": "Kimi prompt ready",
                "limited": False,
            }
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=json.dumps(json.dumps(payload)), stderr="")
        return subprocess.CompletedProcess(args=command, returncode=124, stdout="", stderr="command timed out after 20s")

    monkeypatch.setattr(probe_browser_provider_availability, "_run", fake_run)

    report = probe_browser_provider_availability.probe(
        providers=["webkimi"],
        surf_run=surf,
        max_tabs_per_provider=2,
        explicit_tabs={},
    )

    assert report["status"] == "AVAILABLE_PREFLIGHT"
    assert report["degraded_providers"] == ["webkimi"]
    assert "webkimi" in report["provider_probe_recovery_packets"]
    assert report["providers"]["webkimi"]["probe_degraded"] is True
    assert report["providers"]["webkimi"]["probe_failed"] is False
    assert report["providers"]["webkimi"]["failure_code"] == "browser_provider_probe_timeout"
    packet = report["providers"]["webkimi"]["provider_probe_recovery_packet"]
    assert packet["schema"] == "ask.browser_provider_probe_recovery_packet.v1"
    assert packet["status"] == "DEGRADED"
    assert packet["failure_code"] == "browser_provider_probe_timeout"
    assert packet["checked_tab_ids"] == ["777", "666"]
    assert packet["auto_retry_allowed"] is False
    assert packet["next_command"].startswith("cd skills/ask && ./run.sh browser-availability --provider webkimi")
    assert "--tab-id webkimi=777" in packet["next_command"]
    assert "$ticket to $ask at agent-skills@main" in packet["ticket_instruction"]
    assert "skills/ticket/run.sh bug" in packet["ticket_command"]


def test_probe_degrades_without_blocking_when_all_tab_reads_time_out(monkeypatch, tmp_path: Path) -> None:
    surf = tmp_path / "surf-run.sh"
    surf.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    surf.chmod(0o755)

    def fake_run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        if "tab.list" in command:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps([{"id": 555, "windowId": 1, "title": "ChatGPT", "url": "https://chatgpt.com/", "active": True}]),
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout="",
            stderr="command timed out after 20s",
        )

    monkeypatch.setattr(probe_browser_provider_availability, "_run", fake_run)

    report = probe_browser_provider_availability.probe(
        providers=["webgpt"],
        surf_run=surf,
        max_tabs_per_provider=1,
        explicit_tabs={},
    )

    assert report["status"] == "AVAILABLE_PREFLIGHT"
    assert "error" not in report
    assert report["degraded_providers"] == ["webgpt"]
    assert "webgpt" in report["provider_probe_recovery_packets"]
    assert report["providers"]["webgpt"]["probe_degraded"] is True
    assert report["providers"]["webgpt"]["probe_failed"] is False
    assert report["providers"]["webgpt"]["failure_code"] == "browser_provider_probe_timeout"
    assert report["providers"]["webgpt"]["checked_tabs"][0]["timed_out"] is True
    packet = report["providers"]["webgpt"]["provider_probe_recovery_packet"]
    assert packet["status"] == "DEGRADED"
    assert packet["fallback_instruction"].startswith("Do not block healthy roundtable")
    assert "browser-provider-availability.json" in packet["ticket_instruction"]


def test_probe_reports_error_when_all_tab_reads_fail_non_timeout(monkeypatch, tmp_path: Path) -> None:
    surf = tmp_path / "surf-run.sh"
    surf.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    surf.chmod(0o755)

    def fake_run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        if "tab.list" in command:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps([{"id": 556, "windowId": 1, "title": "ChatGPT", "url": "https://chatgpt.com/", "active": True}]),
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=7,
            stdout="",
            stderr="surf js failed",
        )

    monkeypatch.setattr(probe_browser_provider_availability, "_run", fake_run)

    report = probe_browser_provider_availability.probe(
        providers=["webgpt"],
        surf_run=surf,
        max_tabs_per_provider=1,
        explicit_tabs={},
    )

    assert report["status"] == "ERROR"
    assert report["error"] == "browser_provider_probe_failed"
    assert report["providers"]["webgpt"]["probe_failed"] is True
    assert report["providers"]["webgpt"]["failure_code"] == "browser_provider_probe_failed"


def _fake_surf(
    tmp_path: Path,
    *,
    tabs: list[dict[str, object]],
    tab_text: dict[str, str],
    tab_main_text: dict[str, str] | None = None,
    tab_modal_text: dict[str, str] | None = None,
) -> Path:
    script = tmp_path / "surf-run.sh"
    cases = []
    for tab_id, text in tab_text.items():
        scoped = (tab_main_text or {}).get(tab_id, text)
        modal = (tab_modal_text or {}).get(tab_id, "")
        payload = json.dumps({
            "href": f"https://example.test/{tab_id}",
            "title": f"tab {tab_id}",
            "scoped_text": scoped,
            "modal_text": modal,
            "body_text": text,
            "has_main": True,
        })
        cases.append(
            f"""
    {tab_id})
      python3 - <<'PY'
import json
payload = {payload!r}
print(json.dumps(payload))
PY
      ;;
"""
        )
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(tmp_path / "surf-calls.log")!r}
case "${{1:-}}" in
  tab.list)
    python3 - <<'PY'
import json
print(json.dumps({tabs!r}))
PY
    ;;
  js)
    tab=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --tab-id) tab="${{2:-}}"; shift 2 ;;
        *) shift ;;
      esac
    done
    case "$tab" in
{''.join(cases)}
      *) echo "unknown tab $tab" >&2; exit 7 ;;
    esac
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


# agent-skills#1061: `limited` was computed over the whole body while the report
# showed only the first 600 chars, so a throttle phrase sitting in a sidebar
# conversation title produced an unexplainable NEEDS_ATTENTION.
_WEBGPT_PATTERN = r"too many requests|making requests too quickly|temporarily limited access to your conversations"

_BANNER_FREE_EXCERPT = (
    "ChatGPT\nNew chat\nYesterday\nHandle ChatGPT too many requests cooldown\n"
    "Security Feed Critique Response\nGraham Anderson\n"
)
_BANNER_EXCERPT = (
    "You've sent too many requests in the last hour. Please try again later.\nGot it\n"
)


def test_sidebar_conversation_titles_do_not_prove_a_throttle() -> None:
    # The phrase appears here only as a chat title in the sidebar chrome.
    verdict = probe_browser_provider_availability.throttle_match(_BANNER_FREE_EXCERPT, _WEBGPT_PATTERN)

    assert verdict["limited"] is True  # the raw body text does contain it
    # ...which is exactly why the decision must not run over body text: the
    # scoped main region carries no banner.
    scoped = probe_browser_provider_availability.throttle_match("Ask anything\n", _WEBGPT_PATTERN)
    assert scoped["limited"] is False
    assert scoped["matched_snippet"] is None


def test_real_throttle_banner_is_flagged_with_its_snippet() -> None:
    verdict = probe_browser_provider_availability.throttle_match(_BANNER_EXCERPT, _WEBGPT_PATTERN)

    assert verdict["limited"] is True
    assert verdict["matched_text"].lower() == "too many requests"
    assert "please try again later" in verdict["matched_snippet"].lower()


def test_tab_list_survives_a_vendored_build_banner() -> None:
    contaminated = (
        "Building vendored surf-cli at /x/y...\n"
        "\x1b[33m[INEFFECTIVE_DYNAMIC_IMPORT]\x1b[0m src/native/port-manager.ts is dynamically imported\n"
        '[{"id": 1, "url": "https://chatgpt.com/"}]'
    )

    tabs, error = probe_browser_provider_availability._parse_tab_list_stdout(contaminated)

    assert error is None
    assert tabs == [{"id": 1, "url": "https://chatgpt.com/"}]


def test_tab_list_still_reports_genuinely_unparsable_output() -> None:
    tabs, error = probe_browser_provider_availability._parse_tab_list_stdout("Error: extension not available")

    assert tabs == []
    assert error == "surf_tab_list_invalid_json"


def test_throttle_phrase_in_sidebar_only_does_not_block_the_provider(tmp_path: Path) -> None:
    """The reported #1061 shape: banner words live in the sidebar, not the app."""
    surf = _fake_surf(
        tmp_path,
        tabs=[{"id": 555, "windowId": 3, "title": "ChatGPT", "url": "https://chatgpt.com/", "active": True}],
        tab_text={"555": "New chat\nYesterday\nHandle ChatGPT too many requests cooldown\nGraham Anderson"},
        tab_main_text={"555": "Ask anything"},
    )

    report = probe_browser_provider_availability.probe(
        providers=["webgpt"], surf_run=surf, max_tabs_per_provider=1, explicit_tabs={},
    )

    webgpt = report["providers"]["webgpt"]
    assert webgpt["provider_limited"] is False
    assert report["status"] != "NEEDS_ATTENTION"
    checked = webgpt["checked_tabs"][0]
    assert checked["match_source"] == "main"
    assert checked["matched_snippet"] is None


def test_chatgpt_rate_limit_modal_in_body_overrides_clean_main_region(tmp_path: Path) -> None:
    surf = _fake_surf(
        tmp_path,
        tabs=[{"id": 777, "windowId": 3, "title": "ChatGPT", "url": "https://chatgpt.com/", "active": True}],
        tab_text={
            "777": (
                "What's on the agenda today?\n\nExtra High\n"
                "Too many requests\n"
                "You're making requests too quickly. We've temporarily limited access to your conversations "
                "to protect your data.\n"
                "Please wait a few minutes before trying again.\n"
                "Got it"
            )
        },
        tab_main_text={"777": "What's on the agenda today?\n\nExtra High"},
    )

    report = probe_browser_provider_availability.probe(
        providers=["webgpt"], surf_run=surf, max_tabs_per_provider=1, explicit_tabs={},
    )

    checked = report["providers"]["webgpt"]["checked_tabs"][0]
    assert report["status"] == "NEEDS_ATTENTION"
    assert report["providers"]["webgpt"]["provider_limited"] is True
    assert checked["match_source"] == "body_modal_like"
    assert checked["matched_text"].lower() == "too many requests"
    assert "making requests too quickly" in checked["matched_snippet"].lower()


def test_explicit_dialog_text_overrides_clean_main_region(tmp_path: Path) -> None:
    surf = _fake_surf(
        tmp_path,
        tabs=[{"id": 778, "windowId": 3, "title": "ChatGPT", "url": "https://chatgpt.com/", "active": True}],
        tab_text={"778": "New chat\nAsk anything"},
        tab_main_text={"778": "Ask anything"},
        tab_modal_text={"778": "Too many requests\nPlease wait a few minutes before trying again.\nGot it"},
    )

    report = probe_browser_provider_availability.probe(
        providers=["webgpt"], surf_run=surf, max_tabs_per_provider=1, explicit_tabs={},
    )

    checked = report["providers"]["webgpt"]["checked_tabs"][0]
    assert report["providers"]["webgpt"]["provider_limited"] is True
    assert checked["match_source"] == "modal"
    assert "please wait" in checked["matched_snippet"].lower()


def test_limited_verdict_carries_the_snippet_it_was_made_from(tmp_path: Path) -> None:
    surf = _fake_surf(
        tmp_path,
        tabs=[{"id": 666, "windowId": 3, "title": "ChatGPT", "url": "https://chatgpt.com/", "active": True}],
        tab_text={"666": "sidebar"},
        tab_main_text={"666": "You've sent too many requests in the last hour. Please try again later."},
    )

    report = probe_browser_provider_availability.probe(
        providers=["webgpt"], surf_run=surf, max_tabs_per_provider=1, explicit_tabs={},
    )

    checked = report["providers"]["webgpt"]["checked_tabs"][0]
    assert report["providers"]["webgpt"]["provider_limited"] is True
    assert checked["matched_text"].lower() == "too many requests"
    assert "please try again later" in checked["matched_snippet"].lower()
