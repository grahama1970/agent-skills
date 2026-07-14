#!/usr/bin/env python3
"""Render and serve local artifacts through a bounded mobile reader."""

from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import bleach
import typer
from loguru import logger
from markdown_it import MarkdownIt

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
SKILL_DIR = Path(__file__).resolve().parent.parent
OPS_WORKSTATION = SKILL_DIR.parent / "ops-workstation" / "run.sh"
DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/artifact-reader/outputs")
MANIFEST_NAME = "artifact-reader-manifest.json"
SERVER_RECEIPT_NAME = "artifact-reader-server-receipt.json"
STOP_RECEIPT_NAME = "artifact-reader-stop-receipt.json"
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".text", ".html", ".htm"}


def _now() -> str:
    """Return an RFC3339-like UTC timestamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256(path: Path) -> str:
    """Hash a regular file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_source(path: Path) -> Path:
    """Resolve and validate a supported source artifact."""
    if path.is_symlink():
        raise typer.BadParameter("source_symlink_not_allowed")
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise typer.BadParameter(f"source_not_found:{resolved}")
    if not resolved.is_file():
        raise typer.BadParameter(f"source_not_regular_file:{resolved}")
    if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise typer.BadParameter(f"unsupported_source_type:{resolved.suffix.lower()}")
    return resolved


