"""Read-only browser capture of no-API / broken-API sources via surf.

When a source has no working API (SAM.gov API 404s; hiddenjobs.dev has no
public API), the mandatory-source and API-website-fallback rules require a
read-only website capture. This module drives surf against the authenticated
Chrome to capture those sources into evidence files the pipeline consumes.

Inputs: surf run.sh path, output directory. Outputs: evidence JSON files +
a capture receipt. Failure modes: surf/Chrome unavailable -> receipt records
the failure honestly and the evidence file is absent (the run's enforcement
gate then reports the source as unsatisfied rather than silently passing).

Self-healing: if no browser is reachable, launches a headed Chrome on a
virtual display (Xvfb) — headed to avoid bot detection, virtual so no window pops.
"""

from __future__ import annotations

import contextlib
import json
import multiprocessing
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from loguru import logger

from .util import utc_now

SURF_RUN_DEFAULT = Path(__file__).resolve().parents[3] / "surf" / "run.sh"

_SAM_URL = (
    "https://sam.gov/search/?index=opp&sort=-modifiedDate&pageSize=25&page=1"
    "&sfm%5Bstatus%5D%5Bis_active%5D=true&sfm%5BsimpleSearch%5D%5BkeywordRadio%5D=ALL"
    "&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B0%5D%5Bvalue%5D=artificial%20intelligence"
)

# Only real opportunity links (/opp/<id>/view); org/filter links are excluded so
# the capture is clean. Dedup by opp id. Returns {count, rows} so the poll below
# can tell "not loaded yet" (count 0) from "genuinely empty".
_SAM_EXTRACT_JS = (
    "(function(){"
    "var out=[],seen={};"
    "var links=[].slice.call(document.querySelectorAll(\"a[href*='/opp/']\"));"
    "for (var i=0;i<links.length;i++){"
    "var h=links[i].href||'';"
    "var m=h.match(/\\/opp\\/([0-9a-f]+)\\//);"
    "var t=(links[i].innerText||'').trim();"
    "if (m && t.length>3 && !seen[m[1]]){ seen[m[1]]=1;"
    " out.push({title:t.slice(0,140), url:h, opp_id:m[1]}); }"
    "}"
    "return JSON.stringify({count:out.length, rows:out.slice(0,40)});"
    "})()"
)

# Cheap readiness probe: how many opportunity rows are currently rendered.
_SAM_READY_JS = "(function(){return document.querySelectorAll(\"a[href*='/opp/']\").length;})()"

_MEETUP_CATEGORY_URLS = [
    ("546", "Technology", "https://www.meetup.com/find/?source=GROUPS&distance=anyDistance&categoryId=546"),
    ("405", "Career & Business", "https://www.meetup.com/find/?source=GROUPS&distance=anyDistance&categoryId=405"),
]
_MEETUP_SEED_GROUP_URLS = [
    "https://www.meetup.com/bit-haven-hackerspace/",
    "https://www.meetup.com/infosec-716/",
]
_MEETUP_PAGE_EXTRACT_JS = (
    "(function(){"
    "var links=[].slice.call(document.querySelectorAll('a[href]')).map(function(a){return a.href;});"
    "var seen={},uniq=[];"
    "for(var i=0;i<links.length;i++){var h=links[i];if(h&&h.indexOf('meetup.com')>=0&&!seen[h]){seen[h]=1;uniq.push(h);}}"
    "return JSON.stringify({url:location.href,title:document.title,"
    "text:(document.body.innerText||'').slice(0,18000),links:uniq.slice(0,140)});"
    "})()"
)

# Meetup exists in this sweep to find PEOPLE, not calendar entries: whoever has
# signed up to a Buffalo-area event is a named, locatable contact. The capture
# used to stop at the group page and read marketing copy, so it produced zero
# contacts. An event page in the human's own authenticated session lists
# attendees by name with profile links; reading that page is the same read-only
# act as reading the group page it links from. No RSVP, no join, no message.
_MEETUP_ATTENDEE_EXTRACT_JS = (
    "(function(){"
    "var out=[],seen={};"
    "var anchors=[].slice.call(document.querySelectorAll('a[href*=\"/members/\"]'));"
    "for(var i=0;i<anchors.length;i++){"
    "var a=anchors[i];"
    "var raw=(a.innerText||'').trim();"
    "if(!raw) continue;"
    "var lines=raw.split(String.fromCharCode(10)).map(function(x){return x.trim();}).filter(Boolean);"
    "var role='', name='';"
    "for(var j=0;j<lines.length;j++){"
    "if(/^(Host|Co-?Host|Organizer|Super Organizer|Member|Assistant Organizer|Event Organizer)$/i.test(lines[j])){"
    "if(!role) role=lines[j];"
    "} else if(!name){ name=lines[j]; }"
    "}"
    "if(!name || name.length>80) continue;"
    "var key=name.toLowerCase();"
    "if(seen[key]) continue; seen[key]=1;"
    "out.push({name:name, role:role||'attendee', profile_url:a.href});"
    "}"
    "var t=document.body.innerText||'';"
    "var countMatch=t.match(/([0-9,]+)\\s+(?:attendees|going|members)/i);"
    "return JSON.stringify({url:location.href, title:document.title,"
    "attendee_count_text: countMatch?countMatch[0]:null,"
    "attendees: out.slice(0,60)});"
    "})()"
)

_HIDDENJOBS_URL = "https://hiddenjobs.dev/"
_INDEED_AI_BUFFALO_URL = "https://www.indeed.com/jobs?q=AI&l=Buffalo%2C%20NY"
_G2I_SLACK_TEAM_ID = "T02NLNJ2D"
_G2I_SLACK_JOB_ALERTS_CHANNEL_ID = "C01H317TX7X"
_G2I_SLACK_JOB_ALERTS_URL = f"https://app.slack.com/client/{_G2I_SLACK_TEAM_ID}/{_G2I_SLACK_JOB_ALERTS_CHANNEL_ID}"

_HIDDENJOBS_EXTRACT_JS = (
    "(function(){"
    "var out=[],seen={};"
    "var anchors=[].slice.call(document.querySelectorAll('a[href]'));"
    "for(var i=0;i<anchors.length;i++){"
    "var a=anchors[i], h=a.href||'', t=(a.innerText||'').trim();"
    "if(!h || seen[h]) continue;"
    "var card=a.closest('article,li,section,div');"
    "var text=((card&&card.innerText)||t||'').replace(/\\s+/g,' ').trim();"
    "if(text.length<20) continue;"
    "if(!/job|apply|engineer|developer|data|ai|software|remote/i.test(text)) continue;"
    "seen[h]=1; out.push({title:t.slice(0,140)||text.slice(0,140), url:h, text:text.slice(0,1400)});"
    "}"
    "return JSON.stringify({url:location.href,title:document.title,"
    "text:(document.body.innerText||'').slice(0,12000),records:out.slice(0,80)});"
    "})()"
)

_INDEED_EXTRACT_JS = (
    "(function(){"
    "var data=window._initialData||{};"
    "var results=((((data.hostQueryExecutionResult||{}).data||{}).jobData||{}).results)||[];"
    "var out=[];"
    "for(var i=0;i<results.length;i++){"
    "var job=results[i]&&results[i].job||{};"
    "if(!job.title) continue;"
    "out.push({title:job.title,organization:job.sourceEmployerName||((job.source||{}).name)||'',"
    "location:(((job.location||{}).formatted||{}).long)||((job.location||{}).fullAddress)||'',"
    "url:job.url||'',job_key:job.key||'',date_on_indeed:job.dateOnIndeed||null,"
    "text:(((job.description||{}).html)||'').replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ').trim().slice(0,1800)});"
    "}"
    "if(!out.length){"
    "var cards=[].slice.call(document.querySelectorAll('[data-jk], a[href*=\"/rc/clk\"], a[href*=\"/viewjob\"]'));"
    "var seen={};"
    "for(var j=0;j<cards.length;j++){"
    "var el=cards[j], h=el.href||'', key=el.getAttribute('data-jk')||h;"
    "if(!key||seen[key]) continue; seen[key]=1;"
    "var card=el.closest('li,div'); var txt=((card&&card.innerText)||el.innerText||'').replace(/\\s+/g,' ').trim();"
    "if(txt.length>20) out.push({title:txt.slice(0,140),organization:'',location:'',url:h,text:txt.slice(0,1800)});"
    "}"
    "}"
    "return JSON.stringify({url:location.href,title:document.title,"
    "text:(document.body.innerText||'').slice(0,12000),records:out.slice(0,80)});"
    "})()"
)

_G2I_SLACK_EXTRACT_JS = (
    "(function(){"
    "return JSON.stringify({url:location.href,title:document.title,"
    "text:(document.body.innerText||'').slice(0,24000)});"
    "})()"
)


class BrowserCaptureError(ValueError):
    """Stable browser-capture error."""


_BROWSER_CONTROL_EVENTS: list[dict[str, Any]] = []
_PENDING_TAB_CLOSE_FAILURES: dict[str, dict[str, Any]] = {}


def reset_browser_control_events() -> None:
    _BROWSER_CONTROL_EVENTS.clear()
    _PENDING_TAB_CLOSE_FAILURES.clear()


