"""Stage 0 morning report and decision service."""

from __future__ import annotations

import html
import secrets
import subprocess
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .decisions import ALLOWED_ACTIONS, append_decision, replay
from .report import load_manifest
from .util import read_json

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
REMOTE_BIND_HOSTS = {"0.0.0.0", "::"}
SERVICE_ALLOWED_ACTIONS = ALLOWED_ACTIONS - {
    "MARK_HUMAN_SENT_GMAIL",
    "MARK_HUMAN_SENT_LINKEDIN",
}


def ensure_token(run_dir: Path) -> str:
    path = run_dir / "serve-token.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(24)
    path.write_text(token + "\n", encoding="utf-8")
    if path.read_text(encoding="utf-8").strip() != token:
        raise RuntimeError(f"token readback failed for {path}")
    return token


def _projection(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "decision-projection.json"
    if path.exists():
        return read_json(path)
    return replay(run_dir)


def _item_ids(manifest: Any) -> list[str]:
    ids: list[str] = []
    ids.extend(item.opportunity_id for item in manifest.opportunities)
    ids.extend(item.variant_id for item in manifest.resume_variants)
    ids.extend(item.application_id for item in manifest.applications)
    ids.extend(item.packet_id for item in manifest.application_packets)
    ids.extend(packet.packet_id for packet in manifest.outreach_packets)
    return ids


def _list(items: list[Any] | tuple[Any, ...], empty: str = "None recorded") -> str:
    rendered = "".join(f"<li>{html.escape(str(item))}</li>" for item in items if item)
    return f"<ul>{rendered}</ul>" if rendered else f'<p class="blocker">{html.escape(empty)}</p>'


def _badge(value: str) -> str:
    css = "ok"
    if value in {"FEED_DOWN", "AUTH_REQUIRED", "BLOCKED_STAGE_0", "human_required"}:
        css = "blocked"
    elif value in {"NO_MATCHES", "NOT_SEARCHED", "WOULD_PRESENT_STAGE0", "NOT_RUN", "INDETERMINATE"}:
        css = "pending"
    return f'<span class="badge {css}">{html.escape(value)}</span>'


def _link(label: str, url: str | None) -> str:
    if not url:
        return ""
    safe_url = html.escape(url, quote=True)
    return f'<div><dt>{html.escape(label)}</dt><dd><a href="{safe_url}">{html.escape(url)}</a></dd></div>'


def _draft_readback(packet: Any) -> str:
    if not packet.draft_id and not packet.mailbox_draft_ref and not packet.effect_receipt_digest:
        return ""
    return (
        "<p><strong>Gmail draft:</strong> "
        f"{html.escape(packet.mailbox_draft_ref or packet.draft_id or 'unknown')}</p>"
        f"<p><strong>Effect receipt:</strong> <code>{html.escape(packet.effect_receipt_digest or 'none')}</code></p>"
    )


def _revision_note(packet: Any) -> str:
    if not packet.revision_note and not packet.reviewed_payload_digest:
        return ""
    return (
        f"<p><strong>Revision:</strong> {html.escape(packet.revision_note or 'Roundtable revisions applied.')}</p>"
        f"<p><strong>Reviewed payload digest:</strong> "
        f"<code>{html.escape(packet.reviewed_payload_digest or 'none')}</code></p>"
    )


def _action_options(actions: list[str]) -> str:
    return "".join(
        f'<option value="{html.escape(action)}">{html.escape(action.replace("_", " ").title())}</option>'
        for action in actions
        if action in SERVICE_ALLOWED_ACTIONS
    )


def _decision_form(token: str, item_id: str, label: str, actions: list[str]) -> str:
    options = _action_options(actions)
    if not options:
        return '<p class="blocker">No Stage 0 local decision is available for this item.</p>'
    return (
        f'<form class="decision" method="post" action="/decision?token={html.escape(token)}">'
        f'<input type="hidden" name="item" value="{html.escape(item_id)}">'
        f'<label>{html.escape(label)}<select name="action">{options}</select></label>'
        '<label>Decision key<input name="idempotency_key" required></label>'
        '<label>Reason<input name="reason"></label>'
        '<button type="submit">Record Decision</button></form>'
    )


def _source_evidence(source_ids: list[str], receipts_by_id: dict[str, Any]) -> str:
    rows = []
    for source_id in source_ids:
        receipt = receipts_by_id.get(source_id)
        if receipt is None:
            rows.append(f"<li>{html.escape(source_id)}: missing receipt in manifest</li>")
            continue
        rows.append(
            "<li>"
            f"<strong>{html.escape(receipt.provider)}</strong> "
            f"{_badge(receipt.result_status.value)}"
            f"<div>Source class: {html.escape(receipt.source_class)}</div>"
            f"<div>Automation policy: {html.escape(receipt.automation_policy or 'not applicable')}</div>"
            f"<div>Evidence: {_list(receipt.evidence_refs, 'No evidence URL retained.')}</div>"
            f"<div>Limitations: {_list(receipt.limitations, 'No limitations recorded.')}</div>"
            "</li>"
        )
    return f"<ul>{''.join(rows)}</ul>" if rows else '<p class="blocker">No source receipt IDs.</p>'


def _application_packet(application: Any, token: str, packets: list[Any]) -> str:
    field_rows = "".join(
        "<tr>"
        f"<td>{html.escape(field.name)}</td>"
        f"<td>{html.escape(field.field_type)}</td>"
        f"<td>{str(field.required).lower()}</td>"
        f"<td>{_badge(field.disposition)}</td>"
        "</tr>"
        for field in application.fields
    )
    packet_html = "".join(
        "<section class=\"packet\"><h5>Exact Packet Binding</h5>"
        f"<p>{_badge(packet.approval_status)} visible_in_report={str(packet.visible_in_report).lower()}</p>"
        f"<p>Packet ID: <code>{html.escape(packet.packet_id)}</code></p>"
        f"<p>Packet JSON: <code>{html.escape(packet.packet_ref)}</code></p>"
        f"<p>Resume digest: <code>{html.escape(packet.resume_digest)}</code></p>"
        f"<p>Claim snapshot digest: <code>{html.escape(packet.claim_snapshot_digest)}</code></p>"
        f"<p>Field answer digest: <code>{html.escape(packet.field_answer_digest)}</code></p>"
        f"<p>Approval payload digest: <code>{html.escape(packet.approval_payload_digest)}</code></p>"
        "</section>"
        for packet in packets
    ) or '<p class="blocker">No exact application packet is present.</p>'
    return (
        '<section class="packet"><h4>Application Packet</h4>'
        f"<p>{_badge(application.state)} authorized={str(application.authorized).lower()}</p>"
        f"<p>ATS provider: {html.escape(str(application.ats_provider or 'not established'))}</p>"
        "<table><thead><tr><th>Field</th><th>Type</th><th>Required</th>"
        f"<th>Disposition</th></tr></thead><tbody>{field_rows}</tbody></table>"
        + packet_html
        + _decision_form(
            token,
            application.application_id,
            "Application packet decision",
            ["WITHHOLD_APPLICATION", "AUTHORIZE_APPLICATION_PAYLOAD"],
        )
        + "</section>"
    )


def _load_semantic_addenda(run_dir: Path) -> dict[str, dict[str, Any]]:
    index_path = run_dir / "semantic-addenda" / "index.json"
    if not index_path.exists():
        return {}
    index = read_json(index_path)
    addenda: dict[str, dict[str, Any]] = {}
    for item in index.get("items", []):
        if item.get("external_effects") is not False:
            continue
        addendum_path = Path(str(item.get("addendum") or ""))
        if not addendum_path.is_file():
            continue
        addendum = read_json(addendum_path)
        if addendum.get("external_effects") is False and addendum.get("opportunity_id"):
            addenda[str(addendum["opportunity_id"])] = addendum
    return addenda


def _semantic_addendum_card(addendum: dict[str, Any] | None) -> str:
    if not addendum:
        return '<p class="blocker">No provider semantic addendum is installed for this opportunity.</p>'
    return (
        '<section class="packet semantic"><h4>Provider Semantic Addendum</h4>'
        f"<p>{_badge(str(addendum.get('verdict') or 'NEEDS_REVIEW'))} external_effects=false</p>"
        f"<p>{html.escape(str(addendum.get('semantic_summary') or ''))}</p>"
        f"<h5>Tailoring guidance</h5><p>{html.escape(str(addendum.get('tailoring_guidance') or ''))}</p>"
        f"<h5>Talking points</h5>{_list(addendum.get('talking_points') or [], 'No talking points admitted.')}"
        f"<h5>Interview questions</h5>{_list(addendum.get('interview_questions') or [], 'No interview questions admitted.')}"
        f"<h5>Evidence refs</h5>{_list(addendum.get('evidence_refs') or [], 'No evidence refs admitted.')}"
        f"<h5>Non-claims</h5>{_list(addendum.get('non_claims') or [], 'No non-claims admitted.')}"
        "</section>"
    )


def _opportunity_cards(manifest: Any, token: str, semantic_addenda: dict[str, dict[str, Any]] | None = None) -> str:
    receipts_by_id = {item.receipt_id: item for item in manifest.source_receipts}
    applications: dict[str, list[Any]] = defaultdict(list)
    for item in manifest.applications:
        applications[item.opportunity_id].append(item)
    packets_by_application: dict[str, list[Any]] = defaultdict(list)
    for packet in manifest.application_packets:
        packets_by_application[packet.application_id].append(packet)
    variants: dict[str, list[Any]] = defaultdict(list)
    for item in manifest.resume_variants:
        variants[item.opportunity_id].append(item)
    outreach: dict[str, list[Any]] = defaultdict(list)
    for packet in manifest.outreach_packets:
        outreach[packet.opportunity_id].append(packet)
    prep = {item.opportunity_id: item for item in manifest.interview_prep}

    cards = []
    for rank, item in enumerate(manifest.opportunities, start=1):
        application_html = "".join(
            _application_packet(application, token, packets_by_application.get(application.application_id, []))
            for application in applications.get(item.opportunity_id, [])
        ) or '<p class="blocker">No application packet is present.</p>'
        variant_html = "".join(
            '<section class="packet"><h4>Amended Resume</h4>'
            f"<p>{_badge(variant.status)}</p>"
            f"<p>Claim snapshot: <code>{html.escape(variant.claim_snapshot_sha256)}</code></p>"
            "<h5>Artifacts</h5>"
            f"{_list(variant.artifact_refs, 'No resume artifacts retained.')}"
            "<h5>Allowed Presentation Changes</h5>"
            f"{_list(variant.presentation_diff.allowed_changes, 'No allowed changes recorded.')}"
            + _decision_form(
                token,
                variant.variant_id,
                "Resume decision",
                ["ACCEPT_RESUME_VARIANT", "PROPOSE_CLAIM_AMENDMENT"],
            )
            + "</section>"
            for variant in variants.get(item.opportunity_id, [])
        ) or '<p class="blocker">No amended resume variant is present for this opportunity.</p>'
        outreach_html = "".join(
            '<section class="packet"><h4>Human-Transmitted Outreach</h4>'
            f"<p>{html.escape(packet.channel)} {_badge(packet.effect_status)} "
            f"{_badge(packet.readiness_state)} sendable={str(packet.sendable).lower()}</p>"
            f"<p><strong>Recipient:</strong> {html.escape(packet.recipient)} "
            f"({html.escape(packet.contact_provenance)})</p>"
            f"<p><strong>Subject:</strong> {html.escape(packet.subject or '(none)')}</p>"
            f"<pre>{html.escape(packet.body)}</pre>"
            f"<p>Roundtable verdict: {html.escape(packet.roundtable_verdict or 'not permitting')}</p>"
            f"{_revision_note(packet)}"
            f"<p>Payload digest: <code>{html.escape(packet.payload_digest)}</code></p>"
            f"<p>Roundtable receipt: <code>{html.escape(packet.roundtable_receipt_digest or 'none')}</code></p>"
            f"{_draft_readback(packet)}"
            f"{_list(packet.claim_keys, 'No claim keys retained.')}"
            "<h5>Human send steps</h5>"
            f"{_list(packet.human_send_steps, 'No human send steps retained.')}"
            "</section>"
            for packet in outreach.get(item.opportunity_id, [])
        ) or '<p class="blocker">No outreach packet is present.</p>'
        prep_item = prep.get(item.opportunity_id)
        prep_html = (
            "".join(
                f"<p>{html.escape(point.text)}</p>"
                f"<div class=\"muted\">Claims: {html.escape(', '.join(point.claim_keys))}; "
                f"Sources: {html.escape(', '.join(point.source_refs))}</div>"
                for point in prep_item.talking_points
            )
            if prep_item
            else '<p class="blocker">No interview preparation is present.</p>'
        )
        cards.append(
            "<article class=\"opportunity\">"
            f"<div class=\"rank\">#{rank}</div>"
            f"<h2>{html.escape(item.title)}</h2>"
            f"<p class=\"org\">{html.escape(item.organization)}</p>"
            "<dl class=\"facts\">"
            f"<div><dt>Lane</dt><dd>{html.escape(item.lane)}</dd></div>"
            f"<div><dt>Fit</dt><dd>{item.fit_score:.2f}</dd></div>"
            f"<div><dt>Eligibility</dt><dd>{_badge(item.eligibility_state)}</dd></div>"
            f"<div><dt>Location</dt><dd>{html.escape(item.location.display)}</dd></div>"
            f"<div><dt>Type</dt><dd>{_badge(item.opportunity_type)}</dd></div>"
            f"<div><dt>Relocation Required</dt><dd>{str(item.location.relocation_required).lower()}</dd></div>"
            f"{_link('Primary Evidence', item.primary_evidence_url)}"
            f"{_link('Posting', item.posting_url)}"
            f"{_link('Apply URL', item.apply_url)}"
            "</dl>"
            "<h3>Why this is here</h3>"
            f"{_list(item.why_candidate, 'No candidate rationale retained.')}"
            "<h3>Claim keys</h3>"
            f"{_list(item.claim_keys, 'No claim keys retained.')}"
            "<h3>Source evidence</h3>"
            f"{_source_evidence(item.source_receipt_ids, receipts_by_id)}"
            "<h3>Observed screening evidence</h3>"
            f"{_list(item.screening_interface_profile.observed, 'No observed interface evidence.')}"
            "<h3>Bounded inferences</h3>"
            f"{_list(item.screening_interface_profile.inferred, 'No bounded inferences recorded.')}"
            "<h3>Unknowns</h3>"
            f"{_list(item.screening_interface_profile.unknowns, 'No unknowns recorded.')}"
            f"{_decision_form(token, item.opportunity_id, 'Opportunity decision', ['KEEP', 'REJECT', 'DEFER'])}"
            f"{variant_html}"
            f"{application_html}"
            f"{outreach_html}"
            '<section class="packet"><h4>Interview Preparation</h4>'
            f"{prep_html}</section>"
            f"{_semantic_addendum_card((semantic_addenda or {}).get(item.opportunity_id))}"
            "</article>"
        )
    return "".join(cards) or '<p class="empty">No opportunity cleared the eligibility and quality bar.</p>'


def _headers(handler: BaseHTTPRequestHandler, content_type: str = "text/html; charset=utf-8") -> None:
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header(
        "Content-Security-Policy",
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-src 'self'; child-src 'self'",
    )


def _tailscale_ipv4() -> str | None:
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else None


def _render_page(run_dir: Path, token: str) -> str:
    manifest = load_manifest(run_dir / "report-manifest.json")
    semantic_addenda = _load_semantic_addenda(run_dir)
    projection = _projection(run_dir)
    projection_rows = "".join(
        f"<li>{html.escape(item_id)}: {html.escape(row['last_action'])}</li>"
        for item_id, row in sorted(projection.get("items", {}).items())
    ) or "<li>No decisions yet</li>"
    lanes = "".join(
        "<tr>"
        f"<td>{html.escape(lane.lane)}</td>"
        f"<td>{_badge(lane.result_status.value)}</td>"
        f"<td>{lane.candidates_observed}</td>"
        f"<td>{lane.candidates_admitted}</td>"
        f"<td>{_list(lane.limitations, 'No lane limitations recorded.')}</td>"
        "</tr>"
        for lane in manifest.lane_coverage
    )
    opportunities = _opportunity_cards(manifest, token, semantic_addenda)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Morning Opportunity Interview</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ margin: 0; line-height: 1.45; background: Canvas; color: CanvasText; }}
header, main, footer {{ max-width: 1120px; margin: 0 auto; padding: 1.25rem; }}
header {{ border-bottom: 1px solid #7776; }}
nav a {{ margin-right: 1rem; color: inherit; }}
form.decision {{ display: grid; grid-template-columns: minmax(16rem, 1.2fr) minmax(12rem, .8fr) minmax(12rem, .8fr) minmax(8rem, auto); gap: .5rem; margin: .75rem 0; align-items: end; }}
label {{ display: grid; gap: .25rem; min-width: 0; }}
input, select, button {{ font: inherit; padding: .45rem .55rem; min-width: 0; width: 100%; box-sizing: border-box; }}
button {{ white-space: nowrap; }}
section {{ margin: 1.5rem 0; }}
.opportunity {{ border-bottom: 1px solid #7776; margin: 1rem 0; padding: 1rem 0; }}
.rank {{ font-weight: 700; }}
.org {{ font-size: 1.1rem; margin-top: -.5rem; }}
.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: .75rem; }}
.facts div {{ border-top: 1px solid #7776; padding-top: .5rem; }}
.packet {{ border-left: 4px solid #7776; padding-left: 1rem; margin: 1rem 0; }}
.badge {{ display: inline-block; border: 1px solid currentColor; padding: .1rem .45rem; margin: .1rem; font-size: .85rem; }}
.blocked {{ font-weight: 700; }}
.pending {{ font-style: italic; }}
.blocker {{ font-weight: 700; }}
dt {{ font-size: .8rem; opacity: .72; }}
dd {{ margin: .1rem 0 0; }}
dt, dd {{ overflow-wrap: anywhere; }}
.muted {{ opacity: .72; }}
.empty {{ font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #7776; padding: .5rem; vertical-align: top; }}
pre {{ white-space: pre-wrap; border: 1px solid #7776; padding: .75rem; overflow-wrap: anywhere; }}
code {{ overflow-wrap: anywhere; }}
@media (max-width: 760px) {{ form.decision {{ grid-template-columns: 1fr; }} body {{ padding: .75rem; }} }}
</style>
</head>
<body>
<header>
<h1>Morning Opportunity Interview</h1>
<p>{len(manifest.opportunities)} shortlisted opportunities from run {html.escape(manifest.run_id)}. External effects are disabled.</p>
<p>{html.escape(manifest.immutable_goal.text)}</p>
<nav><a href="#opportunities">Opportunities</a><a href="#coverage">Coverage</a><a href="/report?token={html.escape(token)}">Canonical report</a></nav>
</header>
<main>
<section id="opportunities"><h2>Shortlisted opportunities</h2>{opportunities}</section>
<section id="coverage"><h2>Coverage And Source Health</h2><p>Hidden action-worthy artifacts: {manifest.artifact_accounting.hidden_total}</p><table><thead><tr><th>Lane</th><th>Status</th><th>Observed</th><th>Admitted</th><th>Limitations</th></tr></thead><tbody>{lanes}</tbody></table></section>
<section><h2>Current projection</h2><ul>{projection_rows}</ul></section>
</main>
<footer><p class="muted">Read-only local service. Decisions append local events only; no Gmail, LinkedIn, ATS, or application submission effect is available here.</p></footer>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    run_dir: Path
    token: str

    def _authorized(self) -> bool:
        query = parse_qs(urlparse(self.path).query)
        return query.get("token", [""])[0] == self.token

    def _write(self, status: HTTPStatus, payload: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        _headers(self, content_type)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write(HTTPStatus.OK, b'{"status":"PASS","external_effects":false}\n', "application/json")
            return
        if not self._authorized():
            self._write(HTTPStatus.UNAUTHORIZED, b"missing or invalid token\n", "text/plain; charset=utf-8")
            return
        if parsed.path in {"/", "/index.html"}:
            self._write(HTTPStatus.OK, _render_page(self.run_dir, self.token).encode("utf-8"))
            return
        if parsed.path == "/report":
            self._write(HTTPStatus.OK, (self.run_dir / "report" / "index.html").read_bytes())
            return
        if parsed.path == "/projection.json":
            self._write(HTTPStatus.OK, (self.run_dir / "decision-projection.json").read_bytes(), "application/json")
            return
        self._write(HTTPStatus.NOT_FOUND, b"not found\n", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/decision" or not self._authorized():
            self._write(HTTPStatus.UNAUTHORIZED, b"missing or invalid token\n", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        action = form.get("action", [""])[0]
        if action not in SERVICE_ALLOWED_ACTIONS:
            self._write(
                HTTPStatus.BAD_REQUEST,
                b"action blocked by Stage 0 service policy\n",
                "text/plain; charset=utf-8",
            )
            return
        append_decision(
            run_dir=self.run_dir,
            item_id=form.get("item", [""])[0],
            action=action,
            actor="candidate",
            idempotency_key=form.get("idempotency_key", [""])[0],
            reason=form.get("reason", [""])[0] or None,
        )
        replay(self.run_dir)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/?token={self.token}")
        _headers(self)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(run_dir: Path, host: str, port: int, allow_remote: bool = False) -> None:
    if host not in LOOPBACK_HOSTS and not allow_remote:
        raise ValueError("non-loopback serve requires --allow-remote")
    token = ensure_token(run_dir)

    class BoundHandler(_Handler):
        pass

    BoundHandler.run_dir = run_dir
    BoundHandler.token = token
    server = ThreadingHTTPServer((host, port), BoundHandler)
    shown_host = "127.0.0.1" if host in REMOTE_BIND_HOSTS else host
    print(
        f"monitor-opportunities serve: http://{shown_host}:{server.server_port}/?token={token}",
        flush=True,
    )
    if allow_remote:
        tailscale_ip = _tailscale_ipv4()
        if tailscale_ip:
            print(
                f"monitor-opportunities tailscale: "
                f"http://{tailscale_ip}:{server.server_port}/?token={token}",
                flush=True,
            )
    server.serve_forever()