def _default_output(source: Path) -> Path:
    """Build a timestamped storage-policy-compliant output path."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe_stem = "".join(char if char.isalnum() or char in "-_" else "-" for char in source.stem)
    return DEFAULT_OUTPUT_ROOT / f"{safe_stem or 'artifact'}-{stamp}"


def _render_body(source: Path, raw_text: str) -> str:
    """Render supported source text to safe HTML."""
    suffix = source.suffix.lower()
    if suffix in {".md", ".markdown"}:
        rendered = MarkdownIt("commonmark", {"html": False, "linkify": False}).render(raw_text)
        return bleach.clean(
            rendered,
            tags={
                "a", "blockquote", "br", "code", "em", "h1", "h2", "h3", "h4",
                "h5", "h6", "hr", "li", "ol", "p", "pre", "strong", "table",
                "tbody", "td", "th", "thead", "tr", "ul",
            },
            attributes={"a": ["href", "title"]},
            protocols={"http", "https", "mailto"},
        )
    if suffix in {".html", ".htm"}:
        return bleach.clean(
            raw_text,
            tags=set(bleach.sanitizer.ALLOWED_TAGS)
            | {"article", "aside", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "p", "pre", "section", "table", "tbody", "td", "th", "thead", "tr"},
            attributes={"a": ["href", "title"], "abbr": ["title"]},
            protocols={"http", "https", "mailto"},
        )
    return f"<pre class=\"plain-text\">{html.escape(raw_text)}</pre>"


def _assert_bounded_tree(root: Path) -> None:
    """Reject symlinks before exposing a directory over HTTP."""
    if root.is_symlink() or not root.is_dir():
        raise typer.BadParameter("serve_root_must_be_a_real_directory")
    for entry in root.rglob("*"):
        if entry.is_symlink():
            raise typer.BadParameter(f"serve_root_contains_symlink:{entry.relative_to(root)}")


def _ops_network() -> dict[str, Any]:
    """Collect authoritative local network context from ops-workstation."""
    if not OPS_WORKSTATION.is_file():
        raise RuntimeError(f"ops_workstation_missing:{OPS_WORKSTATION}")
    completed = subprocess.run(
        [str(OPS_WORKSTATION), "net", "--json"],
        cwd=OPS_WORKSTATION.parent,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"ops_workstation_net_failed:{completed.stderr.strip()}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ops_workstation_net_invalid_json") from exc


def _select_lan(network: dict[str, Any]) -> tuple[str, str]:
    """Select the IPv4 address on the default-route interface."""
    routes = network.get("routes", [])
    default_route = next((route for route in routes if str(route).startswith("default ")), "")
    route_parts = str(default_route).split()
    interface_name = route_parts[route_parts.index("dev") + 1] if "dev" in route_parts else ""
    for interface in network.get("interfaces", []):
        ipv4 = str(interface.get("ipv4", "none")).split("/", 1)[0]
        if interface.get("name") == interface_name and ipv4 != "none":
            return interface_name, ipv4
    raise RuntimeError("ops_workstation_no_default_route_ipv4")


class BoundedRequestHandler(SimpleHTTPRequestHandler):
    """Static handler without directory listing or noisy request logs."""

    def list_directory(self, path: str) -> None:
        self.send_error(404, "Directory listing disabled")
        return None

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("http " + format, *args)


@app.command()
def render(
    source: Path = typer.Argument(..., help="Markdown, text, or HTML source file."),
    out: Path | None = typer.Option(None, "--out", help="Generated reader directory."),
    title: str | None = typer.Option(None, "--title", help="Reader title."),
) -> None:
    """Render one source artifact into a self-contained reader directory."""
    source_path = _safe_source(source)
    out_dir = (out or _default_output(source_path)).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=False)
    raw_text = source_path.read_text(encoding="utf-8")
    source_name = f"artifact{source_path.suffix.lower()}"
    copied_source = out_dir / source_name
    shutil.copyfile(source_path, copied_source)

    template = (SKILL_DIR / "assets" / "reader.html").read_text(encoding="utf-8")
    reader_title = title or source_path.stem.replace("-", " ").replace("_", " ").title()
    rendered = (
        template.replace("{{TITLE}}", html.escape(reader_title))
        .replace("{{SOURCE_NAME}}", html.escape(source_path.name))
        .replace("{{SOURCE_FILE_JSON}}", json.dumps(source_name))
        .replace("{{CONTENT}}", _render_body(source_path, raw_text))
    )
    (out_dir / "index.html").write_text(rendered, encoding="utf-8")
    manifest = {
        "schema": "artifact_reader.manifest.v1",
        "created_at": _now(),
        "source": {
            "path": str(source_path),
            "name": source_path.name,
            "sha256": _sha256(source_path),
            "bytes": source_path.stat().st_size,
            "media_type": mimetypes.guess_type(source_path.name)[0] or "text/plain",
        },
        "reader": {"path": "index.html", "copied_source": source_name, "title": reader_title},
        "controls": {"copy": True, "download": True},
        "proof_scope": {
            "proves": ["The source artifact was hash-bound and rendered into a bounded local reader."],
            "does_not_prove": ["The source content is correct.", "The reader has been served or viewed."],
        },
    }
    _write_json(out_dir / MANIFEST_NAME, manifest)
    typer.echo(json.dumps({"ok": True, "output_dir": str(out_dir), "manifest": str(out_dir / MANIFEST_NAME)}))


@app.command(hidden=True)
def serve(
    root: Path = typer.Argument(...),
    lan: bool = typer.Option(False, "--lan"),
    port: int = typer.Option(0, "--port", min=0, max=65535),
    receipt: Path | None = typer.Option(None, "--receipt"),
    instance_token: str = typer.Option(..., "--instance-token"),
) -> None:
    """Run the bounded HTTP server in the foreground."""
    root_path = root.expanduser().resolve()
    _assert_bounded_tree(root_path)
    manifest_path = root_path / MANIFEST_NAME
    if not manifest_path.is_file() or not (root_path / "index.html").is_file():
        raise typer.BadParameter("artifact_reader_manifest_or_index_missing")
    network = _ops_network()
    interface_name, lan_ip = _select_lan(network)
    bind_address = "0.0.0.0" if lan else "127.0.0.1"
    display_host = lan_ip if lan else "127.0.0.1"
    handler = partial(BoundedRequestHandler, directory=str(root_path))
    server = ThreadingHTTPServer((bind_address, port), handler)
    assigned_port = int(server.server_address[1])
    receipt_path = (receipt or root_path / SERVER_RECEIPT_NAME).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = {
        "schema": "artifact_reader.server_receipt.v1",
        "ok": True,
        "status": "PASS",
        "mocked": False,
        "live": True,
        "started_at": _now(),
        "pid": os.getpid(),
        "instance_token": instance_token,
        "root": str(root_path),
        "bind_address": bind_address,
        "port": assigned_port,
        "url": f"http://{display_host}:{assigned_port}/",
        "source_sha256": manifest["source"]["sha256"],
        "ops_workstation": {
            "command": f"{OPS_WORKSTATION} net --json",
            "default_route_interface": interface_name,
            "lan_ipv4": lan_ip,
            "gateway": network.get("gateway"),
        },
        "proof_scope": {
            "proves": ["A local HTTP server bound the recorded address and OS-selected port."],
            "does_not_prove": ["Internet reachability.", "Durable hosting.", "Future server availability.", "Source correctness."],
        },
    }
    _write_json(receipt_path, payload)
    typer.echo(json.dumps(payload), err=False)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


@app.command()
def start(
    root: Path = typer.Argument(..., help="Generated reader directory."),
    lan: bool = typer.Option(False, "--lan", help="Expose on the active LAN interface."),
    port: int = typer.Option(0, "--port", min=0, max=65535, help="Port; 0 asks the OS for an open port."),
) -> None:
    """Start a persistent reader server and wait for its live receipt."""
    root_path = root.expanduser().resolve()
    _assert_bounded_tree(root_path)
    receipt_path = root_path / SERVER_RECEIPT_NAME
    receipt_path.unlink(missing_ok=True)
    token = secrets.token_urlsafe(24)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "serve",
        str(root_path),
        "--port",
        str(port),
        "--receipt",
        str(receipt_path),
        "--instance-token",
        token,
    ]
    if lan:
        command.append("--lan")
    log_path = root_path / "artifact-reader-server.log"
    log_handle = log_path.open("ab")
    process = subprocess.Popen(
        command,
        cwd=root_path,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=log_handle,
        start_new_session=True,
    )
    log_handle.close()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if receipt_path.is_file():
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            if payload.get("instance_token") == token and payload.get("pid") == process.pid:
                typer.echo(json.dumps(payload))
                return
        if process.poll() is not None:
            details = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"artifact_reader_server_exited:{process.returncode}:{details}")
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("artifact_reader_server_readiness_timeout")


def _load_server_receipt(path: Path) -> dict[str, Any]:
    """Load and minimally validate a server receipt."""
    receipt_path = path.expanduser().resolve()
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "artifact_reader.server_receipt.v1":
        raise typer.BadParameter("invalid_server_receipt_schema")
    return payload


def _matching_process(payload: dict[str, Any]) -> bool:
    """Verify that the receipt still identifies the same server process."""
    pid = int(payload["pid"])
    proc = Path(f"/proc/{pid}")
    if not proc.exists():
        return False
    cmdline = (proc / "cmdline").read_bytes().decode("utf-8", errors="replace")
    return "artifact_reader.py" in cmdline and str(payload["instance_token"]) in cmdline


@app.command()
def status(receipt: Path = typer.Argument(..., help="Server receipt path.")) -> None:
    """Report whether the receipt-bound server process remains alive."""
    payload = _load_server_receipt(receipt)
    alive = _matching_process(payload)
    typer.echo(json.dumps({"ok": alive, "alive": alive, "pid": payload["pid"], "url": payload["url"]}))
    if not alive:
        raise typer.Exit(1)


@app.command()
def stop(receipt: Path = typer.Argument(..., help="Server receipt path.")) -> None:
    """Stop only the process identified by a valid server receipt."""
    payload = _load_server_receipt(receipt)
    if not _matching_process(payload):
        raise typer.BadParameter("receipt_process_not_running_or_pid_reused")
    pid = int(payload["pid"])
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and Path(f"/proc/{pid}").exists():
        time.sleep(0.1)
    alive = Path(f"/proc/{pid}").exists()
    stop_payload = {
        "schema": "artifact_reader.stop_receipt.v1",
        "ok": not alive,
        "status": "PASS" if not alive else "BLOCKED",
        "stopped_at": _now(),
        "pid": pid,
        "server_receipt": str(receipt.expanduser().resolve()),
    }
    stop_path = Path(payload["root"]) / STOP_RECEIPT_NAME
    _write_json(stop_path, stop_payload)
    typer.echo(json.dumps(stop_payload))
    if alive:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
