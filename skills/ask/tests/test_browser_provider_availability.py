from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "probe_browser_provider_availability.py"
SPEC = importlib.util.spec_from_file_location("probe_browser_provider_availability", SCRIPT_PATH)
assert SPEC and SPEC.loader
probe_browser_provider_availability = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe_browser_provider_availability
SPEC.loader.exec_module(probe_browser_provider_availability)


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
    assert report["providers"]["webkimi"]["probe_degraded"] is True
    assert report["providers"]["webkimi"]["probe_failed"] is False
    assert report["providers"]["webkimi"]["failure_code"] == "browser_provider_probe_timeout"


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
    assert report["providers"]["webgpt"]["probe_degraded"] is True
    assert report["providers"]["webgpt"]["probe_failed"] is False
    assert report["providers"]["webgpt"]["failure_code"] == "browser_provider_probe_timeout"
    assert report["providers"]["webgpt"]["checked_tabs"][0]["timed_out"] is True


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


def _fake_surf(tmp_path: Path, *, tabs: list[dict[str, object]], tab_text: dict[str, str]) -> Path:
    script = tmp_path / "surf-run.sh"
    cases = []
    for tab_id, text in tab_text.items():
        payload = json.dumps({"href": f"https://example.test/{tab_id}", "title": f"tab {tab_id}", "text_excerpt": text[:600], "text": text})
        cases.append(
            f"""
    {tab_id})
      python3 - <<'PY'
import json
payload = {payload!r}
data = json.loads(payload)
limited = any(s in data["text"].lower() for s in ["too many requests", "temporarily limited access", "system is currently busy"])
data["limited"] = limited
print(json.dumps(json.dumps(data)))
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