def browser_control_summary(surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    flush_browser_control_cleanup(surf_run)
    counts: dict[str, int] = {}
    for event in _BROWSER_CONTROL_EVENTS:
        kind = str(event.get("kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return {
        "status": "DEGRADED" if _BROWSER_CONTROL_EVENTS else "OK",
        "events": len(_BROWSER_CONTROL_EVENTS),
        "counts": counts,
        "recent": _BROWSER_CONTROL_EVENTS[-10:],
    }


def _record_browser_control_event(
    *,
    kind: str,
    operation: str,
    error: BaseException,
    seconds: str | None = None,
    timeout: int | None = None,
    tab_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    event: dict[str, Any] = {
        "kind": kind,
        "operation": operation,
        "error_type": type(error).__name__,
        "error": str(error)[:500],
        "observed_at": utc_now(),
    }
    if seconds is not None:
        event["seconds"] = seconds
    if timeout is not None:
        event["timeout"] = timeout
    if tab_id is not None:
        event["tab_id"] = tab_id
    if details:
        event["details"] = details
    _BROWSER_CONTROL_EVENTS.append(event)


def _nav_js(url: str) -> str:
    """Fire-and-forget navigation. Assigning location.href synchronously makes
    the surf js call block until load (LinkedIn job pages exceed 20s and timed
    out 3 of 4 insight probes on 2026-08-13); defer it so the call returns now
    and the caller's explicit wait covers the load."""
    return (
        "(function(){setTimeout(function(){location.href="
        + json.dumps(url)
        + ";},0); return 'NAV';})()"
    )


_TAB_CLOSE_TIMEOUT_SECONDS = 8
_TAB_CLOSE_NO_LOCK_TIMEOUT_SECONDS = 8
_TAB_CLOSE_LOCK_TIMEOUT_SECONDS = 5
_TAB_CLOSE_ATTEMPTS = 1
_TAB_CLOSE_SWEEP_TIMEOUT_SECONDS = 30
_TAB_CLOSE_INDIVIDUAL_SWEEP_TIMEOUT_SECONDS = 12
_TAB_CLOSE_CIRCUIT_BREAK_THRESHOLD = 3


def _surf_pause(surf_run: Path, seconds: str, timeout: int = 30) -> None:
    """Best-effort pacing sleep that does not consume a surf lease.

    On 2026-08-13 a `surf wait 1` timed out under lease contention (many
    captures now run back-to-back) and aborted the whole top-applicant capture.
    Live promoted receipts on 2026-08-14 showed the fallback itself had become
    the common case. Use local sleep directly; TimeoutError is preserved so
    outer wall-clock capture guards can still interrupt a wedged capture.
    """
    del surf_run, timeout
    time.sleep(min(float(seconds or 1), 10.0))


def _surf(surf_run: Path, *args: str, timeout: int = 90) -> str:
    proc = subprocess.run([str(surf_run), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise BrowserCaptureError(f"surf {args[0]} failed: {proc.stderr[-200:]}")
    return proc.stdout.strip()


def _surf_js(surf_run: Path, tab_id: str, script: str, *, timeout: int = 90) -> str:
    return _surf(surf_run, "js", script, "--tab-id", tab_id, timeout=timeout)


def _surf_json_value(raw: str, default: Any) -> Any:
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, str):
            decoded = json.loads(decoded)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return default if decoded is None else decoded


def _current_tab_ids(surf_run: Path) -> set[str] | None:
    try:
        raw = _surf(surf_run, "tab.list", "--json", timeout=20)
        tabs = json.loads(raw)
    except (BrowserCaptureError, ValueError, subprocess.TimeoutExpired) as exc:
        logger.warning("could not list tabs during cleanup sweep: {}", exc)
        return None
    ids: set[str] = set()
    if isinstance(tabs, list):
        for tab in tabs:
            if isinstance(tab, dict) and tab.get("id") is not None:
                ids.add(str(tab["id"]))
    return ids


def flush_browser_control_cleanup(surf_run: Path = SURF_RUN_DEFAULT) -> None:
    """Sweep tabs whose individual close call timed out before reporting status.

    Surf occasionally times out waiting for the close response even though the
    browser later closes the tab. The run should degrade only for tabs that are
    still present after a final sweep, not for stale timeout receipts.
    """

    if not _PENDING_TAB_CLOSE_FAILURES:
        return

    open_ids = _current_tab_ids(surf_run)
    if open_ids is not None:
        for tab_id in list(_PENDING_TAB_CLOSE_FAILURES):
            if tab_id not in open_ids:
                _PENDING_TAB_CLOSE_FAILURES.pop(tab_id, None)

    remaining = list(_PENDING_TAB_CLOSE_FAILURES)
    sweep_error: BrowserCaptureError | subprocess.TimeoutExpired | None = None
    if remaining:
        try:
            _surf(
                surf_run,
                "tab.close",
                "--ids",
                ",".join(remaining),
                "--no-lock",
                timeout=max(_TAB_CLOSE_SWEEP_TIMEOUT_SECONDS, len(remaining) * 4),
            )
            for tab_id in remaining:
                _PENDING_TAB_CLOSE_FAILURES.pop(tab_id, None)
        except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
            sweep_error = exc
            open_ids = _current_tab_ids(surf_run)
            if open_ids is not None:
                for tab_id in list(_PENDING_TAB_CLOSE_FAILURES):
                    if tab_id not in open_ids:
                        _PENDING_TAB_CLOSE_FAILURES.pop(tab_id, None)

    if _PENDING_TAB_CLOSE_FAILURES:
        for tab_id in list(_PENDING_TAB_CLOSE_FAILURES):
            try:
                _surf(
                    surf_run,
                    "tab.close",
                    tab_id,
                    "--no-lock",
                    timeout=_TAB_CLOSE_INDIVIDUAL_SWEEP_TIMEOUT_SECONDS,
                )
                _PENDING_TAB_CLOSE_FAILURES.pop(tab_id, None)
            except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
                sweep_error = exc
        if _PENDING_TAB_CLOSE_FAILURES:
            open_ids = _current_tab_ids(surf_run)
            if open_ids is not None:
                for tab_id in list(_PENDING_TAB_CLOSE_FAILURES):
                    if tab_id not in open_ids:
                        _PENDING_TAB_CLOSE_FAILURES.pop(tab_id, None)

    if sweep_error is None:
        return

    for tab_id, pending in list(_PENDING_TAB_CLOSE_FAILURES.items()):
        attempted_modes = list(pending.get("attempted_modes") or [])
        attempted_modes.append("final_batch_sweep")
        attempted_modes.append("final_individual_sweep")
        _record_browser_control_event(
            kind="tab_close_failed",
            operation="tab.close",
            tab_id=tab_id,
            timeout=int(pending.get("timeout") or 0)
            + _TAB_CLOSE_SWEEP_TIMEOUT_SECONDS
            + _TAB_CLOSE_INDIVIDUAL_SWEEP_TIMEOUT_SECONDS,
            details={"attempted_modes": attempted_modes, "label": pending.get("label")},
            error=sweep_error,
        )
        _PENDING_TAB_CLOSE_FAILURES.pop(tab_id, None)


def _close_tab(surf_run: Path, tab_id: str, label: str) -> None:
    if len(_PENDING_TAB_CLOSE_FAILURES) >= _TAB_CLOSE_CIRCUIT_BREAK_THRESHOLD:
        _PENDING_TAB_CLOSE_FAILURES[tab_id] = {
            "attempted_modes": ["deferred_by_close_circuit"],
            "error": BrowserCaptureError(
                f"tab close circuit open after {_TAB_CLOSE_CIRCUIT_BREAK_THRESHOLD} pending failures"
            ),
            "label": label,
            "timeout": 0,
        }
        return
    last_error: BrowserCaptureError | subprocess.TimeoutExpired | None = None
    attempts = [
        (
            "locked",
            ("tab.close", tab_id, "--lock-timeout", str(_TAB_CLOSE_LOCK_TIMEOUT_SECONDS)),
            _TAB_CLOSE_TIMEOUT_SECONDS,
        ),
        (
            "no_lock_cleanup",
            ("tab.close", tab_id, "--no-lock"),
            _TAB_CLOSE_NO_LOCK_TIMEOUT_SECONDS,
        ),
    ]
    attempted_modes: list[str] = []
    for mode, args, timeout in attempts:
        attempted_modes.append(mode)
        try:
            _surf(surf_run, *args, timeout=timeout)
            return
        except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            continue
    if last_error is None:
        return
    logger.warning("could not close {} tab {} after {} attempts: {}", label, tab_id, len(attempts), last_error)
    _PENDING_TAB_CLOSE_FAILURES[tab_id] = {
        "attempted_modes": attempted_modes,
        "error": last_error,
        "label": label,
        "timeout": _TAB_CLOSE_TIMEOUT_SECONDS + _TAB_CLOSE_NO_LOCK_TIMEOUT_SECONDS,
    }


def _write_surf_diagnostic_bundle(
    out_dir: Path,
    *,
    source: str,
    surf_run: Path,
    tab_id: str | None,
    reason: str,
    url: str | None = None,
    error: BaseException | None = None,
) -> dict[str, Any]:
    """Preserve live Surf evidence when a source capture degrades.

    This is deliberately best-effort and fail-closed: diagnostics may fail, but
    diagnostic failure must not hide the original source failure or mutate the
    page beyond a screenshot/read-only JS probe.
    """

    safe_source = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in source)
    bundle_dir = out_dir / "surf-diagnostics" / safe_source
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema": "monitor_opportunities.surf_diagnostic_bundle.v1",
        "source": source,
        "observed_at": utc_now(),
        "reason": reason,
        "tab_id": tab_id,
        "url": url,
        "external_effects": False,
        "artifacts": {},
        "errors": [],
    }
    if error is not None:
        manifest["error"] = {
            "type": type(error).__name__,
            "message": str(error)[:1000],
        }

    try:
        tab_list = _surf(surf_run, "tab.list", "--json", timeout=25)
        tab_list_path = bundle_dir / "tab-list.json"
        tab_list_path.write_text(tab_list + "\n", encoding="utf-8")
        manifest["artifacts"]["tab_list"] = str(tab_list_path)
    except (BrowserCaptureError, subprocess.TimeoutExpired, OSError) as exc:
        manifest["errors"].append({"stage": "tab.list", "type": type(exc).__name__, "message": str(exc)[:500]})

    if tab_id:
        page_state_js = (
            "return JSON.stringify({"
            "url: location.href,"
            "title: document.title,"
            "visibility: document.visibilityState,"
            "text_sample: (document.body && document.body.innerText || '').slice(0, 4000),"
            "links: Array.from(document.querySelectorAll('a[href]')).slice(0,80).map(a => ({text:(a.innerText||'').trim().slice(0,120), href:a.href}))"
            "}, null, 2)"
        )
        try:
            page_state = _surf_js(surf_run, tab_id, page_state_js, timeout=30)
            page_state_path = bundle_dir / "page-state.json"
            page_state_path.write_text(page_state + "\n", encoding="utf-8")
            manifest["artifacts"]["page_state"] = str(page_state_path)
        except (BrowserCaptureError, subprocess.TimeoutExpired, OSError) as exc:
            manifest["errors"].append({"stage": "page_state", "type": type(exc).__name__, "message": str(exc)[:500]})

        screenshot_path = bundle_dir / "screenshot.png"
        try:
            _surf(surf_run, "snap", "--tab-id", tab_id, "--output", str(screenshot_path), timeout=60)
            if screenshot_path.exists():
                manifest["artifacts"]["screenshot"] = str(screenshot_path)
        except (BrowserCaptureError, subprocess.TimeoutExpired, OSError) as exc:
            manifest["errors"].append({"stage": "screenshot", "type": type(exc).__name__, "message": str(exc)[:500]})

    manifest_path = bundle_dir / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "path": str(bundle_dir),
        "manifest": str(manifest_path),
        "reason": reason,
        "errors": len(manifest["errors"]),
    }


@contextlib.contextmanager
def _wall_clock_timeout(seconds: int, label: str):
    """Bound capture phases even if a lower-level browser helper wedges."""

    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return
    old_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"{label} exceeded {seconds}s")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def ensure_browser(surf_run: Path = SURF_RUN_DEFAULT) -> str:
    """Guarantee surf has a reachable browser; create a fresh window if not.

    Uses the same mechanism /ask uses for browser-tab-lifecycle=auto: when no
    surf tab is reachable, `surf window.new` opens a fresh window in the
    extension-connected Chrome. This is the correct path — a CDP-launched Chrome
    can NOT be used, because Chrome blocks `--load-extension`, so the surf
    extension never binds and every surf command fails. Returns the mode used.

    Fails honestly if the surf extension host is not connected at all (Chrome
    fully closed / extension unloaded) — that is a real environment gap to
    surface, not something a headless Chrome can paper over.
    """
    try:
        _surf(surf_run, "tab.list", "--json", timeout=25)
        return "existing"
    except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
        logger.warning("no reachable surf tab ({}); creating a fresh window via surf window.new", exc)
    try:
        # The /ask auto-lifecycle mechanism: a fresh window in the connected Chrome.
        _surf(surf_run, "window.new", "about:blank", "--unfocused", timeout=60)
        _surf(surf_run, "tab.list", "--json", timeout=25)
        return "fresh_window"
    except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
        raise BrowserCaptureError(
            f"no surf-connected browser and window.new failed: {exc}. "
            "Chrome must be running with the surf extension loaded "
            "(chrome://extensions -> Load unpacked -> surf/vendor/surf-cli/dist); "
            "a CDP/headless Chrome cannot bind the extension."
        ) from exc


