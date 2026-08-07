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

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger

from .util import utc_now

SURF_RUN_DEFAULT = Path(__file__).resolve().parents[3] / "surf" / "run.sh"

_SAM_URL = (
    "https://sam.gov/search/?index=opp&sort=-modifiedDate&pageSize=25&page=1"
    "&sfm%5Bstatus%5D%5Bis_active%5D=true&sfm%5BsimpleSearch%5D%5BkeywordRadio%5D=ALL"
    "&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B0%5D%5Bvalue%5D=artificial%20intelligence"
)

_SAM_EXTRACT_JS = (
    "(function(){"
    "var out=[],seen={};"
    "var links=[].slice.call(document.querySelectorAll("
    "\"a[href*='/opp/'], a.usa-link, h3 a, [class*='result'] a\"));"
    "for (var i=0;i<links.length;i++){"
    "var t=(links[i].innerText||'').trim();"
    "if (t.length>12 && !seen[t]){ seen[t]=1; out.push({title:t.slice(0,120), href:links[i].href}); }"
    "}"
    "return JSON.stringify(out.slice(0,40));"
    "})()"
)


class BrowserCaptureError(ValueError):
    """Stable browser-capture error."""


def _surf(surf_run: Path, *args: str, timeout: int = 90) -> str:
    proc = subprocess.run([str(surf_run), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise BrowserCaptureError(f"surf {args[0]} failed: {proc.stderr[-200:]}")
    return proc.stdout.strip()


def _start_xvfb(display: str = ":99") -> None:
    """Start a virtual X display if none is on `display` (idempotent)."""
    probe = subprocess.run(["bash", "-c", f"xdpyinfo -display {display}"], capture_output=True, text=True)
    if probe.returncode == 0:
        return
    subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)


def ensure_browser(surf_run: Path = SURF_RUN_DEFAULT) -> str:
    """Guarantee surf has a reachable browser; launch a HEADED Chrome if not.

    Headed (not headless): headless Chrome sets navigator.webdriver and trips
    bot detection. We run a real headed Chrome on a virtual display (Xvfb) so it
    has a genuine browser fingerprint with no visible window — undetectable and
    non-intrusive. This removes the dependency on the user's Chrome being open
    at 2 AM for public sources like SAM.gov. Returns the browser mode used.
    """
    try:
        _surf(surf_run, "tab.list", "--json", timeout=25)
        return "existing"
    except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
        logger.warning("no reachable browser ({}); launching HEADED Chrome on a virtual display", exc)
    if not os.environ.get("DISPLAY"):
        _start_xvfb(":99")
        os.environ["DISPLAY"] = ":99"
    try:
        # No --headless: headed Chrome avoids the webdriver/headless bot-detection tell.
        _surf(surf_run, "cdp", "start", timeout=90)
        _surf(surf_run, "tab.list", "--json", timeout=25)
        return "cdp_headed"
    except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
        raise BrowserCaptureError(f"could not start a headed browser: {exc}") from exc


def capture_sam(out_dir: Path, surf_run: Path = SURF_RUN_DEFAULT) -> dict[str, Any]:
    """Read-only capture of SAM.gov active AI opportunities from the website.

    Writes federal evidence JSON consumable by run --federal-evidence. Returns a
    capture receipt. Honest failure: if surf/Chrome is unavailable, no evidence
    file is written and the receipt records status FAILED.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
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
        _surf(surf_run, "wait", "10")
        raw = _surf(surf_run, "js", "--tab-id", tab_id, _SAM_EXTRACT_JS)
        rows = json.loads(json.loads(raw))
        opps = [
            {"title": r["title"], "url": r.get("href"), "source": "sam.gov_website"}
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
            try:
                _surf(surf_run, "tab.close", tab_id, timeout=30)
            except BrowserCaptureError as exc:
                logger.warning("could not close SAM capture tab {}: {}", tab_id, exc)
    (out_dir / "sam-capture-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt
