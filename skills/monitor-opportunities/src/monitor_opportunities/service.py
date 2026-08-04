"""Stage 0 morning report and decision service."""

from __future__ import annotations

import html
import secrets
import subprocess
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
    "AUTHORIZE_APPLICATION_PAYLOAD",
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
    ids.extend(packet.packet_id for packet in manifest.outreach_packets)
    return ids


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
    projection = _projection(run_dir)
    projection_rows = "".join(
        f"<li>{html.escape(item_id)}: {html.escape(row['last_action'])}</li>"
        for item_id, row in sorted(projection.get("items", {}).items())
    ) or "<li>No decisions yet</li>"
    forms = []
    for item_id in _item_ids(manifest):
        action_options = "".join(
            f'<option value="{html.escape(action)}">{html.escape(action)}</option>'
            for action in sorted(SERVICE_ALLOWED_ACTIONS)
        )
        forms.append(
            f"<form method=\"post\" action=\"/decision?token={html.escape(token)}\">"
            f"<input type=\"hidden\" name=\"item\" value=\"{html.escape(item_id)}\">"
            f"<label>{html.escape(item_id)}<select name=\"action\">{action_options}</select></label>"
            "<input name=\"idempotency_key\" placeholder=\"idempotency key\" required>"
            "<input name=\"reason\" placeholder=\"reason\">"
            "<button type=\"submit\">Record</button></form>"
        )
    lanes = "".join(
        f"<li>Lane {html.escape(lane.lane)}: {html.escape(lane.result_status.value)} "
        f"observed={lane.candidates_observed} admitted={lane.candidates_admitted}</li>"
        for lane in manifest.lane_coverage
    )
    opportunities = "".join(
        f"<li>{html.escape(item.title)} at {html.escape(item.organization)} "
        f"({html.escape(item.opportunity_id)})</li>"
        for item in manifest.opportunities
    ) or "<li>No shortlisted opportunities</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>monitor-opportunities decision loop</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; line-height: 1.4; }}
form {{ display: grid; grid-template-columns: minmax(18rem, 1.2fr) minmax(14rem, .8fr) minmax(14rem, .8fr) minmax(9rem, auto); gap: .5rem; margin: .75rem 0; align-items: end; }}
label {{ display: grid; gap: .25rem; min-width: 0; }}
input, select, button {{ font: inherit; padding: .35rem .45rem; min-width: 0; width: 100%; box-sizing: border-box; }}
button {{ white-space: nowrap; }}
section {{ margin: 1.5rem 0; }}
</style>
</head>
<body>
<h1>monitor-opportunities decision loop</h1>
<p>Run: {html.escape(manifest.run_id)}. External effects: false. Token-gated morning review service.</p>
<section><h2>Current Projection</h2><ul>{projection_rows}</ul></section>
<section><h2>Decision Forms</h2>{''.join(forms)}</section>
<section><h2>Report Summary</h2><p>Hidden action-worthy artifacts: {manifest.artifact_accounting.hidden_total}</p><ul>{lanes}</ul><h3>Shortlist</h3><ul>{opportunities}</ul><p><a href="/report?token={html.escape(token)}">Open full report</a></p></section>
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
