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
from urllib.parse import urlencode

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
    "var a=cards[i].querySelector(\"a[href*='/jobs/view/'], a[href*='currentJobId']\");"
    "out.push({title:title, company:uniq[1]||'', location:uniq[2]||'', href:a?a.href.split('?')[0]:null});"
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
# f_TPR posted-within seconds
_LINKEDIN_POSTED_WEEK = "r604800"


def build_linkedin_search_url(
    keywords: str,
    work_types: list[str],
    experience_levels: list[str] | None = None,
    posted_within: str = _LINKEDIN_POSTED_WEEK,
    location: str | None = None,
    sort_by: str = "DD",
) -> str:
    """Build a LinkedIn advanced job-search URL (pure; no browser).

    Maps candidate preferences to LinkedIn's own filter params so the platform
    does the filtering server-side. `work_types` are keys of _LINKEDIN_WORK_TYPE;
    unknown keys are ignored. sort_by DD=most recent, R=most relevant.
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
    if location:
        params.append(("location", location))
    if sort_by:
        params.append(("sortBy", sort_by))
    return _LINKEDIN_JOB_SEARCH_BASE + "?" + urlencode(params)


def _mandate_keyword_groups(profile: dict[str, Any]) -> list[str]:
    """Derive bounded, high-signal keyword phrases from the candidate mandates.

    Falls back to a sane default set if the profile has no mandates, so the
    search never silently degrades to an empty query.
    """
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
    return out[:4]


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
            raw = _surf(surf_run, "js", "--tab-id", tab_id, _LINKEDIN_EXTRACT_JS, timeout=30)
            try:
                rows = json.loads(json.loads(raw))
            except (ValueError, json.JSONDecodeError):
                rows = []
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
            _surf(surf_run, "js", "--tab-id", tab_id, _LINKEDIN_SCROLL_JS, timeout=20)
            _surf(surf_run, "wait", "1", timeout=15)
        if page < max_pages:
            clicked = _surf(surf_run, "js", "--tab-id", tab_id, _linkedin_next_page_js(page + 1), timeout=20)
            if "CLICKED" not in clicked:
                break
            _surf(surf_run, "wait", "4", timeout=20)
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
        _surf(surf_run, "wait", "9")
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
    except (BrowserCaptureError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        logger.error("LinkedIn top-applicant capture failed: {}", exc)
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["evidence_path"] = None
    finally:
        if tab_id:
            try:
                _surf(surf_run, "tab.close", tab_id, timeout=30)
            except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
                logger.warning("could not close LinkedIn capture tab {}: {}", tab_id, exc)
    (out_dir / "linkedin-capture-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


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
            except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
                logger.warning("could not close SAM capture tab {}: {}", tab_id, exc)
    (out_dir / "sam-capture-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def _load_candidate_profile() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "config" / "candidate_profile.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


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
                    _surf(surf_run, "js", "--tab-id", tab_id, f"(function(){{location.href={json.dumps(query['url'])}; return 'NAV';}})()", timeout=20)
                _surf(surf_run, "wait", "6")
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
            try:
                _surf(surf_run, "tab.close", tab_id, timeout=30)
            except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
                logger.warning("could not close LinkedIn search tab {}: {}", tab_id, exc)
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
        _surf(surf_run, "wait", "8")
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
        raw = _surf(surf_run, "js", "--tab-id", tab_id, _SALES_NAV_EXTRACT_JS)
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
            try:
                _surf(surf_run, "tab.close", tab_id, timeout=30)
            except (BrowserCaptureError, subprocess.TimeoutExpired) as exc:
                logger.warning("could not close Sales Navigator tab {}: {}", tab_id, exc)
    (out_dir / "sales-navigator-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt
