"""Read-only browser capture of no-API / broken-API sources via surf.

When a source has no working API (SAM.gov API 404s; hiddenjobs.dev has no
public API), the mandatory-source and API-website-fallback rules require a
read-only website capture. This module drives surf against the authenticated
Chrome to capture those sources into evidence files the pipeline consumes.

Inputs: surf run.sh path, output directory. Outputs: evidence JSON files +
a capture receipt. Failure modes: surf/Chrome unavailable -> receipt records
the failure honestly and the evidence file is absent (the run's enforcement
gate then reports the source as unsatisfied rather than silently passing).

Operational requirement: Chrome must be running (surf drives the user's
authenticated browser). For the 2 AM nightly this means Chrome is left open.
"""

from __future__ import annotations

import json
import subprocess
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