def _capture_required_job_source(
    *,
    out_dir: Path,
    surf_run: Path,
    source: str,
    url: str,
    extract_js: str,
    wait_seconds: str = "5",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": source,
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "read_only_browser_capture_no_apply_no_message",
        "url": url,
    }
    tab_id = ""
    try:
        ensure_browser(surf_run)
        created = _surf(surf_run, "tab.new", url, "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
        _surf_pause(surf_run, wait_seconds)
        raw = _surf_js(surf_run, tab_id, extract_js, timeout=45)
        snapshot = json.loads(json.loads(raw))
        records = [row for row in snapshot.get("records") or [] if isinstance(row, dict)]
        evidence = {
            "schema_version": "monitor_opportunities.required_browser_source_capture.v1",
            "source": source,
            "capture_method": "surf_read_only_visible_page",
            "automation_policy": receipt["automation_policy"],
            "external_effects": False,
            "observed_at": utc_now(),
            "url": snapshot.get("url") or url,
            "title": snapshot.get("title"),
            "text": snapshot.get("text"),
            "records": records,
            "non_claims": [
                "This evidence satisfies source-health coverage only.",
                "Aggregator or locator rows are not independently admitted as ranked opportunities.",
                "No apply, save, login, message, connection, RSVP, or submit action was taken.",
            ],
        }
        evidence_path = out_dir / f"{source}-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        receipt["status"] = "OK" if records or str(snapshot.get("text") or "").strip() else "EMPTY"
        receipt["records_captured"] = len(records)
        receipt["evidence_path"] = str(evidence_path)
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.error("{} capture failed: {}", source, exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["evidence_path"] = None
        receipt["diagnostic_bundle"] = _write_surf_diagnostic_bundle(
            out_dir,
            source=source,
            surf_run=surf_run,
            tab_id=tab_id or None,
            reason=f"{source}_capture_failed",
            url=url,
            error=exc,
        )
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, source)
    (out_dir / f"{source}-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def capture_hiddenjobs(out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    return _capture_required_job_source(
        out_dir=out_dir,
        surf_run=surf_run,
        source="hiddenjobs",
        url=_HIDDENJOBS_URL,
        extract_js=_HIDDENJOBS_EXTRACT_JS,
        wait_seconds="4",
    )


def capture_indeed_jobs(out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    return _capture_required_job_source(
        out_dir=out_dir,
        surf_run=surf_run,
        source="indeed",
        url=_INDEED_AI_BUFFALO_URL,
        extract_js=_INDEED_EXTRACT_JS,
        wait_seconds="5",
    )


def _g2i_slack_records_from_text(text: str, *, channel_url: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    date_line = re.compile(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),", re.I)
    post_title = re.compile(
        r"\b(?:ai|llm|backend|fullstack|full-stack|systems?|software|developer|engineer|architect|programmer)\b",
        re.I,
    )
    post_context = re.compile(
        r"\b(?:must have|direct hire|contract|hours|location:|looking for|application|g2idev\\.com|apply)\b",
        re.I,
    )
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        if "|" not in line or not post_title.search(line):
            continue
        body: list[str] = [line]
        for follow in lines[index + 1 : index + 10]:
            if date_line.search(follow):
                break
            if "|" in follow and post_title.search(follow):
                break
            if follow in {"View thread", "Message 05_g2i-job-alerts"}:
                break
            body.append(follow)
        content = "\n".join(body)
        if not post_context.search(content):
            continue
        title, organization = [part.strip() for part in line.split("|", 1)]
        key = f"{title.lower()}|{organization.lower()}"
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "title": title,
                "company": organization,
                "channel": "05_g2i-job-alerts",
                "content": content,
                "url": channel_url,
                "permalink": channel_url,
            }
        )
    return records


def _find_existing_slack_tab(surf_run: Path) -> str | None:
    raw = _surf(surf_run, "tab.list", "--json", timeout=25)
    try:
        tabs = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(tabs, list):
        return None
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        url = str(tab.get("url") or "")
        title = str(tab.get("title") or "")
        if _G2I_SLACK_TEAM_ID in url or "G2i - Slack" in title:
            tab_id = tab.get("id")
            return str(tab_id) if tab_id is not None else None
    return None


def capture_g2i_slack_jobs(out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    """Read G2i's job-alerts Slack channel from the authenticated browser tab."""

    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "g2i_slack_job_alerts",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "read_only_slack_channel_capture_no_send_no_reply_no_react_no_apply",
        "team_id": _G2I_SLACK_TEAM_ID,
        "channel_id": _G2I_SLACK_JOB_ALERTS_CHANNEL_ID,
        "channel": "05_g2i-job-alerts",
        "url": _G2I_SLACK_JOB_ALERTS_URL,
    }
    tab_id = ""
    created_tab = False
    try:
        ensure_browser(surf_run)
        tab_id = _find_existing_slack_tab(surf_run) or ""
        if not tab_id:
            created = _surf(surf_run, "tab.new", _G2I_SLACK_JOB_ALERTS_URL, "--json", timeout=30)
            tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
            created_tab = True
        if not tab_id:
            raise BrowserCaptureError("could not find or create an authenticated G2i Slack tab")
        _surf_js(surf_run, tab_id, _nav_js(_G2I_SLACK_JOB_ALERTS_URL), timeout=20)
        _surf_pause(surf_run, "7")
        raw = _surf_js(surf_run, tab_id, _G2I_SLACK_EXTRACT_JS, timeout=45)
        snapshot = _surf_json_value(raw, {})
        if not isinstance(snapshot, dict):
            snapshot = {}
        text = str(snapshot.get("text") or "")
        records = _g2i_slack_records_from_text(text, channel_url=str(snapshot.get("url") or _G2I_SLACK_JOB_ALERTS_URL))
        evidence = {
            "schema_version": "monitor_opportunities.slack_channel_capture.v1",
            "source": "g2i_slack_job_alerts",
            "capture_method": "surf_read_only_authenticated_slack_tab",
            "automation_policy": receipt["automation_policy"],
            "external_effects": False,
            "observed_at": utc_now(),
            "team_id": _G2I_SLACK_TEAM_ID,
            "channel_id": _G2I_SLACK_JOB_ALERTS_CHANNEL_ID,
            "channel": "05_g2i-job-alerts",
            "url": snapshot.get("url") or _G2I_SLACK_JOB_ALERTS_URL,
            "title": snapshot.get("title"),
            "text": text,
            "messages": records,
            "non_claims": [
                "This is read-only Slack browser evidence from Graham's authenticated session.",
                "No Slack message, reply, reaction, DM, join, or application action was taken.",
                "G2i posts still require primary-source review in the G2i portal before outreach or application.",
            ],
        }
        evidence_path = out_dir / "g2i-slack-job-alerts-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        receipt["status"] = "OK" if records else "EMPTY"
        receipt["records_captured"] = len(records)
        receipt["evidence_path"] = str(evidence_path)
        receipt["tab_id"] = tab_id
        receipt["created_tab"] = created_tab
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.warning("G2i Slack job-alert capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["records_captured"] = 0
        receipt["evidence_path"] = None
        receipt["diagnostic_bundle"] = _write_surf_diagnostic_bundle(
            out_dir,
            source="g2i_slack_job_alerts",
            surf_run=surf_run,
            tab_id=tab_id or None,
            reason="g2i_slack_job_alert_capture_failed",
            url=_G2I_SLACK_JOB_ALERTS_URL,
            error=exc,
        )
    finally:
        if tab_id and created_tab:
            _close_tab(surf_run, tab_id, "G2i Slack job alerts")
    (out_dir / "g2i-slack-job-alerts-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


_DISCORD_OPPORTUNITY_CHANNEL_URL = "https://discord.com/channels/1344341191893979290/1344341192518799442"
_DISCORD_OPPORTUNITY_GUILD_ID = "1344341191893979290"
_DISCORD_OPPORTUNITY_CHANNEL_ID = "1344341192518799442"
_DISCORD_EXTRACT_JS = (
    "(function(){return JSON.stringify({url:location.href,title:document.title,"
    "text:(document.body.innerText||'').slice(0,24000)});})()"
)


def _discord_records_from_text(text: str, *, channel_url: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    role_or_skill = re.compile(
        r"\b(?:ai engineer|llm engineer|agentic|backend|full[- ]?stack|software engineer|"
        r"developer|architect|consultant|contract|freelance|python|react|node(?:\\.js)?)\b",
        re.I,
    )
    title_signal = re.compile(
        r"\b(?:ai engineer|llm engineer|backend|full[- ]?stack|software engineer|"
        r"developer|architect|consultant|contract role|freelance role)\b",
        re.I,
    )
    opportunity_context = re.compile(
        r"\b(?:hiring|looking for|seeking|apply|application|job|role|position|"
        r"contract|client needs|team needs|paid|available opportunities)\b",
        re.I,
    )
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        if not title_signal.search(line):
            continue
        body = [line, *lines[index + 1 : index + 8]]
        content = "\n".join(body)
        if not role_or_skill.search(content) or not opportunity_context.search(content):
            continue
        if re.search(r"\b(?:not hiring|no jobs?|not a job|training opportunities\\?)\b", content, re.I):
            continue
        title = line
        if len(title) > 120:
            title = "Discord opportunity signal"
        key = f"{title.lower()}|{content[:240].lower()}"
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "title": title,
                "company": "Discord opportunity channel",
                "channel": "discord:#general",
                "content": content,
                "url": channel_url,
                "permalink": channel_url,
            }
        )
    return records


def _find_existing_discord_tab(surf_run: Path) -> str | None:
    raw = _surf(surf_run, "tab.list", "--json", timeout=25)
    try:
        tabs = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(tabs, list):
        return None
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        url = str(tab.get("url") or "")
        title = str(tab.get("title") or "")
        if (
            _DISCORD_OPPORTUNITY_CHANNEL_URL in url
            or f"discord.com/channels/{_DISCORD_OPPORTUNITY_GUILD_ID}/{_DISCORD_OPPORTUNITY_CHANNEL_ID}" in url
            or "Codename: Practical AI" in title
        ):
            tab_id = tab.get("id")
            return str(tab_id) if tab_id is not None else None
    return None


def capture_discord_opportunity_channel(out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    """Read Graham's configured Discord opportunity channel from an authenticated browser tab."""

    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "discord_opportunity_channel",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "read_only_discord_channel_capture_no_send_no_reply_no_react_no_apply",
        "guild_id": _DISCORD_OPPORTUNITY_GUILD_ID,
        "channel_id": _DISCORD_OPPORTUNITY_CHANNEL_ID,
        "channel": "discord:#general",
        "url": _DISCORD_OPPORTUNITY_CHANNEL_URL,
    }
    tab_id = ""
    created_tab = False
    try:
        ensure_browser(surf_run)
        tab_id = _find_existing_discord_tab(surf_run) or ""
        if not tab_id:
            created = _surf(surf_run, "tab.new", _DISCORD_OPPORTUNITY_CHANNEL_URL, "--json", timeout=30)
            tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
            created_tab = True
        if not tab_id:
            raise BrowserCaptureError("could not find or create an authenticated Discord tab")
        _surf_js(surf_run, tab_id, _nav_js(_DISCORD_OPPORTUNITY_CHANNEL_URL), timeout=20)
        _surf_pause(surf_run, "4")
        raw = _surf_js(surf_run, tab_id, _DISCORD_EXTRACT_JS, timeout=45)
        snapshot = _surf_json_value(raw, {})
        if not isinstance(snapshot, dict):
            snapshot = {}
        text = str(snapshot.get("text") or "")
        channel_url = str(snapshot.get("url") or _DISCORD_OPPORTUNITY_CHANNEL_URL)
        records = _discord_records_from_text(text, channel_url=channel_url)
        evidence = {
            "schema_version": "monitor_opportunities.discord_channel_capture.v1",
            "source": "discord_opportunity_channel",
            "capture_method": "surf_read_only_authenticated_discord_tab",
            "automation_policy": receipt["automation_policy"],
            "external_effects": False,
            "observed_at": utc_now(),
            "guild_id": _DISCORD_OPPORTUNITY_GUILD_ID,
            "channel_id": _DISCORD_OPPORTUNITY_CHANNEL_ID,
            "channel": "discord:#general",
            "url": channel_url,
            "title": snapshot.get("title"),
            "text": text,
            "messages": records,
            "non_claims": [
                "This is read-only Discord browser evidence from Graham's authenticated session.",
                "No Discord message, reply, reaction, DM, join, or application action was taken.",
                "Discord posts are leads only; primary-source details must be checked before outreach or application.",
            ],
        }
        evidence_path = out_dir / "discord-opportunity-channel-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        receipt["status"] = "OK" if records else "EMPTY"
        receipt["records_captured"] = len(records)
        receipt["evidence_path"] = str(evidence_path)
        receipt["tab_id"] = tab_id
        receipt["created_tab"] = created_tab
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.warning("Discord opportunity channel capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["records_captured"] = 0
        receipt["evidence_path"] = None
        receipt["diagnostic_bundle"] = _write_surf_diagnostic_bundle(
            out_dir,
            source="discord_opportunity_channel",
            surf_run=surf_run,
            tab_id=tab_id or None,
            reason="discord_opportunity_channel_capture_failed",
            url=_DISCORD_OPPORTUNITY_CHANNEL_URL,
            error=exc,
        )
    finally:
        if tab_id and created_tab:
            _close_tab(surf_run, tab_id, "Discord opportunity channel")
    (out_dir / "discord-opportunity-channel-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


_LINKEDIN_TOP_APPLICANT_URL = "https://www.linkedin.com/jobs/collections/top-applicant/"

_LINKEDIN_EXTRACT_JS = (
    "(function(){"
    "var out=[],seen={};"
    "var cards=[].slice.call(document.querySelectorAll("
    "'li.scaffold-layout__list-item, li[data-occludable-job-id], div.job-card-container'));"
    "for (var i=0;i<cards.length;i++){"
    "var lines=cards[i].innerText.split('\\n').map(function(s){return s.trim();}).filter(Boolean);"
    "var uniq=[]; for(var j=0;j<lines.length;j++){ if(lines[j]!==lines[j-1]) uniq.push(lines[j]); }"
    "var title=uniq[0]||''; if(!title||seen[title]) continue; seen[title]=1;"
    "uniq=uniq.filter(function(s,idx){return idx===0||!/\\bwith verification\\b/i.test(s);});"
    "var a=cards[i].querySelector(\"a[href*='/jobs/view/'], a[href*='currentJobId']\");"
    # Easy Apply badge: LinkedIn's one-click lane, shown as a card label or a
    # button aria-label. Detect either so the ranker can reward the fast path.
    "var ea=/easy apply/i.test(cards[i].innerText)||!!cards[i].querySelector('[aria-label*=\"Easy Apply\" i], button[aria-label*=\"Easy Apply\" i]');"
    "out.push({title:title, company:uniq[1]||'', location:uniq[2]||'', href:a?a.href.split('?')[0]:null, easy_apply:ea});"
    "}"
    "return JSON.stringify(out);"
    "})()"
)


_LINKEDIN_SCROLL_JS = (
    "(function(){var l=document.querySelector("
    "'.jobs-search-results-list, div[class*=\"jobs-search-results\"], .scaffold-layout__list, ul.jobs-search__results-list');"
    "if(l){l.scrollTop+=900;} window.scrollBy(0,900); return 'ok';})()"
)


def _linkedin_next_page_js(page: int) -> str:
    return (
        "(function(){"
        f"var p={page};"
        "var b=[].slice.call(document.querySelectorAll('button[aria-label]')).filter(function(x){return x.getAttribute('aria-label')==='Page '+p;})[0];"
        "if(!b){b=[].slice.call(document.querySelectorAll('button')).filter(function(x){return x.innerText.trim()===String(p);})[0];}"
        "if(b){b.scrollIntoView(); b.click(); return 'CLICKED';} return 'NO_BUTTON';})()"
    )


# --- LinkedIn advanced search (leverage LinkedIn's own search engine) ------
# Server-side filtering returns fewer, higher-relevance results per page than
# scrolling the virtualized top-applicant list, so it needs far fewer surf
# calls (which is what trips the surf build-lock wedge). This is the robust
# primary path; scroll-paginate of top-applicant is the fallback.
_LINKEDIN_JOB_SEARCH_BASE = "https://www.linkedin.com/jobs/search/"

# f_WT work type: 1=on-site, 2=remote, 3=hybrid
_LINKEDIN_WORK_TYPE = {"on-site": "1", "remote": "2", "hybrid": "3"}
# f_E experience level: 4=mid-senior, 5=director, 6=executive (Graham's floor)
_LINKEDIN_SENIOR_EXPERIENCE = ["4", "5", "6"]
# f_TPR posted-within seconds — 2 weeks (we only care about recent openings).
_LINKEDIN_POSTED_WEEK = "r1209600"


def build_linkedin_search_url(
    keywords: str,
    work_types: list[str],
    experience_levels: list[str] | None = None,
    posted_within: str = _LINKEDIN_POSTED_WEEK,
    location: str | None = None,
    sort_by: str = "DD",
    easy_apply: bool = False,
) -> str:
    """Build a LinkedIn advanced job-search URL (pure; no browser).

    Maps candidate preferences to LinkedIn's own filter params so the platform
    does the filtering server-side. `work_types` are keys of _LINKEDIN_WORK_TYPE;
    unknown keys are ignored. sort_by DD=most recent, R=most relevant.
    easy_apply=True adds LinkedIn's Easy Apply filter (f_AL) — the fast lane that
    pairs with direct outreach.
    """
    params: list[tuple[str, str]] = [("keywords", keywords)]
    wt = [_LINKEDIN_WORK_TYPE[w] for w in work_types if w in _LINKEDIN_WORK_TYPE]
    if wt:
        params.append(("f_WT", ",".join(wt)))
    exp = experience_levels if experience_levels is not None else _LINKEDIN_SENIOR_EXPERIENCE
    if exp:
        params.append(("f_E", ",".join(exp)))
    if posted_within:
        params.append(("f_TPR", posted_within))
    if easy_apply:
        params.append(("f_AL", "true"))
    if location:
        params.append(("location", location))
    if sort_by:
        params.append(("sortBy", sort_by))
    return _LINKEDIN_JOB_SEARCH_BASE + "?" + urlencode(params)


MAX_SEARCH_PHRASES = 6


def _mandate_keyword_groups(profile: dict[str, Any]) -> list[str]:
    """Derive bounded, high-signal keyword phrases from the candidate mandates.

    Falls back to a sane default set if the profile has no mandates, so the
    search never silently degrades to an empty query.
    """
    # Graham states the target directly (2026-08-17: "AI, agentic pipeline,
    # agentic extraction", "R&D", "robotics, if tangentially applicable"), so the
    # profile's own search_phrases win over any derivation. Tangential phrases
    # come last and are the first thing the cap drops.
    configured = profile.get("search_phrases") or {}
    if isinstance(configured, dict):
        stated = [
            phrase
            for phrase in [*configured.get("primary", []), *configured.get("tangential", [])]
            if isinstance(phrase, str) and phrase.strip()
        ]
        if stated:
            return stated[:MAX_SEARCH_PHRASES]

    mandates = [m for m in profile.get("mandates", []) if isinstance(m, str)]
    phrases: list[str] = []
    for m in mandates:
        low = m.lower()
        if "document-extraction" in low or "document extraction" in low:
            phrases.append("document extraction AI")
        elif "agentic-compliance" in low or "compliance" in low:
            phrases.append("AI compliance architect")
        elif "agentic pipelines" in low or "llm systems" in low:
            phrases.append("agentic LLM systems")
        elif "verification" in low:
            phrases.append("AI verification")
    if not phrases:
        phrases = ["AI architect", "agentic LLM systems", "document extraction AI"]
    # de-dup, preserve order, cap to keep surf-call count bounded
    seen: set[str] = set()
    out: list[str] = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:MAX_SEARCH_PHRASES]


def linkedin_search_queries_from_profile(profile: dict[str, Any]) -> list[dict[str, str]]:
    """Build the advanced-search query set (pure) from the candidate profile.

    Two geographies per keyword group: remote/hybrid (Graham's preference) and
    Buffalo/WNY on-site-acceptable. Each entry is {label, url}. Bounded so a run
    makes a predictable, small number of surf navigations.
    """
    pref = profile.get("workplace_preference", {})
    remote_hybrid = [w for w in ("remote", "hybrid") if w in pref.get("preferred", ["remote", "hybrid"])]
    if not remote_hybrid:
        remote_hybrid = ["remote", "hybrid"]
    location = profile.get("identity", {}).get("location", "Buffalo, NY")
    queries: list[dict[str, str]] = []
    for kw in _mandate_keyword_groups(profile):
        queries.append(
            {
                "label": f"{kw} | remote+hybrid",
                "url": build_linkedin_search_url(kw, remote_hybrid),
            }
        )
        queries.append(
            {
                "label": f"{kw} | {location} on-site OK",
                "url": build_linkedin_search_url(
                    kw, ["on-site", "remote", "hybrid"], location=location
                ),
            }
        )
    return queries


def _linkedin_scroll_paginate_capture(surf_run: Path, tab_id: str, max_pages: int = 3) -> list[dict[str, Any]]:
    """Scroll each results page to force LinkedIn's virtualized list to render all
    cards, accumulating them before they unrender, then advance pages. Robust to
    virtualization: keeps a running dedup map keyed by title+company.
    """
    accumulated: dict[str, dict[str, Any]] = {}
    for page in range(1, max_pages + 1):
        stable = 0
        for _ in range(12):
            raw = _surf_js(surf_run, tab_id, _LINKEDIN_EXTRACT_JS, timeout=30)
            rows = _surf_json_value(raw, [])
            new = 0
            for r in rows:
                title = (r.get("title") or "").strip()
                if not title:
                    continue
                key = title + "|" + (r.get("company") or "")
                if key not in accumulated:
                    accumulated[key] = r
                    new += 1
            stable = stable + 1 if new == 0 else 0
            if stable >= 3:
                break
            _surf_js(surf_run, tab_id, _LINKEDIN_SCROLL_JS, timeout=20)
            _surf_pause(surf_run, "1", timeout=15)
        if page < max_pages:
            clicked = _surf_js(surf_run, tab_id, _linkedin_next_page_js(page + 1), timeout=20)
            if "CLICKED" not in clicked:
                break
            _surf_pause(surf_run, "4", timeout=20)
    return list(accumulated.values())


def capture_linkedin_top_applicant(out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    """Read-only capture of LinkedIn 'top applicant' jobs from the authenticated session.

    Requires the user's Chrome to be open and logged into LinkedIn (the common
    case). Navigates a tab to the top-applicant collection and extracts the
    listings. If a sign-in wall appears (no authenticated session), records
    AUTH_REQUIRED honestly — never fabricates results. No LinkedIn automation
    beyond read-only navigation of the human's own authenticated session.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "linkedin_top_applicant",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "linkedin_authorized_read_only_no_actions",
    }
    tab_id = ""
    try:
        ensure_browser(surf_run)
        created = _surf(surf_run, "tab.new", _LINKEDIN_TOP_APPLICANT_URL, "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
        _surf_pause(surf_run, "9")
        wall = _surf(
            surf_run,
            "js",
            "--tab-id",
            tab_id,
            "(function(){return (document.body.innerText.toLowerCase().indexOf('sign in to')>=0 || location.href.indexOf('/login')>=0) ? 'WALL' : 'OK';})()",
        )
        if "WALL" in wall:
            receipt["status"] = "AUTH_REQUIRED"
            receipt["error"] = "LinkedIn sign-in wall — no authenticated session in the reachable browser"
            receipt["evidence_path"] = None
            return receipt
        rows = _linkedin_scroll_paginate_capture(surf_run, tab_id)
        opps = [
            {
                "source": "human_authorized_linkedin_tab",
                "observed_at": utc_now(),
                "title": r["title"],
                "organization": (r.get("company") or "UNKNOWN").strip() or "UNKNOWN",
                "location": (r.get("location") or "UNKNOWN").strip() or "UNKNOWN",
                "linkedin_url": _LINKEDIN_TOP_APPLICANT_URL,
                "primary_evidence_url": r.get("href") or _LINKEDIN_TOP_APPLICANT_URL,
                "top_candidate": True,
                "easy_apply": bool(r.get("easy_apply")),
            }
            for r in rows
        ]
        evidence = {
            "schema_version": "ops-linkedin.opportunity_capture.v1",
            "source": "human_authorized_linkedin_tab",
            "capture_method": "surf_read_only_authenticated_session",
            "automation_policy": "linkedin_authorized_read_only_no_actions",
            "observed_at": utc_now(),
            "linkedin_url": _LINKEDIN_TOP_APPLICANT_URL,
            "primary_evidence_url": _LINKEDIN_TOP_APPLICANT_URL,
            "page_title": "Jobs where you're a top applicant",
            "top_candidate": True,
            "opportunities": opps,
        }
        evidence_path = out_dir / "linkedin-top-applicant-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        receipt["status"] = "OK" if opps else "EMPTY"
        receipt["evidence_path"] = str(evidence_path)
        receipt["opportunities_captured"] = len(opps)
        receipt["top_applicant_count"] = len(opps)
        receipt["easy_apply_count"] = sum(1 for o in opps if o.get("easy_apply") is True)
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.error("LinkedIn top-applicant capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["evidence_path"] = None
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "LinkedIn capture")
    (out_dir / "linkedin-capture-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


# SAM.gov's own frontend search service (discovered 2026-08-12 by watching the
# SPA's network calls). Keyless and cookieless; requires Accept: application/hal+json
# (plain application/json gets 406). Works where api.sam.gov + api_key 404s.
_SAM_SGS_URL = "https://sam.gov/api/prod/sgs/v1/search/"


def _capture_sam_via_sgs(out_dir: Path, receipt: dict[str, Any]) -> dict[str, Any] | None:
    """Try the sgs HTTP endpoint; return the receipt on success, None to fall back."""
    import httpx

    params = {
        "random": "1", "index": "opp", "page": "0", "mode": "search",
        "sort": "-modifiedDate", "size": "40", "responseType": "json",
        "q": "artificial intelligence", "qMode": "ALL", "is_active": "true",
    }
    headers = {
        "Accept": "application/hal+json, application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://sam.gov/search/",
    }
    try:
        timeout = httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(_SAM_SGS_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("SAM sgs endpoint failed ({}); falling back to browser capture", exc)
        return None
    results = (data.get("_embedded") or {}).get("results") or []
    opps = [
        {
            "title": str(r.get("title") or "").strip(),
            "url": f"https://sam.gov/opp/{r.get('_id')}/view",
            "opp_id": r.get("_id"),
            "solicitation_number": r.get("solicitationNumber"),
            "published_at": r.get("publishDate"),
            "updated_at": r.get("modifiedDate"),
            "response_deadline": r.get("responseDateActual") or r.get("responseDate"),
            "source": "sam.gov_website",
        }
        for r in results
        if r.get("_id") and str(r.get("title") or "").strip()
    ]
    if not opps:
        logger.warning("SAM sgs endpoint returned 0 rows; falling back to browser capture")
        return None
    evidence = {
        "schema_version": "monitor_opportunities.federal_capture.v1",
        "source": "sam_sgs_search_service",
        "capture_method": "httpx_read_only_sgs",
        "observed_at": utc_now(),
        "sam_url": _SAM_SGS_URL,
        "result_count": len(opps),
        "total_available": (data.get("page") or {}).get("totalElements"),
        "opportunities": opps,
    }
    evidence_path = out_dir / "sam-website-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
    receipt["status"] = "OK"
    receipt["capture_method"] = "sgs_http"
    receipt["evidence_path"] = str(evidence_path)
    receipt["opportunities_captured"] = len(opps)
    (out_dir / "sam-capture-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def capture_sam(out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    """Read-only capture of SAM.gov active AI opportunities.

    Primary: SAM's own sgs search service over plain HTTP (keyless; the documented
    api.sam.gov + api_key path 404s from this host, and sgs is what sam.gov's
    frontend itself calls). Fallback: surf browser capture of the rendered search.
    Writes federal evidence JSON consumable by run --federal-evidence. Honest
    failure: if both paths fail, no evidence file is written, status FAILED.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    sgs_receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "sam.gov_website",
        "captured_at": utc_now(),
        "external_effects": False,
    }
    done = _capture_sam_via_sgs(out_dir, sgs_receipt)
    if done is not None:
        return done
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "sam.gov_website",
        "captured_at": utc_now(),
        "external_effects": False,
    }
    tab_id = ""
    try:
        browser_mode = ensure_browser(surf_run)
        receipt["browser_mode"] = browser_mode
        created = _surf(surf_run, "tab.new", _SAM_URL, "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
        # SAM is an Angular SPA that renders results only after its backend call
        # returns; a fixed 10s wait was too short and captured 0 rows. Poll for
        # opportunity links (up to ~36s) and proceed as soon as they render.
        _surf_pause(surf_run, "6")
        ready = 0
        for _ in range(10):
            try:
                probe = _surf_js(surf_run, tab_id, _SAM_READY_JS) or "0"
                ready = int(probe.strip())
            except (BrowserCaptureError, ValueError):
                ready = 0
            if ready > 0:
                break
            _surf_pause(surf_run, "3")
        receipt["poll_ready_links"] = ready
        raw = _surf_js(surf_run, tab_id, _SAM_EXTRACT_JS)
        parsed = json.loads(json.loads(raw))
        rows = parsed.get("rows", []) if isinstance(parsed, dict) else []
        opps = [
            {"title": r["title"], "url": r.get("url"), "opp_id": r.get("opp_id"),
             "source": "sam.gov_website"}
            for r in rows
            if r.get("title")
        ]
        evidence = {
            "schema_version": "monitor_opportunities.federal_capture.v1",
            "source": "human_authorized_sam_tab",
            "capture_method": "surf_read_only_website",
            "observed_at": utc_now(),
            "sam_url": _SAM_URL,
            "result_count": len(opps),
            "opportunities": opps,
        }
        evidence_path = out_dir / "sam-website-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        receipt["status"] = "OK" if opps else "EMPTY"
        receipt["evidence_path"] = str(evidence_path)
        receipt["opportunities_captured"] = len(opps)
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.error("SAM website capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["evidence_path"] = None
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "SAM capture")
    (out_dir / "sam-capture-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def _meetup_page_snapshot(surf_run: Path, tab_id: str) -> dict[str, Any]:
    raw = _surf_js(surf_run, tab_id, _MEETUP_PAGE_EXTRACT_JS, timeout=30)
    parsed = json.loads(json.loads(raw))
    return parsed if isinstance(parsed, dict) else {}


def _meetup_event_snapshot(surf_run: Path, tab_id: str) -> dict[str, Any]:
    """Attendees visible on one event page. {} when the page shows none."""

    raw = _surf_js(surf_run, tab_id, _MEETUP_ATTENDEE_EXTRACT_JS, timeout=30)
    parsed = json.loads(json.loads(raw))
    return parsed if isinstance(parsed, dict) else {}


def _meetup_event_urls(links: list[str], limit: int) -> list[str]:
    """Event permalinks from a group page, newest-first as rendered."""

    out: list[str] = []
    seen: set[str] = set()
    for link in links:
        url = str(link).split("?")[0]
        if "/events/" not in url:
            continue
        tail = [part for part in url.split("/") if part]
        if not tail or not tail[-1].isdigit():
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def _meetup_group_url(url: str) -> str | None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if "meetup.com" not in parsed.netloc.lower():
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    slug = parts[0].lower()
    if slug in {
        "account",
        "apps",
        "find",
        "graphql",
        "home",
        "login",
        "members",
        "messages",
        "notifications",
        "hc",
        "topics",
    }:
        return None
    return f"https://www.meetup.com/{parts[0]}/"


def _meetup_name_from_snapshot(snapshot: dict[str, Any], fallback_url: str) -> str:
    title = str(snapshot.get("title") or "").strip()
    for marker in (" | Meetup", " - Meetup"):
        if marker in title:
            title = title.split(marker, 1)[0].strip()
    if title and title.lower() not in {"meetup", "search groups"}:
        return title
    text = str(snapshot.get("text") or "")
    for line in text.splitlines():
        clean = line.strip()
        if clean and clean.lower() not in {"meetup", "log in", "sign up"}:
            return clean[:120]
    return fallback_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()


def _meetup_events_from_text(text: str) -> list[dict[str, Any]]:
    import re

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    events: list[dict[str, Any]] = []
    date_re = re.compile(
        r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+|"
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}\b|"
        r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b",
        re.I,
    )
    for idx, line in enumerate(lines):
        if not date_re.search(line):
            continue
        title = ""
        for prev in reversed(lines[max(0, idx - 4):idx]):
            if len(prev) > 3 and not date_re.search(prev) and prev.lower() not in {"upcoming events", "events"}:
                title = prev
                break
        if title:
            events.append({"title": title[:140], "starts_at_text": line[:120]})
        if len(events) >= 3:
            break
    return events


def _meetup_interleaved_group_sources(
    group_sources: dict[str, dict[str, str]],
    max_group_pages: int,
) -> list[tuple[str, dict[str, str]]]:
    """Choose group pages across categories before spending the full page budget."""

    buckets: dict[str, list[tuple[str, dict[str, str]]]] = {}
    category_order = [category_id for category_id, _name, _url in _MEETUP_CATEGORY_URLS]
    for group_url, source in group_sources.items():
        category_id = source.get("category_id", "")
        if category_id not in buckets:
            buckets[category_id] = []
        buckets[category_id].append((group_url, source))
        if category_id not in category_order:
            category_order.append(category_id)

    selected: list[tuple[str, dict[str, str]]] = []
    while len(selected) < max_group_pages:
        progressed = False
        for category_id in category_order:
            bucket = buckets.get(category_id) or []
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            progressed = True
            if len(selected) >= max_group_pages:
                break
        if not progressed:
            break
    return selected


def capture_meetup_buffalo(
    out_dir: Path,
    surf_run: Path = SURF_RUN_DEFAULT,
    max_group_pages: int = 12,
) -> dict[str, Any]:
    """Read-only Meetup capture for Buffalo source-intel networking.

    Visits the Technology and Career & Business category pages plus known
    high-signal seed groups, then follows each group's own event links to record
    WHO HAS SIGNED UP - the named, locatable contacts that are the entire reason
    Meetup is swept. Writes evidence consumed by run --meetup-evidence.

    Every step is a page read in the human's authenticated session. No GraphQL,
    no RSVP, no join, no message, no connection request, no platform action.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "meetup_buffalo",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "meetup_authorized_read_only_attendee_names_no_rsvp_no_message",
        "category_ids": [row[0] for row in _MEETUP_CATEGORY_URLS],
    }
    tab_id = ""
    groups: list[dict[str, Any]] = []
    group_capture_failures: list[dict[str, str]] = []
    skipped_group_urls: list[str] = []
    try:
        # An explicit budget is honoured verbatim; only the DEFAULT scales with
        # how much work the lane was asked to do.
        events_per_group_env = max(0, int(os.environ.get("MONITOR_MEETUP_EVENTS_PER_GROUP", "2")))
        configured_timeout = os.environ.get("MONITOR_MEETUP_CAPTURE_TIMEOUT_SECONDS")
        wall_timeout = (
            max(1, int(configured_timeout))
            if configured_timeout
            else max(150, 50 + max_group_pages * 12 * (1 + events_per_group_env))
        )
        max_group_failures = max(1, int(os.environ.get("MONITOR_MEETUP_MAX_GROUP_FAILURES", "3")))
        category_wait_seconds = os.environ.get("MONITOR_MEETUP_CATEGORY_WAIT_SECONDS", "4")
        group_wait_seconds = os.environ.get("MONITOR_MEETUP_GROUP_WAIT_SECONDS", "3")
        max_events_per_group = max(0, int(os.environ.get("MONITOR_MEETUP_EVENTS_PER_GROUP", "2")))
        receipt["max_group_pages"] = max_group_pages
        receipt["category_wait_seconds"] = category_wait_seconds
        receipt["group_wait_seconds"] = group_wait_seconds
        with _wall_clock_timeout(wall_timeout, "Meetup Buffalo capture"):
            ensure_browser(surf_run)
            first_url = _MEETUP_CATEGORY_URLS[0][2]
            created = _surf(surf_run, "tab.new", first_url, "--json", timeout=40)
            tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
            if not tab_id:
                raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
            category_pages: list[dict[str, Any]] = []
            group_sources: dict[str, dict[str, str]] = {}
            for idx, (category_id, category_name, url) in enumerate(_MEETUP_CATEGORY_URLS):
                if idx > 0:
                    _surf_js(surf_run, tab_id, _nav_js(url), timeout=20)
                _surf_pause(surf_run, category_wait_seconds)
                snapshot = _meetup_page_snapshot(surf_run, tab_id)
                category_pages.append(
                    {
                        "category_id": category_id,
                        "category_name": category_name,
                        "url": url,
                        "title": snapshot.get("title"),
                    }
                )
                for link in snapshot.get("links") or []:
                    group_url = _meetup_group_url(str(link))
                    if group_url and group_url not in group_sources:
                        group_sources[group_url] = {"category_id": category_id, "category_name": category_name}
            for seed in _MEETUP_SEED_GROUP_URLS:
                group_sources.setdefault(seed, {"category_id": "seed", "category_name": "Seed group"})
            for group_url, source in _meetup_interleaved_group_sources(group_sources, max_group_pages):
                if len(group_capture_failures) >= max_group_failures:
                    skipped_group_urls.append(group_url)
                    continue
                try:
                    _surf_js(surf_run, tab_id, _nav_js(group_url), timeout=20)
                    _surf_pause(surf_run, group_wait_seconds)
                    snapshot = _meetup_page_snapshot(surf_run, tab_id)
                except (BrowserCaptureError, subprocess.TimeoutExpired, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning("Meetup group capture skipped for {}: {}", group_url, exc)
                    group_capture_failures.append(
                        {
                            "url": group_url,
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:500],
                        }
                    )
                    if len(group_capture_failures) == max_group_failures:
                        logger.warning(
                            "Meetup group capture circuit breaker opened after {} failures",
                            max_group_failures,
                        )
                    continue
                text = str(snapshot.get("text") or "")
                # Follow the group's own event links and record who signed up.
                # This is the only reason Meetup is in the sweep.
                attendees: list[dict[str, Any]] = []
                events_read: list[str] = []
                for event_url in _meetup_event_urls(
                    [str(link) for link in (snapshot.get("links") or [])], max_events_per_group
                ):
                    try:
                        _surf_js(surf_run, tab_id, _nav_js(event_url), timeout=20)
                        _surf_pause(surf_run, group_wait_seconds)
                        event_snapshot = _meetup_event_snapshot(surf_run, tab_id)
                    except (
                        BrowserCaptureError,
                        subprocess.TimeoutExpired,
                        TimeoutError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as exc:
                        logger.warning("Meetup attendee capture skipped for {}: {}", event_url, exc)
                        continue
                    events_read.append(event_url)
                    for person in event_snapshot.get("attendees") or []:
                        name = str(person.get("name") or "").strip()
                        if not name:
                            continue
                        attendees.append(
                            {
                                "name": name,
                                "role": str(person.get("role") or "attendee"),
                                "profile_url": str(person.get("profile_url") or ""),
                                "event_url": event_url,
                                "event_title": str(event_snapshot.get("title") or ""),
                                "group_url": group_url,
                                "observed_at": utc_now(),
                            }
                        )
                groups.append(
                    {
                        "attendees": attendees,
                        "attendee_count": len(attendees),
                        "events_read": events_read,
                        "source": "human_authorized_meetup_tab",
                        "observed_at": utc_now(),
                        "name": _meetup_name_from_snapshot(snapshot, group_url),
                        "url": group_url,
                        "category_id": source["category_id"],
                        "category_name": source["category_name"],
                        "location": "Buffalo, NY",
                        "description": text[:1200],
                        "page_text": text,
                        "upcoming_events": _meetup_events_from_text(text),
                    }
                )
        evidence = {
            "schema_version": "monitor_opportunities.meetup_capture.v1",
            "source": "human_authorized_meetup_tab",
            "capture_method": "surf_read_only_visible_pages",
            "automation_policy": "meetup_authorized_read_only_attendee_names_no_rsvp_no_message",
            "external_effects": False,
            "observed_at": utc_now(),
            "category_pages": category_pages,
            "seed_group_urls": _MEETUP_SEED_GROUP_URLS,
            "max_group_pages": max_group_pages,
            "category_wait_seconds": category_wait_seconds,
            "group_wait_seconds": group_wait_seconds,
            "groups": groups,
            "group_capture_failures": group_capture_failures,
            "skipped_group_urls": skipped_group_urls,
            "blocked_by_systemic_failure": bool(skipped_group_urls),
            "failure_signature": (
                "meetup_group_detail_capture_failed"
                if group_capture_failures
                else None
            ),
            "non_claims": [
                "Meetup evidence is source-intel only, not a job/application source.",
                "Capture uses visible page text and links only; no Meetup GraphQL call or attendee scraping.",
            ],
        }
        receipt["status"] = "OK" if groups else "EMPTY"
        receipt["groups_captured"] = len(groups)
        receipt["category_pages_captured"] = len(category_pages)
        receipt["group_capture_failed"] = len(group_capture_failures)
        receipt["group_capture_skipped"] = len(skipped_group_urls)
        receipt["blocked_by_systemic_failure"] = bool(skipped_group_urls)
        receipt["failure_signature"] = evidence["failure_signature"]
        if receipt["status"] != "OK" or group_capture_failures or skipped_group_urls:
            diagnostic = _write_surf_diagnostic_bundle(
                out_dir,
                source="meetup_buffalo",
                surf_run=surf_run,
                tab_id=tab_id,
                reason=str(receipt["failure_signature"] or "meetup_capture_empty"),
                url=str(category_pages[-1].get("url") if category_pages else _MEETUP_CATEGORY_URLS[0][2]),
            )
            receipt["diagnostic_bundle"] = diagnostic
            evidence["diagnostic_bundle"] = diagnostic
            evidence["site_recovery_status"] = "DIAGNOSTIC_BUNDLE_WRITTEN"
        evidence_path = out_dir / "meetup-buffalo-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        receipt["evidence_path"] = str(evidence_path)
    except (BrowserCaptureError, TimeoutError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.error("Meetup Buffalo capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["evidence_path"] = None
        receipt["diagnostic_bundle"] = _write_surf_diagnostic_bundle(
            out_dir,
            source="meetup_buffalo",
            surf_run=surf_run,
            tab_id=tab_id or None,
            reason="meetup_capture_failed",
            url=_MEETUP_CATEGORY_URLS[0][2],
            error=exc,
        )
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "Meetup capture")
    (out_dir / "meetup-capture-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def _meetup_capture_worker(
    out_dir: str,
    surf_run: str,
    max_group_pages: int,
    queue: multiprocessing.Queue,
) -> None:
    try:
        queue.put(capture_meetup_buffalo(Path(out_dir), Path(surf_run), max_group_pages=max_group_pages))
    except Exception as exc:  # noqa: BLE001 - child process converts all failures to receipt shape
        queue.put(
            {
                "schema": "monitor_opportunities.browser_capture_receipt.v1",
                "source": "meetup_buffalo",
                "captured_at": utc_now(),
                "external_effects": False,
                "automation_policy": "meetup_authorized_read_only_attendee_names_no_rsvp_no_message",
                "category_ids": [row[0] for row in _MEETUP_CATEGORY_URLS],
                "status": "FAILED",
                "error": str(exc),
                "evidence_path": None,
            }
        )


def capture_meetup_buffalo_isolated(
    out_dir: Path,
    surf_run: Path = SURF_RUN_DEFAULT,
    max_group_pages: int = 12,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run Meetup capture in a killable child so browser stalls cannot hang cron."""

    out_dir.mkdir(parents=True, exist_ok=True)
    # The budget has to cover what the lane actually does. Attendee capture adds
    # an event-page visit per event per group, so a flat 120s silently zeroed the
    # whole lane on 2026-08-18 (meetup_isolated_capture_timeout, groups_captured 0)
    # and with it the attendee signals and LinkedIn resolution downstream.
    # Roughly 12s per group page plus 12s per event page, floored at 180s.
    events_per_group = max(0, int(os.environ.get("MONITOR_MEETUP_EVENTS_PER_GROUP", "2")))
    configured = os.environ.get("MONITOR_MEETUP_CAPTURE_TIMEOUT_SECONDS")
    timeout_seconds = timeout_seconds or (
        max(1, int(configured)) if configured
        else max(180, 60 + max_group_pages * 12 * (1 + events_per_group))
    )
    ctx = multiprocessing.get_context("fork")
    queue: multiprocessing.Queue = ctx.Queue()
    proc = ctx.Process(
        target=_meetup_capture_worker,
        args=(str(out_dir), str(surf_run), max_group_pages, queue),
    )
    proc.start()
    proc.join(timeout_seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
            proc.join(5)
        receipt = {
            "schema": "monitor_opportunities.browser_capture_receipt.v1",
            "source": "meetup_buffalo",
            "captured_at": utc_now(),
            "external_effects": False,
            "automation_policy": "meetup_authorized_read_only_attendee_names_no_rsvp_no_message",
            "category_ids": [row[0] for row in _MEETUP_CATEGORY_URLS],
            "status": "FAILED",
            "error": f"Meetup Buffalo capture exceeded isolated timeout {timeout_seconds}s",
            "evidence_path": None,
            "groups_captured": 0,
            "group_capture_failed": 0,
            "group_capture_skipped": max_group_pages,
            "blocked_by_systemic_failure": True,
            "failure_signature": "meetup_isolated_capture_timeout",
        }
        (out_dir / "meetup-capture-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return receipt
    if not queue.empty():
        return queue.get()
    receipt = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "meetup_buffalo",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "meetup_authorized_read_only_attendee_names_no_rsvp_no_message",
        "category_ids": [row[0] for row in _MEETUP_CATEGORY_URLS],
        "status": "FAILED",
        "error": f"Meetup Buffalo capture exited {proc.exitcode} without a receipt",
        "evidence_path": None,
        "groups_captured": 0,
    }
    (out_dir / "meetup-capture-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


# --- Live ATS application-form capture (read-only) --------------------------
# Captures the rendered application form's field schema so a human-promoted
# site policy can later drive inspect_ats_form -> build_application_plan. This
# is strictly read-only: a credentialless GET (Greenhouse API) or a read-only
# DOM element query. No field is written and no application is created.

# Generic read-only form-field element query: returns one row per input.
_ATS_FORM_EXTRACT_JS = (
    "(function(){"
    "var out=[];"
    "var els=[].slice.call(document.querySelectorAll('input,select,textarea'));"
    "for (var i=0;i<els.length;i++){"
    "var e=els[i];"
    "var t=(e.type||'').toLowerCase();"
    "if(e.tagName==='INPUT' && (t==='hidden'||t==='submit'||t==='button')) continue;"
    "var id=e.id||'';"
    "var label='';"
    "if(e.getAttribute('aria-label')) label=e.getAttribute('aria-label');"
    "else if(id){var l=document.querySelector('label[for=\"'+id+'\"]'); if(l) label=l.innerText;}"
    "if(!label){var lc=e.closest('label'); if(lc) label=lc.innerText;}"
    "var options=[];"
    "if(e.tagName==='SELECT'){for(var j=0;j<e.options.length;j++){var ov=e.options[j].text.trim(); if(ov) options.push(ov);}}"
    "out.push({tag:e.tagName.toLowerCase(), type:t, id:id, name:e.name||'',"
    "aria:e.getAttribute('aria-label')||'', label:(label||'').trim().slice(0,120),"
    "required:!!(e.required||e.getAttribute('aria-required')==='true'), options:options.slice(0,40)});"
    "}"
    "return JSON.stringify(out.slice(0,120));"
    "})()"
)

# HTML/DOM field-type -> neutral vocabulary consumed by application_plan.
_ATS_SENSITIVE_NEEDLES = (
    ("work_authorization", ("legally authorized", "work authorization", "sponsorship", "visa")),
    ("self_identification", ("gender", "race", "veteran", "disability", "ethnicity", "self-identif")),
    ("salary", ("salary", "compensation")),
    ("clearance", ("clearance",)),
)
_APPLICATION_WNY_MARKERS = ("buffalo", "east aurora", "williamsville", "amherst", "cheektowaga")


def _classify_application_workplace(location: str, provider_workplace_type: str = "") -> str:
    text = str(location or "").lower()
    provider = (
        str(provider_workplace_type or "")
        .lower()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )
    wny = any(marker in text for marker in _APPLICATION_WNY_MARKERS)
    if wny and provider == "hybrid":
        return "WNY_HYBRID"
    if wny:
        return "WNY_ONSITE"
    if provider == "remote" or "remote" in text:
        return "REMOTE"
    if provider in {"onsite", "inperson", "hybrid"} and text and text != "unknown":
        return "ONSITE_ELSEWHERE"
    return "AMBIGUOUS"


def _extract_js_assignment_object(html: str, marker: str) -> dict[str, Any] | None:
    idx = html.find(marker)
    if idx < 0:
        return None
    start = html.find("{", idx)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    quote = ""
    for pos in range(start, len(html)):
        ch = html[pos]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in {'"', "'"}:
            in_string = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : pos + 1])
                except ValueError:
                    return None
    return None


def _ashby_application_metadata_from_html(html: str, url: str) -> dict[str, Any] | None:
    app_data = _extract_js_assignment_object(html, "window.__appData")
    if not isinstance(app_data, dict):
        return None
    posting = app_data.get("posting")
    if not isinstance(posting, dict):
        return None
    location = str(posting.get("locationName") or "").strip()
    secondary = [
        str(item).strip()
        for item in posting.get("secondaryLocationNames") or []
        if str(item).strip()
    ]
    display_parts = [part for part in [location, *secondary] if part]
    provider_workplace = str(posting.get("workplaceType") or "").strip()
    organization = app_data.get("organization")
    return {
        "source": "ashby_window_app_data",
        "authority": "apply_page",
        "url": url,
        "title": posting.get("title"),
        "organization": organization.get("name") if isinstance(organization, dict) else None,
        "location_display": "; ".join(display_parts) if display_parts else None,
        "primary_location": location or None,
        "secondary_locations": secondary,
        "provider_workplace_type": provider_workplace or None,
        "workplace_type": _classify_application_workplace(location, provider_workplace),
    }


def _fetch_ashby_application_metadata(apply_url: str) -> dict[str, Any] | None:
    if "ashbyhq.com" not in str(apply_url or "").lower():
        return None
    try:
        import httpx

        response = httpx.get(apply_url, follow_redirects=True, timeout=20)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - supplemental evidence, not form capture itself
        logger.info("ashby application metadata fetch failed for {}: {}", apply_url, exc)
        return None
    return _ashby_application_metadata_from_html(response.text, apply_url)


def _workday_application_metadata_from_html(html_text: str, url: str) -> dict[str, Any] | None:
    import html as _html
    import re

    match = re.search(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    try:
        data = json.loads(_html.unescape(match.group(1)).strip())
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("@type") != "JobPosting":
        return None
    organization = data.get("hiringOrganization")
    location = data.get("jobLocation")
    address = location.get("address") if isinstance(location, dict) else None
    locality = ""
    if isinstance(address, dict):
        locality = str(address.get("addressLocality") or "").strip()
    identifier = data.get("identifier")
    provider_workplace = str(data.get("jobLocationType") or "").strip()
    return {
        "source": "workday_json_ld_job_posting",
        "authority": "apply_page",
        "url": url,
        "title": data.get("title"),
        "organization": organization.get("name") if isinstance(organization, dict) else None,
        "location_display": locality or None,
        "primary_location": locality or None,
        "secondary_locations": [],
        "provider_workplace_type": provider_workplace or None,
        "workplace_type": _classify_application_workplace(locality, provider_workplace),
        "job_req_id": identifier.get("value") if isinstance(identifier, dict) else None,
        "date_posted": data.get("datePosted"),
        "employment_type": data.get("employmentType"),
    }


def _fetch_workday_application_metadata(apply_url: str) -> dict[str, Any] | None:
    if "myworkdayjobs.com" not in str(apply_url or "").lower():
        return None
    try:
        import httpx

        response = httpx.get(apply_url, follow_redirects=True, timeout=20)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - supplemental evidence, not a submit effect
        logger.info("workday application metadata fetch failed for {}: {}", apply_url, exc)
        return None
    return _workday_application_metadata_from_html(response.text, apply_url)


def _ats_provider_from_url(url: str) -> tuple[str, str, str]:
    """Parse (provider, site, posting_id) from a known ATS apply URL.

    Returns ("unknown", host, "") when the host is not a recognized ATS.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    parts = [p for p in parsed.path.split("/") if p]
    if "greenhouse.io" in host:
        # boards.greenhouse.io/<board>/jobs/<id> or job-boards.../<board>/jobs/<id>
        site = parts[0] if parts else ""
        posting = parts[parts.index("jobs") + 1] if "jobs" in parts and parts.index("jobs") + 1 < len(parts) else (parts[-1] if parts else "")
        return "greenhouse", site, posting
    if "ashbyhq.com" in host:
        posting_parts = [part for part in parts[1:] if part != "application"]
        posting_id = posting_parts[-1] if posting_parts else (parts[-1] if parts else "")
        return "ashby", (parts[0] if parts else ""), posting_id
    if "lever.co" in host:
        return "lever", (parts[0] if parts else ""), (parts[-1] if parts else "")
    if "myworkdayjobs.com" in host:
        return "workday", (parts[0] if parts else host.split(".")[0]), (parts[-1] if parts else "")
    return "unknown", host, (parts[-1] if parts else "")


def _ats_field_type(label: str, tag: str, input_type: str, has_options: bool) -> str:
    lowered = label.lower()
    for field_type, needles in _ATS_SENSITIVE_NEEDLES:
        if any(needle in lowered for needle in needles):
            return field_type
    if input_type == "file":
        return "file"
    if tag == "textarea":
        return "free_text"
    if tag == "select" or has_options:
        return "choice"
    if "email" in lowered or input_type == "email":
        return "email"
    if "phone" in lowered or input_type == "tel":
        return "phone"
    return "text"


def _generic_form_from_dom(
    provider: str,
    site: str,
    posting_id: str,
    url: str,
    rows: list[dict[str, Any]],
    application_page: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields = []
    accepted_attachments: list[str] = []
    seen: set[str] = set()
    for row in rows:
        label = str(row.get("label") or row.get("aria") or row.get("name") or "").rstrip("*").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        tag = str(row.get("tag") or "")
        input_type = str(row.get("type") or "")
        options = [str(o) for o in row.get("options", []) if str(o).strip()]
        field_type = _ats_field_type(label, tag, input_type, bool(options))
        element_id = row.get("id") or ""
        fields.append(
            {
                "name": label,
                "field_type": field_type,
                "required": bool(row.get("required")),
                "options": options,
                "selector": f"#{element_id}" if element_id else None,
            }
        )
        if field_type == "file":
            accepted_attachments.append(label)
    if not fields:
        raise BrowserCaptureError("ATS_DOM_CAPTURE_EMPTY")
    form = {
        "provider": provider,
        "site": site,
        "posting_id": posting_id,
        "url": url,
        "title": application_page.get("title") if application_page else None,
        "organization": application_page.get("organization") if application_page else None,
        "location": application_page.get("location_display") if application_page else None,
        "workplace_type": application_page.get("workplace_type") if application_page else None,
        "application_page": application_page,
        "fields": fields,
        "accepted_attachments": accepted_attachments,
        "policy_observations": [
            "Captured read-only from the rendered application form DOM; no form write, no application created.",
        ],
    }
    return form


def capture_ats_form(apply_url: str, out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    """Read-only capture of one top job's ATS application-form schema.

    Greenhouse: credentialless job-board API (no browser). Other providers or
    an API miss: read-only DOM element query of the rendered form via surf. The
    captured schema lets a human-promoted site policy later drive
    inspect_ats_form -> build_application_plan. Strictly read-only.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    provider, site, posting_id = _ats_provider_from_url(apply_url or "")
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.ats_form_capture_receipt.v1",
        "apply_url": apply_url,
        "provider": provider,
        "site": site,
        "posting_id": posting_id,
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "read_only_no_form_write",
    }
    if not apply_url:
        receipt["status"] = "NO_URL"
        return receipt
    form: dict[str, Any] | None = None
    application_page = None
    if provider == "ashby":
        application_page = _fetch_ashby_application_metadata(apply_url)
    elif provider == "workday":
        application_page = _fetch_workday_application_metadata(apply_url)
    tab_id = ""
    try:
        if provider == "greenhouse" and site and posting_id:
            from .ats.greenhouse import GreenhouseFormError, fetch_greenhouse_form

            try:
                form = fetch_greenhouse_form(site, posting_id)
                receipt["capture_method"] = "greenhouse_api"
            except GreenhouseFormError as exc:
                logger.info("greenhouse API miss for {} ({}); falling back to DOM", apply_url, exc)
        if form is None and provider == "workday" and application_page:
            form = {
                "provider": provider,
                "site": site,
                "posting_id": posting_id,
                "url": apply_url,
                "title": application_page.get("title"),
                "organization": application_page.get("organization"),
                "location": application_page.get("location_display"),
                "workplace_type": application_page.get("workplace_type"),
                "application_page": application_page,
                "fields": [],
                "accepted_attachments": [],
                "policy_observations": [
                    "Captured read-only from Workday JobPosting JSON-LD on the public job page.",
                    "No anonymous Workday application form fields were exposed; human/authorized browser session may be required before field capture.",
                    "No form write, account creation, sign-in, or application submit was performed.",
                ],
            }
            receipt["capture_method"] = "workday_job_page_json_ld"
        if form is None:
            ensure_browser(surf_run)
            created = _surf(surf_run, "tab.new", apply_url, "--json", timeout=30)
            tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
            if not tab_id:
                raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
            _surf_pause(surf_run, "7")
            raw = _surf_js(surf_run, tab_id, _ATS_FORM_EXTRACT_JS, timeout=25)
            rows = json.loads(json.loads(raw))
            form = _generic_form_from_dom(provider, site, posting_id, apply_url, rows, application_page)
            receipt["capture_method"] = "surf_read_only_dom"
        form_path = out_dir / f"ats-form-{(site or 'site')}-{(posting_id or 'id')}.json"
        form_path.write_text(json.dumps(form, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        required = [f["name"] for f in form["fields"] if f.get("required")]
        human_required = [f["name"] for f in form["fields"] if f["field_type"] in {"free_text", "choice", "work_authorization", "self_identification", "salary", "clearance"}]
        receipt["status"] = "OK"
        receipt["form_path"] = str(form_path)
        receipt["field_count"] = len(form["fields"])
        receipt["required_fields"] = required
        receipt["human_required_fields"] = human_required
        receipt["accepted_attachments"] = form.get("accepted_attachments", [])
        if application_page:
            receipt["application_page"] = application_page
            receipt["application_page_location"] = application_page.get("location_display")
            receipt["application_page_workplace_type"] = application_page.get("workplace_type")
            receipt["application_page_location_authority"] = application_page.get("authority")
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.warning("ATS form capture failed for {}: {}", apply_url, exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "ATS form")
    return receipt


def _load_candidate_profile() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "config" / "candidate_profile.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_LINKEDIN_GUEST_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Guest-card grammar (server-rendered, stable base-card markup): per-card title,
# company anchor text, location span, post-date datetime attr, and the /jobs/view
# link. Bounded known grammar with live fixtures — not open-ended HTML parsing.
_GUEST_CARD_SPLIT = '<div class="base-card'
_GUEST_FIELD_RES = {
    "title": r"base-search-card__title[^>]*>\s*([^<]+)",
    "company": r"base-search-card__subtitle[^>]*>\s*<a[^>]*>\s*([^<]+)",
    "location": r"job-search-card__location[^>]*>\s*([^<]+)",
    "posted": r'datetime="([0-9-]+)"',
    "href": r'href="(https://www\.linkedin\.com/jobs/view/[^"?]+)',
}


def _linkedin_guest_search(queries: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Fetch each query via LinkedIn's guest search fragments (plain HTTP GET).

    Returns (query_label, row) pairs; empty list if the endpoint fails so the
    caller can fall back to the browser. Read-only public content, no session.
    """
    import html as _html
    import re as _re

    import httpx

    rows: list[tuple[str, dict[str, Any]]] = []
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"}) as client:
            for query in queries:
                qs = query["url"].split("?", 1)[-1]
                try:
                    resp = client.get(f"{_LINKEDIN_GUEST_SEARCH}?{qs}&start=0")
                    if resp.status_code != 200:
                        continue
                except httpx.HTTPError:
                    continue
                for card in resp.text.split(_GUEST_CARD_SPLIT)[1:]:
                    fields = {}
                    for name, pattern in _GUEST_FIELD_RES.items():
                        m = _re.search(pattern, card)
                        fields[name] = _html.unescape(m.group(1).strip()) if m else ""
                    if not fields["title"]:
                        continue
                    rows.append((query["label"], {
                        "title": fields["title"],
                        "company": fields["company"],
                        "location": fields["location"],
                        "href": fields["href"],
                        "posted": fields["posted"] or None,
                    }))
    except Exception as exc:  # noqa: BLE001 - guest path is best-effort; browser is the fallback
        logger.warning("linkedin guest search failed: {}", exc)
        return []
    return rows


def _finish_linkedin_advanced(
    out_dir: Path,
    receipt: dict[str, Any],
    accumulated: dict[str, dict[str, Any]],
    queries_run: list[str],
) -> dict[str, Any]:
    """Write advanced-search evidence + receipt from accumulated rows."""
    opps = [
        {
            "source": "human_authorized_linkedin_advanced_search",
            "observed_at": utc_now(),
            "title": r["title"],
            "organization": (r.get("company") or "UNKNOWN").strip() or "UNKNOWN",
            "location": (r.get("location") or "UNKNOWN").strip() or "UNKNOWN",
            "primary_evidence_url": r.get("href") or _LINKEDIN_JOB_SEARCH_BASE,
            "matched_query": r.get("matched_query", ""),
            "published_at": r.get("posted"),
            "top_candidate": False,
        }
        for r in accumulated.values()
    ]
    evidence = {
        "schema_version": "ops-linkedin.opportunity_capture.v1",
        "source": "human_authorized_linkedin_advanced_search",
        "capture_method": receipt.get("capture_method", "surf_read_only_authenticated_session"),
        "automation_policy": "linkedin_authorized_read_only_no_actions",
        "observed_at": utc_now(),
        "queries_run": queries_run,
        "opportunities": opps,
    }
    evidence_path = out_dir / "linkedin-advanced-search-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
    receipt["status"] = "OK" if opps else "EMPTY"
    receipt["evidence_path"] = str(evidence_path)
    receipt["opportunities_captured"] = len(opps)
    receipt["queries_run"] = queries_run
    (out_dir / "linkedin-advanced-search-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


# New (2026) virtualized search UI: cards are found via the accessibility-mandated
# aria-labels ('Dismiss <title> job'), then the enclosing card's text carries
# company/location plus the PREMIUM signals: 'Be an early applicant' (low
# competition), 'connection works here' (warm path), and the posted age.
_LI_ARIA_EXTRACT_JS = (
    "(function(){var out=[];"
    "var btns=[].slice.call(document.querySelectorAll('button[aria-label^=\"Dismiss\"]'));"
    "for(var i=0;i<btns.length;i++){"
    "var al=btns[i].getAttribute('aria-label')||'';"
    "var title=al.replace(/^Dismiss\\s*/,'').replace(/\\s*job$/,'').trim();"
    "if(!title||title.toLowerCase()==='dismiss'||title===al)continue;"
    "var card=btns[i].parentElement;var best=null;"
    "for(var d=0;d<12&&card;d++){var t=card.innerText||'';"
    "if(/ago/.test(t)&&t.length<1200){best=card;}"
    "if(t.length>1500)break;card=card.parentElement;}"
    "var txt=best?best.innerText:'';"
    "var lines=txt.split(String.fromCharCode(10))"
    ".map(function(s){return s.trim()}).filter(Boolean);"
    "var ti=lines.indexOf(title);"
    "var detail=ti>=0?lines.slice(ti+1).filter(function(s){return !/\\bwith verification\\b/i.test(s);}):[];"
    "var company=detail[0]||'';"
    "var loc=detail[1]||'';"
    "var warm=/connection works here|connections work here|school alumni/.test(txt);"
    "var early=/Be an early applicant/.test(txt);"
    "var age=(txt.match(/(\\d+ (?:minute|hour|day|week|month)s? ago)/)||[])[1]||null;"
    # Per-job link. Without it every row inherits the generic search URL, which
    # made job-insights read the SAME page 8x and attribute one page's numbers
    # to 8 different jobs (2026-08-13). The virtualized card renders NO anchor
    # of its own (verified live: card subtree has 0 <a>); the job id lives in an
    # ancestor's componentkey="job-card-component-ref-<id>". Fall back to any
    # in-card anchor for older/other layouts.
    "var href=null;"
    "var walk=btns[i];"
    "for(var k=0;k<12&&walk&&!href;k++){"
    "var ck=walk.getAttribute&&walk.getAttribute('componentkey');"
    "var cm=ck&&ck.match(/job-card-component-ref-(\\d+)/);"
    "if(cm){href='https://www.linkedin.com/jobs/view/'+cm[1]+'/';}"
    "walk=walk.parentElement;}"
    "if(!href&&best){var a=best.querySelector(\"a[href*='/jobs/view/']\");"
    "if(a){href=a.href.split('?')[0];}"
    "else{var a2=best.querySelector(\"a[href*='currentJobId=']\");"
    "if(a2){var m=a2.href.match(/currentJobId=(\\d+)/);"
    "if(m){href='https://www.linkedin.com/jobs/view/'+m[1]+'/';}}}}"
    "out.push({title:title,company:company,location:loc,warm:warm,early:early,"
    "age:age,href:href});"
    "}return JSON.stringify(out);})()"
)


def capture_linkedin_premium(
    out_dir: Path,
    surf_run: Path = SURF_RUN_DEFAULT,
    profile: dict[str, Any] | None = None,
    max_queries: int = 3,
) -> dict[str, Any]:
    """Read-only capture of LinkedIn Premium low-competition search results.

    Runs the profile's search queries with f_EA=true (Under 10 applicants) so
    LinkedIn's own engine pre-filters for the response-first thesis, then
    extracts each card via aria-labels (stable against class churn). Cards carry
    the premium signals the ranker wants: under-10-applicants -> competition 0.1,
    'connection works here' -> warm_path 0.9. Strictly read-only navigation of
    the human's authenticated session; no LinkedIn action is taken.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = profile if profile is not None else _load_candidate_profile()
    queries = linkedin_search_queries_from_profile(profile)[:max_queries]
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "linkedin_premium_under10",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "linkedin_authorized_read_only_no_actions",
        "queries_planned": [q["label"] for q in queries],
    }
    tab_id = ""
    rows: list[dict[str, Any]] = []
    queries_run: list[str] = []
    query_failures: list[dict[str, str]] = []
    # Two Premium filter lanes per query (LinkedIn URL params, brave-search
    # verified 2026-08-12): f_EA=true = Under 10 applicants (low competition);
    # f_JIYN=true = jobs at companies where Graham has connections (every result
    # is a warm path by construction).
    lanes = [("under-10-applicants", "f_EA=true", False),
             ("in-your-network", "f_JIYN=true", True),
             # First-mover slot: posted <24h AND still under 10 applicants.
             ("fresh-24h-under10", "f_TPR=r86400&f_EA=true", False)]
    plan = [(q, lane) for q in queries for lane in lanes]
    try:
        ensure_browser(surf_run)
        first_url = plan[0][0]["url"] + "&" + plan[0][1][1]
        created = _surf(surf_run, "tab.new", first_url, "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
        for pi, (query, (lane_label, lane_param, lane_warm)) in enumerate(plan):
            try:
                if pi > 0:
                    url = query["url"] + "&" + lane_param
                    _surf_js(surf_run, tab_id, _nav_js(url), timeout=20)
                _surf_pause(surf_run, "8")
                raw = _surf_js(surf_run, tab_id, _LI_ARIA_EXTRACT_JS, timeout=30)
                for r in _surf_json_value(raw, []):
                    if r.get("title"):
                        r["matched_query"] = query["label"] + " | " + lane_label
                        if lane_warm:
                            r["warm"] = True  # network presence is the filter itself
                        rows.append(r)
                label = query["label"] + " | " + lane_label
                queries_run.append(label)
            except (BrowserCaptureError, ValueError, json.JSONDecodeError,
                    subprocess.TimeoutExpired) as exc:
                logger.warning("premium query {!r} skipped: {}", query["label"], exc)
                query_failures.append(
                    {
                        "query": query["label"] + " | " + lane_label,
                        "error": str(exc)[:300],
                    }
                )
        seen: dict[str, dict[str, Any]] = {}
        for r in rows:
            key = r["title"] + "|" + (r.get("company") or "")
            if key in seen:  # same job from both lanes -> union the signals
                seen[key]["warm"] = bool(seen[key].get("warm") or r.get("warm"))
                seen[key]["early"] = bool(seen[key].get("early") or r.get("early"))
            else:
                seen[key] = r
        opps = [
            {
                "source": "human_authorized_linkedin_advanced_search",
                "observed_at": utc_now(),
                "title": r["title"],
                "organization": (r.get("company") or "UNKNOWN").strip() or "UNKNOWN",
                "location": (r.get("location") or "UNKNOWN").strip() or "UNKNOWN",
                "primary_evidence_url": r.get("href") or _LINKEDIN_JOB_SEARCH_BASE,
                "matched_query": r.get("matched_query", ""),
                "posted_age": r.get("age"),
                "under_10_applicants": bool(r.get("early")),
                "warm_path": 0.9 if r.get("warm") else 0.0,
                "warm_path_via": "LinkedIn: connection works here" if r.get("warm") else None,
                "top_candidate": False,
            }
            for r in seen.values()
        ]
        evidence = {
            "schema_version": "ops-linkedin.opportunity_capture.v1",
            "source": "human_authorized_linkedin_advanced_search",
            "capture_method": "surf_read_only_authenticated_session_premium_under10",
            "automation_policy": "linkedin_authorized_read_only_no_actions",
            "observed_at": utc_now(),
            "queries_run": queries_run,
            "opportunities": opps,
        }
        evidence_path = out_dir / "linkedin-premium-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        if opps:
            receipt["status"] = "OK"
        elif query_failures and len(query_failures) == len(plan):
            receipt["status"] = "FAILED"
            receipt["error"] = "all LinkedIn Premium browser queries failed"
        else:
            receipt["status"] = "EMPTY"
        receipt["evidence_path"] = str(evidence_path)
        receipt["opportunities_captured"] = len(opps)
        receipt["top_applicant_count"] = sum(1 for o in opps if o.get("top_candidate") is True)
        receipt["easy_apply_count"] = sum(1 for o in opps if o.get("easy_apply") is True)
        receipt["under_10_applicants_count"] = sum(1 for o in opps if o.get("under_10_applicants") is True)
        receipt["warm_paths_found"] = sum(1 for o in opps if o["warm_path"])
        receipt["queries_run"] = queries_run
        receipt["query_failures"] = query_failures
    except (BrowserCaptureError, ValueError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        logger.error("LinkedIn premium capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["evidence_path"] = None
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "premium capture")
    (out_dir / "linkedin-premium-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def _page_text(surf_run: Path, tab_id: str, limit: int = 20000) -> str:
    """Read-only innerText snapshot of the current page (bounded)."""
    raw = _surf_js(
        surf_run,
        tab_id,
        f"(function(){{return JSON.stringify(document.body.innerText.slice(0,{limit}));}})()",
        timeout=30,
    )
    return json.loads(json.loads(raw))


def capture_linkedin_job_insights(
    job_urls: list[str],
    surf_run: Path = SURF_RUN_DEFAULT,
) -> dict[str, dict[str, Any]]:
    """Premium per-job insights for a BOUNDED set of jobs (the digest top).

    Visits each LinkedIn job page read-only and parses the Premium competitive
    insights from the page text: applicant-rank percentile ('top N% of
    applicants'), applicant count, and salary range when shown. Returns
    {url: {applicant_rank_pct, applicants, salary, insights_text}}. Fail-soft:
    a page that won't load or shows no insights simply yields {}.
    """
    import re as _re

    out: dict[str, dict[str, Any]] = {}
    li_urls = [u for u in job_urls if u and "linkedin.com/jobs" in u][:8]
    if not li_urls:
        return out
    tab_id = ""
    try:
        ensure_browser(surf_run)
        created = _surf(surf_run, "tab.new", li_urls[0], "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            return out
        for ui, url in enumerate(li_urls):
            try:
                if ui > 0:
                    _surf_js(surf_run, tab_id, _nav_js(url), timeout=20)
                _surf_pause(surf_run, "7")
                text = _page_text(surf_run, tab_id)
            except (BrowserCaptureError, ValueError, subprocess.TimeoutExpired) as exc:
                logger.warning("job insights skipped for {}: {}", url[:60], exc)
                continue
            # Guard: the search-results chrome ("Under 10 applicants" filter chip,
            # sidebar cards) parses as job data. Only read insights when the page
            # actually IS a job view for the requested id.
            job_id = (_re.search(r"/jobs/view/(\d+)", url) or [None, None])[1]
            on_job_page = bool(job_id) and (
                "people clicked apply" in text.lower()
                or "applicant" in text.lower()
                and "Under 10 applicants" not in text
            )
            if not on_job_page:
                logger.warning("job insights: {} did not render a job view; skipping", url[:70])
                continue
            info: dict[str, Any] = {}
            rank = _re.search(r"top (\d+)% of (?:\d+ )?applicants|in the top (\d+)%", text, _re.I)
            if rank:
                info["applicant_rank_pct"] = int(rank.group(1) or rank.group(2))
            # 'Under 10 applicants' is a FILTER CHIP, not job data — exclude it.
            count = _re.search(
                r"(?<!Under )\b(\d+)\s+(?:people clicked apply|applicants)\b", text, _re.I
            )
            if count:
                info["applicants"] = int(count.group(1))
            salary = _re.search(
                r"(\$[\d,.]+(?:K)?(?:/yr)?\s*[-–]\s*\$[\d,.]+(?:K)?(?:/yr)?|\$[\d,.]+K?/yr)", text
            )
            if salary:
                info["salary"] = salary.group(1).rstrip(".,").strip()
            if info:
                out[url] = info
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "job insight")
    # FAIL CLOSED on the 2026-08-13 defect: >2 jobs all reporting byte-identical
    # insights means we read one page repeatedly, not N jobs. Wrong-but-plausible
    # per-job facts are worse than no facts, so emit nothing.
    if len(out) > 2:
        fingerprints = {json.dumps(v, sort_keys=True) for v in out.values()}
        if len(fingerprints) == 1:
            logger.error(
                "job insights identical across {} jobs — page navigation failed; discarding",
                len(out),
            )
            return {}
    return out


_WHO_VIEWED_URL = "https://www.linkedin.com/analytics/profile-views/"


def capture_linkedin_who_viewed(
    out_dir: Path,
    surf_run: Path = SURF_RUN_DEFAULT,
) -> dict[str, Any]:
    """Read-only capture of Premium 'Who viewed your profile' — INBOUND leads.

    People who viewed the profile already showed interest: the warmest possible
    top-of-funnel for both employment and consulting. Parses viewer name /
    headline / when from the analytics page text; 'X at ORG' headlines yield the
    org for the warm-paths overlay. Honest EMPTY when the page yields nothing.
    """
    import re as _re

    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "linkedin_who_viewed",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "linkedin_authorized_read_only_no_actions",
    }
    tab_id = ""
    viewers: list[dict[str, Any]] = []
    try:
        ensure_browser(surf_run)
        created = _surf(surf_run, "tab.new", _WHO_VIEWED_URL, "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
        _surf_pause(surf_run, "8")
        text = _page_text(surf_run, tab_id, 30000)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        # Observed block shape (live 2026-08-12): name / '• 2nd|3rd' degree /
        # headline / 'Viewed Nh ago'. Anchor on the Viewed line, walk back.
        # Page chrome is not a person. "Sort by most recent" was captured as a
        # viewer and sent through the research pass (2026-08-13 digest), so UI
        # controls are excluded explicitly. A real viewer name also has no verb
        # phrasing and at least two characters of a given name.
        _junk = _re.compile(
            r"viewed|profile|premium|upgrade|search appearance|view all|pending|"
            r"graham anderson|^•|^\d+$|sort by|filter|most recent|show more|"
            r"see all|all filters|^results?$|^people$|dismiss|^back$", _re.I,
        )
        seen_names: set[str] = set()
        for i, ln in enumerate(lines):
            m = _re.match(
                r"Viewed\s+(\d+[hdwm]o?\s+ago|\d+ (?:hour|day|week|month)s? ago)", ln, _re.I
            )
            if not m or i < 3:
                continue
            headline = lines[i - 1]
            degree = lines[i - 2]
            name = lines[i - 3]
            if not degree.startswith("•"):  # some blocks omit the degree bullet
                headline, name = lines[i - 1], lines[i - 2]
            if _junk.search(name) or not (2 < len(name) < 60) or name in seen_names:
                continue
            seen_names.add(name)
            # Org from the headline. "X at Y" is the common shape, but many
            # headlines use "Y | role" or "role @Y" or bare "Y" (2 of 4 viewers
            # yielded None on 2026-08-13), so try those too before giving up.
            org = None
            for pat in (
                r"\bat @?([A-Z][\w&.' -]{2,40}?)(?:\s*[|,•]|$)",
                r"@([A-Z][\w&.'-]{2,40})",
                r"^([A-Z][\w&.' -]{2,40}?)\s*[|]",
            ):
                om = _re.search(pat, headline)
                if om:
                    org = om.group(1).strip().rstrip(".,")
                    break
            viewers.append({"name": name, "degree": degree.lstrip("• ").strip(), "headline": headline[:120], "org": org,
                            "when": m.group(1)})
            if len(viewers) >= 20:
                break
        receipt["extract_strategy"] = "text_blocks"
        if not viewers:
            # SELF-HEAL: the text-block heuristic is layout-sensitive. Before
            # reporting EMPTY, retry with the anchor-based strategy (profile
            # links + card climb), which survives most layout reshuffles.
            try:
                alt = json.loads(json.loads(
                    _surf_js(surf_run, tab_id, _PEOPLE_EXTRACT_JS, timeout=30)
                ))
                for c in alt:
                    viewers.append({"name": c.get("name"), "degree": c.get("degree"), "headline": c.get("current") or "",
                                    "org": c.get("org"), "when": None, "profile": c.get("profile")})
                if viewers:
                    receipt["extract_strategy"] = "anchor_fallback"
                    logger.warning(
                        "who-viewed text-block parser found 0; anchor fallback recovered {}",
                        len(viewers),
                    )
            except (BrowserCaptureError, ValueError, subprocess.TimeoutExpired):
                pass
        if not viewers:
            # Both strategies dry: that is a maintainer signal, not just an EMPTY.
            receipt["needs_attention"] = {
                "reason": "who_viewed_parsers_both_empty",
                "hint": "LinkedIn likely reshaped the profile-views page; "
                        "re-derive the block shape from a live screenshot "
                        "(see capture_linkedin_who_viewed).",
            }
        receipt["status"] = "OK" if viewers else "EMPTY"
        receipt["viewers_captured"] = len(viewers)
    except (BrowserCaptureError, ValueError, subprocess.TimeoutExpired) as exc:
        logger.warning("who-viewed capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "LinkedIn who-viewed")
    evidence_path = out_dir / "linkedin-who-viewed.json"
    evidence_path.write_text(
        json.dumps({"schema_version": "monitor_opportunities.who_viewed.v1",
                    "observed_at": utc_now(), "viewers": viewers}, indent=1),
        encoding="utf-8",
    )
    receipt["evidence_path"] = str(evidence_path)
    (out_dir / "linkedin-who-viewed-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


# People search: actively-hiring 1st/2nd-degree connections (param discovered
# live 2026-08-12 by clicking the filter: activelyHiringForJobTitles=["-100"]
# means 'any job title'). Every result is a warm hiring contact by construction.
_ACTIVELY_HIRING_URL = (
    "https://www.linkedin.com/search/results/people/"
    "?keywords={kw}&network=%5B%22F%22%2C%22S%22%5D"
    "&activelyHiringForJobTitles=%5B%22-100%22%5D"
)

_PEOPLE_EXTRACT_JS = (
    "(function(){var out=[],seen={};"
    "var as=[].slice.call(document.querySelectorAll('main a[href*=\"/in/\"]'));"
    "for(var i=0;i<as.length;i++){var a=as[i];var prof=a.href.split('?')[0];"
    "var name=(a.innerText||'').trim().split(String.fromCharCode(10))[0];"
    "if(!name||name.length<3||name.length>50||seen[prof])continue;"
    "var card=a,best=null;"
    "for(var d=0;d<10&&card;d++){card=card.parentElement;if(!card)break;"
    "var t=card.innerText||'';"
    "if(/Current:|mutual connection/.test(t)&&t.length<700){best=card;}"
    "if(t.length>=700)break;}"
    "if(!best)continue;var txt=best.innerText;"
    "var first=(txt.split(String.fromCharCode(10))[0]||'').trim();"
    "if(first.indexOf(name)!==0)continue;seen[prof]=1;"
    "var cur=(txt.match(/Current: ([^\\n]+)/)||[])[1]||'';"
    "var deg=(txt.match(/\\u2022 (1st|2nd|3rd)/)||[])[1]||'';"
    "var mut=(txt.match(/([\\w ,.&]+(?:& \\d+ other)? mutual connections?)/)||[])[1]||null;"
    "var org=(cur.match(/\\bat (.+)$/)||[])[1]||null;"
    "out.push({name:name,degree:deg,current:cur.slice(0,90),org:org,"
    "mutuals:mut?mut.slice(0,70):null,profile:prof});}"
    "return JSON.stringify(out.slice(0,15));})()"
)


def capture_linkedin_actively_hiring(
    out_dir: Path,
    surf_run: Path = SURF_RUN_DEFAULT,
    keywords: str = "AI%20engineering",
) -> dict[str, Any]:
    """Actively-hiring people in the 1st/2nd-degree network — warm hiring leads.

    Read-only people search with LinkedIn's actively-hiring filter. Each contact
    comes with the mutual connections that form the referral path. Serves BOTH
    tracks: employment (a hiring manager you can be introduced to) and
    consulting (a leader with budget and urgency, warm by network).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "linkedin_actively_hiring",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "linkedin_authorized_read_only_no_actions",
    }
    tab_id = ""
    contacts: list[dict[str, Any]] = []
    try:
        ensure_browser(surf_run)
        created = _surf(surf_run, "tab.new", _ACTIVELY_HIRING_URL.format(kw=keywords), "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
        _surf_pause(surf_run, "8")
        contacts = json.loads(json.loads(
            _surf_js(surf_run, tab_id, _PEOPLE_EXTRACT_JS, timeout=30)
        ))
        receipt["status"] = "OK" if contacts else "EMPTY"
        receipt["contacts_captured"] = len(contacts)
    except (BrowserCaptureError, ValueError, subprocess.TimeoutExpired) as exc:
        logger.warning("actively-hiring capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "LinkedIn actively-hiring")
    evidence_path = out_dir / "linkedin-actively-hiring.json"
    evidence_path.write_text(
        json.dumps({"schema_version": "monitor_opportunities.actively_hiring.v1",
                    "observed_at": utc_now(), "contacts": contacts}, indent=1),
        encoding="utf-8",
    )
    receipt["evidence_path"] = str(evidence_path)
    (out_dir / "linkedin-actively-hiring-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def capture_linkedin_advanced_search(
    out_dir: Path,
    surf_run: Path = SURF_RUN_DEFAULT,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only capture of LinkedIn ADVANCED SEARCH from the authenticated session.

    Leverages LinkedIn's own search engine (server-side filtering on Graham's
    mandates + workplace/seniority preferences) instead of scrolling the
    virtualized top-applicant list. Fewer surf calls, higher relevance. One tab,
    navigated across the bounded query set; a sign-in wall records AUTH_REQUIRED
    honestly. No LinkedIn automation beyond read-only navigation of the human's
    own authenticated session.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = profile if profile is not None else _load_candidate_profile()
    queries = linkedin_search_queries_from_profile(profile)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "linkedin_advanced_search",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "linkedin_authorized_read_only_no_actions",
        "queries_planned": [q["label"] for q in queries],
    }
    tab_id = ""
    accumulated: dict[str, dict[str, Any]] = {}
    queries_run: list[str] = []
    # Primary: LinkedIn's server-rendered guest search fragments (plain HTTP,
    # read-only, public content). The logged-in search UI moved to a virtualized
    # /jobs/search-results/ page whose list our DOM extractor cannot see
    # (observed 2026-08-12: 0 rows on every query), while the guest endpoint
    # returns parseable cards with title/company/location/post-date.
    guest_rows = _linkedin_guest_search(queries)
    if guest_rows:
        for label, r in guest_rows:
            key = r["title"] + "|" + (r.get("company") or "")
            if key not in accumulated:
                r["matched_query"] = label
                accumulated[key] = r
            if label not in queries_run:
                queries_run.append(label)
        receipt["capture_method"] = "linkedin_guest_http"
        return _finish_linkedin_advanced(out_dir, receipt, accumulated, queries_run)
    logger.warning("linkedin guest search returned 0 rows; falling back to browser capture")
    try:
        ensure_browser(surf_run)
        created = _surf(surf_run, "tab.new", queries[0]["url"], "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
        for qi, query in enumerate(queries):
            # Per-query resilience: a single hung/slow surf js call (LinkedIn
            # pages are heavy) must skip that query, not tank the whole batch.
            try:
                if qi > 0:
                    _surf_js(surf_run, tab_id, _nav_js(query["url"]), timeout=20)
                _surf_pause(surf_run, "6")
                wall = _surf(
                    surf_run,
                    "js",
                    "--tab-id",
                    tab_id,
                    "(function(){return (document.body.innerText.toLowerCase().indexOf('sign in to')>=0 || location.href.indexOf('/login')>=0) ? 'WALL' : 'OK';})()",
                    timeout=20,
                )
                if "WALL" in wall:
                    receipt["status"] = "AUTH_REQUIRED"
                    receipt["error"] = "LinkedIn sign-in wall — no authenticated session in the reachable browser"
                    receipt["evidence_path"] = None
                    return receipt
                rows = _linkedin_scroll_paginate_capture(surf_run, tab_id, max_pages=1)
            except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
                logger.warning("advanced-search query {!r} skipped: {}", query["label"], exc)
                continue
            for r in rows:
                title = (r.get("title") or "").strip()
                if not title:
                    continue
                key = title + "|" + (r.get("company") or "")
                if key not in accumulated:
                    r["matched_query"] = query["label"]
                    accumulated[key] = r
            queries_run.append(query["label"])
        opps = [
            {
                "source": "human_authorized_linkedin_advanced_search",
                "observed_at": utc_now(),
                "title": r["title"],
                "organization": (r.get("company") or "UNKNOWN").strip() or "UNKNOWN",
                "location": (r.get("location") or "UNKNOWN").strip() or "UNKNOWN",
                "primary_evidence_url": r.get("href") or _LINKEDIN_JOB_SEARCH_BASE,
                "matched_query": r.get("matched_query", ""),
                "top_candidate": False,
            }
            for r in accumulated.values()
        ]
        evidence = {
            "schema_version": "ops-linkedin.opportunity_capture.v1",
            "source": "human_authorized_linkedin_advanced_search",
            "capture_method": "surf_read_only_authenticated_session",
            "automation_policy": "linkedin_authorized_read_only_no_actions",
            "observed_at": utc_now(),
            "queries_run": queries_run,
            "opportunities": opps,
        }
        evidence_path = out_dir / "linkedin-advanced-search-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        receipt["status"] = "OK" if opps else "EMPTY"
        receipt["evidence_path"] = str(evidence_path)
        receipt["opportunities_captured"] = len(opps)
        receipt["queries_run"] = queries_run
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.error("LinkedIn advanced-search capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["evidence_path"] = None
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "LinkedIn search")
    (out_dir / "linkedin-advanced-search-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


_SALES_NAV_SAVED_URL = "https://www.linkedin.com/sales/lists/people"

_SALES_NAV_EXTRACT_JS = (
    "(function(){"
    "var out=[],seen={};"
    "var rows=[].slice.call(document.querySelectorAll("
    "'[data-x--people-list-entity], li.artdeco-list__item, tr[data-x-search-result]'));"
    # Fallback: Sales Nav DOM changes often; if the strict row selectors match
    # nothing, derive rows from the lead/people anchors themselves (closest LI/TR).
    "if(!rows.length){"
    "var anchors=[].slice.call(document.querySelectorAll(\"a[href*='/sales/lead/'], a[href*='/sales/people/']\"));"
    "rows=anchors.map(function(a){return a.closest('li,tr,div[class*=entity],div[class*=result]')||a.parentElement;}).filter(Boolean);"
    "}"
    "for (var i=0;i<rows.length;i++){"
    "var lines=(rows[i].innerText||'').split('\\n').map(function(s){return s.trim();}).filter(Boolean);"
    "var uniq=[]; for(var j=0;j<lines.length;j++){ if(lines[j]!==lines[j-1]) uniq.push(lines[j]); }"
    "var name=uniq[0]||''; if(!name||seen[name]) continue; seen[name]=1;"
    "var a=rows[i].querySelector(\"a[href*='/sales/lead/'], a[href*='/sales/people/']\");"
    "out.push({name:name, headline:uniq[1]||'', company:uniq[2]||'', href:a?a.href.split('?')[0]:null});"
    "}"
    "return JSON.stringify(out.slice(0,100));"
    "})()"
)


def capture_sales_navigator_saved(out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    """Read-only capture of the human's OWN saved Sales Navigator lead list.

    CLIENT-PROSPECTING engine (not the jobs engine): captures decision-makers
    Graham has already saved in Sales Navigator, for the consulting pipeline.
    STRICTLY read-only — no InMail, no connection requests, no bulk scraping,
    no automated messaging (Sales Nav ToS + the standing LinkedIn-automation
    prohibition). Graham transmits every outreach himself. A sign-in wall or a
    Sales Nav entitlement wall records AUTH_REQUIRED honestly.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.browser_capture_receipt.v1",
        "source": "sales_navigator_saved_leads",
        "captured_at": utc_now(),
        "external_effects": False,
        "automation_policy": "linkedin_authorized_read_only_no_actions",
        "engine": "client_prospecting",
    }
    tab_id = ""
    try:
        ensure_browser(surf_run)
        created = _surf(surf_run, "tab.new", _SALES_NAV_SAVED_URL, "--json")
        tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
        if not tab_id:
            raise BrowserCaptureError(f"could not parse tab id from: {created[:120]}")
        _surf_pause(surf_run, "8")
        wall = _surf(
            surf_run,
            "js",
            "--tab-id",
            tab_id,
            "(function(){var t=document.body.innerText.toLowerCase();"
            "return (t.indexOf('sign in')>=0 || location.href.indexOf('/login')>=0"
            " || t.indexOf('reactivate')>=0 || t.indexOf('start your free trial')>=0) ? 'WALL' : 'OK';})()",
        )
        if "WALL" in wall:
            receipt["status"] = "AUTH_REQUIRED"
            receipt["error"] = "Sales Navigator sign-in or entitlement wall in the reachable browser"
            receipt["evidence_path"] = None
            return receipt
        raw = _surf_js(surf_run, tab_id, _SALES_NAV_EXTRACT_JS)
        rows = json.loads(json.loads(raw))
        leads = [
            {
                "source": "human_authorized_sales_navigator",
                "observed_at": utc_now(),
                "name": r["name"],
                "headline": (r.get("headline") or "").strip(),
                "company": (r.get("company") or "").strip(),
                "profile_url": r.get("href"),
                "prospect_class": "client_decision_maker",
            }
            for r in rows
            if r.get("name")
        ]
        evidence = {
            "schema_version": "ops-linkedin.client_prospect_capture.v1",
            "source": "human_authorized_sales_navigator",
            "capture_method": "surf_read_only_authenticated_session",
            "automation_policy": "linkedin_authorized_read_only_no_actions",
            "observed_at": utc_now(),
            "sales_nav_url": _SALES_NAV_SAVED_URL,
            "prospects": leads,
        }
        evidence_path = out_dir / "sales-navigator-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        receipt["status"] = "OK" if leads else "EMPTY"
        receipt["evidence_path"] = str(evidence_path)
        receipt["prospects_captured"] = len(leads)
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.error("Sales Navigator capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["evidence_path"] = None
    finally:
        if tab_id:
            _close_tab(surf_run, tab_id, "Sales Navigator")
    (out_dir / "sales-navigator-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt
