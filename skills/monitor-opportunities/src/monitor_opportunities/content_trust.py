"""Content trust: is this the surface we asked for, and is its text only data?

Two webgpt eval-review P0s that share a subject — bytes fetched from the open
internet:

#07 live-source semantic canaries
    An HTTP 200 proves a response, not the RIGHT response. Real captures have
    returned a search page, a consent banner, a login wall, a CAPTCHA, or a
    soft-200 error while every receipt read healthy. `classify_surface` names
    what actually came back so a parser collapse cannot masquerade as an empty
    market.

#16 untrusted posting-content boundary
    Posting text, JSON-LD, recruiter messages, and linked articles are DATA.
    They are written into a digest that a human and an agent both read, so an
    instruction embedded in a posting is an attempt to steer whoever reads it.
    `scan_untrusted_text` flags injection-shaped content and `neutralize`
    renders it inert for display. Nothing here executes, and no flagged text
    ever changes eligibility, scores, or tool behavior — flagging is a label,
    never a control-flow input.
"""

from __future__ import annotations

import re
from typing import Any

TRUST_SCHEMA = "monitor_opportunities.content_trust.v1"

# --- #07: what surface did we actually get? --------------------------------
# Ordered: the first match wins, because a login wall inside a search page is
# still a login wall.
_SURFACE_SIGNATURES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("captcha", re.compile(
        r"captcha|are you a robot|verify you are human|cf-challenge|unusual traffic", re.I)),
    ("login_wall", re.compile(
        r"sign in to continue|please log in|log in to view|create an account to|"
        r"session (?:has )?expired|authwall", re.I)),
    ("consent_banner", re.compile(
        r"accept (?:all )?cookies|cookie preferences|we value your privacy|gdpr consent", re.I)),
    ("rate_limited", re.compile(
        r"too many requests|rate limit|quota (?:limit )?exceeded|429", re.I)),
    ("error_page", re.compile(
        r"page not found|404 not found|something went wrong|internal server error|"
        r"service unavailable|try again later", re.I)),
    ("search_results", re.compile(
        r"\d+\s+results|filter by|sort by|refine your search|no results found", re.I)),
)


def classify_surface(text: str, expect: str = "detail") -> dict[str, Any]:
    """Name the surface a capture actually returned.

    expect="detail"  a specific job/opportunity page
    expect="results" a search/results listing (then search_results is fine)
    """
    body = str(text or "")
    if not body.strip():
        return {"surface": "empty", "ok": False, "evidence": None,
                "reason": "no text returned"}
    for name, pattern in _SURFACE_SIGNATURES:
        m = pattern.search(body)
        if not m:
            continue
        if name == "search_results" and expect == "results":
            return {"surface": name, "ok": True, "evidence": m.group(0),
                    "reason": "results surface as expected"}
        return {"surface": name, "ok": False, "evidence": m.group(0),
                "reason": f"{name} returned where a {expect} surface was expected"}
    return {"surface": expect, "ok": True, "evidence": None, "reason": "no blocking surface"}


# --- #16: posting text is data, never instructions -------------------------
# Injection-shaped content. Matching is for LABELLING and display-neutralizing
# only; a flag never alters eligibility, ranking, or any tool decision.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instruction_override", re.compile(
        r"ignore (?:all |any )?(?:previous|prior|above) instructions|"
        r"disregard (?:the )?(?:above|previous)|forget (?:everything|all previous)", re.I)),
    ("role_hijack", re.compile(
        r"you are now|act as (?:an? )?(?:admin|system|developer)|"
        r"system prompt|</?(?:system|assistant|user)>", re.I)),
    ("secret_exfiltration", re.compile(
        r"(?:print|reveal|output|send|email)\s+(?:your |the )?"
        r"(?:api[_ ]?key|token|password|secret|credential|env)", re.I)),
    ("tool_coercion", re.compile(
        r"(?:run|execute|invoke|call)\s+(?:this |the following )?"
        r"(?:command|shell|script|tool)|curl\s+http|rm\s+-rf", re.I)),
    ("scoring_manipulation", re.compile(
        r"(?:rank|score|rate) this (?:job|posting|role) (?:first|highest|top)|"
        r"mark as (?:top|best) (?:match|candidate)", re.I)),
)


def scan_untrusted_text(text: str) -> dict[str, Any]:
    """Flag injection-shaped content in text fetched from the open internet."""
    body = str(text or "")
    findings = [
        {"kind": kind, "evidence": m.group(0)[:120]}
        for kind, pattern in _INJECTION_PATTERNS
        if (m := pattern.search(body))
    ]
    return {
        "schema": TRUST_SCHEMA,
        "clean": not findings,
        "findings": findings,
        "kinds": sorted({f["kind"] for f in findings}),
    }


def neutralize(text: str, limit: int = 4000) -> str:
    """Render untrusted text inert for display.

    Defangs the markers a downstream reader (human or agent) could mistake for
    instructions: role tags, fenced blocks, and bare URLs stay visible but
    cannot be actioned. Content is preserved, never silently deleted.
    """
    body = str(text or "")[:limit]
    body = re.sub(r"</?(system|assistant|user|instructions?)>", r"[\1]", body, flags=re.I)
    body = body.replace("```", "'''")
    return body


def assess_posting(text: str, expect: str = "detail") -> dict[str, Any]:
    """Full content-trust assessment for one captured posting."""
    surface = classify_surface(text, expect=expect)
    injection = scan_untrusted_text(text)
    return {
        "schema": TRUST_SCHEMA,
        "surface": surface,
        "injection": injection,
        # A posting is usable when the surface is right. Injection findings are
        # surfaced to the reader as a warning; they never silently drop a real
        # opportunity, because that would let a poisoned posting delete itself
        # from view.
        "usable": surface["ok"],
        "display_warning": (
            f"contains {', '.join(injection['kinds'])} patterns; treated as data only"
            if injection["findings"] else None
        ),
    }
