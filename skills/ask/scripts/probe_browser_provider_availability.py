#!/usr/bin/env python3
"""Read-only provider availability probe for Ask browser handlers."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer


ASK_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SURF_RUN = ASK_DIR.parent / "surf" / "run.sh"


@dataclass(frozen=True)
class ProviderProbe:
    hosts: tuple[str, ...]
    limited_pattern: str


PROVIDERS: dict[str, ProviderProbe] = {
    "webgpt": ProviderProbe(
        hosts=("chatgpt.com",),
        limited_pattern=r"too many requests|making requests too quickly|temporarily limited access to your conversations",
    ),
    "webclaude": ProviderProbe(
        hosts=("claude.ai",),
        limited_pattern=r"rate limit|capacity|try again later|too many requests",
    ),
    "webkimi": ProviderProbe(
        hosts=("kimi.com",),
        limited_pattern=r"system is currently busy|capacity is busy|try again later|too many requests",
    ),
    "webgemini": ProviderProbe(
        hosts=("gemini.google.com",),
        limited_pattern=r"rate limit|try again later|too many requests|temporarily unavailable",
    ),
    "webgrok": ProviderProbe(
        hosts=("grok.com", "x.com"),
        limited_pattern=r"before limit is gone|wait or upgrade|rate limit|too many requests|system is currently busy",
    ),
}


app = typer.Typer(add_completion=False, help=__doc__)


@app.callback(invoke_without_command=True)
def main(
    provider: list[str] | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="Browser provider to probe. Repeatable. Default: webgpt, webclaude, webkimi, webgemini.",
    ),
    surf_run: Path = typer.Option(DEFAULT_SURF_RUN, "--surf-run", help="Path to surf/run.sh."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional JSON report path."),
    max_tabs_per_provider: int = typer.Option(2, "--max-tabs-per-provider", min=1, max=20),
    tab_id: list[str] | None = typer.Option(
        None,
        "--tab-id",
        help="Explicit provider=tab_id override. Repeatable.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print full JSON report."),
) -> None:
    selected = provider or ["webgpt", "webclaude", "webkimi", "webgemini"]
    unknown = [name for name in selected if name not in PROVIDERS]
    if unknown:
        raise typer.BadParameter(f"Unknown provider(s): {', '.join(unknown)}. Known: {', '.join(sorted(PROVIDERS))}")

    explicit_tabs = _parse_tab_overrides(tab_id or [])
    report = probe(
        providers=selected,
        surf_run=surf_run,
        max_tabs_per_provider=max_tabs_per_provider,
        explicit_tabs=explicit_tabs,
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["output"] = str(output)
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        limited = [name for name, payload in report["providers"].items() if payload.get("provider_limited")]
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "limited": limited,
                    "output": report.get("output"),
                    "tab_counts": {
                        name: payload.get("tab_count") for name, payload in report["providers"].items()
                    },
                },
                sort_keys=True,
            )
        )
    raise typer.Exit(1 if report["status"] == "ERROR" else 0)


def probe(
    *,
    providers: list[str],
    surf_run: Path,
    max_tabs_per_provider: int,
    explicit_tabs: dict[str, list[str]],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "ask.browser_provider_availability.v1",
        "mocked": False,
        "live": True,
        "started_at_unix": int(time.time()),
        "surf_run": str(surf_run),
        "providers": {},
    }
    tab_proc = _run([str(surf_run), "tab.list", "--json"], timeout=45)
    report["tab_list"] = _proc_summary(tab_proc)
    if tab_proc.returncode != 0:
        report["status"] = "ERROR"
        report["error"] = "surf_tab_list_failed"
        return report
    try:
        tabs = json.loads(tab_proc.stdout)
    except json.JSONDecodeError as exc:
        report["status"] = "ERROR"
        report["error"] = f"surf_tab_list_invalid_json: {exc}"
        return report
    if not isinstance(tabs, list):
        report["status"] = "ERROR"
        report["error"] = "surf_tab_list_unexpected_shape"
        return report

    for provider in providers:
        report["providers"][provider] = _probe_provider(
            provider=provider,
            config=PROVIDERS[provider],
            tabs=tabs,
            surf_run=surf_run,
            max_tabs=max_tabs_per_provider,
            explicit_tab_ids=explicit_tabs.get(provider, []),
        )

    report["status"] = (
        "NEEDS_ATTENTION"
        if any(payload.get("provider_limited") for payload in report["providers"].values())
        else "AVAILABLE_PREFLIGHT"
    )
    report["finished_at_unix"] = int(time.time())
    return report


def _probe_provider(
    *,
    provider: str,
    config: ProviderProbe,
    tabs: list[Any],
    surf_run: Path,
    max_tabs: int,
    explicit_tab_ids: list[str],
) -> dict[str, Any]:
    provider_tabs = [_tab_summary(tab) for tab in tabs if _tab_matches(tab, config.hosts)]
    checked = []
    for tab_id_value in _candidate_tab_ids(provider_tabs, explicit_tab_ids, max_tabs):
        checked.append(_check_tab(surf_run=surf_run, tab_id=tab_id_value, pattern=config.limited_pattern))
    return {
        "provider": provider,
        "tab_count": len(provider_tabs),
        "tabs": provider_tabs[:25],
        "checked_tabs": checked,
        "provider_limited": any(item.get("limited") is True for item in checked),
        "read_only": True,
    }


def _check_tab(*, surf_run: Path, tab_id: str, pattern: str) -> dict[str, Any]:
    js = (
        "const text = document.body && document.body.innerText || '';"
        "return JSON.stringify({"
        "href: location.href,"
        "title: document.title,"
        "text_excerpt: text.slice(0, 600),"
        f"limited: /{pattern}/i.test(text)"
        "});"
    )
    proc = _run([str(surf_run), "js", js, "--tab-id", tab_id, "--no-activate"], timeout=45)
    payload: dict[str, Any] = {"tab_id": tab_id, **_proc_summary(proc)}
    if proc.returncode == 0:
        decoded = _decode_surf_js_stdout(proc.stdout)
        if isinstance(decoded, dict):
            payload.update(decoded)
    return payload


def _candidate_tab_ids(provider_tabs: list[dict[str, Any]], explicit_tab_ids: list[str], max_tabs: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tab_id in explicit_tab_ids:
        normalized = re.sub(r"\D", "", tab_id)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    sorted_tabs = sorted(provider_tabs, key=lambda tab: (not bool(tab.get("active")), -int(tab.get("id") or 0)))
    for tab in sorted_tabs:
        tab_id = str(tab.get("id") or "")
        if tab_id and tab_id not in seen:
            seen.add(tab_id)
            result.append(tab_id)
        if len(result) >= max_tabs:
            break
    return result


def _tab_matches(tab: Any, hosts: tuple[str, ...]) -> bool:
    if not isinstance(tab, dict):
        return False
    url = str(tab.get("url") or "")
    return any(host in url for host in hosts)


def _tab_summary(tab: Any) -> dict[str, Any]:
    if not isinstance(tab, dict):
        return {}
    return {
        "id": tab.get("id"),
        "windowId": tab.get("windowId"),
        "title": tab.get("title"),
        "url": tab.get("url"),
        "active": tab.get("active"),
    }


def _parse_tab_overrides(values: list[str]) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for value in values:
        if "=" not in value:
            raise typer.BadParameter(f"--tab-id must be provider=tab_id, got {value!r}")
        provider, tab = value.split("=", 1)
        provider = provider.strip()
        if provider not in PROVIDERS:
            raise typer.BadParameter(f"Unknown --tab-id provider {provider!r}")
        parsed.setdefault(provider, []).append(tab.strip())
    return parsed


def _decode_surf_js_stdout(stdout: str) -> Any:
    text = stdout.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {"raw_stdout": text[-1000:]}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"raw_stdout": value[-1000:]}
    return value


def _run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout)


def _proc_summary(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-1000:],
        "stdout_tail": proc.stdout[-1000:],
    }


if __name__ == "__main__":
    app()
