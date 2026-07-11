#!/usr/bin/env python3
"""Validate local media URL/hash locking for a persona-dream run root.

This proves local media bytes, hashes, and HTTP serving mechanics. It does not
prove provider accessibility and never contacts Kling or any paid provider.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import socketserver
import sys
import threading
import urllib.request
from functools import partial
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/provider_media_lock_receipt.schema.json"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _serve_root(run_root: Path) -> tuple[socketserver.TCPServer, str]:
    handler = partial(_QuietHandler, directory=str(run_root))
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


def validate_local_media_lock(run_root: Path, *, serve: bool = False) -> dict[str, Any]:
    run_root = run_root.resolve()
    receipt_path = run_root / "receipts/provider_media_lock_receipt.json"
    schema = _read_json(SCHEMA_PATH)
    receipt = _read_json(receipt_path)
    jsonschema.Draft202012Validator(schema).validate(receipt)

    server: socketserver.TCPServer | None = None
    base_url: str | None = None
    try:
        if serve:
            server, base_url = _serve_root(run_root)

        media_results: list[dict[str, Any]] = []
        blockers: list[str] = []
        for item in receipt["media"]:
            local_path = run_root / item["local_path"]
            if not local_path.exists():
                blockers.append(f"missing_local_media:{item['local_path']}")
                media_results.append({"id": item["id"], "local_hash_ok": False, "http_hash_ok": False})
                continue

            expected = item["sha256"]
            local_hash = _sha256_file(local_path)
            local_hash_ok = local_hash == expected
            if not local_hash_ok:
                blockers.append(f"local_hash_mismatch:{item['id']}")

            http_hash_ok = None
            fetched_url = None
            if serve:
                fetched_url = f"{base_url}{item['url_path']}"
                with urllib.request.urlopen(fetched_url, timeout=10) as response:
                    fetched_hash = _sha256_bytes(response.read())
                http_hash_ok = fetched_hash == expected
                if not http_hash_ok:
                    blockers.append(f"http_hash_mismatch:{item['id']}")

            media_results.append(
                {
                    "id": item["id"],
                    "role": item["role"],
                    "local_path": item["local_path"],
                    "url_path": item["url_path"],
                    "served_url": fetched_url,
                    "local_hash_ok": local_hash_ok,
                    "http_hash_ok": http_hash_ok,
                }
            )

        status = "PASS_LOCAL_MEDIA_LOCK" if not blockers else "BLOCKED"
        return {
            "schema": "persona_dream.local_media_lock_validation.v1",
            "run_root": str(run_root),
            "status": status,
            "provider_accessible": False,
            "live_provider_call_made": False,
            "mocked": "yes" if "fixtures" in run_root.parts else "no",
            "live": "no",
            "receipt": str(receipt_path),
            "media": media_results,
            "blockers": blockers,
            "exercised": "local file hash and localhost HTTP byte hash" if serve else "local file hash",
            "unverified": "public provider accessibility, Kling fetch behavior, paid call submission",
        }
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--serve", action="store_true", help="Serve run root on localhost and fetch media over HTTP")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_local_media_lock(args.run_root, serve=args.serve)
    except Exception as exc:
        result = {
            "schema": "persona_dream.local_media_lock_validation.v1",
            "run_root": str(args.run_root),
            "status": "BLOCKED",
            "blockers": [str(exc)],
            "provider_accessible": False,
            "live_provider_call_made": False,
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["status"])
    return 0 if result["status"] == "PASS_LOCAL_MEDIA_LOCK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
