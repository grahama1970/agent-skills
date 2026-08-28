"""Self-contained Stage 0 report rendering."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, Iterable

from .contracts import ReportManifest, validate_manifest


def canonical_json_bytes(manifest: ReportManifest) -> bytes:
    return (
        json.dumps(
            manifest.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(path: Path) -> ReportManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        from .contracts import ContractError

        raise ContractError("INPUT_INVALID_JSON", f"Cannot read report manifest: {exc}") from exc
    return validate_manifest(raw)


def _list(items: Iterable[Any]) -> str:
    rendered = "".join(f"<li>{html.escape(str(item))}</li>" for item in items)
    return f"<ul>{rendered}</ul>" if rendered else "<p class=\"muted\">None</p>"


def _badge(value: str) -> str:
    safe = html.escape(value)
    css = "bad" if value in {"FEED_DOWN", "BLOCKED_STAGE_0", "human_required"} else "ok"
    if value in {"NOT_SEARCHED", "NO_MATCHES", "NOT_RUN", "WOULD_PRESENT_STAGE0", "INDETERMINATE"}:
        css = "warn"
    return f'<span class="badge {css}">{safe}</span>'


def _link(label: str, url: str | None) -> str:
    if not url:
        return ""
    safe_url = html.escape(url, quote=True)
    safe_label = html.escape(label)
    return f'<p><strong>{safe_label}:</strong> <a href="{safe_url}">{html.escape(url)}</a></p>'


def _table_link(label: str, url: str | None) -> str:
    if not url:
        return '<span class="muted">None</span>'
    safe_url = html.escape(url, quote=True)
    return f'<a href="{safe_url}">{html.escape(label)}</a>'


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _anchor(prefix: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _source_receipt_lookup(manifest: ReportManifest) -> dict[str, Any]:
    return {receipt.receipt_id: receipt for receipt in manifest.source_receipts}


def _linkedin_evidence_label(source_receipt_ids: list[str], receipts_by_id: dict[str, Any]) -> str:
    for receipt_id in source_receipt_ids:
        receipt = receipts_by_id.get(receipt_id)
        if receipt is None:
            continue
        haystack = " ".join(
            str(value or "")
            for value in (
                receipt.provider,
                receipt.source_class,
                receipt.channel,
                receipt.request_summary,
                *receipt.evidence_refs,
            )
        ).lower()
        if "linkedin" in haystack:
            return "LinkedIn evidence present; Top Applicant/Easy Apply only if stated in source receipt."
    return "No LinkedIn Top Applicant/Easy Apply evidence on this row."


def _contact_label(item: Any, signals_by_id: dict[str, Any], *, has_binding_diagnostics: bool = False) -> str:
    ids = list(getattr(item, "relationship_signal_ids", []) or [])
    labels: list[str] = []
    for signal_id in ids:
        signal = signals_by_id.get(signal_id)
        if signal is None:
            continue
        labels.append(f"{signal.subject} ({signal.degree_label})")
    if labels:
        return "; ".join(labels)
    organization = str(getattr(item, "organization", "") or "").strip()
    if has_binding_diagnostics:
        org_label = f" for {organization}" if organization else ""
        return f"No direct contact path{org_label} found; see relationship binding diagnostics."
    return "No relationship signal captured for this opportunity."


def _application_packet_by_opportunity(manifest: ReportManifest) -> dict[str, Any]:
    packets: dict[str, Any] = {}
    for packet in manifest.application_packets:
        packets.setdefault(packet.opportunity_id, packet)
    return packets


def _decision_table(manifest: ReportManifest, signals_by_id: dict[str, Any]) -> str:
    receipts_by_id = _source_receipt_lookup(manifest)
    packets_by_opp = _application_packet_by_opportunity(manifest)
    rows: list[str] = []
    for idx, item in enumerate(manifest.opportunities, start=1):
        packet = packets_by_opp.get(item.opportunity_id)
        packet_label = (
            f"{packet.approval_status}; packet {packet.packet_id}"
            if packet is not None
            else "NO_APPLICATION_PACKET"
        )
        next_action = (
            "Review packet; exact human authorization is required before submit."
            if packet is not None
            else "No application packet; inspect deep section."
        )
        rows.append(
            f"<tr id=\"{_anchor('source-intel', item.signal_id)}\">"
            f"<td>{idx}</td>"
            "<td>Employment</td>"
            f"<td><a href=\"#{_anchor('opportunity', item.opportunity_id)}\">"
            f"{html.escape(item.title)} — {html.escape(item.organization)}</a></td>"
            f"<td>{html.escape(item.location.display)}</td>"
            f"<td>{item.fit_score:.2f}</td>"
            f"<td>{html.escape(packet_label)}</td>"
            f"<td>{html.escape(_contact_label(item, signals_by_id, has_binding_diagnostics=bool(manifest.relationship_binding_diagnostics)))}</td>"
            f"<td>{html.escape(_linkedin_evidence_label(item.source_receipt_ids, receipts_by_id))}</td>"
            f"<td>{html.escape(next_action)}</td>"
            "</tr>"
        )
    for idx, item in enumerate(manifest.source_intel, start=1):
        rows.append(
            "<tr>"
            f"<td>S{idx}</td>"
            "<td>Consulting / source intel</td>"
            f"<td><a href=\"#{_anchor('source-intel', item.signal_id)}\">"
            f"{html.escape(item.title)} — {html.escape(item.organization)}</a></td>"
            f"<td>{html.escape(item.signal_type)}</td>"
            "<td></td>"
            f"<td>{html.escape(item.decision)}</td>"
            "<td>See source-intel detail.</td>"
            f"<td>{html.escape(_linkedin_evidence_label(item.source_receipt_ids, receipts_by_id))}</td>"
            "<td>Research/contact action only; not an ATS application packet.</td>"
            "</tr>"
        )
    body = "".join(rows) or '<tr><td colspan="9">No report-visible opportunities or source-intel rows.</td></tr>'
    return (
        "<table class=\"decision-table\"><thead><tr>"
        "<th>Rank</th><th>Kind</th><th>Opportunity</th><th>Location / signal</th>"
        "<th>Fit</th><th>Authorization</th><th>Contact path</th>"
        "<th>LinkedIn evidence</th><th>Next action</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _source_intel_table(items: Iterable[Any]) -> str:
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{_badge(item.decision)}<br><span class=\"small\">Action-worthy: {_yes_no(item.action_worthy)}</span></td>"
            f"<td>{_badge(item.signal_type)}</td>"
            f"<td><strong>{html.escape(item.organization)}</strong><br>{html.escape(item.title)}</td>"
            f"<td>{html.escape(item.summary)}{_list(item.reasons)}</td>"
            f"<td>{_table_link('source', item.primary_evidence_url)}{_list(item.evidence_refs)}</td>"
            "</tr>"
        )
    if not rows:
        return "<p>None</p>"
    return (
        '<table class="source-intel-table">'
        "<thead><tr>"
        "<th>Decision</th>"
        "<th>Signal</th>"
        "<th>Role</th>"
        "<th>Next action</th>"
        "<th>Evidence</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _relationship_summary(item: Any, signals_by_id: dict[str, Any]) -> str:
    ids = list(getattr(item, "relationship_signal_ids", []) or [])
    if not ids:
        return '<p class="muted">No relationship signal attached to this opportunity.</p>'
    rows = []
    for signal_id in ids:
        signal = signals_by_id.get(signal_id)
        if signal is None:
            rows.append(f"<li><code>{html.escape(signal_id)}</code>: missing from manifest</li>")
            continue
        rows.append(
            (
                "<li>"
                f"<strong>{html.escape(signal.subject)}</strong> — {html.escape(signal.organization)} "
                f"({_badge(signal.signal_type)})"
                f"<div>{html.escape(signal.provenance)}</div>"
                f"<div>Action: {html.escape(signal.recommended_action)}</div>"
                f"<div>Channels: {html.escape(', '.join(signal.preferred_human_channels))}</div>"
            )
            + (
                f"<div>Event: {_table_link(signal.event_title or 'event', signal.event_url)}</div>"
                if getattr(signal, "event_title", None) or getattr(signal, "event_url", None)
                else ""
            )
            + "</li>"
        )
    return f"<ul>{''.join(rows)}</ul>"


def _linkedin_candidate_table(candidates: list[dict[str, Any]]) -> str:
    rows = []
    for candidate in candidates[:3]:
        name = str(candidate.get("name") or candidate.get("subject") or "").strip()
        profile = str(candidate.get("profile") or candidate.get("url") or "").strip()
        headline = str(candidate.get("headline") or candidate.get("title") or "").strip()
        evidence = str(candidate.get("source_url") or candidate.get("evidence_url") or "").strip()
        if not (name or profile or headline or evidence):
            continue
        rows.append(
            "<tr>"
            f"<td>{html.escape(name or 'candidate')}</td>"
            f"<td>{html.escape(headline or 'not supplied')}</td>"
            f"<td>{_table_link('profile', profile)}{_table_link('evidence', evidence)}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        '<table class="relationship-candidates">'
        "<thead><tr><th>Candidate</th><th>Public signal</th><th>Links</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_relationships_table(signals: list[Any]) -> str:
    rows = []
    for item in signals:
        event = ""
        if getattr(item, "event_title", None) or getattr(item, "event_url", None):
            event = _table_link(item.event_title or "event", item.event_url)
        profile = _table_link("profile", getattr(item, "profile_url", None))
        candidates = _linkedin_candidate_table(list(getattr(item, "linkedin_candidates", []) or []))
        confirmation = (
            '<div class="warn">LinkedIn identity confirmation required before outreach.</div>'
            if getattr(item, "linkedin_confirmation_required", False)
            else ""
        )
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(item.subject)}</strong><div class=\"small\">{html.escape(item.organization)}</div></td>"
            f"<td>{_badge(item.signal_type)}<div class=\"small\">{html.escape(item.provenance)}</div></td>"
            f"<td>{event}{profile}{candidates}{confirmation}</td>"
            f"<td>{html.escape(item.recommended_action)}<div class=\"small\">{html.escape(item.contact_channel_risk)}</div></td>"
            f"<td>{_list(item.preferred_human_channels)}{_list(item.channel_guidance)}</td>"
            f"<td>{_list(item.evidence_refs)}</td>"
            "</tr>"
        )
    if not rows:
        return "<p>None</p>"
    return (
        '<table class="relationship-signal-table">'
        "<thead><tr>"
        "<th>Contact</th><th>Signal</th><th>Event / LinkedIn candidates</th>"
        "<th>Human action</th><th>Channels</th><th>Evidence</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _draft_readback(item: Any) -> str:
    if not item.draft_id and not item.mailbox_draft_ref and not item.effect_receipt_digest:
        return ""
    return (
        "<p><strong>Gmail draft:</strong> "
        f"{html.escape(item.mailbox_draft_ref or item.draft_id or 'unknown')}</p>"
        f"<p><strong>Effect receipt:</strong> <code>{html.escape(item.effect_receipt_digest or 'none')}</code></p>"
    )


def _revision_note(item: Any) -> str:
    if not item.revision_note and not item.reviewed_payload_digest:
        return ""
    return (
        f"<p><strong>Revision:</strong> {html.escape(item.revision_note or 'Roundtable revisions applied.')}</p>"
        f"<p><strong>Reviewed payload digest:</strong> <code>{html.escape(item.reviewed_payload_digest or 'none')}</code></p>"
    )


def render_html(manifest: ReportManifest) -> str:
    signals_by_id = {signal.signal_id: signal for signal in manifest.relationship_signals}
    lanes = "".join(
        "<tr>"
        f"<td>{html.escape(lane.lane)}</td>"
        f"<td>{_badge(lane.result_status.value)}</td>"
        f"<td>{lane.candidates_observed}</td>"
        f"<td>{lane.candidates_admitted}</td>"
        f"<td>{_list(lane.limitations)}</td>"
        "</tr>"
        for lane in manifest.lane_coverage
    )

    decision_table = _decision_table(manifest, signals_by_id)

    opportunities = "".join(
        f"<article id=\"{_anchor('opportunity', item.opportunity_id)}\"><h3>{html.escape(item.title)} — {html.escape(item.organization)}</h3>"
        f"<p>{_badge(item.eligibility_state)} score {item.fit_score:.2f}</p>"
        f"<p><strong>Location:</strong> {html.escape(item.location.display)}</p>"
        f"{_link('Primary evidence', item.primary_evidence_url)}"
        f"{_link('Posting', item.posting_url)}"
        f"{_link('Apply URL', item.apply_url)}"
        f"<h4>Why this candidate</h4>{_list(item.why_candidate)}"
        f"<h4>Claim keys</h4>{_list(item.claim_keys)}"
        f"<h4>Observed screening evidence</h4>{_list(item.screening_interface_profile.observed)}"
        f"<h4>Bounded inferences</h4>{_list(item.screening_interface_profile.inferred)}"
        f"<h4>Unknowns</h4>{_list(item.screening_interface_profile.unknowns)}"
        f"<h4>Relationship signals ({item.relationship_signal_count})</h4>"
        f"{_relationship_summary(item, signals_by_id)}</article>"
        for item in manifest.opportunities
    ) or '<p class="empty">No opportunity cleared the eligibility and quality bar.</p>'

    relationships = _render_relationships_table(list(manifest.relationship_signals))

    relationship_diagnostics = "".join(
        "<tr>"
        f"<td><code>{html.escape(item.signal_id)}</code></td>"
        f"<td>{html.escape(item.opportunity_id or '')}</td>"
        f"<td><code>{html.escape(item.organization_key)}</code></td>"
        f"<td>{_badge(item.reason_code)}</td>"
        f"<td>{html.escape(item.detail)}</td>"
        "</tr>"
        for item in manifest.relationship_binding_diagnostics
    ) or '<tr><td colspan="5">None</td></tr>'

    rejections = "".join(
        f"<li><strong>{html.escape(item.title)}</strong> — {html.escape(item.organization)} "
        f"{_badge(item.reason_code)}</li>"
        for item in manifest.eligibility_rejections
    ) or "<li>None</li>"

    source_intel = _source_intel_table(manifest.source_intel)

    variants = "".join(
        f"<article><h3>{html.escape(item.variant_id)}</h3>"
        f"<p>{_badge(item.status)}</p><h4>Claims</h4>{_list(item.claim_keys)}"
        f"<h4>Artifacts</h4>{_list(item.artifact_refs)}"
        f"<h4>Allowed presentation changes</h4>{_list(item.presentation_diff.allowed_changes)}"
        "</article>"
        for item in manifest.resume_variants
    ) or "<p>None</p>"

    outreach = "".join(
        f"<article><h3>{html.escape(item.channel)} — {html.escape(item.packet_id)}</h3>"
        f"<p>{_badge(item.effect_status)} {_badge(item.readiness_state)} "
        f"candidate_transmits={str(item.candidate_transmits).lower()}</p>"
        f"<p><strong>Recipient:</strong> {html.escape(item.recipient)} "
        f"({html.escape(item.contact_provenance)})</p>"
        f"<p><strong>Subject:</strong> {html.escape(item.subject or '(none)')}</p>"
        f"<pre>{html.escape(item.body)}</pre>"
        f"<p><strong>Characters:</strong> {item.character_count}</p>"
        f"<p><strong>Roundtable verdict:</strong> {html.escape(item.roundtable_verdict or 'not permitting')}</p>"
        f"{_revision_note(item)}"
        f"<p><strong>Payload digest:</strong> <code>{html.escape(item.payload_digest)}</code></p>"
        f"<p><strong>Roundtable receipt digest:</strong> <code>{html.escape(item.roundtable_receipt_digest or 'none')}</code></p>"
        f"{_draft_readback(item)}"
        f"<h4>Claims</h4>{_list(item.claim_keys)}"
        f"<h4>Human send steps</h4>{_list(item.human_send_steps)}</article>"
        for item in manifest.outreach_packets
    ) or "<p>None</p>"

    applications = "".join(
        f"<article><h3>{html.escape(item.application_id)}</h3><p>{_badge(item.state)}</p>"
        + "<table><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Disposition</th></tr></thead><tbody>"
        + "".join(
            "<tr>"
            f"<td>{html.escape(field.name)}</td>"
            f"<td>{html.escape(field.field_type)}</td>"
            f"<td>{str(field.required).lower()}</td>"
            f"<td>{_badge(field.disposition)}</td>"
            "</tr>"
            for field in item.fields
        )
        + "</tbody></table></article>"
        for item in manifest.applications
    ) or "<p>None</p>"

    application_packets = "".join(
        f"<article><h3>{html.escape(item.packet_id)}</h3>"
        f"<p>{_badge(item.approval_status)} visible_in_report={str(item.visible_in_report).lower()}</p>"
        f"<p><strong>Application:</strong> {html.escape(item.application_id)}</p>"
        f"<p><strong>Resume digest:</strong> <code>{html.escape(item.resume_digest)}</code></p>"
        f"<p><strong>Claim snapshot digest:</strong> <code>{html.escape(item.claim_snapshot_digest)}</code></p>"
        f"<p><strong>Field answer digest:</strong> <code>{html.escape(item.field_answer_digest)}</code></p>"
        f"<p><strong>Posting digest:</strong> <code>{html.escape(item.posting_digest)}</code></p>"
        f"<p><strong>Approval payload digest:</strong> <code>{html.escape(item.approval_payload_digest)}</code></p>"
        f"<h4>Policy observations</h4>{_list(item.policy_observations)}"
        f"<h4>Packet JSON</h4>{_list([item.packet_ref])}</article>"
        for item in manifest.application_packets
    ) or "<p>None</p>"

    interview = "".join(
        f"<article><h3>{html.escape(item.opportunity_id)}</h3>"
        + "".join(
            f"<p>{html.escape(point.text)}</p><div class=\"small\">Claims: "
            f"{html.escape(', '.join(point.claim_keys))}; Sources: "
            f"{html.escape(', '.join(point.source_refs))}</div>"
            for point in item.talking_points
        )
        + "</article>"
        for item in manifest.interview_prep
    ) or "<p>None</p>"

    sources = "".join(
        f"<tr><td>{html.escape(item.lane)}</td><td>{html.escape(item.provider)}</td>"
        f"<td>{html.escape(item.target)}</td><td>{html.escape(item.source_class)}</td>"
        f"<td>{html.escape(item.automation_policy or 'not applicable')}</td>"
        f"<td>{_badge(item.result_status.value)}</td>"
        f"<td>{_list(item.evidence_refs)}</td><td>{_list(item.limitations)}</td></tr>"
        for item in manifest.source_receipts
    )

    decisions = "".join(
        f"<li>{html.escape(item.action)} — target {html.escape(item.target_type)} — "
        f"enabled={str(item.enabled).lower()} — external_effect=false</li>"
        for item in manifest.decision_actions
    )

    non_claims = _list(manifest.non_claims)
    accounting = manifest.artifact_accounting

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>monitor-opportunities — {html.escape(manifest.run_id)}</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ max-width: 1100px; margin: 0 auto; padding: 2rem; line-height: 1.45; }}
section {{ margin: 2rem 0; }} article {{ border: 1px solid #7776; padding: 1rem; margin: 1rem 0; border-radius: .5rem; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ border: 1px solid #7776; padding: .5rem; vertical-align: top; }}
th {{ text-align: left; }}
.decision-table {{ font-size: .94rem; }}
.source-intel-table td:nth-child(1), .source-intel-table td:nth-child(2) {{ white-space: nowrap; }}
.source-intel-table th:nth-child(1) {{ width: 22%; }}
.source-intel-table th:nth-child(2) {{ width: 16%; }}
.source-intel-table th:nth-child(3) {{ width: 24%; }}
.source-intel-table th:nth-child(5) {{ width: 14%; }}
.badge {{ display: inline-block; border: 1px solid currentColor; border-radius: 999px; padding: .1rem .5rem; font-size: .85rem; }}
.bad {{ font-weight: 700; }} .warn {{ font-style: italic; }} .small, .muted {{ opacity: .75; font-size: .9rem; }}
pre {{ white-space: pre-wrap; border: 1px solid #7776; padding: .75rem; }} .empty {{ font-weight: 700; }}
</style>
</head>
<body>
<header><h1>Morning opportunity report</h1>
<p><strong>Run:</strong> {html.escape(manifest.run_id)} · <strong>Stage:</strong> {_badge(manifest.stage)} · <strong>Readiness:</strong> {_badge(manifest.operational_readiness)}</p>
<p>{html.escape(manifest.immutable_goal.text)}</p></header>
<section><h2>Coverage and feed health</h2><table><thead><tr><th>Lane</th><th>Status</th><th>Observed</th><th>Admitted</th><th>Limitations</th></tr></thead><tbody>{lanes}</tbody></table></section>
<section><h2>Morning decision table</h2>{decision_table}</section>
<section><h2>Opportunities</h2>{opportunities}<h3>Source intelligence</h3>{source_intel}<h3>Hard rejections</h3><ul>{rejections}</ul></section>
<section><h2>Tailored resume variants</h2>{variants}</section>
<section><h2>Human-transmitted outreach</h2><p><strong>The human transmits. Stage 0 packets are not sendable.</strong></p>{outreach}</section>
<section><h2>ATS application state</h2>{applications}</section>
<section><h2>Application packets</h2>{application_packets}</section>
<section><h2>Relationship signals</h2>{relationships}</section>
<section><h2>Relationship binding diagnostics</h2><table><thead><tr><th>Signal</th><th>Opportunity</th><th>Organization key</th><th>Reason</th><th>Detail</th></tr></thead><tbody>{relationship_diagnostics}</tbody></table></section>
<section><h2>Interview preparation</h2>{interview}</section>
<section><h2>Source receipts</h2><table><thead><tr><th>Lane</th><th>Provider</th><th>Target</th><th>Source class</th><th>Automation policy</th><th>Status</th><th>Evidence</th><th>Limitations</th></tr></thead><tbody>{sources}</tbody></table></section>
<section><h2>Available local decisions</h2><ul>{decisions}</ul></section>
<section><h2>Visibility accounting</h2><p>Action-worthy: {accounting.action_worthy_total}; visible: {accounting.visible_total}; hidden: {accounting.hidden_total}</p></section>
<section><h2>Non-claims</h2>{non_claims}</section>
<footer><p class="small">Self-contained local report. No form, script, tracker, or remote asset is present.</p></footer>
</body></html>
"""


def render_report(manifest: ReportManifest, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_bytes = canonical_json_bytes(manifest)
    html_text = render_html(manifest)
    json_path = out_dir / "report.json"
    html_path = out_dir / "index.html"
    json_path.write_bytes(report_bytes)
    html_path.write_text(html_text, encoding="utf-8")

    if json_path.read_bytes() != report_bytes:
        from .contracts import ContractError

        raise ContractError("REPORT_READBACK_FAILED", "Normalized report JSON did not read back")
    if html_path.read_text(encoding="utf-8") != html_text:
        from .contracts import ContractError

        raise ContractError("REPORT_READBACK_FAILED", "Rendered HTML did not read back")

    return {
        "report_json": str(json_path),
        "report_html": str(html_path),
        "report_sha256": sha256_bytes(report_bytes),
        "html_sha256": sha256_bytes(html_text.encode("utf-8")),
    }
