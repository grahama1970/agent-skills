#!/usr/bin/env python3
"""Read-only provider availability probe for Ask browser handlers."""

from __future__ import annotations

import json
import os
import re
import signal
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
        limited_pattern=r"claude is at capacity|rate limit(?:ed)?|too many requests|you'?ve reached.*limit",
    ),
    "webkimi": ProviderProbe(
        hosts=("kimi.com",),
        limited_pattern=r"system is currently busy|capacity is busy|too many requests",
    ),
    "webgemini": ProviderProbe(
        hosts=("gemini.google.com",),
        limited_pattern=r"rate limit(?:ed)?|too many requests|temporarily unavailable|you'?ve reached.*limit",
    ),
    "webgrok": ProviderProbe(
        hosts=("grok.com", "x.com"),
        limited_pattern=r"before limit is gone|wait or upgrade|rate limit|too many requests|system is currently busy",
    ),
    "webdeepseek": ProviderProbe(
        hosts=("chat.deepseek.com",),
        limited_pattern=r"server is busy|too many requests|rate limit(?:ed)?|try again later",
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
        report.update(_surf_tab_list_failure_recovery(tab_proc, surf_run=surf_run))
        return report
    tabs, tab_list_error = _parse_tab_list_stdout(tab_proc.stdout)
    if tab_list_error:
        report["status"] = "ERROR"
        report["error"] = tab_list_error
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

    report["degraded_providers"] = [
        name for name, payload in report["providers"].items() if payload.get("probe_degraded")
    ]
    report["provider_probe_recovery_packets"] = {
        name: payload["provider_probe_recovery_packet"]
        for name, payload in report["providers"].items()
        if isinstance(payload.get("provider_probe_recovery_packet"), dict)
    }
    report["status"] = (
        "NEEDS_ATTENTION"
        if any(payload.get("provider_limited") for payload in report["providers"].values())
        else "ERROR"
        if any(payload.get("probe_failed") for payload in report["providers"].values())
        else "AVAILABLE_PREFLIGHT"
    )
    if report["status"] == "ERROR":
        report["error"] = "browser_provider_probe_failed"
    report["finished_at_unix"] = int(time.time())
    return report


def _surf_tab_list_failure_recovery(
    proc: subprocess.CompletedProcess[str],
    *,
    surf_run: Path,
) -> dict[str, Any]:
    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    lower = combined.lower()
    if "stale_socket_no_listener" in lower or "connection refused" in lower:
        return {
            "failure_code": "surf_browser_connection_unavailable",
            "recovery_kind": "surf_stale_socket_no_listener",
            "human_action": (
                "Surf found /tmp/surf.sock, but no native host is accepting connections. "
                "Move the stale socket aside only if no listener owns it, then reload Surf or restart Chrome."
            ),
            "next_command": f"cd {surf_run.parent} && ./run.sh tab.list --json",
            "ticket_instruction": (
                "If tab.list keeps reporting stale_socket_no_listener after stale socket cleanup and Chrome reload, "
                "file a $ticket to $surf with browser-provider-availability.json, /tmp/surf-host.log, "
                "the native host manifest, and `ss -xlpn | grep /tmp/surf.sock` output."
            ),
        }
    if "socket_missing_after_recovery" in lower or "/tmp/surf.sock" in lower:
        return {
            "failure_code": "surf_browser_connection_unavailable",
            "recovery_kind": "surf_extension_socket_missing",
            "human_action": (
                "Open Chrome chrome://extensions, reload the Surf extension, or use Load unpacked "
                "with /home/graham/workspace/experiments/agent-skills/skills/surf/vendor/surf-cli/dist. "
                "If the native host was just installed, restart Chrome so the service worker reconnects."
            ),
            "next_command": f"cd {surf_run.parent} && ./run.sh tab.list --json",
            "ticket_instruction": (
                "If the human reloads or loads the Surf extension and this command still reports "
                "socket_missing_after_recovery, file a $ticket to $surf with browser-provider-availability.json, "
                "the Surf extension id, /tmp/surf-host.log, and the native messaging host manifest."
            ),
        }
    return {
        "failure_code": "surf_tab_list_failed",
        "recovery_kind": "surf_tab_inventory_unavailable",
        "next_command": f"cd {surf_run.parent} && ./run.sh tab.list --json",
        "ticket_instruction": (
            "If tab.list keeps failing without a provider cooldown, file a $ticket to $surf with "
            "browser-provider-availability.json and the Surf stderr."
        ),
    }


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
    has_explicit_tabs = bool(explicit_tab_ids)
    checked = []
    for tab_id_value in _candidate_tab_ids(provider_tabs, explicit_tab_ids, max_tabs):
        checked.append(_check_tab(surf_run=surf_run, tab_id=tab_id_value, pattern=config.limited_pattern))
    payload = {
        "provider": provider,
        "tab_count": len(provider_tabs),
        "explicit_tab_ids": [re.sub(r"\D", "", tab) for tab in explicit_tab_ids if re.sub(r"\D", "", tab)],
        "explicit_tabs_only": has_explicit_tabs,
        "tabs": provider_tabs[:25],
        "checked_tabs": checked,
        "provider_limited": any(item.get("limited") is True for item in checked),
        "probe_degraded": any(item.get("returncode") != 0 for item in checked),
        "probe_failed": _provider_probe_failed(checked),
        "failure_code": _provider_probe_failure_code(checked),
        "read_only": True,
    }
    if payload["probe_degraded"]:
        packet = _provider_probe_recovery_packet(provider=provider, checked=checked, payload=payload)
        payload["provider_probe_recovery_packet"] = packet
        payload["next_command"] = packet["next_command"]
        payload["ticket_command"] = packet["ticket_command"]
        payload["ticket_instruction"] = packet["ticket_instruction"]
    return payload


def _parse_tab_list_stdout(stdout: str) -> tuple[list[Any], str | None]:
    """Read the tab array even when a build banner precedes it.

    The first surf invocation in a fresh checkout prints "Building vendored
    surf-cli at ..." before the JSON, which used to abort the whole probe with
    surf_tab_list_invalid_json (agent-skills#1061).
    """
    text = stdout.strip()
    if not text:
        return [], "surf_tab_list_invalid_json"
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(text)
    except json.JSONDecodeError:
        value = None
    else:
        if text[end:].strip():
            value = None
    if value is None:
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            break
    if value is not None:
        if isinstance(value, dict):
            value = value.get("tabs")
        if isinstance(value, list):
            return value, None
        return [], "surf_tab_list_unexpected_shape"
    return [], "surf_tab_list_invalid_json"


def throttle_match(text: str, pattern: str) -> dict[str, Any]:
    """Locate a provider throttle banner and keep the proof of the decision.

    The decision runs here rather than in the page so it can be tested over
    recorded excerpts, and so a `provider_limited` verdict always carries the
    snippet it was made from (agent-skills#1061).
    """
    match = re.search(pattern, text or "", flags=re.IGNORECASE)
    if not match:
        return {"limited": False, "matched_text": None, "matched_snippet": None}
    start, end = match.span()
    return {
        "limited": True,
        "matched_text": match.group(0),
        "matched_snippet": (text[max(0, start - 90) : end + 60]).strip(),
    }


def _check_tab(*, surf_run: Path, tab_id: str, pattern: str) -> dict[str, Any]:
    js = (
        "const main = document.querySelector('main') || document.querySelector('[role=\"main\"]');"
        "const modal = document.querySelector('[role=\"dialog\"], [role=\"alertdialog\"], [aria-modal=\"true\"]');"
        "const body = document.body && document.body.innerText || '';"
        "const scoped = main && main.innerText ? main.innerText : '';"
        "const modalText = modal && modal.innerText ? modal.innerText : '';"
        "return JSON.stringify({"
        "href: location.href,"
        "title: document.title,"
        "scoped_text: scoped.slice(0, 8000),"
        "modal_text: modalText.slice(0, 4000),"
        "body_text: body.slice(0, 8000),"
        "has_main: !!main"
        "});"
    )
    proc = _run([str(surf_run), "js", js, "--tab-id", tab_id, "--no-activate"], timeout=20)
    payload: dict[str, Any] = {"tab_id": tab_id, **_proc_summary(proc)}
    if proc.returncode != 0:
        return payload
    decoded = _decode_surf_js_stdout(proc.stdout)
    if not isinstance(decoded, dict):
        return payload
    scoped = str(decoded.get("scoped_text") or "")
    modal = str(decoded.get("modal_text") or "")
    body = str(decoded.get("body_text") or "")
    # Sidebar conversation titles live in body text, so a bare page whose
    # history mentions a throttle would otherwise read as throttled. Judge the
    # main region when the app exposes one, but let explicit modal/dialog text
    # and modal-shaped body fallback override clean main text.
    decision_text, match_source = _provider_decision_text(
        scoped=scoped,
        modal=modal,
        body=body,
        has_main=bool(decoded.get("has_main")),
        pattern=pattern,
    )
    verdict = throttle_match(decision_text, pattern)
    payload.update(
        {
            "href": decoded.get("href"),
            "title": decoded.get("title"),
            "match_source": match_source,
            "text_excerpt": decision_text[:600],
            **verdict,
        }
    )
    return payload


def _provider_decision_text(
    *,
    scoped: str,
    modal: str,
    body: str,
    has_main: bool,
    pattern: str,
) -> tuple[str, str]:
    if throttle_match(modal, pattern)["limited"]:
        return modal, "modal"
    if has_main and scoped:
        body_verdict = throttle_match(body, pattern)
        scoped_verdict = throttle_match(scoped, pattern)
        if (
            body_verdict["limited"]
            and not scoped_verdict["limited"]
            and _body_has_modal_throttle_shape(body)
        ):
            return body, "body_modal_like"
        return scoped, "main"
    return body, "body"


def _body_has_modal_throttle_shape(body: str) -> bool:
    lowered = (body or "").lower()
    marker_count = sum(
        marker in lowered
        for marker in (
            "got it",
            "please wait",
            "temporarily limited access",
            "protect your data",
            "upgrade now",
            "wait or upgrade",
            "before limit is gone",
            "system is currently busy",
        )
    )
    return marker_count >= 1


def _provider_probe_failure_code(checked: list[dict[str, Any]]) -> str | None:
    failures = [item for item in checked if item.get("returncode") != 0]
    if not failures:
        return None
    if any(item.get("timed_out") is True for item in failures):
        return "browser_provider_probe_timeout"
    return "browser_provider_probe_failed"


def _provider_probe_failed(checked: list[dict[str, Any]]) -> bool:
    failures = [item for item in checked if item.get("returncode") != 0]
    if not checked or not failures:
        return False
    if all(item.get("timed_out") is True for item in failures):
        return False
    return len(failures) == len(checked)


def _provider_probe_recovery_packet(
    *,
    provider: str,
    checked: list[dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    failure_code = str(payload.get("failure_code") or "browser_provider_probe_degraded")
    checked_tab_ids = [str(item.get("tab_id")) for item in checked if item.get("tab_id")]
    next_command_parts = [
        "cd skills/ask && ./run.sh browser-availability",
        f"--provider {provider}",
        *[f"--tab-id {provider}={tab_id}" for tab_id in checked_tab_ids],
        f"--output /tmp/ask-browser-availability-{provider}.json",
        "--json",
    ]
    repro_command = " ".join(next_command_parts)
    observed = (
        f"{provider} provider availability probe degraded with {failure_code}; "
        f"checked tabs: {', '.join(checked_tab_ids) if checked_tab_ids else 'none'}"
    )
    proof = (
        "Non-mocked browser-availability receipt showing the provider either reads cleanly, "
        "is visibly provider-limited, or emits this recovery packet without blocking healthy providers."
    )
    ticket_command = (
        "skills/ticket/run.sh bug "
        + json.dumps(f"Ask browser availability probe degraded for {provider}")
        + " --target skills/ask"
        + " --observed "
        + json.dumps(observed)
        + " --expected "
        + json.dumps(
            "The provider probe reads reliably or emits a recoverable, lane-local availability uncertainty packet."
        )
        + " --repro "
        + json.dumps(repro_command)
        + " --proof "
        + json.dumps(proof)
        + " --apply"
    )
    return {
        "schema": "ask.browser_provider_probe_recovery_packet.v1",
        "status": "NEEDS_ATTENTION" if payload.get("probe_failed") else "DEGRADED",
        "provider": provider,
        "failure_code": failure_code,
        "provider_limited": bool(payload.get("provider_limited")),
        "probe_failed": bool(payload.get("probe_failed")),
        "probe_degraded": bool(payload.get("probe_degraded")),
        "checked_tab_ids": checked_tab_ids,
        "cooldown_seconds": 600 if payload.get("provider_limited") else 0,
        "auto_retry_allowed": False,
        "auto_retry_blocked_reason": (
            "provider_probe_uncertain_requires_readback"
            if not payload.get("provider_limited")
            else "browser_provider_rate_limit_requires_backoff"
        ),
        "next_command": repro_command,
        "fallback_instruction": (
            "Do not block healthy roundtable or competition participants on this probe. "
            "Rerun only this provider availability probe, or use Ask's browser provider selection "
            "to replace this lane when enough alternatives are available."
        ),
        "ticket_target": "$ask at agent-skills@main",
        "ticket_instruction": (
            "If this provider remains degraded after rerunning next_command, if the provider is needed "
            "for the Ask workflow, or if the packet lacks enough evidence to recover, file a $ticket "
            "to $ask at agent-skills@main with browser-provider-availability.json and the provider entry."
        ),
        "ticket_command": ticket_command,
        "evidence": {
            "checked_tabs": checked,
            "tab_count": payload.get("tab_count"),
            "provider_tabs": payload.get("tabs"),
        },
    }


def _candidate_tab_ids(provider_tabs: list[dict[str, Any]], explicit_tab_ids: list[str], max_tabs: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tab_id in explicit_tab_ids:
        normalized = re.sub(r"\D", "", tab_id)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    if result:
        return result
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
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(
            args=command,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired as exc:
        if proc is not None:
            _terminate_process_group(proc.pid)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_process_group(proc.pid)
                stdout, stderr = proc.communicate()
        else:
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout=stdout or "",
            stderr=(stderr or "") + f"\n[provider-availability] command timed out after {timeout}s; killed process group\n",
        )
    except OSError as exc:
        return subprocess.CompletedProcess(args=command, returncode=127, stdout="", stderr=str(exc))


def _terminate_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _proc_summary(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-1000:],
        "stdout_tail": proc.stdout[-1000:],
        "timed_out": proc.returncode == 124,
    }


if __name__ == "__main__":
    app()
