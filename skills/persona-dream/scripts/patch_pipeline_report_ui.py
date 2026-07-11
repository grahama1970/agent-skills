#!/usr/bin/env python3
"""Post-process pipeline review HTML as a sequential pipeline brief (not a dashboard)."""

from __future__ import annotations

import argparse
import hashlib
import httpx
import html
import json
import re
import subprocess
import zipfile
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from regenerate_asset import (
    build_all_panel_bundles,
    build_contact_sheet_bundle,
    build_panel_bundle,
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


PIPELINE_SECTION_ORDER = (
    "idea-story",
    "memories-used",
    "story-package",
    "producer-phase",
    "contact-sheets",
    "script-phase",
    "voice-section",
    "panels-phase",
    "gate-status",
    "export-kling",
    "pipeline-errata",
)


def _normalize_phase_status_label(status: str) -> str:
    s = (status or "").strip().lower()
    if s in {"pass", "complete", "structural pass"}:
        return "pass"
    if s in {"blocked", "fail", "failed"}:
        return "blocked"
    return "warn"


def _section_badge_html(status: str) -> str:
    norm = _normalize_phase_status_label(status)
    if norm == "pass":
        return '<span class="section-badge section-pass"><i data-lucide="check-circle"></i> Pass</span>'
    if norm == "blocked":
        return '<span class="section-badge section-fail"><i data-lucide="x-circle"></i> Blocked</span>'
    return '<span class="section-badge section-warn"><i data-lucide="alert-circle"></i> Draft</span>'


def pipeline_phase_statuses(run_root: Path) -> dict[str, str]:
    review = run_root / "pipeline_review_8892" / "artifacts"
    p1 = load_json(review / "phase_01_idea_anti_hallucination_gate.json")
    p2 = load_json(review / "phase_02_memory_anti_hallucination_gate.json")
    p5 = load_json(review / "phase_05_contact_sheets_anti_hallucination_gate.json")
    panel_gate = load_json(run_root / "storyboard/panel_entity_environment_interaction_gate_receipt.json")
    panel_verdict = str(panel_gate.get("verdict") or "").upper()
    return {
        "idea-story": "Pass" if p1.get("phase_verdict") else "—",
        "memories-used": "Pass" if p2.get("proceed_to_phase_3") else "Blocked",
        "story-package": "Structural pass",
        "producer-phase": "Pass",
        "contact-sheets": "Pass" if p5.get("verdict") == "PASS" else "Blocked",
        "script-phase": "Draft",
        "voice-section": "Blocked",
        "panels-phase": "Blocked" if panel_verdict == "FAIL" else "Draft",
        "gate-status": "Blocked",
        "export-kling": "Blocked",
        "pipeline-errata": "Evidence",
    }


def _section_is_provisional(section_id: str, statuses: dict[str, str]) -> bool:
    first_blocked_idx: int | None = None
    for index, sid in enumerate(PIPELINE_SECTION_ORDER):
        if _normalize_phase_status_label(statuses.get(sid, "")) == "blocked":
            first_blocked_idx = index
            break
    if first_blocked_idx is None:
        return False
    try:
        section_idx = PIPELINE_SECTION_ORDER.index(section_id)
    except ValueError:
        return False
    return section_idx > first_blocked_idx


def gate_summary_banner_html(run_root: Path) -> str:
    statuses = pipeline_phase_statuses(run_root)
    label_map = {
        "memories-used": "Memories",
        "contact-sheets": "Contact sheets",
        "voice-section": "Voice",
        "panels-phase": "Panels",
    }
    blocked_labels = [
        label
        for key, label in label_map.items()
        if _normalize_phase_status_label(statuses.get(key, "")) == "blocked"
    ]
    chips = "".join(
        f'<span class="gate-chip gate-chip-blocked">{html.escape(label)}</span>'
        for label in blocked_labels
    )
    export_chip = (
        '<span class="gate-chip gate-chip-export-blocked">'
        '<i data-lucide="octagon-alert"></i> Export to Kling: BLOCKED</span>'
    )
    return (
        '<section class="gate-summary-banner card" aria-label="Pipeline gate summary">'
        '<div class="gate-summary-title"><i data-lucide="octagon-alert"></i> Pipeline gate review</div>'
        f'<div class="gate-summary-chips">{export_chip}{chips}</div>'
        '<p class="muted gate-summary-note">Blocked phases must pass before any live or paid Kling call. '
        'Machine receipts remain in <a href="#pipeline-errata">Technical Appendix</a>.</p>'
        "</section>"
    )


def pipeline_outline_html(run_root: Path) -> str:
    statuses = pipeline_phase_statuses(run_root)
    phases = [
        ("#idea-story", "Idea", statuses["idea-story"]),
        ("#memories-used", "Memories", statuses["memories-used"]),
        ("#story-package", "Story", statuses["story-package"]),
        ("#producer-phase", "Producer", statuses["producer-phase"]),
        ("#contact-sheets", "Contact sheets", statuses["contact-sheets"]),
        ("#script-phase", "Script", statuses["script-phase"]),
        ("#voice-section", "Voice", statuses["voice-section"]),
        ("#panels-phase", "Panels", statuses["panels-phase"]),
        ("#gate-status", "Gate", statuses["gate-status"]),
        ("#export-kling", "Export to Kling", statuses["export-kling"]),
        ("#pipeline-errata", "Errata", statuses["pipeline-errata"]),
    ]
    items = []
    for href, label, status in phases:
        norm = _normalize_phase_status_label(status)
        items.append(
            f'<li class="phase-status-{norm}">'
            f'<a href="{html.escape(href)}">{html.escape(label)}</a> '
            f'<span class="phase-outline-status">{html.escape(status)}</span></li>'
        )
    return f'<nav class="pipeline-outline" aria-label="Pipeline phases"><ol>{"".join(items)}</ol></nav>'



def _flow_status_attr(status: str) -> str:
    norm = _normalize_phase_status_label(status)
    return norm if norm in {"pass", "blocked", "warn"} else "warn"


STICKY_NAV_PHASES: tuple[tuple[str, str, str, str], ...] = (
    ("#idea-story", "Idea", "lightbulb", "idea-story"),
    ("#memories-used", "Memories", "brain", "memories-used"),
    ("#story-package", "Story", "book-open", "story-package"),
    ("#producer-phase", "Producer", "sliders-horizontal", "producer-phase"),
    ("#contact-sheets", "Refs", "images", "contact-sheets"),
    ("#script-phase", "Script", "pen-tool", "script-phase"),
    ("#voice-section", "Voice", "mic", "voice-section"),
    ("#panels-phase", "Panels", "layout-grid", "panels-phase"),
    ("#gate-status", "Gate", "octagon-alert", "gate-status"),
    ("#export-kling", "Movie", "monitor-play", "export-kling"),
)


def rebuild_sticky_nav(html_text: str, run_root: Path) -> str:
    statuses = pipeline_phase_statuses(run_root)
    blocked = [
        label
        for _href, label, _icon, key in STICKY_NAV_PHASES
        if _normalize_phase_status_label(statuses.get(key, "")) == "blocked"
    ]
    flow_links = []
    for href, label, icon, key in STICKY_NAV_PHASES:
        status = statuses.get(key, "warn")
        flow_links.append(
            f'<a href="{html.escape(href)}" class="flow-link" data-status="{_flow_status_attr(status)}">'
            f'<i data-lucide="{html.escape(icon)}"></i><span>{html.escape(label)}</span></a>'
        )
    blocked_text = ", ".join(blocked[:4]) + ("…" if len(blocked) > 4 else "")
    nav = (
        '<nav class="sticky-nav" aria-label="Pipeline flow">'
        '<div class="sticky-nav-inner">'
        '<div class="pipeline-flow">'
        + "".join(flow_links)
        + '</div>'
        '<a href="#pipeline-errata" class="flow-link flow-appendix" data-status="warn">'
        '<i data-lucide="archive"></i><span>Appendix</span></a>'
        "</div>"
        '<div class="pipeline-flow-status">'
        '<span class="pipeline-flow-status-pill">Blocked before Kling</span>'
        f'<span class="pipeline-flow-status-detail">{html.escape(blocked_text or "Review gate receipts before export.")}</span>'
        "</div>"
        "</nav>"
    )
    html_text = re.sub(r'<nav class="sticky-nav"[\s\S]*?</nav>\s*', nav, html_text, count=1)
    html_text = re.sub(r'<nav class="pipeline-outline"[\s\S]*?</nav>\s*', "", html_text, count=1)
    return html_text


def fix_inline_status_css(html_text: str) -> str:
    html_text = re.sub(
        r"\.status, \.status-alert \{",
        ".status:not(.phase-gate-line):not(.phase-gate-pass):not(.phase-gate-warn):not(.phase-gate-blocked):not(.status-note), "
        ".status-alert:not(.phase-gate-line):not(.phase-gate-pass):not(.phase-gate-warn):not(.phase-gate-blocked):not(.status-note) {",
        html_text,
        count=1,
    )
    return html_text


def strip_dashboard_chrome(html_text: str) -> str:
    html_text = re.sub(r'<nav class="pipeline-stepper"[\s\S]*?</nav>\s*', "", html_text)
    html_text = re.sub(r'<div class="report-toolbar">[\s\S]*?</div>\s*', "", html_text)
    html_text = re.sub(r'<p class="report-toolbar-hint[\s\S]*?</p>\s*', "", html_text)
    html_text = re.sub(r'<nav class="pipeline-manifest card"[\s\S]*?</nav>\s*', "", html_text)
    html_text = html_text.replace(' data-report-view="human"', "")
    return html_text


ANTI_HALLUCINATION_GATE_BLOCK = re.compile(
    r'<div class="status-alert">'
    r'(<strong>[^<]*(?:anti-hallucination gate|prop behavior gate)[^<]*</strong>)'
    r'(?:\s*|:\s*)'
    r'(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


def _section_is_failed(section_html: str) -> bool:
    """Heuristic: a phase section failed if it contains a fail/blocked badge."""
    return bool(
        re.search(
            r'<span class="badge badge-(?:fail|bad)">|<dt>Phase verdict</dt>\s*<dd>\s*<span class="badge badge-fail">',
            section_html,
            re.IGNORECASE | re.DOTALL,
        )
    )


def transform_gate_definitions(html_text: str) -> str:
    """Convert anti-hallucination gate definition blocks into neutral info accordions.

    The rule definition itself is not a failure status, so it should not be a
    massive red alert when the surrounding phase has passed. Failed phases keep
    the accordion open with a red accent so the rule is still visible next to
    the actual failure evidence.
    """

    def _replacer(match: re.Match[str]) -> str:
        summary = match.group(1)
        body = match.group(2).strip()
        start = match.start()
        section_start = html_text.rfind('<section', 0, start)
        section_end = html_text.find('</section>', start)
        section_html = (
            html_text[section_start:section_end]
            if section_start != -1 and section_end != -1
            else ""
        )
        failed = _section_is_failed(section_html)
        open_attr = ' open' if failed else ''
        failed_class = ' is-failed' if failed else ''
        return (
            f'<details class="gate-definition{failed_class}"{open_attr}>'
            f'<summary>{summary}</summary>'
            f'<div class="gate-definition-body">{body}</div>'
            f'</details>'
        )

    return ANTI_HALLUCINATION_GATE_BLOCK.sub(_replacer, html_text)


# Matches both "Claim Audit" and "Memory Claim Audit" blocks
# Regular claim audits: heading + table-scroll
CLAIM_AUDIT_BLOCK = re.compile(
    r"<h[2-4][^>]*>\s*Claim\s+Audit\s*</h[2-4]>\s*<div class=\"table-scroll\">.*?</div>",
    re.IGNORECASE | re.DOTALL,
)

# Memory claim audits: heading + paragraph + stage-audit-list (different structure)
MEMORY_CLAIM_AUDIT_BLOCK = re.compile(
    r"<h[2-4][^>]*>\s*Memory\s+Claim\s+Audit\s*</h[2-4]>\s*"
    r"<p>.*?</p>\s*"
    r"<div class=\"stage-audit-list\">.*?</div>\s*"
    r"(?=<h[2-4]|<section|</section>|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _strip_claim_audit_heading(audit_html: str) -> str:
    # Strip both "Claim Audit" and "Memory Claim Audit" headings
    audit_html = re.sub(
        r"<h[2-4][^>]*>\s*Memory\s+Claim\s+Audit\s*</h[2-4]>\s*",
        "",
        audit_html,
        count=1,
        flags=re.IGNORECASE,
    )
    audit_html = re.sub(
        r"<h[2-4][^>]*>\s*Claim\s+Audit\s*</h[2-4]>\s*",
        "",
        audit_html,
        count=1,
        flags=re.IGNORECASE,
    )
    # Also strip the paragraph tag that follows memory claim audit heading
    audit_html = re.sub(
        r'<p>.*?</p>\s*',
        "",
        audit_html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return audit_html

def _verdict_badge_html(verdict: str) -> str:
    upper = verdict.upper()
    if any(token in upper for token in ("FAIL", "LIE", "FORBIDDEN", "BLOCKED")) and "EXPLICITLY_NOT_PROVEN" not in upper:
        badge = "badge-fail"
        icon = "octagon-x"
    elif any(token in upper for token in ("WARN", "QUARANTINE", "PARTIAL", "MOVED", "NOT_PROVEN", "RECONCILED")):
        badge = "badge-warn"
        icon = "alert-circle"
    else:
        badge = "badge-pass"
        icon = "check-circle"
    return (
        f"<span class='badge {badge}'><i data-lucide='{icon}'></i>"
        f"{html.escape(verdict)}</span>"
    )


def _render_claim_audit_table(claims: list[dict[str, Any]]) -> str:
    rows = []
    for claim in claims:
        # Handle both 'id' (standard) and 'claim_id' (memory claims) fields
        claim_id = claim.get('id') or claim.get('claim_id', '')
        # Handle different verdict fields: 'verdict' or 'default_state'
        verdict = claim.get('verdict') or claim.get('default_state', '')
        rows.append(
            "<tr>"
            f"<td><span class='code'>{html.escape(str(claim_id))}</span></td>"
            f"<td>{html.escape(str(claim.get('claim', '')))}</td>"
            f"<td>{_verdict_badge_html(str(verdict))}</td>"
            f"<td>{html.escape(str(claim.get('basis', '')))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table><thead><tr>'
        "<th>Claim</th><th>Statement</th><th>Verdict</th><th>Basis</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _render_memory_claim_audit_table(claims: list[dict[str, Any]]) -> str:
    """Render memory claims with recall-specific columns."""
    rows = []
    for claim in claims:
        claim_id = claim.get('claim_id', '')
        verdict = claim.get('default_state', '')
        # Get recall info
        recall_q = claim.get('recall_question', claim.get('recall_request', {}).get('q', ''))
        collections = claim.get('recall_request', {}).get('collections', [])
        found = claim.get('found', False)
        item_count = claim.get('item_count', 0)

        rows.append(
            "<tr>"
            f"<td><span class='code'>{html.escape(str(claim_id))}</span></td>"
            f"<td>{html.escape(str(claim.get('claim', '')))}</td>"
            f"<td>{_verdict_badge_html(str(verdict))}</td>"
            f"<td><span class='code'>{','.join(collections)}</span></td>"
            f"<td>{'Yes' if found else 'No'}</td>"
            f"<td>{item_count}</td>"
            f"<td>{html.escape(str(claim.get('basis', '')))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table><thead><tr>'
        "<th>Claim</th><th>Statement</th><th>Verdict</th><th>Collections</th><th>Found</th><th>Items</th><th>Basis</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


PHASE_CLAIM_SOURCES: list[tuple[str, str, str, str]] = [
    ("idea-story", "Phase 1 — Idea", "phase_01_idea_anti_hallucination_gate.json", "claims"),
    (
        "memory-recall",
        "Phase 2 — Memory Recall",
        "phase_02_memory_anti_hallucination_gate.json",
        "claims",
    ),
    (
        "story-package",
        "Phase 3 — Story package",
        "phase_03_story_package_anti_hallucination_gate.json",
        "claim_audit",
    ),
    (
        "creative-leadership",
        "Phase 4 — Creative leadership",
        "phase_04_creative_leadership_anti_hallucination_gate.json",
        "claim_audit",
    ),
]


def _claim_audit_article(section_id: str, title: str, table_html: str) -> str:
    anchor = f"errata-claim-audit-{section_id}"
    return (
        f'<article class="errata-phase claim-audit-errata" id="{html.escape(anchor)}">'
        f"<h4>{html.escape(title)}</h4>{table_html}</article>"
    )


def _collect_existing_claim_audit_articles(errata_body: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in re.finditer(
        r'<article class="errata-phase claim-audit-errata" id="([^"]+)">(.*?)</article>',
        errata_body,
        flags=re.DOTALL,
    ):
        found[match.group(1)] = match.group(0)
    return found


def _collect_errata_phase_claim_table(errata_body: str, article_id: str) -> str:
    pattern = re.compile(
        rf'(<article class="errata-phase" id="{re.escape(article_id)}">.*?<h4>\s*Claim audit\s*</h4>\s*)(<div class="table-scroll">.*?</div>)',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(errata_body)
    return match.group(2) if match else ""


def rebuild_claim_audits_section(html_text: str, run_root: Path) -> str:
    errata_match = re.search(
        r'(<section class="card content-block" id="pipeline-errata">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not errata_match:
        return html_text

    errata_open, errata_body, errata_close = errata_match.groups()
    existing = _collect_existing_claim_audit_articles(errata_body)
    articles: list[str] = []

    for section_id, title, artifact_name, claims_key in PHASE_CLAIM_SOURCES:
        anchor = f"errata-claim-audit-{section_id}"
        if anchor in existing:
            articles.append(_strip_claim_audit_heading(existing[anchor]))
            continue
        gate_path = run_root / "pipeline_review_8892" / "artifacts" / artifact_name
        gate = load_json(gate_path)
        claims = gate.get(claims_key) or []
        if claims:
            # Use specialized renderer for memory claims
            if section_id == "memory-recall":
                articles.append(_claim_audit_article(section_id, title, _render_memory_claim_audit_table(claims)))
            else:
                articles.append(_claim_audit_article(section_id, title, _render_claim_audit_table(claims)))

    phase1_table = _collect_errata_phase_claim_table(errata_body, "errata-phase-1")
    if phase1_table and "errata-claim-audit-idea-story" not in existing:
        if not any('id="errata-claim-audit-idea-story"' in article for article in articles):
            articles.insert(0, _claim_audit_article("idea-story", "Phase 1 — Idea", phase1_table))

    errata_body = re.sub(
        r'<section class="errata-subsection" id="errata-claim-audits"[\s\S]*?</section>\s*',
        "",
        errata_body,
        flags=re.IGNORECASE,
    )
    errata_body = re.sub(
        r'<article class="errata-phase claim-audit-errata"[\s\S]*?</article>\s*',
        "",
        errata_body,
        flags=re.IGNORECASE,
    )
    # Replace inline claim audit tables with pointers to Errata (Phase 1 and Phase 2)
    errata_body = re.sub(
        r'(<article class="errata-phase" id="errata-phase-1">.*?<h4>\s*Claim audit\s*</h4>\s*)<div class="table-scroll">.*?</div>',
        r'\1<p class="muted claim-audit-pointer"><a href="#errata-claim-audit-idea-story">Claim audit</a> is in <a href="#errata-claim-audits">Errata</a>.</p>',
        errata_body,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Phase 2 Memory Claim Audit - replace with pointer
    errata_body = re.sub(
        r'(<article class="errata-phase" id="errata-phase-2">.*?<h4>\s*(?:Memory\s+)?Claim\s+Audit\s*</h4>\s*)<div class="table-scroll">.*?</div>',
        r'\1<p class="muted claim-audit-pointer"><a href="#errata-claim-audit-memory-recall">Memory claim audit</a> is in <a href="#errata-claim-audits">Errata</a>.</p>',
        errata_body,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if articles:
        claim_index = (
            '<section class="errata-subsection" id="errata-claim-audits">'
            "<h3>Claim audits</h3>"
            '<p class="muted">All phase claim-audit tables live here. Main phase sections link to this index.</p>'
            + "".join(articles)
            + "</section>\n"
        )
        insert_at = errata_body.find('<article class="errata-phase" id="errata-phase-3-interactions"')
        if insert_at == -1:
            insert_at = errata_body.find('<article class="errata-phase"')
        if insert_at == -1:
            errata_body = errata_body.rstrip() + "\n" + claim_index
        else:
            errata_body = errata_body[:insert_at] + claim_index + errata_body[insert_at:]

    return (
        html_text[: errata_match.start()]
        + errata_open
        + errata_body
        + errata_close
        + html_text[errata_match.end() :]
    )




def repair_nested_errata_duplicate(html_text: str) -> str:
    pattern = re.compile(
        r'<dt>Machine-readable gate</dt><dd><a href="a<section class="card content-block" id="pipeline-errata">.*?(?=<dt>Machine-readable gate</dt><dd><a href="artifacts/phase_02_memory_anti_hallucination_gate\.json">)',
        re.DOTALL,
    )
    return pattern.sub(
        '<dt>Machine-readable gate</dt><dd><a href="artifacts/phase_02_memory_anti_hallucination_gate.json">',
        html_text,
        count=1,
    )


def ensure_errata_section(html_text: str, run_root: Path) -> str:
    """Ensure the pipeline-errata section exists; create it if missing."""
    if 'id="pipeline-errata"' in html_text:
        return html_text

    # Create a basic Errata section
    errata_section = '''<section class="card content-block" id="pipeline-errata">
  <h2>Errata — machine evidence</h2>
  <p class="muted">All machine-readable proof, claim audits, and interaction ledgers are collected here. Main phase sections link to specific entries.</p>
  <article class="errata-phase" id="errata-phase-1">
    <h3>Phase 1 — Idea</h3>
    <p class="muted">Idea anti-hallucination gate and claim audit.</p>
  </article>
  <article class="errata-phase" id="errata-phase-2">
    <h3>Phase 2 — Memory Recall</h3>
    <p class="muted">Memory recall anti-hallucination gate and memory claim audit.</p>
  </article>
  <article class="errata-phase" id="errata-phase-3-interactions">
    <h3>Phase 3 — Story Package</h3>
    <p class="muted">Story package claim audit and machine artifacts.</p>
  </article>
</section>'''

    # Insert before </main> or at the end
    if "</main>" in html_text:
        html_text = html_text.replace("</main>", f"{errata_section}\n</main>", 1)
    else:
        # Insert before closing body tag
        html_text = html_text.replace("</body>", f"{errata_section}\n</body>", 1)

    return html_text


def move_claim_audits_to_errata(html_text: str) -> str:
    errata_match = re.search(
        r'(<section class="card content-block" id="pipeline-errata">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not errata_match:
        return html_text

    # Skip only the main Errata container itself - process all phase sections
    skip_sections = {"pipeline-errata"}
    section_pattern = re.compile(
        r'(<section class="card[^"]*" id="([^"]+)">)(.*?)(</section>)',
        re.DOTALL,
    )

    # Map section IDs to claim audit anchors for consistency with PHASE_CLAIM_SOURCES
    SECTION_TO_ANCHOR: dict[str, str] = {
        "idea-story": "idea-story",
        "memories-used": "memory-recall",
        "story-package": "story-package",
        "creative-leadership": "creative-leadership",
    }

    def section_replacer(match: re.Match[str]) -> str:
        open_tag, section_id, body, close_tag = match.groups()
        if section_id in skip_sections:
            return match.group(0)
        # Try Memory Claim Audit pattern first, then regular Claim Audit
        audit_match = MEMORY_CLAIM_AUDIT_BLOCK.search(body) or CLAIM_AUDIT_BLOCK.search(body)
        if not audit_match:
            return match.group(0)
        audit_html = _strip_claim_audit_heading(audit_match.group(0))
        h2 = re.search(r"<h2[^>]*>(.*?)</h2>", body, re.DOTALL)
        phase_title = re.sub(r"<[^>]+>", "", h2.group(1)).strip() if h2 else section_id
        # Use mapped anchor if available, otherwise use section_id
        anchor_suffix = SECTION_TO_ANCHOR.get(section_id, section_id)
        anchor = f"errata-claim-audit-{anchor_suffix}"
        pointer = (
            f'<p class="muted claim-audit-pointer">'
            f'<a href="#{html.escape(anchor)}">Claim audit</a> is in '
            f'<a href="#errata-claim-audits">Errata</a>.</p>'
        )
        # Replace either Memory Claim Audit or regular Claim Audit
        new_body = MEMORY_CLAIM_AUDIT_BLOCK.sub(pointer, body, count=1)
        if new_body == body:  # No memory claim audit found, try regular
            new_body = CLAIM_AUDIT_BLOCK.sub(pointer, body, count=1)
        new_body = re.sub(
            r'<p class="muted claim-audit-pointer">[\s\S]*?</p>',
            pointer,
            new_body,
            count=1,
        )
        return open_tag + new_body + close_tag

    html_text = section_pattern.sub(section_replacer, html_text)

    return html_text


def move_tom_edges_appendix_to_errata(html_text: str) -> str:
    """Move tom_edges data gap appendix section to Errata."""
    # Pattern to match the tom_edges appendix section (greedy to capture full content)
    tom_edges_pattern = re.compile(
        r'<h3>(?:Appendix: )?tom_edges[^<]*</h3>\s*'
        r'(?:<p>.*?</p>\s*)?'
        r'(?:<div class="table-scroll">.*?</div>\s*)?'
        r'(?:<ul>.*?</ul>)',
        re.IGNORECASE | re.DOTALL,
    )

    # Find all tom_edges sections in the main body first
    tom_edges_matches = list(tom_edges_pattern.finditer(html_text))
    if not tom_edges_matches:
        return html_text

    # Extract sections for Errata (before any modifications)
    tom_edges_sections = []
    for match in tom_edges_matches:
        section_html = match.group(0)
        wrapped = (
            '<article class="errata-phase tom-edges-errata" id="errata-tom-edges-data-gap">'
            '<h4>tom_edges Data Gap (M2-C05B)</h4>'
            f'{section_html}'
            '</article>'
        )
        tom_edges_sections.append(wrapped)

    # Now find Errata section
    errata_match = re.search(
        r'(<section class="card content-block" id="pipeline-errata">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not errata_match:
        return html_text

    errata_open, errata_body, errata_close = errata_match.groups()

    # Build new Errata body with tom_edges section
    if tom_edges_sections:
        insert_point = errata_body.rfind('</section>')
        if insert_point == -1:
            insert_point = len(errata_body)
        new_errata_body = (
            errata_body[:insert_point]
            + '<section class="errata-subsection" id="errata-tom-edges"><h3>Data Gap Diagnostics</h3>'
            + ''.join(tom_edges_sections)
            + '</section>\n'
            + errata_body[insert_point:]
        )
        # Update html_text with new Errata
        html_text = (
            html_text[:errata_match.start()]
            + errata_open
            + new_errata_body
            + errata_close
            + html_text[errata_match.end():]
        )

    # Replace tom_edges sections in main body with pointer (after Errata update)
    pointer = '<p class="muted tom-edges-pointer"><a href="#errata-tom-edges-data-gap">tom_edges data gap diagnosis</a> is in <a href="#pipeline-errata">Errata</a>.</p>'
    html_text = tom_edges_pattern.sub(pointer, html_text)

    return html_text


def move_per_claim_audit_to_errata(html_text: str) -> str:
    """Move Per-claim audit sections (detailed memory claim blocks) to Errata."""
    # Find the Per-claim audit heading
    heading_match = re.search(r'<h3>Per-claim audit</h3>', html_text, re.IGNORECASE)
    if not heading_match:
        return html_text

    # Find the start of the stage-audit-list div after the heading
    start_pos = heading_match.end()
    list_start_match = re.search(r'<div class="stage-audit-list">', html_text[start_pos:], re.IGNORECASE)
    if not list_start_match:
        return html_text

    list_start_pos = start_pos + list_start_match.start()

    # Find the end of the stage-audit-list div by counting nested divs
    pos = list_start_pos + len('<div class="stage-audit-list">')
    depth = 1
    while depth > 0 and pos < len(html_text):
        next_open = html_text.find('<div', pos)
        next_close = html_text.find('</div>', pos)

        if next_close == -1:
            break

        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + len('<div')
        else:
            depth -= 1
            pos = next_close + len('</div>')

    list_end_pos = pos

    # Extract the full section
    full_section = html_text[heading_match.start():list_end_pos]

    # Find Errata section
    errata_match = re.search(
        r'(<section class="card content-block" id="pipeline-errata">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not errata_match:
        return html_text

    errata_open, errata_body, errata_close = errata_match.groups()

    # Wrap section for Errata
    wrapped = (
        '<article class="errata-phase per-claim-audit-errata" id="errata-per-claim-audit">'
        '<h4>Per-claim Audit Details</h4>'
        f'{full_section}'
        '</article>'
    )

    # Insert into Errata
    insert_point = errata_body.rfind('</section>')
    if insert_point == -1:
        insert_point = len(errata_body)
    new_errata_body = (
        errata_body[:insert_point]
        + '<section class="errata-subsection" id="errata-per-claim-audits"><h3>Per-claim Audit Details</h3>'
        + wrapped
        + '</section>\n'
        + errata_body[insert_point:]
    )

    # Build new HTML
    new_html = (
        html_text[:errata_match.start()]
        + errata_open
        + new_errata_body
        + errata_close
        + html_text[errata_match.end():]
    )

    # Replace the per-claim audit section in main body with pointer
    pointer = '<p class="muted per-claim-audit-pointer"><a href="#errata-per-claim-audit">Per-claim audit details</a> are in <a href="#pipeline-errata">Errata</a>.</p>'
    new_html = new_html[:heading_match.start()] + pointer + new_html[list_end_pos:]

    return new_html


def tag_panel_interaction_ledgers(html_text: str) -> str:
    return re.sub(
        r'<details class="phase-details(?: panel-interaction-ledger)?"(?: id="panel-interaction-ledger-(\d+)")?><summary>Panel (\d+) required interactions \((\d+)\)</summary>',
        lambda m: (
            f'<details class="phase-details panel-interaction-ledger" id="panel-interaction-ledger-{m.group(2)}">'
            f"<summary>Panel {m.group(2)} required interactions ({m.group(3)})</summary>"
        ),
        html_text,
    )


def add_panel_ledger_links(html_text: str) -> str:
    def row_repl(match: re.Match[str]) -> str:
        panel_no = match.group(1)
        rest = match.group(2)
        if "panel-ledger-link" in rest:
            return match.group(0)
        link = (
            f'<a class="panel-ledger-link" href="#panel-interaction-ledger-{panel_no}">'
            "Full ledger</a>"
        )
        return (
            f'<td class="panel-identity-cell"><div class="panel-identity-label">Panel {panel_no}</div>'
            + rest
            + link
            + "</td>"
        )

    return re.sub(
        r'<td class="panel-identity-cell"><div class="panel-identity-label">Panel (\d+)</div>(.*?)</td>',
        row_repl,
        html_text,
        flags=re.DOTALL,
    )


PANEL_SUMMARY_ROW = re.compile(
    r"<tr><td><strong>(\d+)</strong><br><span class='code'>([^<]+)</span></td>"
    r"<td>([^<]+)</td><td>(\d+)</td><td>(.*?)</td><td>(.*?)</td></tr>",
    re.DOTALL | re.IGNORECASE,
)


def _format_weather_text(weather_raw: str) -> str:
    value = re.sub(r"<br\s*/?>", ". ", weather_raw, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def _strip_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def _parse_motion_bullets(motion_text: str) -> str:
    parts = [p.strip() for p in _strip_html(motion_text).split(";") if p.strip()]
    grouped: list[tuple[str, str]] = []
    for part in parts:
        if ":" in part:
            entity, action = part.split(":", 1)
            grouped.append((entity.strip(), action.strip()))
        elif grouped:
            entity, action = grouped[-1]
            grouped[-1] = (entity, f"{action}; {part}")
        else:
            grouped.append(("", part))

    items = []
    for entity, action in grouped:
        if entity:
            items.append(
                f"<li><strong>{html.escape(entity)}:</strong> {html.escape(action)}</li>"
            )
        else:
            items.append(f"<li>{html.escape(action)}</li>")
    return "<ul class=\"motion-bullet-list\">" + "".join(items) + "</ul>"








def polish_scene_constraints(html_text: str) -> str:
    pattern = re.compile(
        r'(<div class="scene-constraints-card">.*?<p>)(.*?)(</p></div>)',
        re.DOTALL,
    )

    def repl(match: re.Match[str]) -> str:
        body = match.group(2).strip()
        body = re.sub(r"\bpauses\s+cold wind\b", "pauses. Cold wind", body, flags=re.IGNORECASE)
        if body and body[0].islower():
            body = body[0].upper() + body[1:]
        return match.group(1) + body + match.group(3)

    return pattern.sub(repl, html_text, count=1)


def normalize_timing_pills(html_text: str) -> str:
    def _fix(match: re.Match[str]) -> str:
        timing = match.group(1).replace(" - ", "-")
        if timing.count("-") == 1 and " - " not in match.group(1):
            timing = timing.replace("-", " - ", 1)
        return f'<span class="pill timing-pill">{timing}</span>'

    return re.sub(
        r'<span class="pill timing-pill">([^<]+)</span>',
        _fix,
        html_text,
    )


def consolidate_motion_bullet_lists(html_text: str) -> str:
    def _fix_list(match: re.Match[str]) -> str:
        items = re.findall(r"<li>(.*?)</li>", match.group(1), flags=re.DOTALL)
        merged: list[str] = []
        for item in items:
            item = item.strip()
            if not merged:
                merged.append(item)
                continue
            if item.startswith("<strong>"):
                merged.append(item)
            else:
                merged[-1] = merged[-1] + "; " + item
        return "<ul class=\"motion-bullet-list\">" + "".join(f"<li>{part}</li>" for part in merged) + "</ul>"

    return re.sub(
        r"<ul class=\"motion-bullet-list\">(.*?)</ul>",
        _fix_list,
        html_text,
        flags=re.DOTALL,
    )


def _render_story_memory_grounding(run_root: Path) -> str:
    contract = load_json(run_root / "story_contract.json")
    grounding_path = contract.get("grounding_summary")
    summary: dict[str, Any] = {}
    if grounding_path and Path(str(grounding_path)).exists():
        summary = load_json(Path(str(grounding_path)))
    else:
        fallback = run_root / "grounding/memory_recall_live/story_grounding_summary.json"
        if fallback.exists():
            summary = load_json(fallback)

    parts: list[str] = []
    integration = summary.get("story_integration") or {}
    if integration.get("codebase_topic"):
        parts.append(
            "<p><strong>Code topic from memory:</strong> "
            f"{html.escape(str(integration['codebase_topic']))}</p>"
        )
    if integration.get("persona_interjection"):
        parts.append(
            "<p><strong>How it lands in dialogue:</strong> "
            f"{html.escape(str(integration['persona_interjection']))}</p>"
        )

    recalls_used = [r for r in summary.get("recalls") or [] if r.get("used_in_story")]
    if recalls_used:
        items: list[str] = []
        for recall in recalls_used:
            lane = html.escape(str(recall.get("lane") or "memory"))
            mapping = html.escape(str(recall.get("story_mapping") or "").strip())
            status = html.escape(str(recall.get("use_status") or ""))
            line = f"<li><strong>{lane}</strong>"
            if status:
                line += f' <span class="muted">({status})</span>'
            if mapping:
                line += f" — {mapping}"
            line += "</li>"
            items.append(line)
        parts.append('<ul class="story-memory-grounding">' + "".join(items) + "</ul>")

    if not parts:
        return '<p class="muted">Memory grounding summary not recorded for this story.</p>'
    return "".join(parts)


def _entity_card(title: str, entity_id: str, description: str, details: list[tuple[str, str]], anchors: list[str] | None = None) -> str:
    bits = [
        '<article class="story-entity-card">',
        f"<h4>{html.escape(title)}</h4>",
        f'<p class="muted entity-id"><span class="code">{html.escape(entity_id)}</span></p>',
    ]
    if description:
        bits.append(f"<p>{html.escape(description)}</p>")
    if details:
        bits.append('<dl class="kv story-entity-details">')
        for label, value in details:
            if value:
                bits.append(f"<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>")
        bits.append("</dl>")
    if anchors:
        bits.append("<ul>")
        bits.extend(f"<li>{html.escape(item)}</li>" for item in anchors)
        bits.append("</ul>")
    bits.append("</article>")
    return "".join(bits)


def _render_story_entity_inventory(run_root: Path) -> str:
    ledger = load_json(run_root / "story_package" / "story_package_entity_environment_ledger_v2.json")
    visual = load_json(run_root / "story_visual_package.json")
    keyed = visual.get("keyed_entities") or {}

    parts: list[str] = [
        "<h3>Characters, props &amp; environment</h3>",
        '<p class="muted">Every visible entity the story commits to before contact sheets, script, or panels. '
        "If it is not named here, downstream art should not invent it.</p>",
    ]

    global_env = ledger.get("global_environment") or {}
    if global_env:
        parts.append("<h4>Global environment</h4>")
        parts.append('<dl class="kv story-global-environment">')
        for label, key in (
            ("Temperature", "temperature"),
            ("Weather", "weather"),
            ("Wind", "wind"),
            ("Lighting", "lighting"),
            ("Sound bed", "sound_bed"),
        ):
            value = str(global_env.get(key) or "").strip()
            if value:
                parts.append(f"<dt>{label}</dt><dd>{html.escape(value)}</dd>")
        parts.append("</dl>")

    ledger_chars = {str(item.get("id") or ""): item for item in ledger.get("characters") or []}

    def render_group(heading: str, bucket: str) -> None:
        entities = keyed.get(bucket) or {}
        if not entities:
            return
        parts.append(f"<h4>{html.escape(heading)}</h4>")
        parts.append('<div class="story-entity-list">')
        for slug, entity in entities.items():
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("entity_id") or slug)
            title = str(entity.get("display_name") or slug.replace("_", " ").title())
            description = str(entity.get("description") or "").strip()
            details: list[tuple[str, str]] = []
            if entity.get("contact_sheet_required") is True:
                details.append(("Contact sheet", "Required"))
            elif entity.get("contact_sheet_required") is False:
                details.append(("Contact sheet", "Optional / effect only"))

            if bucket == "characters":
                ledger_row = next(
                    (row for row in ledger_chars.values() if title.split("/")[0].strip() in str(row.get("name") or "") or slug in str(row.get("id") or "")),
                    None,
                )
                if ledger_row:
                    if ledger_row.get("required_identity"):
                        details.append(("Identity", str(ledger_row["required_identity"])))
                    if ledger_row.get("scale"):
                        details.append(("Scale", str(ledger_row["scale"])))
                    skin = ledger_row.get("skin_realism_required") or []
                    if skin:
                        details.append(("Skin realism", "; ".join(str(item) for item in skin)))

            must_not = entity.get("must_not_include") or []
            if must_not:
                details.append(("Must not include", "; ".join(str(item) for item in must_not)))

            anchors = [str(item) for item in (entity.get("visual_anchors") or []) if item]
            parts.append(_entity_card(title, entity_id, description, details, anchors))
            if slug == "embry" and entity_id == "character_embry":
                research_paths = _existing_embry_research_paths()
                if research_paths:
                    _ensure_embry_research_assets(run_root, research_paths)
                    research_items = [{"path": str(path.resolve())} for path in research_paths]
                    grid = _render_research_image_grid(
                        research_items,
                        run_root,
                        heading="Pre-existing persona reference images (12TB)",
                        asset_subdir="embry",
                    )
                    if grid:
                        parts.append(
                            '<div class="story-entity-research embry-research">'
                            + grid
                            + "</div>"
                        )
        parts.append("</div>")

    render_group("Characters", "characters")
    render_group("Creatures", "creatures")
    render_group("Props", "props")
    render_group("Scenery", "scenery")
    render_group("Effects", "effects")

    if len(parts) <= 2:
        return '<p class="muted">Story visual inventory not recorded.</p>'

    parts.append(
        '<p class="muted story-artifact">Artifacts: '
        '<a href="../story_visual_package.json">story_visual_package.json</a> · '
        '<a href="../story_package/story_package_entity_environment_ledger_v2.json">'
        "story_package_entity_environment_ledger_v2.json</a>. "
        'Per-panel timing lives under <a href="#panels-phase">Panels</a>; '
        'machine interaction ledgers in <a href="#pipeline-errata">Errata</a>.</p>'
    )
    return "".join(parts)


def rebuild_story_package_section(html_text: str, run_root: Path) -> str:
    section_match = re.search(
        r'(<section class="card content-block" id="story-package">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not section_match:
        return html_text

    open_tag, body, close_tag = section_match.groups()

    gate_match = re.search(r'<details class="gate-definition"[\s\S]*?</details>', body)
    verdict_match = re.search(r"<dt>Phase verdict</dt><dd>.*?</dd>", body, re.DOTALL)
    gate_result_match = re.search(r"<h3>Gate Result</h3>\s*<ul>[\s\S]*?</ul>", body)
    gate_result_html = gate_result_match.group(0) if gate_result_match else ""
    full_dl_match = re.search(r'<dl class="panel-metadata"[\s\S]*?</dl>', body)
    full_dl_html = full_dl_match.group(0) if full_dl_match else ""

    claim_match = re.search(r'<p class="muted claim-audit-pointer">[\s\S]*?</p>', body)
    claim_ptr = (
        claim_match.group(0)
        if claim_match
        else (
            '<p class="muted claim-audit-pointer"><a href="#errata-claim-audit-story-package">'
            "Claim audit</a> is in <a href=\"#pipeline-errata\">Errata</a>.</p>"
        )
    )

    panel_start = body.find('<div class="scene-constraints-card">')
    if panel_start == -1:
        panel_start = body.find("<h3>Panel breakdown</h3>")
    if panel_start == -1:
        panel_start = body.find("<h3>Panel Story Package Summary</h3>")
    panel_block = ""
    if panel_start != -1:
        panel_block = body[panel_start:]
        panel_block = re.sub(
            r"<h3>Panel Story Package Summary</h3>",
            "<h3>Panel breakdown</h3>",
            panel_block,
            count=1,
        )
        panel_block = re.sub(
            r'<p class="muted">Two-column storyboard summary\.[\s\S]*?</p>\s*',
            '<p class="muted">Timed beats derived from the story above. Per-panel machine ledgers are in Errata.</p>\n  ',
            panel_block,
            count=1,
        )
        panel_block = re.sub(r"<h3>Gate Result</h3>\s*<ul>[\s\S]*?</ul>\s*", "", panel_block)
        panel_block = re.sub(r'<p class="muted claim-audit-pointer">[\s\S]*?</p>\s*', "", panel_block)
        panel_block = re.sub(r"<h3>Story</h3>[\s\S]*?(?=<h3>Panel breakdown</h3>|<div class=\"scene-constraints-card\">)", "", panel_block)

    contract = load_json(run_root / "story_contract.json")
    story = str(contract.get("story") or "").strip()
    seed = str(contract.get("seed") or "").strip()
    if not story:
        md_path = run_root / "story_contract.md"
        if md_path.exists():
            story = "\n".join(
                line for line in md_path.read_text().splitlines() if not line.startswith("#")
            ).strip()

    slim_dl = '<dl class="panel-metadata" style="margin-bottom:1.5rem;">'
    if verdict_match:
        slim_dl += verdict_match.group(0)
    slim_dl += '<dt>Gate proof</dt><dd><a href="#errata-phase-3-gate-proof">Errata</a></dd>'
    slim_dl += (
        '<dt>Story artifact</dt><dd><a href="../story_contract.json">story_contract.json</a>'
        ' · <a href="../story_contract.md">story_contract.md</a></dd>'
    )
    slim_dl += "</dl>"

    story_section = (
        "<h3>Story</h3>"
        '<p class="muted">The narrative generated from the Phase 1 idea and Phase 2 memory recall.</p>'
        + (
            f'<p class="muted story-seed"><strong>Seed:</strong> {html.escape(seed)}</p>'
            if seed
            else ""
        )
        + (
            f'<div class="story-package-prose"><p>{html.escape(story)}</p></div>'
            if story
            else '<div class="story-package-prose"><p class="muted">(story not recorded)</p></div>'
        )
        + "<h3>Memory grounding</h3>"
        + _render_story_memory_grounding(run_root)
        + _render_story_entity_inventory(run_root)
        + claim_ptr
    )

    new_body = "\n".join(
        part
        for part in [
            gate_match.group(0) if gate_match else "",
            slim_dl,
            story_section,
        ]
        if part
    )
    html_text = html_text.replace(section_match.group(0), open_tag + new_body + close_tag, 1)

    if not gate_result_html and not full_dl_html:
        return html_text

    errata_bits: list[str] = []
    if gate_result_html:
        errata_bits.append(gate_result_html.replace("<h3>Gate Result</h3>", "", 1))
    if full_dl_html:
        errata_bits.append(full_dl_html)

    errata_article = (
        '<article class="errata-phase" id="errata-phase-3-gate-proof">'
        "<h3>Phase 3 — story package gate proof</h3>"
        '<p class="muted">Repair history, ledger paths, and structural verification receipts. '
        "The phase body shows the story itself.</p>"
        + "".join(errata_bits)
        + "</article>"
    )

    if 'id="errata-phase-3-gate-proof"' in html_text:
        return re.sub(
            r'<article class="errata-phase" id="errata-phase-3-gate-proof">[\s\S]*?</article>',
            errata_article,
            html_text,
            count=1,
        )

    errata_match = re.search(
        r'(<section class="card content-block" id="pipeline-errata">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not errata_match:
        return html_text

    errata_open, errata_body, errata_close = errata_match.groups()
    insert_at = errata_body.find('<article class="errata-phase" id="errata-phase-3-interactions"')
    if insert_at == -1:
        errata_body = errata_body.rstrip() + "\n" + errata_article + "\n"
    else:
        errata_body = errata_body[:insert_at] + errata_article + "\n" + errata_body[insert_at:]

    return (
        html_text[: errata_match.start()]
        + errata_open
        + errata_body
        + errata_close
        + html_text[errata_match.end() :]
    )

def redesign_panel_story_summary(html_text: str) -> str:
    marker = "<h3>Panel Story Package Summary</h3>"
    if marker not in html_text or "panel-story-summary-table" in html_text:
        return html_text

    start = html_text.find(marker)
    table_start = html_text.find('<div class="table-scroll"><table>', start)
    table_end = html_text.find("</table></div>", table_start)
    if table_start == -1 or table_end == -1:
        return html_text

    table_html = html_text[table_start:table_end + len("</table></div>")]
    rows = list(PANEL_SUMMARY_ROW.finditer(table_html))
    if not rows:
        return html_text

    weather_values = []
    parsed_rows = []
    for match in rows:
        panel_no, timing, shot, interactions, weather_raw, motion_raw = match.groups()
        weather_values.append(_format_weather_text(weather_raw))
        parsed_rows.append(
            {
                "panel_no": panel_no,
                "timing": timing.strip(),
                "shot": shot.strip(),
                "interactions": interactions.strip(),
                "motion_html": _parse_motion_bullets(motion_raw),
            }
        )

    global_weather = weather_values[0] if weather_values and len(set(weather_values)) == 1 else ""
    constraints = ""
    if global_weather:
        constraints = (
            '<div class="scene-constraints-card">'
            "<strong>Scene constraints</strong>"
            f"<p>{html.escape(global_weather)}</p>"
            "</div>"
        )

    body_rows = []
    for row in parsed_rows:
        body_rows.append(
            "<tr>"
            '<td class="panel-identity-cell">'
            f'<div class="panel-identity-label">Panel {html.escape(row["panel_no"])}</div>'
            f'<span class="pill timing-pill">{html.escape(row["timing"].replace("-", " - ", 1))}</span>'
            f'<div class="panel-shot-label"><em>{html.escape(row["shot"])}</em></div>'
            "</td>"
            '<td class="panel-motion-cell">'
            f'<span class="interaction-count-badge">{html.escape(row["interactions"])} interactions</span>'
            f'{row["motion_html"]}'
            "</td>"
            "</tr>"
        )

    replacement = (
        constraints
        + marker
        + '\n  <p class="muted">Two-column storyboard summary. Global weather/temperature is listed once above when it is shared across panels.</p>'
        + '\n  <div class="table-scroll"><table class="panel-story-summary-table"><thead><tr>'
        + "<th>Panel Identity</th><th>Key Motions &amp; Interactions</th>"
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>"
    )

    return html_text[:start] + replacement + html_text[table_end + len("</table></div>"):]


FULL_INTERACTIONS_BLOCK = re.compile(
    r"<h3>Full Required Interaction Tables</h3>\s*(?P<body>(?:\s*<details class=\"phase-details\">.*?</details>\s*)+)",
    re.DOTALL,
)


def move_full_interaction_tables_to_errata(html_text: str) -> str:
    if 'id="errata-phase-3-interactions"' in html_text:
        return html_text

    section_match = re.search(
        r'(<section class="card content-block" id="story-package">.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not section_match:
        return html_text

    section_body = section_match.group(1)
    block_match = FULL_INTERACTIONS_BLOCK.search(section_body)
    if not block_match:
        return html_text

    interactions_html = block_match.group(0)
    pointer = (
        '<p class="muted interaction-tables-pointer">'
        'Full per-panel interaction tables are in '
        '<a href="#errata-phase-3-interactions">Errata</a>.</p>'
    )
    new_section_body = FULL_INTERACTIONS_BLOCK.sub(pointer, section_body, count=1)
    html_text = html_text.replace(section_match.group(1), new_section_body, 1)

    errata_article = (
        '<article class="errata-phase" id="errata-phase-3-interactions">'
        "<h3>Phase 3 — full required interaction tables</h3>"
        "<p class=\"muted\">Machine-level interaction ledger by panel. Collapsed by default.</p>"
        + interactions_html.replace("<h3>Full Required Interaction Tables</h3>", "", 1)
        + "</article>"
    )

    errata_match = re.search(
        r'(<section class="card content-block" id="pipeline-errata">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not errata_match:
        return html_text

    errata_open, errata_body, errata_close = errata_match.groups()
    errata_body = errata_body.rstrip() + "\n" + errata_article + "\n"
    return (
        html_text[: errata_match.start()]
        + errata_open
        + errata_body
        + errata_close
        + html_text[errata_match.end() :]
    )


CSS = """
.pipeline-outline { margin: 0 0 1.5rem; padding: 0.75rem 0 0.75rem 1rem; border-left: 3px solid var(--border-medium); color: var(--text-muted); }
.pipeline-outline ol { margin: 0; padding-left: 1.25rem; }
.pipeline-outline li { margin: 0.35rem 0; }
.pipeline-outline a { color: var(--text-strong); text-decoration: none; font-weight: 600; }
.pipeline-outline a:hover { text-decoration: underline; }
.pipeline-next { margin-top: 1rem; color: var(--text-muted); }
.phase-gate-line { margin: 0.15rem 0 1rem; font-size: 0.95rem; }
.phase-gate-line.pass { color: var(--badge-green-text); }
.phase-gate-line.warn { color: var(--badge-amber-text); }
.phase-gate-line.blocked { color: var(--badge-red-text); }
.phase-gate-pass, .status-pass { color: var(--badge-green-text); background: transparent; border: 0; padding: 0; margin: 0 0 0.75rem; font-weight: 600; }
.phase-gate-warn, .status-warn { color: var(--badge-amber-text); background: transparent; border: 0; padding: 0; margin: 0 0 0.75rem; font-weight: 600; }
.phase-gate-blocked, .status-blocked { color: var(--badge-red-text); background: var(--badge-red-bg); border: 1px solid color-mix(in srgb, var(--badge-red-text) 25%, transparent); padding: 0.75rem 1rem; border-radius: 8px; margin: 0 0 1rem; font-weight: 600; }
.status-note { background: var(--bg-header); border: 1px solid var(--border-light); color: var(--text-muted); padding: 0.5rem 0.75rem; border-radius: 6px; margin: 0.75rem 0; font-size: 0.9rem; }
#memories-used .recall-overview-table { width: 100%; border-collapse: collapse; }
#memories-used .recall-overview-table th, #memories-used .recall-overview-table td { border: 1px solid var(--border-light); padding: 0.65rem 0.75rem; vertical-align: top; }
#memories-used .recall-overview-table th { background: var(--bg-header); text-align: left; }

#memories-used .recall-overview-claim-cell { font-weight: 700; white-space: nowrap; vertical-align: middle; }
#memories-used .recall-overview-claim-cell a { vertical-align: middle; }
#memories-used .recall-overview-question { font-size: 0.92rem; }
#memories-used .recall-overview-summary-cell { font-size: 0.92rem; color: var(--text-muted); }

.status-dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-right: 0.6rem;
  flex-shrink: 0;
  vertical-align: middle;
}
.status-dot.badge-pass { background-color: var(--badge-green-text); box-shadow: 0 0 5px var(--badge-green-text); }
.status-dot.badge-warn { background-color: var(--badge-amber-text); box-shadow: 0 0 5px var(--badge-amber-text); }
.status-dot.badge-fail { background-color: var(--badge-red-text); box-shadow: 0 0 5px var(--badge-red-text); }
.claim-audit:target { scroll-margin-top: 1.25rem; outline: 2px solid color-mix(in srgb, var(--badge-green-text) 55%, transparent); border-radius: 8px; background: color-mix(in srgb, var(--badge-green-bg) 35%, transparent); }
#memories-used .claim-link { font-weight: 700; text-decoration: none; }
#memories-used .claim-link:hover { text-decoration: underline; }

#memories-used .recall-overview-table table { width: 100%; font-size: 0.9rem; }
.idea-hero { margin: 0 0 1.25rem; padding: 1.35rem 1.5rem; border-radius: 12px; border: 1px solid var(--border-light); background: linear-gradient(135deg, var(--bg-header), var(--bg-card)); }
.idea-hero-label { margin: 0 0 0.65rem; font-size: 0.72rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); }
.idea-hero-text { margin: 0; font-size: 1.28rem; line-height: 1.55; font-weight: 600; color: var(--text-strong); }
.idea-hero-meta { margin: 0.85rem 0 0; font-size: 0.92rem; }
.recall-proof-table td { vertical-align: top; }
#pipeline-errata { margin-top: 2rem; }
.contact-sheet-list { display: flex; flex-direction: column; gap: 2rem; margin: 0 0 1.5rem; }
.contact-sheet-entry { border: 1px solid var(--border-light); border-radius: 8px; padding: 1rem 1rem 1.1rem; background: var(--bg-header); }
.contact-sheet-entry-header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.65rem 0.85rem; margin-bottom: 0.85rem; }
.contact-sheet-entry-header h4 { margin: 0; font-size: 1.05rem; }
.contact-sheet-entry-meta { font-size: 0.82rem; color: var(--text-muted); }
.contact-sheet-full-image { background: var(--inline-code-bg); border-radius: 6px; overflow: hidden; margin-bottom: 0.85rem; }
.contact-sheet-full-image img { display: block; width: 100%; max-width: 1600px; height: auto; margin: 0 auto; }
.contact-sheet-missing { padding: 3rem 1rem; color: var(--text-muted); font-size: 0.9rem; text-align: center; border: 1px dashed var(--border-medium); border-radius: 6px; width: 100%; }
.contact-sheet-provenance { margin: 0.75rem 0 0; }
.contact-sheet-provenance summary { cursor: pointer; font-weight: 600; }
.contact-sheet-prompt-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  list-style: none;
}
.contact-sheet-prompt-summary::-webkit-details-marker { display: none; }
.contact-sheet-summary-label { flex: 1 1 auto; }
.contact-sheet-copy-bundle {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-light);
  background: var(--inline-code-bg);
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.28rem 0.42rem;
  border-radius: 6px;
  line-height: 0;
}
.contact-sheet-copy-bundle:hover {
  color: var(--text-primary, #e8eaed);
  border-color: var(--border-medium);
  background: rgba(255,255,255,0.06);
}
.contact-sheet-copy-bundle.copied {
  color: #3dd68c;
  border-color: rgba(61, 214, 140, 0.45);
}
.contact-sheet-copy-bundle.failed {
  color: #ff8f8f;
  border-color: rgba(255, 143, 143, 0.45);
}
.contact-sheet-copy-bundle .contact-sheet-copy-icon { display: block; }
.panel-header {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
}
.panel-header strong { margin-right: auto; }
.asset-recreate-actions { display: inline-flex; align-items: center; gap: 0.35rem; margin-left: auto; }
.panel-header .asset-recreate-actions { margin-left: auto; }
.contact-sheet-regenerate-bundle {
  border: 1px solid var(--border, #3a3f4b);
  background: var(--surface-2, #1e2128);
  color: var(--text, #e8eaed);
  border-radius: 6px;
  width: 2rem;
  height: 2rem;
  cursor: pointer;
  font-size: 1.1rem;
  line-height: 1;
}
.contact-sheet-regenerate-bundle:hover { border-color: #7aa2ff; color: #7aa2ff; }
.contact-sheet-regenerate-bundle.running { opacity: 0.6; cursor: wait; }
.contact-sheet-regenerate-bundle.done { border-color: #6fcf97; color: #6fcf97; }
.contact-sheet-regenerate-bundle.failed { border-color: #ff7b72; color: #ff7b72; }
.pipeline-copy-toast {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  z-index: 9999;
  max-width: min(28rem, calc(100vw - 2rem));
  padding: 0.7rem 0.9rem;
  border-radius: 8px;
  border: 1px solid var(--border-light);
  background: rgba(18, 20, 24, 0.96);
  color: var(--text-primary, #e8eaed);
  box-shadow: 0 8px 24px rgba(0,0,0,0.35);
  font-size: 0.88rem;
}
.pipeline-copy-toast.is-success { border-color: rgba(61, 214, 140, 0.45); }
.pipeline-copy-toast.is-warn { border-color: rgba(255, 196, 86, 0.45); }
.pipeline-copy-toast.is-error { border-color: rgba(255, 143, 143, 0.45); }
.contact-sheet-prompt pre { margin: 0.65rem 0 0; padding: 0.85rem; border-radius: 6px; background: var(--inline-code-bg); white-space: pre-wrap; word-break: break-word; font-size: 0.84rem; line-height: 1.5; }
.contact-sheet-research { margin-top: 0.65rem; }
.contact-sheet-research h5 { margin: 0.75rem 0 0.35rem; font-size: 0.9rem; }
.contact-sheet-research ul { margin: 0; padding-left: 1.2rem; }
.contact-sheet-research li { margin: 0.35rem 0; font-size: 0.86rem; line-height: 1.45; }
.research-image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.75rem;
  margin: 0.5rem 0 1rem;
}
.research-image-tile {
  margin: 0;
  border: 1px solid var(--border, #2a2f3a);
  border-radius: 6px;
  overflow: hidden;
  background: rgba(0,0,0,0.15);
}
.research-image-tile img {
  display: block;
  width: 100%;
  height: auto;
  max-height: 220px;
  object-fit: contain;
  background: #111;
}
.research-image-tile figcaption a {
  color: var(--accent, #6ea8fe);
  word-break: break-all;
}
.research-image-tile figcaption {
  font-size: 0.78rem;
  padding: 0.4rem 0.5rem;
  line-height: 1.35;
}
.story-entity-research {
  margin: -0.25rem 0 1rem 1rem;
  padding-left: 0.75rem;
  border-left: 3px solid var(--accent, #6ea8fe);
}

.contact-sheet-research-empty { margin: 0.5rem 0 0; font-size: 0.85rem; color: var(--text-muted); }

.story-package-prose p { margin: 0.85rem 0 0; font-size: 1.05rem; line-height: 1.65; }
.story-seed { margin: 0.5rem 0 0; }
.story-memory-grounding { margin: 0.5rem 0 0; padding-left: 1.2rem; }
.story-memory-grounding li { margin: 0.35rem 0; line-height: 1.45; }

.scene-constraints-card { margin: 0 0 1rem; padding: 0.85rem 1rem; border: 1px solid var(--border-light); border-radius: 8px; background: var(--bg-header); }
.scene-constraints-card p { margin: 0.35rem 0 0; color: var(--text-muted); }
.panel-story-summary-table { width: 100%; border-collapse: collapse; }
.panel-story-summary-table th, .panel-story-summary-table td { border: 1px solid var(--border-light); padding: 0.75rem; vertical-align: top; }
.panel-story-summary-table th { background: var(--bg-header); text-align: left; }
.panel-identity-cell { width: 24%; }
.panel-motion-cell { width: 76%; }
.panel-identity-label { font-size: 1.05rem; font-weight: 800; margin-bottom: 0.35rem; }
.timing-pill { display: inline-block; margin-bottom: 0.45rem; font-size: 0.82rem; color: var(--text-muted); background: var(--inline-code-bg); }
.panel-shot-label { color: var(--text-muted); font-size: 0.92rem; }
.section-badge { float: right; font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem; border-radius: 4px; display: inline-flex; align-items: center; gap: 0.25rem; }
.section-pass { color: #22c55e; background: rgba(34,197,94,0.12); }
.section-fail { color: #ef4444; background: rgba(239,68,68,0.12); }
.section-warn { color: #fbbf24; background: rgba(251,191,36,0.12); }
.section-badge i { width: 14px; height: 14px; }
h2 { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
.section-title-text { flex: 1 1 auto; }
.gate-summary-banner { margin: 0 0 1.5rem; border-left: 4px solid #ef4444; }
.gate-summary-title { display: flex; align-items: center; gap: 0.5rem; font-weight: 700; color: var(--text-strong); margin-bottom: 0.65rem; }
.gate-summary-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.65rem; }
.gate-chip { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.25rem 0.6rem; border-radius: 999px; font-size: 0.82rem; font-weight: 700; }
.gate-chip-blocked { color: #fecaca; background: rgba(127,29,29,0.55); border: 1px solid #7f1d1d; }
.gate-chip-export-blocked { color: #fff; background: #991b1b; border: 1px solid #7f1d1d; }
.pipeline-outline .phase-outline-status { font-weight: 700; margin-left: 0.35rem; }
.pipeline-outline .phase-status-pass .phase-outline-status { color: #22c55e; }
.pipeline-outline .phase-status-blocked .phase-outline-status { color: #ef4444; }
.pipeline-outline .phase-status-warn .phase-outline-status { color: #fbbf24; }
.section-provisional { opacity: 0.92; border-style: dashed; }
.section-provisional-note { margin: 0 0 1rem; padding: 0.65rem 0.85rem; border-radius: 8px; background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.35); color: var(--text-main); }
.panel-storyboard-table { width: 100%; border-collapse: collapse; }
.panel-storyboard-table th, .panel-storyboard-table td { border: 1px solid var(--border-light); padding: 0.75rem; vertical-align: top; }
.panel-storyboard-table th { background: var(--bg-header); text-align: left; }
.panel-thumb-cell { width: 210px; }
.panel-storyboard-thumb { width: 200px; max-width: 100%; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.25); display: block; }
.panel-action-cell { min-width: 280px; }
.panel-beat-text { margin: 0.45rem 0 0.35rem; }
.motion-cue-badge { display: inline-block; margin: 0.15rem 0.35rem 0.15rem 0; padding: 0.1rem 0.45rem; border-radius: 999px; font-size: 0.75rem; background: var(--inline-code-bg); color: var(--text-muted); }
.panel-audio-play { background: transparent; border: 0; color: #fbbf24; cursor: pointer; padding: 0; }
.panel-audio-muted { color: var(--text-muted); }
.panel-gate-badge.gate-pass { color: #22c55e; }
.panel-gate-badge.gate-fail { color: #ef4444; }

.interaction-count-badge { display: inline-block; margin-bottom: 0.55rem; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.8rem; font-weight: 700; color: var(--text-muted); background: var(--inline-code-bg); }
.motion-bullet-list { margin: 0.25rem 0 0; padding-left: 1.1rem; }
.motion-bullet-list li { margin: 0.35rem 0; }

.stage-audit-list { display: grid; gap: 1rem; margin-top: 1rem; }

/* Gate definition: neutral info panel, collapsed by default when phase passes.
   Heavy red is reserved for actual failure/blocked status messages. */
.gate-definition {
  background: var(--bg-header);
  border: 1px solid var(--border-light);
  border-left: 3px solid #3b82f6;
  color: var(--text-muted);
  border-radius: 0 8px 8px 0;
  margin: 0.75rem 0 1rem;
  font-size: 0.92rem;
  overflow: hidden;
}
.gate-definition summary {
  cursor: pointer;
  list-style: none;
  padding: 0.65rem 0.85rem;
  font-weight: 600;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  user-select: none;
}
.gate-definition summary::-webkit-details-marker { display: none; }
.gate-definition summary::before {
  content: "i";
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #3b82f6;
  color: #fff;
  font-size: 0.72rem;
  font-weight: 800;
  font-family: Georgia, "Times New Roman", serif;
  line-height: 1;
}
.gate-definition .gate-definition-body {
  padding: 0 0.85rem 0.75rem;
  line-height: 1.55;
}
.gate-definition .gate-definition-body > *:first-child { margin-top: 0; }
.gate-definition .gate-definition-body > *:last-child { margin-bottom: 0; }
.gate-definition[open] summary { margin-bottom: 0.25rem; }
.gate-definition.is-failed {
  border-left-color: var(--badge-red-text);
}
.gate-definition.is-failed summary { color: var(--badge-red-text); }

.gate-definition.is-failed summary::before {
  background: var(--badge-red-text);
  content: "!";
}

/* Sticky pipeline nav */
.sticky-nav {
  position: sticky;
  top: 0;
  z-index: 1000;
  margin: -2rem -2rem 1.25rem;
  padding: 0.65rem 2rem 0.7rem;
  background: color-mix(in srgb, var(--bg-page) 94%, transparent);
  border-bottom: 1px solid var(--border-light);
  backdrop-filter: blur(12px);
}
.sticky-nav-inner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}
.pipeline-flow {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex: 1 1 auto;
  min-width: 0;
  flex-wrap: wrap;
}
.flow-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.32rem 0.62rem;
  border-radius: 999px;
  border: 1px solid var(--border-light);
  background: var(--bg-card);
  color: var(--text-main);
  font-size: 0.82rem;
  font-weight: 650;
  line-height: 1;
  text-decoration: none;
  white-space: nowrap;
}
.flow-link:hover {
  border-color: var(--border-medium);
  background: var(--bg-header);
}
.flow-link svg {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
}
.flow-link[data-status="pass"] { border-color: color-mix(in srgb, var(--badge-green-text) 35%, var(--border-light)); }
.flow-link[data-status="pass"] svg { color: var(--badge-green-text); }
.flow-link[data-status="warn"] { border-color: color-mix(in srgb, var(--badge-amber-text) 35%, var(--border-light)); }
.flow-link[data-status="warn"] svg { color: var(--badge-amber-text); }
.flow-link[data-status="blocked"] { border-color: color-mix(in srgb, var(--badge-red-text) 40%, var(--border-light)); }
.flow-link[data-status="blocked"] svg { color: var(--badge-red-text); }
.flow-appendix {
  margin-left: auto;
  flex: 0 0 auto;
}
.flow-chevron, .flow-separator { display: none !important; }
.pipeline-flow-status {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin-top: 0.55rem;
  min-width: 0;
  color: var(--text-muted);
  font-size: 0.8rem;
  line-height: 1.35;
}
.pipeline-flow-status-pill {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  padding: 0.18rem 0.55rem;
  border-radius: 999px;
  background: var(--badge-red-bg);
  color: var(--badge-red-text);
  font-size: 0.74rem;
  font-weight: 800;
  white-space: nowrap;
}
.pipeline-flow-status-detail {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
section.card { scroll-margin-top: 7.5rem; }
@media (max-width: 900px) {
  .sticky-nav { margin-left: -1rem; margin-right: -1rem; padding-left: 1rem; padding-right: 1rem; }
  .flow-link span { max-width: 5.5rem; overflow: hidden; text-overflow: ellipsis; }
}
"""



JS = r"""
(function () {
  'use strict';

  /**
   * Promote anti-hallucination gate definition blocks from red alerts to
   * neutral info accordions. Actual failure/blocked status messages stay red.
   */
  function upgradeGateDefinitions() {
    document.querySelectorAll('.status-alert, .status').forEach((el) => {
      const t = el.textContent || '';
      const lower = t.toLowerCase();

      if (/phase gate:/i.test(t)) {
        el.classList.remove('status-alert');
        if (/\b(fail|blocked|lie_not|missing dedicated|not live|remains blocked)\b/i.test(lower)) {
          el.classList.add('phase-gate-blocked');
        } else if (/\b(warn|review|stale|quarantine|partial|reconciled)\b/i.test(lower)) {
          el.classList.add('phase-gate-warn');
        } else if (/\b(complete|pass|proven|safe to proceed|recorded)\b/i.test(lower)) {
          el.classList.add('phase-gate-pass');
        } else {
          el.classList.add('status-note');
        }
        return;
      }

      if (/anti-hallucination gate|foreground prop behavior gate/i.test(t)) {
        convertToGateDefinition(el);
        return;
      }

      if (/live kling execution is/i.test(lower) && /blocked/i.test(lower)) {
        el.classList.remove('status');
        el.classList.add('status-blocked');
      }
    });
  }

  function convertToGateDefinition(el) {
    const html = el.innerHTML;
    const match = html.match(/^(<strong>[^<]+(?:anti-hallucination gate|prop behavior gate)[^<]*<\/strong>)(?:\s*|:\s*)(.*)$/i);
    if (!match) return;

    const summaryHtml = match[1];
    const bodyHtml = match[2].trim();
    const section = el.closest('section.pipeline-phase, section.card, section');
    const failed = section ? /\bbadge-fail\b|\bbadge-bad\b|\bFAIL\b|\bBlocked\b/.test(section.innerHTML) : false;

    const details = document.createElement('details');
    details.className = 'gate-definition' + (failed ? ' is-failed' : '');
    if (failed) details.open = true;

    const summary = document.createElement('summary');
    summary.innerHTML = summaryHtml;

    const body = document.createElement('div');
    body.className = 'gate-definition-body';
    body.innerHTML = bodyHtml || '';

    details.appendChild(summary);
    details.appendChild(body);
    el.replaceWith(details);
  }

  function openPanelLedgerFromHash() {
    const hash = window.location.hash || '';
    const match = hash.match(/^#panel-interaction-ledger-(\d+)$/);
    if (!match) return;
    const details = document.getElementById(`panel-interaction-ledger-${match[1]}`);
    if (!details) return;
    details.open = true;
    details.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function openPanelContractFromHash() {
    const hash = window.location.hash || '';
    const match = hash.match(/^#errata-panel-(\d+)-interaction-contract$/);
    if (!match) return;
    const details = document.getElementById(`errata-panel-${match[1]}-interaction-contract`);
    if (!details) return;
    details.open = true;
    details.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function initPanelLedgerLinks() {
    document.querySelectorAll('.panel-ledger-link').forEach((link) => {
      link.addEventListener('click', (event) => {
        const href = link.getAttribute('href') || '';
        const match = href.match(/^#panel-interaction-ledger-(\d+)$/);
        if (!match) return;
        const details = document.getElementById(`panel-interaction-ledger-${match[1]}`);
        if (!details) return;
        event.preventDefault();
        details.open = true;
        history.pushState(null, '', href);
        details.scrollIntoView({ block: 'start', behavior: 'smooth' });
      });
    });
  }

  function initPanelContractLinks() {
    document.querySelectorAll('.panel-contract-pointer a[href^="#errata-panel-"]').forEach((link) => {
      link.addEventListener('click', (event) => {
        const href = link.getAttribute('href') || '';
        const match = href.match(/^#errata-panel-(\d+)-interaction-contract$/);
        if (!match) return;
        const details = document.getElementById(`errata-panel-${match[1]}-interaction-contract`);
        if (!details) return;
        event.preventDefault();
        details.open = true;
        history.pushState(null, '', href);
        details.scrollIntoView({ block: 'start', behavior: 'smooth' });
      });
    });
  }


  function showCopyBundleToast(message, kind) {
    let toast = document.getElementById('pipeline-copy-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'pipeline-copy-toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = 'pipeline-copy-toast' + (kind ? ' is-' + kind : '');
    toast.hidden = false;
    clearTimeout(showCopyBundleToast._timer);
    showCopyBundleToast._timer = setTimeout(() => {
      toast.hidden = true;
    }, 2600);
  }

  async function copyContactSheetBundle(button) {
    const absPath = button.getAttribute('data-bundle-path') || '';
    const href = button.getAttribute('data-bundle-href') || '';
    if (!absPath) {
      showCopyBundleToast('Recreate bundle missing', 'error');
      return;
    }

    const endpoints = [
      'http://127.0.0.1:8893/clipboard/file',
      'http://127.0.0.1:8892/api/clipboard/file',
    ];

    button.disabled = true;
    button.classList.remove('copied', 'failed');

    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: absPath, target: 'kde' }),
        });
        if (!response.ok) {
          continue;
        }
        button.classList.add('copied');
        showCopyBundleToast(button.dataset.sheetStem && button.dataset.sheetStem.startsWith('panel_') ? 'Panel recreate bundle copied to clipboard' : 'Recreate bundle copied to clipboard', 'success');
        button.disabled = false;
        return;
      } catch (_error) {
        /* try next endpoint */
      }
    }

    if (href) {
      const link = document.createElement('a');
      link.href = href;
      link.download = '';
      document.body.appendChild(link);
      link.click();
      link.remove();
      button.classList.add('failed');
      showCopyBundleToast('Clipboard bridge offline — downloaded bundle instead', 'warn');
    } else {
      button.classList.add('failed');
      showCopyBundleToast('Clipboard bridge offline', 'error');
    }
    button.disabled = false;
  }

  async function regenerateFromBundle(button) {
    const absPath = button.getAttribute('data-bundle-path') || '';
    const kind = button.getAttribute('data-regenerate-kind') || '';
    const runRoot = button.getAttribute('data-run-root') || '';
    if (!absPath || !kind) {
      showCopyBundleToast('Recreate bundle missing', 'error');
      return;
    }
    const endpoints = ['http://127.0.0.1:8893/regenerate/run'];
    button.disabled = true;
    button.classList.remove('done', 'failed');
    button.classList.add('running');
    showCopyBundleToast('Regenerating ' + (kind === 'panel' ? 'panel' : 'contact sheet') + '…', 'warn');
    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind, bundle: absPath, run_root: runRoot || undefined }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) {
          const detail = (payload.stderr || payload.stdout || 'regenerate failed').trim();
          throw new Error(detail.slice(0, 240));
        }
        button.classList.add('done');
        showCopyBundleToast('Regeneration finished — reload report to see updates', 'success');
        button.disabled = false;
        button.classList.remove('running');
        return;
      } catch (error) {
        showCopyBundleToast(String(error.message || error), 'error');
      }
    }
    button.classList.add('failed');
    button.disabled = false;
    button.classList.remove('running');
  }

  function initContactSheetRegenerateButtons() {
    document.querySelectorAll('.contact-sheet-regenerate-bundle').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        regenerateFromBundle(button);
      });
    });
  }

  function initContactSheetCopyButtons() {
    document.querySelectorAll('.contact-sheet-copy-bundle').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        copyContactSheetBundle(button);
      });
    });
  }

  upgradeGateDefinitions();
  initPanelLedgerLinks();
  initPanelContractLinks();
  initContactSheetCopyButtons();
  initContactSheetRegenerateButtons();
  window.addEventListener('hashchange', () => {
    openPanelLedgerFromHash();
    openPanelContractFromHash();
  });
  openPanelLedgerFromHash();
  openPanelContractFromHash();
})();
"""




def _ensure_contact_sheet_assets(run_root: Path) -> None:
    assets_dir = run_root / "pipeline_review_8892" / "assets"
    ref_dir = run_root / "reference_sheets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if not ref_dir.exists():
        return
    for ref in ref_dir.glob("*.png"):
        target = assets_dir / ref.name
        if target.exists():
            continue
        try:
            target.symlink_to(ref.resolve())
        except OSError:
            pass


PANEL_INTERACTION_CONTRACT = re.compile(
    r'<div class="panel-interactions" id="panel-(\d+)-interactions">'
    r'(<h3>Characters / Props / Environment Contract</h3>[\s\S]*?</table></div>\s*)</div>',
    re.DOTALL,
)


def move_panel_interaction_contracts_to_errata(html_text: str) -> str:
    matches = list(PANEL_INTERACTION_CONTRACT.finditer(html_text))
    if not matches:
        return html_text

    details_blocks: list[str] = []
    for match in matches:
        panel_no = match.group(1)
        inner = re.sub(
            r"<h3>Characters / Props / Environment Contract</h3>\s*",
            "",
            match.group(2),
            count=1,
        )
        anchor = f"errata-panel-{panel_no}-interaction-contract"
        pointer = (
            f'<p class="muted panel-contract-pointer">'
            f'<a href="#{anchor}">Characters / Props / Environment Contract</a> is in '
            f'<a href="#errata-phase-6-panel-interaction-contracts">Errata</a>.</p>'
        )
        html_text = html_text.replace(match.group(0), pointer, 1)
        details_blocks.append(
            f'<details class="phase-details panel-interaction-contract" id="{anchor}">'
            f"<summary>Panel {panel_no} — Characters / Props / Environment Contract</summary>"
            + inner
            + "</details>"
        )

    errata_article = (
        '<article class="errata-phase" id="errata-phase-6-panel-interaction-contracts">'
        "<h3>Phase 6 — Characters / Props / Environment contracts</h3>"
        '<p class="muted">Per-panel repair contracts from storyboard anti-hallucination review. '
        "Collapsed by default.</p>"
        + "".join(details_blocks)
        + "</article>"
    )

    if 'id="errata-phase-6-panel-interaction-contracts"' in html_text:
        return re.sub(
            r'<article class="errata-phase" id="errata-phase-6-panel-interaction-contracts">[\s\S]*?</article>',
            errata_article,
            html_text,
            count=1,
        )

    errata_match = re.search(
        r'(<section class="card content-block" id="pipeline-errata">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not errata_match:
        return html_text

    errata_open, errata_body, errata_close = errata_match.groups()
    insert_at = errata_body.find('<article class="errata-phase" id="errata-phase-5-contact-sheets"')
    if insert_at != -1:
        end = errata_body.find("</article>", insert_at)
        if end != -1:
            insert_at = end + len("</article>")
            errata_body = errata_body[:insert_at] + "\n" + errata_article + "\n" + errata_body[insert_at:]
        else:
            errata_body = errata_body.rstrip() + "\n" + errata_article + "\n"
    else:
        insert_at = errata_body.find('<article class="errata-phase" id="errata-phase-3-interactions"')
        if insert_at != -1:
            end = errata_body.find("</article>", insert_at)
            if end != -1:
                insert_at = end + len("</article>")
                errata_body = errata_body[:insert_at] + "\n" + errata_article + "\n" + errata_body[insert_at:]
            else:
                errata_body = errata_body.rstrip() + "\n" + errata_article + "\n"
        else:
            errata_body = errata_body.rstrip() + "\n" + errata_article + "\n"

    return (
        html_text[: errata_match.start()]
        + errata_open
        + errata_body
        + errata_close
        + html_text[errata_match.end() :]
    )


REQUIRED_COVERAGE_BLOCK = re.compile(
    r"<h3>Required Coverage</h3><div class=\"table-scroll\"><table>[\s\S]*?</table></div>\s*",
    re.DOTALL,
)


def _required_coverage_table_html(run_root: Path) -> str:
    gate = load_json(run_root / "pipeline_review_8892" / "artifacts" / "phase_05_contact_sheets_anti_hallucination_gate.json")
    requirements = gate.get("requirements") or []
    if not requirements:
        return ""

    rows: list[str] = []
    for req in requirements:
        rid = html.escape(str(req.get("id") or ""))
        name = html.escape(str(req.get("name") or rid))
        req_type = html.escape(str(req.get("type") or ""))
        file_name = req.get("file")
        mapped = html.escape(str(file_name)) if file_name else "MISSING"
        verdict = str(req.get("verdict") or "UNKNOWN").upper()
        basis = html.escape(str(req.get("basis") or ""))
        if verdict == "FAIL":
            badge = "<span class='badge badge-fail'><i data-lucide='octagon-x'></i>FAIL</span>"
        elif verdict == "PARTIAL":
            badge = "<span class='badge badge-warn'><i data-lucide='alert-circle'></i>PARTIAL</span>"
        else:
            badge = "<span class='badge badge-pass'><i data-lucide='check-circle'></i>PASS</span>"
        rows.append(
            "<tr>"
            f"<td><span class='code'>{rid}</span><br>{name}</td>"
            f"<td>{req_type}</td>"
            f"<td>{mapped}</td>"
            f"<td>{badge}</td>"
            f"<td>{basis}</td>"
            "</tr>"
        )

    return (
        "<h3>Required Coverage</h3><div class=\"table-scroll\"><table><thead><tr>"
        "<th>Required group</th><th>Type</th><th>Mapped file</th><th>Verdict</th><th>Basis</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def move_required_coverage_to_errata(html_text: str, run_root: Path) -> str:
    table = _required_coverage_table_html(run_root)
    if not table:
        return html_text

    section_match = re.search(
        r'(<section class="card content-block" id="contact-sheets">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if section_match:
        open_tag, body, close_tag = section_match.groups()
        body = REQUIRED_COVERAGE_BLOCK.sub("", body)
        pointer = (
            '<p class="muted contact-coverage-pointer">Required coverage table is in '
            '<a href="#errata-phase-5-contact-sheets">Errata</a>.</p>'
        )
        if "contact-coverage-pointer" not in body:
            body = body.rstrip() + "\n  " + pointer + "\n"
        else:
            body = re.sub(
                r'<p class="muted contact-coverage-pointer">[\s\S]*?</p>',
                pointer,
                body,
                count=1,
            )
        html_text = html_text.replace(section_match.group(0), open_tag + body + close_tag, 1)

    errata_article = (
        '<article class="errata-phase" id="errata-phase-5-contact-sheets">'
        "<h3>Phase 5 — contact sheet required coverage</h3>"
        '<p class="muted">Per-group gate mapping: requirement ID, mapped file, verdict, and basis.</p>'
        + table
        + "</article>"
    )

    if 'id="errata-phase-5-contact-sheets"' in html_text:
        return re.sub(
            r'<article class="errata-phase" id="errata-phase-5-contact-sheets">[\s\S]*?</article>',
            errata_article,
            html_text,
            count=1,
        )

    errata_match = re.search(
        r'(<section class="card content-block" id="pipeline-errata">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not errata_match:
        return html_text

    errata_open, errata_body, errata_close = errata_match.groups()
    insert_at = errata_body.find('<article class="errata-phase" id="errata-phase-3-interactions"')
    if insert_at != -1:
        end = errata_body.find("</article>", insert_at)
        if end != -1:
            insert_at = end + len("</article>")
            errata_body = errata_body[:insert_at] + "\n" + errata_article + "\n" + errata_body[insert_at:]
        else:
            errata_body = errata_body.rstrip() + "\n" + errata_article + "\n"
    else:
        errata_body = errata_body.rstrip() + "\n" + errata_article + "\n"

    return (
        html_text[: errata_match.start()]
        + errata_open
        + errata_body
        + errata_close
        + html_text[errata_match.end() :]
    )



def _requirements_for_file(file_name: str, requirements: list[dict]) -> list[dict]:
    return [req for req in requirements if str(req.get("file") or "") == file_name]


def _contact_sheet_label_for_file(file_name: str, requirements: list[dict]) -> str:
    names = [
        str(req.get("name") or req.get("id") or "")
        for req in _requirements_for_file(file_name, requirements)
    ]
    names = [name for name in names if name]
    if not names:
        stem = Path(file_name).stem.replace("_", " ")
        return stem[:48] + ("…" if len(stem) > 48 else "")
    if len(names) == 1:
        return names[0]
    return " · ".join(names)


def _merge_verdict(verdicts: list[str]) -> str:
    normalized = [str(v or "UNKNOWN").upper() for v in verdicts]
    if "FAIL" in normalized:
        return "FAIL"
    if "PARTIAL" in normalized:
        return "PARTIAL"
    return normalized[0] if normalized else "UNKNOWN"


def _dedupe_contact_sheet_requirements(requirements: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for req in requirements:
        file_name = req.get("file")
        if not file_name or str(file_name) in {"MISSING", "None"}:
            key = f"missing:{req.get('id') or req.get('name') or len(order)}"
        else:
            key = f"file:{file_name}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(req)

    merged: list[dict] = []
    for key in order:
        reqs = groups[key]
        names = [str(req.get("name") or req.get("id") or "Unknown") for req in reqs]
        types = list(dict.fromkeys(str(req.get("type") or "") for req in reqs if str(req.get("type") or "")))
        verdict = _merge_verdict([str(req.get("verdict") or "UNKNOWN") for req in reqs])
        bases = [str(req.get("basis") or "").strip() for req in reqs if str(req.get("basis") or "").strip()]
        if len(bases) > 1:
            basis = "Shared sheet across " + ", ".join(names) + ". " + " ".join(bases)
        else:
            basis = bases[0] if bases else ""
        merged.append(
            {
                "name": names[0] if len(names) == 1 else " · ".join(names),
                "type": "; ".join(types),
                "file": reqs[0].get("file"),
                "verdict": verdict,
                "basis": basis,
                "shared_groups": len(reqs),
            }
        )
    return merged


def _contact_sheet_meta_path(run_root: Path, file_name: str) -> Path:
    return run_root / "reference_sheets" / f"{Path(file_name).stem}.contact_sheet.meta.json"



EMBRY_RESEARCH_SOURCE_PATHS: tuple[str, ...] = (
    "/mnt/storage12tb/skills/persona-dream/outputs/20260611-horus-embry-casting/asset_packs/kling_reference_pack_v1/images/character_embry_01_main_front_full_body.png",
    "/mnt/storage12tb/skills/persona-dream/outputs/20260611-horus-embry-casting/asset_packs/kling_reference_pack_v1/images/character_embry_02_three_quarter_full_body.png",
    "/mnt/storage12tb/skills/persona-dream/outputs/20260611-horus-embry-casting/asset_packs/kling_reference_pack_v1/images/character_embry_03_side_or_back_view.png",
    "/mnt/storage12tb/skills/persona-dream/outputs/20260611-horus-embry-casting/asset_packs/kling_reference_pack_v1/images/character_embry_04_face_or_detail_closeup.png",
    "/mnt/storage12tb/skills/persona-dream/outputs/horus-embry-tea-void-sparta-r13-regenerated/research/bakeoff/reference_rebuild_20260610T2117Z/images/embry_character_reference_sheet.png",
)


def _existing_embry_research_paths() -> list[Path]:
    return [Path(raw) for raw in EMBRY_RESEARCH_SOURCE_PATHS if Path(raw).is_file()]


def _research_asset_rel_href(run_root: Path, source_path: Path) -> str | None:
    assets_root = run_root / "pipeline_review_8892" / "assets"
    for candidate in (source_path, source_path.resolve()):
        try:
            rel = candidate.relative_to(assets_root)
        except ValueError:
            try:
                rel = candidate.relative_to(assets_root.resolve())
            except ValueError:
                continue
        return f"assets/{rel.as_posix()}"
    return None


def _hydrate_embry_research(run_root: Path) -> None:
    """Wire authorized 12TB Embry persona references into casting + report assets."""
    source_paths = _existing_embry_research_paths()
    if not source_paths:
        return

    manifest = {
        "schema": "persona_dream.embry_research_manifest.v1",
        "entity_id": "character_embry",
        "reference_strategy": "provided_reference",
        "note": "Authorized local/persona reference images on 12TB — not Brave canon search.",
        "source_runs": [
            "20260611-horus-embry-casting/kling_reference_pack_v1",
            "horus-embry-tea-void-sparta-r13-regenerated/reference_rebuild_20260610T2117Z",
        ],
        "image_paths": [str(path.resolve()) for path in source_paths],
    }
    casting_dir = run_root / "casting"
    casting_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = casting_dir / "embry_research_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    casting_path = casting_dir / "casting_contract.json"
    if casting_path.is_file():
        casting = json.loads(casting_path.read_text(encoding="utf-8"))
        for entity in casting.get("entities") or []:
            if str(entity.get("entity_id")) != "character_embry":
                continue
            entity["reference_strategy"] = "provided_reference"
            entity["provided_references"] = [str(path.resolve()) for path in source_paths]
            entity["brave_search_queries"] = []
            break
        casting_path.write_text(json.dumps(casting, indent=2) + "\n", encoding="utf-8")

    visual_path = run_root / "story_visual_package.json"
    if visual_path.is_file():
        visual = json.loads(visual_path.read_text(encoding="utf-8"))
        embry = ((visual.get("keyed_entities") or {}).get("characters") or {}).get("embry")
        if isinstance(embry, dict):
            output_sheet = str(
                (run_root / "reference_sheets" / "embry_reference_sheet.png").resolve()
            )
            paths = [str(path.resolve()) for path in source_paths]
            if output_sheet not in paths:
                paths.append(output_sheet)
            embry["image_file_paths"] = paths
            visual_path.write_text(json.dumps(visual, indent=2) + "\n", encoding="utf-8")

    package_visual = run_root / "casting" / "package_inputs" / "visual_entities.json"
    if package_visual.is_file():
        package = json.loads(package_visual.read_text(encoding="utf-8"))
        embry = ((package.get("keyed_entities") or {}).get("characters") or {}).get("embry")
        if isinstance(embry, dict):
            output_sheet = str(
                (run_root / "reference_sheets" / "embry_reference_sheet.png").resolve()
            )
            paths = [str(path.resolve()) for path in source_paths]
            if output_sheet not in paths:
                paths.append(output_sheet)
            embry["image_file_paths"] = paths
            package_visual.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

    _ensure_embry_research_assets(run_root, source_paths)

    sync_script = Path(__file__).resolve().parent / "sync_contact_sheet_sidecars.py"
    if sync_script.is_file():
        subprocess.run(
            [
                sys.executable,
                str(sync_script),
                "--run-root",
                str(run_root),
                "--write",
                "--only",
                "embry_reference_sheet.png",
            ],
            check=False,
            capture_output=True,
            text=True,
        )



def _brave_search_module_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "brave-search",
        Path.home() / ".cursor" / "skills" / "brave-search",
        Path.home() / ".claude" / "skills" / "brave-search",
    ]
    for candidate in candidates:
        if (candidate / "brave_search.py").is_file():
            return candidate
    return candidates[0]


def _download_research_url(url: str, dest: Path, *, timeout: float = 20.0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return True
    try:
        response = httpx.get(url, follow_redirects=True, timeout=timeout)
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        if "image" not in content_type and not url.lower().split("?", 1)[0].endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".gif")
        ):
            return False
        dest.write_bytes(response.content)
        return dest.stat().st_size > 0
    except (httpx.HTTPError, OSError):
        return False


def _ensure_research_asset_symlinks(
    run_root: Path,
    source_paths: list[Path],
    asset_subdir: str,
) -> dict[str, str]:
    research_dir = run_root / "pipeline_review_8892" / "assets" / "research" / asset_subdir
    research_dir.mkdir(parents=True, exist_ok=True)
    hrefs: dict[str, str] = {}
    for source in source_paths:
        if not source.is_file():
            continue
        target = research_dir / source.name
        if not target.exists():
            try:
                target.symlink_to(source.resolve())
            except OSError:
                continue
        href = _research_asset_rel_href(run_root, target)
        if href:
            hrefs[str(source.resolve())] = href
    return hrefs


def _ensure_embry_research_assets(run_root: Path, source_paths: list[Path]) -> dict[str, str]:
    return _ensure_research_asset_symlinks(run_root, source_paths, "embry")


def _brave_image_search(query: str, *, count: int = 3) -> list[dict[str, Any]]:
    module_dir = _brave_search_module_dir()
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    try:
        from brave_search import image_search  # type: ignore
    except Exception:
        return []
    try:
        payload = image_search(query, count=count)
    except Exception:
        return []
    return list(payload.get("results") or [])


def _prepare_brave_research_thumbnails(
    run_root: Path,
    meta: dict[str, Any],
    sheet_stem: str,
) -> list[dict[str, Any]]:
    cache_dir = run_root / "pipeline_review_8892" / "assets" / "research" / "brave" / sheet_stem
    manifest_path = cache_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            cached = json.loads(manifest_path.read_text(encoding="utf-8"))
            return list(cached.get("items") or [])
        except json.JSONDecodeError:
            pass

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_item(*, thumb_url: str, title: str, summary: str, source_url: str, query: str) -> None:
        thumb_url = thumb_url.strip()
        if not thumb_url or thumb_url in seen:
            return
        seen.add(thumb_url)
        digest = hashlib.sha256(thumb_url.encode("utf-8")).hexdigest()[:12]
        ext = ".jpg"
        lowered = thumb_url.lower().split("?", 1)[0]
        for candidate in (".png", ".webp", ".jpeg", ".jpg", ".gif"):
            if lowered.endswith(candidate):
                ext = candidate if candidate != ".jpeg" else ".jpg"
                break
        dest = cache_dir / f"{digest}{ext}"
        if not _download_research_url(thumb_url, dest):
            return
        href = _research_asset_rel_href(run_root, dest)
        if not href:
            return
        items.append(
            {
                "path": str(dest),
                "href": href,
                "title": title,
                "summary": summary,
                "source_url": source_url,
                "query": query,
                "kind": "brave",
            }
        )

    for artifact in meta.get("brave_search_grounding") or []:
        query = str(artifact.get("query") or "").strip()
        for fact in artifact.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            title = str(fact.get("source_title") or "Brave source").strip()
            summary = str(fact.get("summary") or "").strip()
            source_url = str(fact.get("source_url") or "").strip()
            thumb_url = str(fact.get("thumbnail_url") or fact.get("image_url") or "").strip()
            if thumb_url:
                add_item(
                    thumb_url=thumb_url,
                    title=title,
                    summary=summary,
                    source_url=source_url,
                    query=query,
                )
        if query:
            for result in _brave_image_search(query, count=3):
                add_item(
                    thumb_url=str(result.get("thumbnail_url") or result.get("image_url") or "").strip(),
                    title=str(result.get("title") or query).strip(),
                    summary=str(result.get("source") or "Brave image search").strip(),
                    source_url=str(result.get("page_url") or result.get("url") or "").strip(),
                    query=query,
                )

    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"items": items}, indent=2) + "\n", encoding="utf-8")
    return items


def _render_research_thumbnail_tiles(
    items: list[dict[str, Any]],
    run_root: Path,
    *,
    asset_subdir: str,
    exclude_names: set[str] | None = None,
) -> list[str]:
    exclude_names = exclude_names or set()
    tiles: list[str] = []
    local_paths: list[Path] = []
    for item in items:
        path_raw = str(item.get("path") or "").strip()
        if path_raw:
            local_paths.append(Path(path_raw))
    hrefs = _ensure_research_asset_symlinks(run_root, local_paths, asset_subdir)

    for item in items:
        path_raw = str(item.get("path") or item.get("url") or "").strip()
        if not path_raw:
            continue
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        source_url = str(item.get("source_url") or "").strip()
        href = str(item.get("href") or "").strip()
        path = Path(path_raw)
        if path.name in exclude_names:
            continue
        if not href:
            href = hrefs.get(str(path.resolve())) or _research_asset_rel_href(run_root, path)
        label = html.escape(title or path.name)
        caption_bits = [f"<strong>{label}</strong>"]
        if summary:
            caption_bits.append(html.escape(summary))
        if source_url:
            caption_bits.append(
                f'<a href="{html.escape(source_url)}">{html.escape(source_url)}</a>'
            )
        elif path_raw.startswith(("http://", "https://")):
            caption_bits.append(f'<a href="{html.escape(path_raw)}">{html.escape(path_raw)}</a>')
        else:
            caption_bits.append(f'<span class="code">{html.escape(path.name)}</span>')
        caption = "<br>".join(caption_bits)
        if href and (path.is_file() or path_raw.startswith(("http://", "https://"))):
            img_src = href if not path_raw.startswith(("http://", "https://")) else path_raw
            tiles.append(
                f'<figure class="research-image-tile">'
                f'<img src="{html.escape(img_src)}" alt="{label}" loading="lazy">'
                f"<figcaption>{caption}</figcaption></figure>"
            )
        else:
            tiles.append(
                f'<figure class="research-image-tile missing"><figcaption>{caption}</figcaption></figure>'
            )
    return tiles


def _render_research_image_grid(
    items: list[dict[str, Any]],
    run_root: Path,
    *,
    heading: str,
    asset_subdir: str,
    exclude_names: set[str] | None = None,
) -> str:
    tiles = _render_research_thumbnail_tiles(
        items,
        run_root,
        asset_subdir=asset_subdir,
        exclude_names=exclude_names,
    )
    if not tiles:
        return ""
    return (
        f"<h5>{html.escape(heading)}</h5>"
        f'<div class="research-image-grid">{"".join(tiles)}</div>'
    )


def _render_contact_sheet_research(
    meta: dict[str, Any],
    *,
    run_root: Path | None = None,
    sheet_stem: str = "local",
) -> str:
    blocks: list[str] = []
    output_name = Path(str(meta.get("png_file") or meta.get("file") or "")).name
    exclude_names = {output_name} if output_name else set()
    inline = meta.get("creation_prompt_inline_references") or {}
    casting = meta.get("casting_context") or {}
    entity_id = str(casting.get("entity_id") or "")
    local_subdir = "embry" if entity_id == "character_embry" else f"local/{sheet_stem}"

    if run_root is not None and (meta.get("brave_search_grounding") or []):
        brave_items = _prepare_brave_research_thumbnails(run_root, meta, sheet_stem)
        for artifact in meta.get("brave_search_grounding") or []:
            query = str(artifact.get("query") or "").strip()
            status = str(artifact.get("status") or "").strip()
            heading = query or str(artifact.get("artifact_id") or "Brave search")
            artifact_items = [item for item in brave_items if str(item.get("query") or "") == query]
            if not artifact_items and brave_items:
                artifact_items = brave_items
            status_note = f" ({status})" if status else ""
            grid = _render_research_image_grid(
                artifact_items,
                run_root,
                heading=f"Brave search: {heading}{status_note}",
                asset_subdir=f"brave/{sheet_stem}",
                exclude_names=exclude_names,
            )
            if grid:
                blocks.append(grid)

    remote_items: list[dict[str, Any]] = []
    for entry in inline.get("remote_urls") or []:
        url = str((entry or {}).get("url") if isinstance(entry, dict) else entry).strip()
        if url:
            remote_items.append({"path": url, "title": "Reference URL", "source_url": url})
    if run_root is not None and remote_items:
        grid = _render_research_image_grid(
            remote_items,
            run_root,
            heading="Reference URLs",
            asset_subdir=f"remote/{sheet_stem}",
            exclude_names=exclude_names,
        )
        if grid:
            blocks.append(grid)

    provided = list(casting.get("provided_references") or [])
    inline_locals = list(inline.get("local_image_files") or [])
    research_items = provided + inline_locals
    if run_root is not None and research_items:
        local_heading = (
            "Pre-existing reference images (12TB / authorized local)"
            if entity_id == "character_embry"
            else "Local reference images"
        )
        grid = _render_research_image_grid(
            research_items,
            run_root,
            heading=local_heading,
            asset_subdir=local_subdir,
            exclude_names=exclude_names,
        )
        if grid:
            blocks.append(grid)

    memory_queries = [str(q).strip() for q in casting.get("memory_reference_queries") or [] if str(q).strip()]
    if memory_queries:
        blocks.append(
            "<h5>Memory queries</h5><ul>"
            + "".join(f"<li>{html.escape(q)}</li>" for q in memory_queries)
            + "</ul>"
        )

    if not blocks:
        return '<p class="contact-sheet-research-empty">No separate research artifacts recorded for this sheet.</p>'
    return '<div class="contact-sheet-research">' + "".join(blocks) + "</div>"



COPY_BUNDLE_ICON_SVG = (
    '<svg class="contact-sheet-copy-icon" viewBox="0 0 24 24" width="18" height="18" '
    'aria-hidden="true" focusable="false">'
    '<path fill="currentColor" d="M16 1H4c-1.1 0-2 .9-2 2v12h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>'
    '</svg>'
)

CLIPBOARD_BRIDGE_URLS = (
    "http://127.0.0.1:8893/clipboard/file",
    "http://127.0.0.1:8892/api/clipboard/file",
)


def _collect_contact_sheet_research_paths(
    run_root: Path,
    meta: dict[str, Any],
    *,
    sheet_stem: str,
    file_name: str,
) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    output_name = Path(file_name).name

    def add(raw: Any) -> None:
        path_raw = str((raw or {}).get("path") if isinstance(raw, dict) else raw or "").strip()
        if not path_raw:
            return
        path = Path(path_raw)
        if path.name == output_name:
            return
        if not path.is_file():
            return
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        paths.append(path.resolve())

    casting = meta.get("casting_context") or {}
    for ref in casting.get("provided_references") or []:
        add(ref)
    inline = meta.get("creation_prompt_inline_references") or {}
    for ref in inline.get("local_image_files") or []:
        add(ref)

    brave_dir = run_root / "pipeline_review_8892" / "assets" / "research" / "brave" / sheet_stem
    if brave_dir.is_dir():
        for img in sorted(brave_dir.iterdir()):
            if img.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
                add(img)

    if str(casting.get("entity_id") or "") == "character_embry":
        for embry_path in _existing_embry_research_paths():
            add(embry_path)

    return paths


def _build_contact_sheet_recreate_bundle(
    run_root: Path,
    file_name: str,
    meta: dict[str, Any],
    prompt_text: str,
) -> Path | None:
    sheet_stem = Path(file_name).stem
    bundle_dir = run_root / "pipeline_review_8892" / "assets" / "contact_sheet_bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"{sheet_stem}_recreate.zip"

    research_paths = _collect_contact_sheet_research_paths(
        run_root,
        meta,
        sheet_stem=sheet_stem,
        file_name=file_name,
    )
    brave_artifacts = [
        Path(str(item.get("artifact_path")))
        for item in (meta.get("brave_search_grounding") or [])
        if str(item.get("artifact_path") or "").strip()
    ]

    readme = (
        f"# Contact sheet recreate bundle: {sheet_stem}\n\n"
        "Contains the creation prompt, sidecar metadata, Brave grounding JSON, and research images "
        "used to regenerate this contact sheet.\n\n"
        "- `creation_prompt.md` — image-generation prompt\n"
        "- `contact_sheet.meta.json` — probed dimensions, casting context, inline refs\n"
        "- `research_images/` — local and cached Brave thumbnails\n"
        "- `brave_grounding/` — Brave search grounding artifacts when present\n"
        "- `manifest.json` — machine-readable file list\n"
    )

    manifest = {
        "schema": "persona_dream.contact_sheet_recreate_bundle.v1",
        "sheet_stem": sheet_stem,
        "png_file": file_name,
        "entity_id": (meta.get("casting_context") or {}).get("entity_id"),
        "research_image_paths": [str(path) for path in research_paths],
        "brave_artifact_paths": [str(path) for path in brave_artifacts if path.is_file()],
    }

    used_names: set[str] = set()
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("creation_prompt.md", (prompt_text or "").strip() + "\n")
        archive.writestr("README.md", readme)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")

        meta_path = _contact_sheet_meta_path(run_root, file_name)
        if meta_path.is_file():
            archive.write(meta_path, "contact_sheet.meta.json")

        for index, image_path in enumerate(research_paths):
            arcname = f"research_images/{image_path.name}"
            if arcname in used_names:
                arcname = f"research_images/{index:02d}_{image_path.name}"
            used_names.add(arcname)
            archive.write(image_path, arcname)

        for artifact_path in brave_artifacts:
            if artifact_path.is_file():
                archive.write(artifact_path, f"brave_grounding/{artifact_path.name}")

    return bundle_path.resolve() if bundle_path.is_file() else None


def _contact_sheet_copy_bundle_button(bundle_path: Path, *, sheet_stem: str) -> str:
    rel_href = ""
    if bundle_path.name.endswith(".zip"):
        if "panel_bundles" in bundle_path.as_posix():
            rel_href = f"assets/panel_bundles/{bundle_path.name}"
        else:
            rel_href = f"assets/contact_sheet_bundles/{bundle_path.name}"
    title = (
        "Copy panel recreate bundle (prompt + reference sheets) to clipboard"
        if sheet_stem.startswith("panel_")
        else "Copy recreate bundle (prompt + research images) to clipboard"
    )
    return (
        f'<button type="button" class="contact-sheet-copy-bundle" '
        f'data-bundle-path="{html.escape(str(bundle_path))}" '
        f'data-bundle-href="{html.escape(rel_href)}" '
        f'data-sheet-stem="{html.escape(sheet_stem)}" '
        f'title="{html.escape(title)}" '
        f'aria-label="Copy recreate bundle to clipboard">'
        f"{COPY_BUNDLE_ICON_SVG}"
        f"</button>"
    )


def _contact_sheet_regenerate_bundle_button(
    bundle_path: Path, *, sheet_stem: str, run_root: Path
) -> str:
    kind = "panel" if sheet_stem.startswith("panel_") else "contact-sheet"
    title = "Regenerate panel image via scillm" if kind == "panel" else "Regenerate contact sheet via scillm"
    return (
        f'<button type="button" class="contact-sheet-regenerate-bundle" '
        f'data-bundle-path="{html.escape(str(bundle_path))}" '
        f'data-sheet-stem="{html.escape(sheet_stem)}" '
        f'data-regenerate-kind="{kind}" '
        f'data-run-root="{html.escape(str(run_root.resolve()))}" '
        f'title="{html.escape(title)}" '
        f'aria-label="Regenerate from bundle">↻</button>'
    )


def _asset_recreate_buttons(
    bundle_path: Path | None, *, sheet_stem: str, run_root: Path
) -> str:
    if bundle_path is None or not bundle_path.is_file():
        return ""
    return (
        '<span class="asset-recreate-actions">'
        + _contact_sheet_copy_bundle_button(bundle_path, sheet_stem=sheet_stem)
        + _contact_sheet_regenerate_bundle_button(bundle_path, sheet_stem=sheet_stem, run_root=run_root)
        + "</span>"
    )


def _contact_sheet_entry_html(
    run_root: Path,
    file_name: str,
    merged: dict[str, Any],
    requirements: list[dict],
) -> str:
    assets_dir = run_root / "pipeline_review_8892" / "assets"
    ref_dir = run_root / "reference_sheets"
    label = _contact_sheet_label_for_file(file_name, requirements)
    req_type = html.escape(str(merged.get("type") or ""))
    verdict = str(merged.get("verdict") or "UNKNOWN").upper()
    if verdict == "FAIL":
        badge_class = "badge-fail"
    elif verdict == "PARTIAL":
        badge_class = "badge-warn"
    else:
        badge_class = "badge-pass"

    meta = load_json(_contact_sheet_meta_path(run_root, file_name))
    prompt_text = str(meta.get("creation_prompt") or "").strip()
    if not prompt_text:
        prompt_link = meta.get("prompt_link_path") or meta.get("prompt_path")
        if prompt_link and Path(str(prompt_link)).exists():
            prompt_text = Path(str(prompt_link)).read_text().strip()

    probed = str(meta.get("probed_size_label") or "").strip()
    gen = meta.get("generation_attempt") or {}
    gen_bits = [
        bit
        for bit in (
            str(gen.get("backend") or "").strip(),
            str(gen.get("model") or "").strip(),
            probed,
        )
        if bit
    ]
    gen_line = " · ".join(gen_bits)

    asset_path = assets_dir / file_name
    ref_path = ref_dir / file_name
    if asset_path.exists() or ref_path.exists():
        image_html = (
            f'<img src="assets/{html.escape(file_name)}" '
            f'alt="{html.escape(label)} contact sheet" loading="lazy">'
        )
    else:
        image_html = f'<div class="contact-sheet-missing">Missing file: {html.escape(file_name)}</div>'

    sheet_stem = Path(file_name).stem
    bundle_path = build_contact_sheet_bundle(run_root, file_name, meta, prompt_text)
    copy_button = _asset_recreate_buttons(bundle_path, sheet_stem=sheet_stem, run_root=run_root)
    prompt_html = (
        '<details class="contact-sheet-provenance contact-sheet-prompt-panel">'
        '<summary class="contact-sheet-prompt-summary">'
        '<span class="contact-sheet-summary-label">Creation prompt</span>'
        f"{copy_button}"
        "</summary>"
        f'<div class="contact-sheet-prompt"><pre>{html.escape(prompt_text) if prompt_text else "(prompt not recorded)"}</pre></div>'
        "</details>"
    )
    research_html = (
        '<details class="contact-sheet-provenance">'
        "<summary>Research grounding</summary>"
        + _render_contact_sheet_research(meta, run_root=run_root, sheet_stem=Path(file_name).stem)
        + "</details>"
    )

    meta_bits = [html.escape(file_name)]
    if req_type:
        meta_bits.append(req_type)
    if gen_line:
        meta_bits.append(html.escape(gen_line))

    entry_id = re.sub(r"[^a-z0-9_-]+", "-", Path(file_name).stem.lower()).strip("-")
    return (
        f'<article class="contact-sheet-entry" id="contact-sheet-{entry_id}">'
        '<div class="contact-sheet-entry-header">'
        f"<h4>{html.escape(label)}</h4>"
        f'<span class="badge {badge_class}">{html.escape(verdict)}</span>'
        f'<span class="contact-sheet-entry-meta">{" · ".join(meta_bits)}</span>'
        "</div>"
        f'<div class="contact-sheet-full-image">{image_html}</div>'
        + prompt_html
        + research_html
        + "</article>"
    )


def _contact_sheet_blocks_html(run_root: Path, requirements: list[dict]) -> str:
    ref_dir = run_root / "reference_sheets"
    merged_by_file = {
        str(item.get("file") or ""): item for item in _dedupe_contact_sheet_requirements(requirements)
    }
    entries: list[str] = []
    for png in sorted(ref_dir.glob("*.png")):
        file_name = png.name
        merged = merged_by_file.get(file_name, {"verdict": "UNKNOWN", "type": ""})
        entries.append(_contact_sheet_entry_html(run_root, file_name, merged, requirements))
    if not entries:
        return ""
    return (
        "<h3>Contact Sheets</h3>"
        '<p class="muted">Full-size installed sheets with the creation prompt and recorded research grounding.</p>'
        '<div class="contact-sheet-list">'
        + "".join(entries)
        + "</div>"
    )

def inject_contact_sheet_gallery(html_text: str, run_root: Path) -> str:
    if 'id="contact-sheets"' not in html_text:
        return html_text

    section_match = re.search(
        r'(<section class="card content-block" id="contact-sheets">)(.*?)(</section>)',
        html_text,
        flags=re.DOTALL,
    )
    if not section_match:
        return html_text

    open_tag, body, close_tag = section_match.groups()

    body = re.sub(
        r'<div class="contact-sheet-thumb-strip"[\s\S]*?</div>\s*',
        "",
        body,
        count=1,
    )
    body = re.sub(
        r"<h3>Contact Sheets</h3>[\s\S]*?<div class=\"contact-sheet-list\">[\s\S]*?</div>\s*",
        "",
        body,
        count=1,
    )
    body = re.sub(
        r"<h3>Contact sheet previews</h3>[\s\S]*?<div class=\"contact-sheet-gallery\">[\s\S]*?</div>\s*",
        "",
        body,
        count=1,
    )

    h2_match = re.search(r"<h2[^>]*>.*?</h2>", body, re.DOTALL)
    gate_match = re.search(r"<details class=\"gate-definition[\s\S]*?</details>", body, re.DOTALL)
    dl_match = re.search(r"<dl class=\"panel-metadata\"[\s\S]*?</dl>", body, re.DOTALL)

    gate = load_json(run_root / "pipeline_review_8892" / "artifacts" / "phase_05_contact_sheets_anti_hallucination_gate.json")
    requirements = gate.get("requirements") or []
    if not requirements:
        return html_text

    contact_sheets = _contact_sheet_blocks_html(run_root, requirements)

    preserved: list[str] = []
    if h2_match:
        preserved.append(h2_match.group(0))
    if contact_sheets:
        preserved.append(contact_sheets)
    if gate_match:
        preserved.append(gate_match.group(0))
    if dl_match:
        preserved.append(dl_match.group(0))

    pointer = (
        '<p class="muted contact-coverage-pointer">Required coverage table is in '
        '<a href="#errata-phase-5-contact-sheets">Errata</a>.</p>'
    )

    claim_pointer = ""
    claim_match = re.search(r'<p class="muted claim-audit-pointer">[\s\S]*?</p>', body)
    if claim_match:
        claim_pointer = "\n  " + claim_match.group(0)

    new_body = "\n".join(preserved) + "\n  " + pointer + claim_pointer + "\n"
    return html_text.replace(section_match.group(0), open_tag + new_body + close_tag, 1)



def humanize_creative_leadership_headings(html_text: str) -> str:
    replacements = {
        "<h3>Producer-Selected Scriptwriter</h3>": "<h3>Scriptwriter</h3>",
        "<h3>Producer-Selected Director / DoP</h3>": "<h3>Director</h3>",
    }
    for old, new in replacements.items():
        html_text = html_text.replace(old, new)
    return html_text




TOP_LEVEL_SECTION_IDS = (
    "idea-story",
    "memories-used",
    "story-package",
    "creative-leadership",
    "producer-phase",
    "contact-sheets",
    "script-phase",
    "panels-phase",
    "scene-directions",
    "export-kling",
    "final-kling-api",
    "production-payload",
    "panel-interaction-gate",
    "pipeline-errata",
)


def _section_marker_positions(html_text: str, section_ids: tuple[str, ...]) -> list[tuple[int, str]]:
    positions: list[tuple[int, str]] = []
    for sid in section_ids:
        match = re.search(rf'<section[^>]*\bid="{re.escape(sid)}"', html_text)
        if match:
            positions.append((match.start(), sid))
    positions.sort(key=lambda item: item[0])
    return positions


def _extract_section_inner(html_text: str, section_id: str, *, until_ids: tuple[str, ...] = TOP_LEVEL_SECTION_IDS) -> str:
    match = re.search(
        rf'<section[^>]*\bid="{re.escape(section_id)}"(?:\s|>)[^>]*>(.*)',
        html_text,
        flags=re.DOTALL,
    )
    if not match:
        return ""
    body = match.group(1)
    end_positions = [len(body)]
    for sid in until_ids:
        if sid == section_id:
            continue
        nested = re.search(
            rf'</section>\s*<section[^>]*\bid="{re.escape(sid)}"(?:\s|>)',
            body,
        )
        if nested:
            end_positions.append(nested.start())
    return body[: min(end_positions)]


def _strip_all_h2(body: str) -> str:
    body = re.sub(r"<h2[^>]*>.*?</h2>\s*", "", body, flags=re.DOTALL)
    body = re.sub(r"(?m)^[^<\n]+</h2>\s*$\n?", "", body)
    return body.strip()


def _panel_ledger_by_number(run_root: Path) -> dict[int, dict[str, Any]]:
    payload = load_json(run_root / "storyboard/panel_continuity_and_repair_ledger.json")
    panels = payload.get("panels")
    if isinstance(payload, list):
        panels = payload
    elif not panels:
        panels = [value for value in payload.values() if isinstance(value, dict) and value.get("panel") is not None]
    out: dict[int, dict[str, Any]] = {}
    for item in panels or []:
        if isinstance(item, dict) and item.get("panel") is not None:
            out[int(item["panel"])] = item
    return out


def _kling_panels_by_number(run_root: Path) -> dict[int, dict[str, Any]]:
    payload = load_json(run_root / "storyboard/kling_scene_payloads.json")
    out: dict[int, dict[str, Any]] = {}
    for item in payload.get("panels") or []:
        if item.get("panel") is not None:
            out[int(item["panel"])] = item
    return out


def _panel_thumbnail_html(run_root: Path, panel_no: int) -> str:
    review_assets = run_root / "pipeline_review_8892/assets/panels"
    file_name = f"panel_{panel_no:02d}_storyboard.png"
    if (review_assets / file_name).exists():
        return (
            f'<a class="panel-thumb-link" href="assets/panels/{file_name}">'
            f'<img class="panel-storyboard-thumb" src="assets/panels/{file_name}" '
            f'alt="Panel {panel_no:02d} thumbnail" loading="lazy"></a>'
        )
    return '<span class="panel-thumb-missing" aria-hidden="true">—</span>'


def _panel_gate_badge(ledger: dict[str, Any] | None) -> str:
    if not ledger:
        return '<span class="panel-gate-badge gate-unknown" title="Unknown"><i data-lucide="help-circle"></i></span>'
    status = str(
        ledger.get("visual_review_status")
        or ledger.get("deterministic_interaction_gate_status")
        or "UNKNOWN"
    )
    upper = status.upper()
    if "PASS" in upper and "FAIL" not in upper:
        return '<span class="panel-gate-badge gate-pass" title="Pass"><i data-lucide="check-circle"></i></span>'
    return '<span class="panel-gate-badge gate-fail" title="Blocked"><i data-lucide="x-circle"></i></span>'


def _panel_audio_cell(panel_no: int, kling_panel: dict[str, Any] | None) -> str:
    dialogue = (kling_panel or {}).get("dialogue") or []
    if dialogue:
        return (
            f'<button class="panel-audio-play" type="button" data-panel="{panel_no:02d}" '
            f'title="Dialogue preview" aria-label="Play dialogue for panel {panel_no:02d}">'
            '<i data-lucide="play-circle"></i></button>'
        )
    return '<span class="panel-audio-muted" aria-label="Silent panel"><i data-lucide="volume-x"></i></span>'


def _panel_script_cell(kling_panel: dict[str, Any] | None) -> str:
    if not kling_panel:
        return "—"
    parts: list[str] = []
    for line in kling_panel.get("dialogue") or []:
        speaker = html.escape(str(line.get("speaker") or ""))
        text_value = html.escape(str(line.get("text") or ""))
        if speaker and text_value:
            parts.append(f"<strong>{speaker}</strong> {text_value}")
    return "<br>".join(parts) if parts else "—"


def _panel_motion_cues_from_ledger(ledger: dict[str, Any] | None) -> str:
    if not ledger:
        return ""
    cues = ledger.get("required_dynamic_behaviors") or []
    if not cues:
        return ""
    return "".join(
        f'<span class="motion-cue-badge">{html.escape(str(cue))}</span>' for cue in cues[:4]
    )


def _render_panel_breakdown_from_timed_beats(run_root: Path) -> str:
    payload = load_json(run_root / "timed_beats.json")
    beats = payload.get("beats") or []
    if not beats:
        return ""
    ledgers = _panel_ledger_by_number(run_root)
    kling = _kling_panels_by_number(run_root)
    rows: list[str] = []
    for index, beat in enumerate(beats, start=1):
        start_s = beat.get("start_s", 0)
        end_s = beat.get("end_s", 0)
        timing = f"{start_s:.1f}s – {end_s:.1f}s"
        visual = str(beat.get("visual") or "").strip()
        caption = str(beat.get("caption") or "").strip()
        ledger = ledgers.get(index)
        kling_panel = kling.get(index)
        action = (
            '<div class="panel-action-beat">'
            f'<div class="panel-identity-label">Panel {index:02d}</div>'
            f'<span class="pill timing-pill">{html.escape(timing)}</span>'
            f'<div class="panel-shot-label"><em>{html.escape(visual)}</em></div>'
            f'<p class="panel-beat-text">{html.escape(caption)}</p>'
            f"{_panel_motion_cues_from_ledger(ledger)}"
            "</div>"
        )
        rows.append(
            "<tr>"
            f'<td class="panel-thumb-cell">{_panel_thumbnail_html(run_root, index)}</td>'
            f'<td class="panel-action-cell">{action}</td>'
            f'<td class="panel-audio-cell">{_panel_audio_cell(index, kling_panel)}</td>'
            f'<td class="panel-script-cell">{_panel_script_cell(kling_panel)}</td>'
            f'<td class="panel-gates-cell">{_panel_gate_badge(ledger)}</td>'
            "</tr>"
        )
    return (
        "<h3>Panel breakdown</h3>"
        '<p class="muted">Professional storyboard summary. Machine ledgers and repair contracts are in '
        '<a href="#pipeline-errata">Errata</a>.</p>'
        '<div class="table-scroll"><table class="panel-storyboard-table"><thead><tr>'
        "<th>Thumbnail</th><th>Action &amp; Beat</th><th>Audio</th><th>Script</th><th>Cues &amp; Gates</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _extract_h3_block(body: str, heading: str) -> tuple[str, str]:
    pattern = rf'<h3>{re.escape(heading)}</h3>'
    match = re.search(pattern, body)
    if not match:
        return "", body
    start = match.start()
    rest = body[match.end() :]
    next_h3 = re.search(r"<h3>", rest)
    block = body[start : match.end() + (next_h3.start() if next_h3 else len(rest))]
    remainder = body[:start] + rest[next_h3.start() if next_h3 else len(rest) :]
    return block.strip(), remainder.strip()


def _extract_h2_block(body: str, heading: str) -> tuple[str, str]:
    pattern = rf"<h2[^>]*>{re.escape(heading)}</h2>"
    match = re.search(pattern, body)
    if not match:
        return "", body
    start = match.start()
    rest = body[match.end() :]
    next_h2 = re.search(r"<h2[^>]*>", rest)
    block = body[start : match.end() + (next_h2.start() if next_h2 else len(rest))]
    remainder = body[:start] + rest[next_h2.start() if next_h2 else len(rest) :]
    return block.strip(), remainder.strip()


def _rename_h2(block: str, title: str) -> str:
    if re.search(r"<h2[^>]*>", block):
        return re.sub(r"<h2[^>]*>.*?</h2>", f"<h2>{html.escape(title)}</h2>", block, count=1, flags=re.DOTALL)
    return f"<h2>{html.escape(title)}</h2>\n" + block


def _render_script_dna_block(run_root: Path) -> str:
    payload = load_json(run_root / "storyboard" / "script_dna_selection.json")
    dna = payload.get("script_dna") or {}
    if not dna:
        return ""

    rows = [
        ("Primary mode", dna.get("primary_mode")),
        ("Scene engine", dna.get("scene_engine")),
        ("Dialogue style", dna.get("dialogue_style")),
        ("Conflict pattern", dna.get("conflict_pattern")),
        ("Structure", dna.get("structure")),
        ("Theme", dna.get("theme")),
        ("Rationale", dna.get("rationale")),
    ]
    table_rows = "".join(
        f"<tr><th>{html.escape(str(label))}</th><td>{html.escape(str(value or ''))}</td></tr>"
        for label, value in rows
        if value
    )
    influences = dna.get("influences_as_techniques") or []
    beat_rules = dna.get("beat_rules") or []
    do_not = dna.get("do_not_use") or []
    lineage = dna.get("named_script_technique_lineage") or []

    parts = [
        "<h3>Script DNA</h3>",
        '<p class="muted">Narrative technique selection for dialogue craft — recorded before panel timing and provider text.</p>',
        '<div class="table-scroll"><table class="script-dna-table"><tbody>',
        table_rows,
        "</tbody></table></div>",
    ]
    if influences:
        parts.append("<h4>Techniques (not voice copy)</h4><ul>")
        parts.extend(f"<li>{html.escape(str(item))}</li>" for item in influences)
        parts.append("</ul>")
    if lineage:
        parts.append("<h4>Craft lineage labels</h4><ul>")
        for item in lineage:
            if not isinstance(item, dict):
                continue
            parts.append(
                "<li>"
                f"<strong>{html.escape(str(item.get('name') or ''))}</strong> — "
                f"{html.escape(str(item.get('used_as') or ''))}: "
                f"{html.escape(str(item.get('applied_trait') or ''))}"
                "</li>"
            )
        parts.append("</ul>")
    if beat_rules:
        parts.append("<h4>Beat rules</h4><ul>")
        parts.extend(f"<li>{html.escape(str(item))}</li>" for item in beat_rules)
        parts.append("</ul>")
    if do_not:
        parts.append("<h4>Do not use</h4><ul>")
        parts.extend(f"<li>{html.escape(str(item))}</li>" for item in do_not)
        parts.append("</ul>")
    parts.append(
        '<p class="muted script-artifact">Artifact: '
        '<a href="../storyboard/script_dna_selection.json">script_dna_selection.json</a></p>'
    )
    return "\n".join(parts)


def _extract_panel_dialogue_block(html_text: str) -> str:
  panels: list[str] = []
  for panel_no in ("06", "07"):
      match = re.search(
          rf'<article class="panel-card[^"]*" id="panel-{panel_no}"[\s\S]*?<dt>Dialogue</dt>\s*<dd>(.*?)</dd>',
          html_text,
          flags=re.DOTALL,
      )
      if match:
          panels.append(
              f'<div class="script-dialogue-line"><strong>Panel {panel_no}</strong><p>{match.group(1).strip()}</p></div>'
          )
  if not panels:
      return ""
  return (
      "<h3>Dialogue</h3>"
      '<p class="muted">Spoken lines locked in script before panel provider text and Kling voice tags.</p>'
      + "".join(panels)
  )


PANEL_BREAKDOWN_BLOCK = re.compile(
    r"<h3>Panel breakdown</h3>[\s\S]*?</table></div>",
    re.IGNORECASE,
)


def dedupe_panel_breakdown_blocks(html_text: str) -> str:
    matches = list(PANEL_BREAKDOWN_BLOCK.finditer(html_text))
    if len(matches) <= 1:
        return html_text
    for match in reversed(matches[1:]):
        html_text = html_text[: match.start()] + html_text[match.end() :]
    return html_text


def _extract_panel_breakdown_block(story_body: str) -> tuple[str, str]:
    markers = (
        '<div class="scene-constraints-card">',
        "<h3>Panel breakdown</h3>",
        "<h3>Panel Story Package Summary</h3>",
    )
    start = -1
    for marker in markers:
        pos = story_body.find(marker)
        if pos != -1 and (start == -1 or pos < start):
            start = pos
    if start == -1:
        return "", story_body
    panel_block = story_body[start:].strip()
    story_only = story_body[:start].strip()
    panel_block = re.sub(
        r"<h3>Panel Story Package Summary</h3>",
        "<h3>Panel breakdown</h3>",
        panel_block,
        count=1,
    )
    return panel_block, story_only


def _wrap_pipeline_section(
    section_id: str,
    title: str,
    body: str,
    *,
    status: str = "",
    statuses: dict[str, str] | None = None,
    extra_class: str = "content-block",
) -> str:
    clean = _strip_all_h2(body.strip())
    if not clean:
        return ""
    badge = _section_badge_html(status) if status else ""
    provisional = ""
    if statuses and _section_is_provisional(section_id, statuses):
        provisional = ' data-provisional="true"'
        extra_class = f"{extra_class} section-provisional"
    clean = (
        f'<h2><span class="section-title-text">{html.escape(title)}</span>{badge}</h2>\n' + clean
    )
    if statuses and _section_is_provisional(section_id, statuses):
        clean = (
            '<p class="status-note section-provisional-note">'
            "<strong>Provisional:</strong> an upstream gate is blocked. Treat this section as review-only until the blocker clears."
            "</p>\n" + clean
        )
    return f'<section class="card {extra_class}" id="{section_id}"{provisional}>\n{clean}\n</section>'


def restructure_pipeline_sections(html_text: str, run_root: Path) -> str:
    positions = _section_marker_positions(html_text, TOP_LEVEL_SECTION_IDS)
    if not positions:
        return html_text

    first_main = positions[0][0]
    errata_match = re.search(
        r'<section class="card content-block" id="pipeline-errata">',
        html_text,
    )
    if not errata_match:
        return html_text
    errata_start = errata_match.start()

    idea = _extract_section_inner(html_text, "idea-story")
    memories = _extract_section_inner(html_text, "memories-used")
    story_raw = _extract_section_inner(html_text, "story-package")
    creative = _extract_section_inner(html_text, "creative-leadership")
    producer_existing = _strip_all_h2(_extract_section_inner(html_text, "producer-phase"))
    script_existing = _strip_all_h2(_extract_section_inner(html_text, "script-phase"))
    contact = _extract_section_inner(html_text, "contact-sheets")
    kling_api = (
        _extract_section_inner(html_text, "export-kling")
        or _extract_section_inner(html_text, "final-kling-api")
    )
    production = _extract_section_inner(html_text, "production-payload")
    panel_gate = _extract_section_inner(html_text, "panel-interaction-gate")

    panel_breakdown, story_body = _extract_panel_breakdown_block(story_raw)
    rendered_panel_breakdown = _render_panel_breakdown_from_timed_beats(run_root)
    if rendered_panel_breakdown:
        panel_breakdown = rendered_panel_breakdown
    elif not panel_breakdown:
        panels_existing = _extract_section_inner(html_text, "panels-phase")
        panel_breakdown, _ = _extract_panel_breakdown_block(panels_existing)
    if not panel_breakdown:
        panel_breakdown_match = re.search(
            r"(?:<div class=\"scene-constraints-card\">[\s\S]*?)?<h3>Panel breakdown</h3>[\s\S]*?</table></div>",
            html_text,
        )
        if panel_breakdown_match:
            panel_breakdown = panel_breakdown_match.group(0).strip()

    if producer_existing and not creative:
        core = producer_existing
        gate = re.search(r'<details class="gate-definition"[\s\S]*?</details>', core)
        if gate:
            core = core.replace(gate.group(0), "", 1).strip()
        meta = re.search(r'<dl class="panel-metadata"[\s\S]*?</dl>', core)
        if meta:
            core = core.replace(meta.group(0), "", 1).strip()
        core = re.sub(r'<p class="muted claim-audit-pointer">[\s\S]*?</p>\s*', "", core)
        producer_block, core = _extract_h3_block(core, "Producer Selection")
        director_block, core = _extract_h3_block(core, "Director")
        look_lock_block, core = _extract_h3_block(core, "Look Lock")
        core = re.sub(r'<dl class="panel-metadata"[\s\S]*?</dl>\s*', "", core)
        core = re.sub(r'<p class="muted claim-audit-pointer">[\s\S]*?</p>\s*', "", core)
        producer_body = "\n".join(
            part
            for part in [
                gate.group(0) if gate else "",
                meta.group(0) if meta else "",
                producer_block,
                director_block,
                look_lock_block,
                '<p class="muted claim-audit-pointer"><a href="#errata-claim-audit-creative-leadership">Claim audit</a> is in <a href="#pipeline-errata">Errata</a>.</p>',
            ]
            if part
        )
        scriptwriter_block = ""
        script_body = script_existing
    else:
        creative_core = _strip_all_h2(creative)
        creative_gate = re.search(r'<details class="gate-definition"[\s\S]*?</details>', creative_core)
        if creative_gate:
            creative_core = creative_core.replace(creative_gate.group(0), "", 1).strip()
        creative_meta = re.search(r'<dl class="panel-metadata"[\s\S]*?</dl>', creative_core)
        if creative_meta:
            creative_core = creative_core.replace(creative_meta.group(0), "", 1).strip()
        creative_claim = re.search(r'<p class="muted claim-audit-pointer">[\s\S]*?</p>', creative_core)

        producer_block, creative_core = _extract_h3_block(creative_core, "Producer Selection")
        scriptwriter_block, creative_core = _extract_h3_block(creative_core, "Scriptwriter")
        director_block, creative_core = _extract_h3_block(creative_core, "Director")
        look_lock_block, creative_core = _extract_h3_block(creative_core, "Look Lock")

        producer_body = "\n".join(
            part
            for part in [
                creative_gate.group(0) if creative_gate else "",
                creative_meta.group(0) if creative_meta else "",
                producer_block,
                director_block,
                look_lock_block,
                creative_claim.group(0) if creative_claim else "",
            ]
            if part
        )
        script_body = ""

    if not script_body:
        script_dna_from_bundle, kling_bundle_rest = _extract_h3_block(kling_api, "Script DNA / Narrative Technique Selection")
        script_dna_block = _render_script_dna_block(run_root) or script_dna_from_bundle
        dialogue_block = _extract_panel_dialogue_block(html_text)
        script_body = "\n".join(
            part
            for part in [
                scriptwriter_block,
                script_dna_block,
                dialogue_block,
                '<p class="muted claim-audit-pointer"><a href="#errata-claim-audit-creative-leadership">Producer/script claim audit</a> is in <a href="#pipeline-errata">Errata</a>.</p>',
            ]
            if part
        )
    else:
        kling_bundle_rest = kling_api
        if "<h3>Dialogue</h3>" not in script_body:
            dialogue_block = _extract_panel_dialogue_block(html_text)
            if dialogue_block:
                script_body = script_body.rstrip() + "\n" + dialogue_block
        if "errata-claim-audit-creative-leadership" not in script_body:
            script_body = script_body.rstrip() + (
                '\n<p class="muted claim-audit-pointer"><a href="#errata-claim-audit-creative-leadership">'
                'Producer/script claim audit</a> is in <a href="#pipeline-errata">Errata</a>.</p>'
            )

    panels_existing = _strip_all_h2(_extract_section_inner(html_text, "panels-phase"))
    scene_intro_match = re.search(
        r'<section class="card scene-intro" id="scene-directions">(.*?)</section>\s*',
        html_text,
        flags=re.DOTALL,
    )
    if panels_existing:
        scene_intro = panels_existing
        scene_intro, _ = _extract_panel_breakdown_block(scene_intro)
        scene_intro = re.sub(
            r'<p class="muted">Panels are the timed visual breakdown[\s\S]*?</p>\s*',
            "",
            scene_intro,
            count=1,
        )
        scene_intro = re.sub(
            r'<p class="muted interaction-tables-pointer">[\s\S]*?</p>\s*',
            "",
            scene_intro,
        )
        scene_grid_match = re.search(
            r'<div class="scene-grid">[\s\S]*?</div>\s*(?=<p class="muted interaction-tables-pointer">)',
            panels_existing,
        )
        if not scene_grid_match:
            scene_grid_match = re.search(
                r'<section class="scene-grid">[\s\S]*?</section>\s*(?=<p class="muted interaction-tables-pointer">)',
                panels_existing,
            )
    else:
        scene_intro = scene_intro_match.group(1).strip() if scene_intro_match else ""
        scene_intro = _strip_all_h2(scene_intro)
        scene_grid_match = re.search(r'<section class="scene-grid">[\s\S]*?</section>', html_text)

    scene_grid = scene_grid_match.group(0) if scene_grid_match else ""
    if scene_intro and scene_grid:
        scene_intro = scene_intro.replace(scene_grid, "").strip()

    scene_tail_start = scene_grid_match.end() if scene_grid_match else (scene_intro_match.end() if scene_intro_match else 0)
    kling_start = html_text.find('id="export-kling"')
    if kling_start == -1:
        kling_start = html_text.find('id="final-kling-api"')
    scene_tail = html_text[scene_tail_start:kling_start] if kling_start != -1 else ""
    voice_block, scene_tail = _extract_h2_block(scene_tail, "Voice And Image Manifest")
    live_gate_block, scene_tail = _extract_h2_block(scene_tail, "Live Kling Gate")

    panels_body = "\n".join(
        part
        for part in [
            '<p class="muted">Panels are the timed visual breakdown of the locked script — not a substitute for screenplay.</p>',
            panel_breakdown,
            scene_intro,
            scene_grid.replace("<section class=\"scene-grid\">", '<div class="scene-grid">', 1).replace("</section>", "</div>", 1) if scene_grid else "",
            '<p class="muted interaction-tables-pointer">Per-panel interaction ledgers and repair contracts are in <a href="#pipeline-errata">Errata</a>.</p>',
        ]
        if part
    )

    dry_run_block, kling_api_rest = _extract_h2_block(kling_api, "Final Kling Omni Dry-Run Bundle For Repair Review")
    export_body = "\n".join(
        part
        for part in [
            voice_block,
            live_gate_block,
            kling_api_rest.strip(),
            dry_run_block,
            kling_bundle_rest.strip(),
            production.strip(),
            '<p class="muted">Packet remains blocked until interaction ledgers pass, provider media URLs exist, and Kling voice IDs exist.</p>',
        ]
        if part
    )

    story_gate = re.search(r'<details class="gate-definition"[\s\S]*?</details>', story_body)
    story_without_gate = re.sub(r'<details class="gate-definition"[\s\S]*?</details>\s*', "", story_body, count=1)
    story_section_body = _strip_all_h2(story_without_gate)
    if story_gate:
        story_section_body = story_gate.group(0) + "\n" + story_section_body

    phase_statuses = pipeline_phase_statuses(run_root)
    rebuilt = "\n".join(
        part
        for part in [
            _wrap_pipeline_section("idea-story", "Idea", idea, status=phase_statuses["idea-story"], statuses=phase_statuses, extra_class="content-block pipeline-phase"),
            _wrap_pipeline_section("memories-used", "Memories", memories, status=phase_statuses["memories-used"], statuses=phase_statuses, extra_class="content-block pipeline-phase"),
            _wrap_pipeline_section("story-package", "Story", story_section_body, status=phase_statuses["story-package"], statuses=phase_statuses),
            _wrap_pipeline_section("producer-phase", "Producer", producer_body, status=phase_statuses["producer-phase"], statuses=phase_statuses),
            _wrap_pipeline_section("contact-sheets", "Contact sheets", contact, status=phase_statuses["contact-sheets"], statuses=phase_statuses),
            _wrap_pipeline_section("script-phase", "Script", script_body, status=phase_statuses["script-phase"], statuses=phase_statuses),
            _wrap_pipeline_section("panels-phase", "Panels", panels_body, status=phase_statuses["panels-phase"], statuses=phase_statuses, extra_class="scene-intro"),
            _wrap_pipeline_section("export-kling", "Export to Kling", export_body, status=phase_statuses["export-kling"], statuses=phase_statuses),
        ]
        if part
    )

    html_text = html_text[:first_main] + rebuilt + "\n" + html_text[errata_start:]

    if panel_gate.strip():
        errata_article = (
            '<article class="errata-phase" id="errata-panel-interaction-gate">'
            "<h3>Panel repair contract</h3>"
            + panel_gate
            + "</article>"
        )
        if 'id="errata-panel-interaction-gate"' not in html_text:
            html_text = re.sub(
                r'(<section class="card content-block" id="pipeline-errata">.*?<h2[^>]*>Errata[^<]*</h2>)',
                r"\1\n" + errata_article,
                html_text,
                count=1,
                flags=re.DOTALL,
            )

    html_text = re.sub(
        r'<section class="card content-block" id="panel-interaction-gate">[\s\S]*?</section>\s*',
        "",
        html_text,
        count=1,
    )
    html_text = re.sub(
        r'<section class="card content-block" id="(final-kling-api|production-payload)">[\s\S]*?</section>\s*',
        "",
        html_text,
    )
    html_text = re.sub(
        r'<section class="card content-block" id="creative-leadership">[\s\S]*?</section>\s*',
        "",
        html_text,
        count=1,
    )
    html_text = re.sub(
        r'<section class="card scene-intro" id="scene-directions">[\s\S]*?</section>\s*',
        "",
        html_text,
        count=1,
    )
    while True:
        extra_errata = list(
            re.finditer(r'<section class="card content-block" id="pipeline-errata">', html_text)
        )
        if len(extra_errata) <= 1:
            break
        second = extra_errata[1].start()
        third = extra_errata[2].start() if len(extra_errata) > 2 else len(html_text)
        html_text = html_text[:second] + html_text[third:]
    return html_text




def inject_panel_regenerate_buttons(html_text: str, run_root: Path) -> str:
    bundle_dir = run_root / "pipeline_review_8892" / "assets" / "panel_bundles"

    def panel_actions(panel_num: int) -> str:
        bundle = bundle_dir / f"panel_{panel_num:02d}_recreate.zip"
        if not bundle.is_file():
            built = build_panel_bundle(run_root, panel_num)
            bundle = built if built is not None else bundle
        if not bundle.is_file():
            return ""
        return _asset_recreate_buttons(bundle, sheet_stem=f"panel_{panel_num:02d}", run_root=run_root)

    def repl_plain(match: re.Match[str]) -> str:
        panel_num = int(match.group(1))
        actions = panel_actions(panel_num)
        return (
            f'<div class="panel-header"><span>Panel {panel_num}</span>'
            f"<strong>{match.group(2)}</strong>{actions}</div>"
        )

    html_text = re.sub(
        r'<div class="panel-header"><span>Panel (\d+)</span><strong>([^<]+)</strong></div>',
        repl_plain,
        html_text,
    )

    def repl_upgrade(match: re.Match[str]) -> str:
        header = match.group(0)
        if "contact-sheet-regenerate-bundle" in header:
            return header
        panel_num = int(match.group(1))
        timing = match.group(2)
        actions = panel_actions(panel_num)
        if not actions:
            return header
        return (
            f'<div class="panel-header"><span>Panel {panel_num}</span>'
            f"<strong>{timing}</strong>{actions}</div>"
        )

    return re.sub(
        r'<div class="panel-header"><span>Panel (\d+)</span><strong>([^<]+)</strong>(?:<button[^>]*contact-sheet-copy-bundle[\s\S]*?</button>)+</div>',
        repl_upgrade,
        html_text,
    )

def patch_index_html(index_path: Path, run_root: Path) -> None:
    html_text = index_path.read_text()
    assets_dir = index_path.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "pipeline-ui.css").write_text(CSS.strip() + "\n")
    (assets_dir / "pipeline-ui.js").write_text(JS.strip() + "\n")

    html_text = re.sub(r'href="assets/pipeline-ui\.css(?:\?v=\d+)?"', 'href="assets/pipeline-ui.css?v=29"', html_text, count=1)
    html_text = re.sub(r'src="assets/pipeline-ui\.js(?:\?v=\d+)?"', 'src="assets/pipeline-ui.js?v=29"', html_text, count=1)
    if "pipeline-ui.css" not in html_text:
        html_text = html_text.replace(
            '</style><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js',
            '</style><link rel="stylesheet" href="assets/pipeline-ui.css?v=29"><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js',
        )
    if "pipeline-ui.js" not in html_text:
        # If the highlight.js script tag is missing, inject just before </body> or </main> or at the end.
        js_tag = '<script src="assets/pipeline-ui.js?v=29"></script>'
        if "</body>" in html_text:
            html_text = html_text.replace("</body>", f"{js_tag}\n</body>", 1)
        elif "</main>" in html_text:
            html_text = html_text.replace("</main>", f"{js_tag}\n</main>", 1)
        else:
            html_text = html_text.rstrip() + f"\n{js_tag}\n"

    html_text = repair_nested_errata_duplicate(html_text)
    html_text = strip_dashboard_chrome(html_text)
    html_text = rebuild_sticky_nav(html_text, run_root)
    html_text = fix_inline_status_css(html_text)
    html_text = transform_gate_definitions(html_text)
    # Ensure Errata section exists before moving claim audits
    html_text = ensure_errata_section(html_text, run_root)
    html_text = move_claim_audits_to_errata(html_text)
    html_text = move_tom_edges_appendix_to_errata(html_text)
    html_text = move_per_claim_audit_to_errata(html_text)
    html_text = rebuild_claim_audits_section(html_text, run_root)
    _hydrate_embry_research(run_root)
    build_all_panel_bundles(run_root)
    _ensure_contact_sheet_assets(run_root)
    html_text = inject_contact_sheet_gallery(html_text, run_root)
    html_text = move_required_coverage_to_errata(html_text, run_root)
    html_text = humanize_creative_leadership_headings(html_text)
    html_text = redesign_panel_story_summary(html_text)
    html_text = consolidate_motion_bullet_lists(html_text)
    html_text = normalize_timing_pills(html_text)
    html_text = polish_scene_constraints(html_text)
    html_text = rebuild_story_package_section(html_text, run_root)
    html_text = restructure_pipeline_sections(html_text, run_root)
    html_text = dedupe_panel_breakdown_blocks(html_text)
    html_text = inject_panel_regenerate_buttons(html_text, run_root)
    html_text = move_full_interaction_tables_to_errata(html_text)
    html_text = move_panel_interaction_contracts_to_errata(html_text)
    html_text = tag_panel_interaction_ledgers(html_text)
    html_text = add_panel_ledger_links(html_text)
    intro = (
        '<p class="intro">Read in production order: idea → memories → story → producer → contact sheets → script → panels → export to Kling. Script (dialogue and craft) comes before panels. Claim audits and machine proof live in <a href="#pipeline-errata">Errata</a>.</p>'
    )
    html_text = re.sub(r'<p class="intro">.*?</p>', intro, html_text, count=1)
    outline = pipeline_outline_html(run_root)
    if 'class="pipeline-outline"' in html_text:
        html_text = re.sub(r'<nav class="pipeline-outline"[\s\S]*?</nav>\s*', outline + "\n", html_text, count=1)
    else:
        html_text = re.sub(
            r'(<p class="intro">.*?</p>\s*)',
            r'\1' + outline + "\n",
            html_text,
            count=1,
            flags=re.DOTALL,
        )
    banner = gate_summary_banner_html(run_root)
    if "gate-summary-banner" not in html_text:
        html_text = re.sub(
            r'(<nav class="sticky-nav"[\s\S]*?</nav>\s*)',
            r'\1' + banner + "\n",
            html_text,
            count=1,
        )
    html_text = re.sub(
        r'<div class="status(?:-blocked phase-gate-blocked)?">',
        '<div class="status-blocked phase-gate-blocked">',
        html_text,
        count=1,
    )

    index_path.write_text(html_text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    review_dir = args.run_root / "pipeline_review_8892"
    index_path = review_dir / "index.html"
    patch_index_html(index_path, args.run_root.resolve())
    full_report_path = review_dir / "full-report.html"
    if full_report_path.exists() or index_path.exists():
        full_report_path.write_text(index_path.read_text())


if __name__ == "__main__":
    main()
