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
    if value in {"NOT_SEARCHED", "NO_MATCHES", "NOT_RUN", "WOULD_PRESENT_STAGE0"}:
        css = "warn"
    return f'<span class="badge {css}">{safe}</span>'


def render_html(manifest: ReportManifest) -> str:
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

    opportunities = "".join(
        f"<article><h3>{html.escape(item.title)} — {html.escape(item.organization)}</h3>"
        f"<p>{_badge(item.eligibility_state)} score {item.fit_score:.2f}</p>"
        f"<p><strong>Location:</strong> {html.escape(item.location.display)}</p>"
        f"<h4>Why this candidate</h4>{_list(item.why_candidate)}"
        f"<h4>Claim keys</h4>{_list(item.claim_keys)}"
        f"<h4>Observed screening evidence</h4>{_list(item.screening_interface_profile.observed)}"
        f"<h4>Bounded inferences</h4>{_list(item.screening_interface_profile.inferred)}"
        f"<h4>Unknowns</h4>{_list(item.screening_interface_profile.unknowns)}</article>"
        for item in manifest.opportunities
    ) or '<p class="empty">No opportunity cleared the eligibility and quality bar.</p>'

    rejections = "".join(
        f"<li><strong>{html.escape(item.title)}</strong> — {html.escape(item.organization)} "
        f"{_badge(item.reason_code)}</li>"
        for item in manifest.eligibility_rejections
    ) or "<li>None</li>"

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
        f"<p>{_badge(item.effect_status)} candidate_transmits={str(item.candidate_transmits).lower()}</p>"
        f"<p><strong>Subject:</strong> {html.escape(item.subject or '(none)')}</p>"
        f"<pre>{html.escape(item.body)}</pre><h4>Claims</h4>{_list(item.claim_keys)}</article>"
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
        f"<td>{html.escape(item.target)}</td><td>{_badge(item.result_status.value)}</td>"
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
<section><h2>Opportunities</h2>{opportunities}<h3>Hard rejections</h3><ul>{rejections}</ul></section>
<section><h2>Tailored resume variants</h2>{variants}</section>
<section><h2>Human-transmitted outreach</h2><p><strong>The human transmits. Stage 0 packets are not sendable.</strong></p>{outreach}</section>
<section><h2>ATS application state</h2>{applications}</section>
<section><h2>Interview preparation</h2>{interview}</section>
<section><h2>Source receipts</h2><table><thead><tr><th>Lane</th><th>Provider</th><th>Target</th><th>Status</th><th>Evidence</th><th>Limitations</th></tr></thead><tbody>{sources}</tbody></table></section>
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
