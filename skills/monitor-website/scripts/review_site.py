#!/usr/bin/env python3
"""Prepare, verify, serve, and stop immutable website section-review bundles."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"
CORPUS_ROOT = SITE / "design-roundtable" / "rendered-screens"
MANIFEST_NAME = "review-manifest.json"
SERVER_STATE_NAME = "server.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def rel(path: Path, base: Path = REPO) -> str:
    return str(path.resolve().relative_to(base.resolve()))


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stable_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{proc.stdout}")
    return proc.stdout


def source_state() -> dict[str, Any]:
    commit = git_output("rev-parse", "HEAD").strip()
    ls_files = git_output(
        "ls-files",
        "-s",
        "site",
        "skills/monitor-website",
        "skills/best-practices-bespoke-design",
    )
    diff = git_output(
        "diff",
        "--",
        "site",
        "skills/monitor-website",
        "skills/best-practices-bespoke-design",
    )
    digest_input = {
        "commit": commit,
        "tracked_files": ls_files,
        "diff": diff,
    }
    return {
        "commit": commit,
        "dirty": bool(diff.strip()),
        "state_digest_sha256": sha256_bytes(stable_json(digest_input)),
    }


def latest_corpus_manifest() -> Path | None:
    manifests = sorted(CORPUS_ROOT.glob("responsive-section-corpus-*/manifest.json"))
    return manifests[-1] if manifests else None


def safe_unit_id(record: dict[str, Any]) -> str:
    segment = ""
    if int(record.get("segment_count") or 1) > 1:
        segment = f"-s{int(record.get('segment_index') or 0) + 1:02d}of{int(record.get('segment_count') or 1):02d}"
    raw = f"{record.get('viewport_id')}-{record.get('id')}{segment}"
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in str(raw).lower())


def unit_live_url(base_url: str, record: dict[str, Any]) -> str:
    section = str(record.get("id") or "").lstrip("#")
    parsed = urlparse(base_url)
    root = base_url if base_url.endswith("/") else base_url + "/"
    if parsed.fragment:
        root = base_url.split("#", 1)[0]
    return root + (f"#{section}" if section else "")


def copy_artifact(src_value: str, out_dir: Path, unit_id: str) -> dict[str, str]:
    src = repo_path(src_value).resolve()
    if not src.is_file():
        raise SystemExit(f"missing corpus artifact: {src_value}")
    if REPO.resolve() not in src.parents and src != REPO.resolve():
        raise SystemExit(f"refusing artifact outside repo: {src_value}")
    dest_dir = out_dir / "artifacts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{unit_id}{src.suffix or '.artifact'}"
    shutil.copy2(src, dest)
    return {
        "path": rel(dest, out_dir),
        "sha256": sha256_file(dest),
        "source_path": rel(src),
    }


def html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{html.escape(title)}</title>
<style>
  body {{ margin: 0; background: #11100f; color: #eee8dc; font-family: system-ui, sans-serif; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
  code, .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  a {{ color: #e7b75f; }}
  .meta {{ border-left: 3px solid #e7b75f; padding-left: 16px; color: #c9bbab; }}
  .grid {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; }}
  iframe {{ width: 100%; min-height: 560px; border: 1px solid #3a2a18; background: #050505; }}
  img {{ max-width: 100%; height: auto; border: 1px solid #3a2a18; background: #050505; }}
  li {{ margin-block: 8px; }}
</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""


def write_templates(out_dir: Path, manifest: dict[str, Any]) -> None:
    unit_links = "\n".join(
        f'<li><a href="__ACCESS_BASE__/{quote(unit["unit_id"])}/">{html.escape(unit["unit_id"])}</a> '
        f'<span class="mono">{html.escape(unit["viewport_id"])}</span> '
        f'{html.escape(unit["section_id"])}</li>'
        for unit in manifest["review_units"]
    )
    index_body = f"""
<h1>Review Bundle</h1>
<div class="meta">
  <p>candidate_fingerprint: <code>{manifest["candidate_fingerprint"]}</code></p>
  <p>unit_count: <code>{len(manifest["review_units"])}</code></p>
  <p>source_commit: <code>{manifest["source_state"]["commit"]}</code></p>
</div>
<h2>Review Units</h2>
<ol>{unit_links}</ol>
"""
    (out_dir / "review-index.template.html").write_text(
        html_page("Review Bundle", index_body),
        encoding="utf-8",
    )

    units_dir = out_dir / "units"
    units_dir.mkdir(exist_ok=True)
    for unit in manifest["review_units"]:
        body = f"""
<h1>{html.escape(unit["unit_id"])}</h1>
<div class="meta">
  <p>candidate_fingerprint: <code>{manifest["candidate_fingerprint"]}</code></p>
  <p>unit_id: <code>{html.escape(unit["unit_id"])}</code></p>
  <p>viewport/state: <code>{html.escape(unit["viewport_id"])} / {html.escape(unit["page_state_label"])}</code></p>
  <p>canonical_render_sha256: <code>{unit["canonical_render"]["sha256"]}</code></p>
  <p>intended_proof: {html.escape(unit["intended_proof"])}</p>
</div>
<div class="grid">
  <section>
    <h2>Actual Live Candidate</h2>
    <iframe src="{html.escape(unit["live_surface_url"])}" title="live candidate {html.escape(unit["unit_id"])}"></iframe>
  </section>
  <section>
    <h2>Canonical Render</h2>
    <img src="__ACCESS_BASE__/artifacts/{quote(unit["canonical_render"]["path"])}" alt="canonical render for {html.escape(unit["unit_id"])}">
  </section>
</div>
"""
        (units_dir / f"{unit['unit_id']}.template.html").write_text(
            html_page(unit["unit_id"], body),
            encoding="utf-8",
        )


def build_manifest(source_manifest: Path, out_dir: Path, base_url: str, blind: bool) -> dict[str, Any]:
    corpus = read_json(source_manifest)
    if corpus.get("schema") != "grahama.responsive_section_corpus.v1":
        raise SystemExit("source corpus schema must be grahama.responsive_section_corpus.v1")
    if (corpus.get("counts") or {}).get("failures") != 0:
        raise SystemExit("source corpus has capture failures")
    units = []
    for record in corpus.get("screenshots") or []:
        if record.get("status") != "PASS":
            continue
        unit_id = safe_unit_id(record)
        canonical = copy_artifact(str(record.get("path")), out_dir, unit_id)
        if canonical["sha256"] != record.get("sha256"):
            raise SystemExit(f"copied artifact digest mismatch for {unit_id}")
        page_state = record.get("page_state") or {}
        section = page_state.get("section") or {}
        units.append(
            {
                "unit_id": unit_id,
                "section_id": str(record.get("id") or ""),
                "route": str(record.get("route") or ""),
                "selector": str(section.get("selector") or f"#{record.get('id')}"),
                "viewport_id": str(record.get("viewport_id") or ""),
                "viewport": record.get("viewport") or {},
                "segment_index": int(record.get("segment_index") or 0),
                "segment_count": int(record.get("segment_count") or 1),
                "page_state_label": "default",
                "dimensions": record.get("dimensions") or {},
                "canonical_render": canonical,
                "live_surface_url": unit_live_url(base_url, record),
                "intended_proof": str(record.get("intended_proof") or "section review crop"),
                "does_not_prove": [
                    "provider usability",
                    "blind-rater threshold",
                    "whole-site screenshot review",
                ],
            }
        )
    if not units:
        raise SystemExit("source corpus contains no reviewable units")
    state = source_state()
    fingerprint_input = {
        "schema_version": "monitor_website.review_site.v1",
        "source_state": state,
        "source_corpus_sha256": sha256_file(source_manifest),
        "base_url": base_url,
        "review_units": [
            {
                key: unit[key]
                for key in (
                    "unit_id",
                    "section_id",
                    "route",
                    "selector",
                    "viewport_id",
                    "segment_index",
                    "segment_count",
                    "dimensions",
                    "canonical_render",
                    "intended_proof",
                )
            }
            for unit in units
        ],
    }
    candidate_fingerprint = sha256_bytes(stable_json(fingerprint_input))
    manifest = {
        "schema": "monitor_website.review_site.v1",
        "created_at": utc_now(),
        "mocked": False,
        "live": False,
        "base_url": base_url,
        "source_state": state,
        "source_corpus": {
            "path": rel(source_manifest),
            "sha256": sha256_file(source_manifest),
            "counts": corpus.get("counts") or {},
        },
        "candidate_fingerprint": candidate_fingerprint,
        "candidate_fingerprint_usage": "integrity_only",
        "access_nonce_policy": "runtime_only_redacted_from_durable_manifest",
        "blind_mode": {
            "enabled": blind,
            "leakage_scan_status": "NOT_TESTED" if not blind else "PASS",
        },
        "review_units": units,
        "counts": {
            "review_units": len(units),
            "viewports": len({unit["viewport_id"] for unit in units}),
            "sections": len({unit["section_id"] for unit in units}),
        },
        "fingerprint_input_sha256": sha256_bytes(stable_json(fingerprint_input)),
        "does_not_prove": [
            "external reviewer saw the URL",
            "formal G11 threshold",
            "access control for private, regulated, or ITAR material",
        ],
    }
    return manifest


def prepare(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source_manifest = Path(args.corpus_manifest).resolve() if args.corpus_manifest else latest_corpus_manifest()
    if not source_manifest:
        raise SystemExit("no responsive section-corpus manifest found; run capture_responsive_section_corpus.py first")
    manifest = build_manifest(source_manifest, out_dir, args.url, args.blind)
    write_templates(out_dir, manifest)
    files = [
        MANIFEST_NAME,
        "review-index.template.html",
        *[f"units/{unit['unit_id']}.template.html" for unit in manifest["review_units"]],
        *[unit["canonical_render"]["path"] for unit in manifest["review_units"]],
    ]
    manifest["bundle_files"] = sorted(files)
    write_json(out_dir / MANIFEST_NAME, manifest)
    print(json.dumps({"status": "PASS", "run_dir": str(out_dir), "candidate_fingerprint": manifest["candidate_fingerprint"], "counts": manifest["counts"]}, indent=2))
    return 0


def verify_manifest(run_dir: Path) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    manifest_path = run_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return None, [f"missing {MANIFEST_NAME}"]
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        return None, [f"invalid manifest JSON: {exc}"]
    if manifest.get("schema") != "monitor_website.review_site.v1":
        errors.append("manifest schema must be monitor_website.review_site.v1")
    if manifest.get("candidate_fingerprint_usage") != "integrity_only":
        errors.append("candidate_fingerprint_usage must be integrity_only")
    if not isinstance(manifest.get("review_units"), list) or not manifest.get("review_units"):
        errors.append("review_units must be non-empty")
    unit_ids = []
    for unit in manifest.get("review_units") or []:
        if not isinstance(unit, dict):
            errors.append("review unit must be an object")
            continue
        unit_id = str(unit.get("unit_id") or "")
        unit_ids.append(unit_id)
        if ".." in Path(unit_id).parts or "/" in unit_id:
            errors.append(f"unsafe unit id: {unit_id}")
        template = run_dir / "units" / f"{unit_id}.template.html"
        if not template.is_file():
            errors.append(f"missing unit template: {unit_id}")
        canonical = unit.get("canonical_render") if isinstance(unit.get("canonical_render"), dict) else {}
        path_value = str(canonical.get("path") or "")
        if not path_value:
            errors.append(f"{unit_id}: canonical render path missing")
            continue
        path = (run_dir / path_value).resolve()
        if run_dir.resolve() not in path.parents and path != run_dir.resolve():
            errors.append(f"{unit_id}: path traversal in canonical render")
            continue
        if not path.is_file():
            errors.append(f"{unit_id}: canonical render missing")
        elif sha256_file(path) != canonical.get("sha256"):
            errors.append(f"{unit_id}: canonical render sha256 mismatch")
    if len(set(unit_ids)) != len(unit_ids):
        errors.append("unit ids must be unique")
    if not (run_dir / "review-index.template.html").is_file():
        errors.append("missing review-index.template.html")
    allowed = set(manifest.get("bundle_files") or [])
    allowed.update({MANIFEST_NAME, SERVER_STATE_NAME})
    actual = {
        rel(path, run_dir)
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != SERVER_STATE_NAME
    }
    unexpected = sorted(actual - allowed)
    if unexpected:
        errors.append(f"unexpected bundle files: {unexpected[:10]}")
    return manifest, errors


def verify(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest, errors = verify_manifest(run_dir)
    result = {
        "status": "PASS" if not errors else "FAIL",
        "run_dir": str(run_dir),
        "candidate_fingerprint": manifest.get("candidate_fingerprint") if manifest else None,
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "MonitorWebsiteReview/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    @property
    def review_server(self) -> "ReviewServer":
        return self.server  # type: ignore[return-value]

    def send_text(self, status: HTTPStatus, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        data = text.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        srv = self.review_server
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 3 or parts[0] != "__review":
            self.send_text(HTTPStatus.NOT_FOUND, "not found")
            return
        nonce, fingerprint = parts[1], parts[2]
        if nonce != srv.access_nonce or fingerprint != srv.manifest["candidate_fingerprint"]:
            self.send_text(HTTPStatus.NOT_FOUND, "invalid review token")
            return
        if len(parts) == 4 and parts[3] == "index":
            template = (srv.run_dir / "review-index.template.html").read_text(encoding="utf-8")
            self.send_text(HTTPStatus.OK, template.replace("__ACCESS_BASE__", srv.access_base), "text/html; charset=utf-8")
            return
        if len(parts) == 4:
            unit_id = parts[3]
            if unit_id not in srv.unit_ids:
                self.send_text(HTTPStatus.NOT_FOUND, "unknown unit")
                return
            template_path = srv.run_dir / "units" / f"{unit_id}.template.html"
            self.send_text(
                HTTPStatus.OK,
                template_path.read_text(encoding="utf-8").replace("__ACCESS_BASE__", srv.access_base),
                "text/html; charset=utf-8",
            )
            return
        if len(parts) >= 5 and parts[3] == "artifacts":
            rel_path = "/".join(parts[4:])
            candidate = (srv.run_dir / rel_path).resolve()
            if srv.run_dir.resolve() not in candidate.parents or not candidate.is_file():
                self.send_text(HTTPStatus.NOT_FOUND, "artifact not found")
                return
            data = candidate.read_bytes()
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", "image/png" if candidate.suffix == ".png" else "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_text(HTTPStatus.NOT_FOUND, "not found")


class ReviewServer(ThreadingHTTPServer):
    def __init__(self, addr: tuple[str, int], handler, run_dir: Path, access_nonce: str):
        super().__init__(addr, handler)
        self.run_dir = run_dir
        self.manifest = read_json(run_dir / MANIFEST_NAME)
        self.access_nonce = access_nonce
        self.access_base = f"/__review/{access_nonce}/{self.manifest['candidate_fingerprint']}"
        self.unit_ids = {unit["unit_id"] for unit in self.manifest["review_units"]}


def serve_foreground(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest, errors = verify_manifest(run_dir)
    if errors or not manifest:
        raise SystemExit("cannot serve invalid review bundle: " + "; ".join(errors))
    server = ReviewServer((args.bind, args.port), ReviewHandler, run_dir, args.access_nonce)
    server.serve_forever()
    return 0


def serve(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest, errors = verify_manifest(run_dir)
    if errors or not manifest:
        raise SystemExit("cannot serve invalid review bundle: " + "; ".join(errors))
    state_path = run_dir / SERVER_STATE_NAME
    if state_path.is_file():
        old = read_json(state_path)
        pid = int(old.get("pid") or 0)
        if pid and Path(f"/proc/{pid}").exists():
            raise SystemExit(f"review server already running with pid {pid}")
    access_nonce = secrets.token_urlsafe(24)
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_serve-foreground",
        "--run-dir",
        str(run_dir),
        "--bind",
        args.bind,
        "--port",
        str(args.port),
        "--access-nonce",
        access_nonce,
    ]
    proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(0.4)
    if proc.poll() is not None:
        raise SystemExit("review server failed to start")
    base = f"http://{args.bind}:{args.port}/__review/{access_nonce}/{manifest['candidate_fingerprint']}"
    state = {
        "schema": "monitor_website.review_site.server.v1",
        "pid": proc.pid,
        "bind": args.bind,
        "port": args.port,
        "candidate_fingerprint": manifest["candidate_fingerprint"],
        "access_nonce_sha256": sha256_bytes(access_nonce.encode("utf-8")),
        "review_index_url": f"{base}/index/",
        "review_index_url_redacted": f"http://{args.bind}:{args.port}/__review/<redacted>/{manifest['candidate_fingerprint']}/index/",
        "started_at": utc_now(),
    }
    write_json(state_path, state)
    public = dict(state)
    public["access_nonce"] = access_nonce
    print(json.dumps({"status": "PASS", **public}, indent=2, sort_keys=True))
    return 0


def stop(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    state_path = run_dir / SERVER_STATE_NAME
    if not state_path.is_file():
        print(json.dumps({"status": "PASS", "stopped": False, "reason": "server state missing"}, indent=2))
        return 0
    state = read_json(state_path)
    pid = int(state.get("pid") or 0)
    stopped = False
    if pid and Path(f"/proc/{pid}").exists():
        os.killpg(pid, signal.SIGTERM)
        stopped = True
        for _ in range(20):
            if not Path(f"/proc/{pid}").exists():
                break
            time.sleep(0.1)
    state["stopped_at"] = utc_now()
    state["stopped"] = stopped
    write_json(state_path, state)
    print(json.dumps({"status": "PASS", "pid": pid, "stopped": stopped, "server_state": str(state_path)}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--url", required=True)
    p_prepare.add_argument("--out", required=True)
    p_prepare.add_argument("--corpus-manifest")
    p_prepare.add_argument("--blind", action="store_true")
    p_prepare.add_argument("--json", action="store_true")
    p_prepare.set_defaults(func=prepare)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--run-dir", required=True)
    p_verify.add_argument("--json", action="store_true")
    p_verify.set_defaults(func=verify)

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--run-dir", required=True)
    p_serve.add_argument("--bind", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, required=True)
    p_serve.add_argument("--json", action="store_true")
    p_serve.set_defaults(func=serve)

    p_stop = sub.add_parser("stop")
    p_stop.add_argument("--run-dir", required=True)
    p_stop.add_argument("--json", action="store_true")
    p_stop.set_defaults(func=stop)

    p_fg = sub.add_parser("_serve-foreground")
    p_fg.add_argument("--run-dir", required=True)
    p_fg.add_argument("--bind", required=True)
    p_fg.add_argument("--port", type=int, required=True)
    p_fg.add_argument("--access-nonce", required=True)
    p_fg.set_defaults(func=serve_foreground)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
