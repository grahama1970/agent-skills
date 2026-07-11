#!/usr/bin/env python3
"""Run or plan a bounded Tailscale Funnel publication/probe/teardown canary.

The command is fail-closed. It performs no public side effect unless both
--execute and --allow-publication are supplied. It never calls a video provider.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _run(cmd: list[str], *, timeout: int = 30) -> dict[str, Any]:
    started = _now_iso()
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "command": cmd,
            "started_at": started,
            "completed_at": _now_iso(),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:  # noqa: BLE001 - receipt must capture command failure.
        return {
            "command": cmd,
            "started_at": started,
            "completed_at": _now_iso(),
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }


def _start_supervised_process(cmd: list[str]) -> tuple[subprocess.Popen[str] | None, dict[str, Any]]:
    started = _now_iso()
    try:
        proc = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as exc:  # noqa: BLE001 - receipt must capture process failure.
        return None, {
            "command": cmd,
            "started_at": started,
            "returncode": None,
            "pid": None,
            "stdout": "",
            "stderr": str(exc),
            "foreground_supervised": True,
            "running_after_start": False,
        }
    time.sleep(3)
    returncode = proc.poll()
    stdout = ""
    stderr = ""
    if returncode is not None:
        try:
            stdout, stderr = proc.communicate(timeout=1)
        except Exception as exc:  # noqa: BLE001
            stderr = str(exc)
    return proc, {
        "command": cmd,
        "started_at": started,
        "returncode": returncode,
        "pid": proc.pid,
        "stdout": stdout,
        "stderr": stderr,
        "foreground_supervised": True,
        "running_after_start": returncode is None,
    }


def _stop_supervised_process(proc: subprocess.Popen[str] | None) -> dict[str, Any] | None:
    if proc is None:
        return None
    if proc.poll() is not None:
        return {
            "pid": proc.pid,
            "already_exited": True,
            "returncode": proc.returncode,
            "stopped_at": _now_iso(),
        }
    proc.terminate()
    try:
        stdout, stderr = proc.communicate(timeout=5)
        return {
            "pid": proc.pid,
            "already_exited": False,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stopped_at": _now_iso(),
        }
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
        return {
            "pid": proc.pid,
            "already_exited": False,
            "killed": True,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stopped_at": _now_iso(),
        }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def _start_server(directory: Path, port: int) -> tuple[socketserver.TCPServer, threading.Thread]:
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(directory), **kwargs)
    server = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _tailscale_funnel_url(status_json: dict[str, Any], filename: str, https_port: int) -> str | None:
    web = status_json.get("Web")
    if isinstance(web, dict):
        for host_port, config in web.items():
            if not isinstance(host_port, str):
                continue
            if not host_port.endswith(f":{https_port}"):
                continue
            host = host_port.rsplit(":", 1)[0]
            handlers = config.get("Handlers") if isinstance(config, dict) else None
            if not isinstance(handlers, dict):
                continue
            if "/" not in handlers:
                continue
            port_suffix = "" if https_port == 443 else f":{https_port}"
            return f"https://{host}{port_suffix}/{filename}"
    text = json.dumps(status_json)
    marker = ".ts.net"
    index = text.find(marker)
    if index == -1:
        return None
    start = text.rfind('"', 0, index)
    if start == -1:
        start = text.rfind(" ", 0, index)
    host = text[start + 1 : index + len(marker)]
    host = host.strip(":/,{}[]\"'")
    if not host:
        return None
    port_suffix = "" if https_port == 443 else f":{https_port}"
    return f"https://{host}{port_suffix}/{filename}"


def _probe(url: str, expected_sha256: str, timeout: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "requested_url": url,
        "expected_sha256": expected_sha256,
        "status": "BLOCKED_PROVIDER_MEDIA_PUBLIC_FETCH",
        "http_status": None,
        "content_type": None,
        "downloaded_byte_count": 0,
        "downloaded_sha256": None,
        "public_fetch_proven": False,
        "provider_fetch_proven": False,
        "blockers": [],
    }
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "persona-dream-funnel-canary/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            result["http_status"] = response.status
            result["content_type"] = response.headers.get("Content-Type")
            result["downloaded_byte_count"] = len(body)
            result["downloaded_sha256"] = _sha256_bytes(body)
    except Exception as exc:  # noqa: BLE001
        result["blockers"].append(f"fetch_failed:{exc}")
        return result
    if result["http_status"] != 200:
        result["blockers"].append(f"http_status_not_200:{result['http_status']}")
    if result["downloaded_sha256"] != expected_sha256:
        result["blockers"].append("sha256_mismatch")
    if not result["blockers"]:
        result["status"] = "PASS_PROVIDER_MEDIA_PUBLIC_FETCH"
        result["public_fetch_proven"] = True
    return result


def _probe_until(url: str, expected_sha256: str, *, per_attempt_timeout: int, deadline_seconds: int) -> dict[str, Any]:
    started = time.time()
    attempts: list[dict[str, Any]] = []
    attempt_index = 0
    while True:
        attempt_index += 1
        probe = _probe(url, expected_sha256, per_attempt_timeout)
        probe["attempt"] = attempt_index
        attempts.append(dict(probe))
        if probe.get("public_fetch_proven") is True:
            probe["attempts"] = list(attempts)
            probe["probe_deadline_seconds"] = deadline_seconds
            return probe
        if time.time() - started >= deadline_seconds:
            probe["attempts"] = list(attempts)
            probe["probe_deadline_seconds"] = deadline_seconds
            probe.setdefault("blockers", []).append("probe_deadline_exceeded")
            return probe
        time.sleep(5)


def build_plan(args: argparse.Namespace, asset_sha256: str, asset_bytes: int) -> dict[str, Any]:
    return {
        "schema": "persona_dream.provider_media_publication_plan.v1",
        "created_at": _now_iso(),
        "status": "DRY_RUN_PROVIDER_MEDIA_PUBLICATION_PLAN",
        "publication_backend": "tailscale_funnel",
        "asset": {
            "local_path": str(args.asset.resolve()),
            "sha256": asset_sha256,
            "bytes": asset_bytes,
            "asset_id": args.asset_id,
            "asset_role": args.asset_role,
        },
        "planned_side_effects": [
            "start loopback static HTTP server",
            "start tailscale funnel",
            "probe exact public URL",
            "turn tailscale funnel off",
            "stop loopback static HTTP server",
            "negative-probe public URL",
        ],
        "required_flags_for_live_side_effect": ["--execute", "--allow-publication"],
        "provider_live": False,
        "actual_provider_call_attempts": 0,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "live": False,
        "claims": {
            "proves": ["dry-run plan for a bounded Tailscale Funnel publication canary"],
            "does_not_prove": ["public URL creation", "public fetch", "provider fetch", "provider submit"],
        },
    }


def run_canary(args: argparse.Namespace) -> dict[str, Any]:
    asset = args.asset.resolve()
    asset_sha256 = _sha256_file(asset)
    asset_bytes = asset.stat().st_size
    if not args.execute or not args.allow_publication:
        return build_plan(args, asset_sha256, asset_bytes)
    if shutil.which("tailscale") is None:
        receipt = build_plan(args, asset_sha256, asset_bytes)
        receipt["status"] = "BLOCKED_FUNNEL_PREFLIGHT"
        receipt["blockers"] = ["tailscale_cli_not_found"]
        return receipt

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    publication_receipt_path = output_root / "provider_media_publication_receipt.json"
    probe_receipt_path = output_root / "provider_media_probe_receipt.json"
    teardown_receipt_path = output_root / "provider_media_teardown_receipt.json"
    filename = asset.name
    start_time = time.time()
    tmpdir = Path(tempfile.mkdtemp(prefix="persona-dream-funnel-"))
    staged_asset = tmpdir / filename
    shutil.copy2(asset, staged_asset)
    port = _free_port()
    server = None
    funnel_proc: subprocess.Popen[str] | None = None
    funnel_started = False
    public_url = None
    status_before = _run(["tailscale", "funnel", "status", "--json"], timeout=20)
    try:
        server, _thread = _start_server(tmpdir, port)
        funnel_cmd = ["tailscale", "funnel", f"--https={args.https_port}", f"http://127.0.0.1:{port}"]
        funnel_proc, funnel_start = _start_supervised_process(funnel_cmd)
        funnel_started = bool(funnel_start.get("running_after_start")) or funnel_start.get("returncode") == 0
        status_after_start = _run(["tailscale", "funnel", "status", "--json"], timeout=20)
        try:
            status_doc = json.loads(status_after_start.get("stdout") or "{}")
        except json.JSONDecodeError:
            status_doc = {}
        public_url = _tailscale_funnel_url(status_doc, filename, args.https_port)
        publication_receipt = {
            "schema": "persona_dream.provider_media_publication_receipt.v1",
            "created_at": _now_iso(),
            "status": "PASS_PROVIDER_MEDIA_PUBLISHED" if funnel_started and public_url else "BLOCKED_FUNNEL_PREFLIGHT",
            "publication_backend": "tailscale_funnel",
            "asset": {
                "local_path": str(asset),
                "staged_path": str(staged_asset),
                "sha256": asset_sha256,
                "bytes": asset_bytes,
                "asset_id": args.asset_id,
                "asset_role": args.asset_role,
            },
            "local_origin": f"http://127.0.0.1:{port}",
            "public_url": public_url,
            "tailscale": {
                "status_before": status_before,
                "funnel_start": funnel_start,
                "status_after_start": status_after_start,
            },
            "maximum_exposure_seconds": args.max_exposure_seconds,
            "provider_live": False,
            "actual_provider_call_attempts": 0,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "mocked": False,
            "live": True,
        }
        publication_receipt_path.write_text(json.dumps(publication_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        probe = _probe_until(
            public_url,
            asset_sha256,
            per_attempt_timeout=args.probe_timeout,
            deadline_seconds=args.probe_deadline_seconds,
        ) if public_url else {
            "status": "BLOCKED_PROVIDER_MEDIA_PUBLIC_FETCH",
            "blockers": ["public_url_not_discovered"],
            "public_fetch_proven": False,
            "provider_fetch_proven": False,
        }
        probe.update({
            "schema": "persona_dream.provider_media_probe_receipt.v1",
            "created_at": _now_iso(),
            "publication_receipt": str(publication_receipt_path),
            "mocked": False,
            "live": True,
            "actual_provider_call_attempts": 0,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
        })
        probe_receipt_path.write_text(json.dumps(probe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        teardown_started = _now_iso()
        off_result = _run(["tailscale", "funnel", f"--https={args.https_port}", f"http://127.0.0.1:{port}", "off"], timeout=30) if funnel_started else None
        supervised_stop = _stop_supervised_process(funnel_proc)
        if server is not None:
            server.shutdown()
            server.server_close()
        negative_probe = None
        if public_url:
            time.sleep(1)
            negative_probe = _probe(public_url, asset_sha256, min(args.probe_timeout, 10))
        status_after_teardown = _run(["tailscale", "funnel", "status", "--json"], timeout=20) if shutil.which("tailscale") else None
        exposure_duration = time.time() - start_time
        teardown_receipt = {
            "schema": "persona_dream.provider_media_teardown_receipt.v1",
            "created_at": _now_iso(),
            "status": "PASS_PROVIDER_MEDIA_TEARDOWN",
            "teardown_started_at": teardown_started,
            "publication_receipt": str(publication_receipt_path),
            "probe_receipt": str(probe_receipt_path),
            "public_url": public_url,
            "targeted_off_command": off_result,
            "supervised_process_stop": supervised_stop,
            "local_origin_stopped": True,
            "negative_public_probe": negative_probe,
            "tailscale_status_after_teardown": status_after_teardown,
            "exposure_duration_seconds": round(exposure_duration, 3),
            "maximum_exposure_seconds": args.max_exposure_seconds,
            "deadline_respected": exposure_duration <= args.max_exposure_seconds,
            "provider_live": False,
            "actual_provider_call_attempts": 0,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "mocked": False,
            "live": True,
            "claims": {
                "proves": ["Tailscale Funnel route was targeted for teardown"],
                "does_not_prove": ["provider fetch", "provider submit", "provider return"],
            },
        }
        if exposure_duration > args.max_exposure_seconds:
            teardown_receipt["status"] = "BLOCKED_PUBLICATION_TTL_EXCEEDED"
        if negative_probe and negative_probe.get("public_fetch_proven") is True:
            teardown_receipt["status"] = "BLOCKED_PROVIDER_MEDIA_STILL_PUBLIC"
        teardown_receipt_path.write_text(json.dumps(teardown_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.rmtree(tmpdir, ignore_errors=True)

    publication_status = "MISSING_PUBLICATION_RECEIPT"
    probe_status = "MISSING_PROBE_RECEIPT"
    teardown_status = "MISSING_TEARDOWN_RECEIPT"
    try:
        publication_status = json.loads(publication_receipt_path.read_text(encoding="utf-8")).get("status")
    except Exception:
        pass
    try:
        probe_status = json.loads(probe_receipt_path.read_text(encoding="utf-8")).get("status")
    except Exception:
        pass
    try:
        teardown_status = json.loads(teardown_receipt_path.read_text(encoding="utf-8")).get("status")
    except Exception:
        pass
    blockers = []
    if publication_status != "PASS_PROVIDER_MEDIA_PUBLISHED":
        blockers.append(f"publication_status:{publication_status}")
    if probe_status != "PASS_PROVIDER_MEDIA_PUBLIC_FETCH":
        blockers.append(f"probe_status:{probe_status}")
    if teardown_status != "PASS_PROVIDER_MEDIA_TEARDOWN":
        blockers.append(f"teardown_status:{teardown_status}")
    summary_status = "PASS_PROVIDER_MEDIA_PUBLICATION_CANARY" if not blockers else "BLOCKED_PROVIDER_MEDIA_PUBLICATION_CANARY"
    return {
        "schema": "persona_dream.tailscale_funnel_publication_canary_receipt.v1",
        "created_at": _now_iso(),
        "status": summary_status,
        "output_root": str(output_root),
        "publication_receipt": str(publication_receipt_path),
        "publication_status": publication_status,
        "probe_receipt": str(probe_receipt_path),
        "probe_status": probe_status,
        "teardown_receipt": str(teardown_receipt_path),
        "teardown_status": teardown_status,
        "public_url": public_url,
        "blockers": blockers,
        "provider_live": False,
        "actual_provider_call_attempts": 0,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "live": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--asset-id", default="phase11_publication_canary_asset")
    parser.add_argument("--asset-role", default="provider_input_probe")
    parser.add_argument("--https-port", type=int, default=443, choices=[443, 8443, 10000])
    parser.add_argument("--max-exposure-seconds", type=int, default=900)
    parser.add_argument("--probe-timeout", type=int, default=30)
    parser.add_argument("--probe-deadline-seconds", type=int, default=120)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-publication", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    receipt = run_canary(args)
    summary_path = args.output_root / "tailscale_funnel_publication_canary_receipt.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if str(receipt["status"]).startswith(("PASS_", "DRY_RUN_")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
