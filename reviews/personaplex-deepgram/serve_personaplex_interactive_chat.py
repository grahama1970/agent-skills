#!/usr/bin/env python3
"""Serve the PersonaPlex static ChatWell parity page with runtime env injection.

The page is intentionally standalone because the ux-lab production build is
pre-broken. The server serves the repository root so the existing URL remains:

    http://127.0.0.1:8771/reviews/personaplex-deepgram/personaplex-interactive-chat.html

It injects DEEPGRAM_API_KEY from the process environment into window.__ENV__ at
request time. No key is committed to the HTML file or this script.
"""
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

CHAT_PAGE_RELATIVE = Path("reviews/personaplex-deepgram/personaplex-interactive-chat.html")
ENV_PLACEHOLDER = "__PERSONAPLEX_ENV_JSON__"
ENV_KEYS = (
    "DEEPGRAM_API_KEY",
    "VITE_DEEPGRAM_API_KEY",
    "PERSONAPLEX_WS_URL",
    "GOLDEN_STATE_WS_URL",
    "PERSONAPLEX_PERSONA_ID",
    "PERSONA_ID",
    "PERSONAPLEX_SESSION_ID",
    "DEEPGRAM_WS_URL",
)
SHELL_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)\s*$")


def shell_unquote(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value[0] in {"'", '"'} and value[-1:] == value[0]:
        return value[1:-1]
    return value.split("#", 1)[0].strip()


def read_env_assignment_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return values
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = SHELL_ASSIGNMENT_RE.match(line)
            if not match:
                continue
            key = match.group("key")
            if key in ENV_KEYS and key not in values:
                values[key] = shell_unquote(match.group("value"))
    except OSError:
        return values
    return values


def load_runtime_env() -> dict[str, str]:
    """Resolve env values without requiring users to paste secrets in the UI.

    Process environment wins. Local shell/dotenv files are a convenience fallback
    for the documented dev setup where DEEPGRAM_API_KEY lives in ~/.zshrc but the
    static server may be started from a non-login shell.
    """
    merged: dict[str, str] = {}
    for candidate in (
        Path.cwd() / ".env",
        Path.cwd() / ".env.local",
        Path.home() / ".zshrc",
        Path.home() / ".bashrc",
        Path.home() / ".profile",
    ):
        merged.update(read_env_assignment_file(candidate))
    for key in ENV_KEYS:
        if os.environ.get(key):
            merged[key] = os.environ[key]

    deepgram = merged.get("DEEPGRAM_API_KEY") or merged.get("VITE_DEEPGRAM_API_KEY") or ""
    return {
        "DEEPGRAM_API_KEY": deepgram,
        "VITE_DEEPGRAM_API_KEY": deepgram,
        "PERSONAPLEX_WS_URL": merged.get("PERSONAPLEX_WS_URL") or merged.get("GOLDEN_STATE_WS_URL") or "ws://127.0.0.1:8788/ws",
        "GOLDEN_STATE_WS_URL": merged.get("GOLDEN_STATE_WS_URL") or merged.get("PERSONAPLEX_WS_URL") or "ws://127.0.0.1:8788/ws",
        "PERSONAPLEX_PERSONA_ID": merged.get("PERSONAPLEX_PERSONA_ID") or merged.get("PERSONA_ID") or "embry",
        "PERSONA_ID": merged.get("PERSONA_ID") or merged.get("PERSONAPLEX_PERSONA_ID") or "embry",
        "PERSONAPLEX_SESSION_ID": merged.get("PERSONAPLEX_SESSION_ID") or "",
        "DEEPGRAM_WS_URL": merged.get("DEEPGRAM_WS_URL") or "",
    }


def safe_js_env() -> str:
    payload = load_runtime_env()
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


class PersonaPlexHandler(SimpleHTTPRequestHandler):
    server_version = "PersonaPlexStatic/1.0"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urlparse(self.path)
        rel_path = Path(unquote(parsed.path.lstrip("/")))
        if rel_path == CHAT_PAGE_RELATIVE:
            self.serve_injected_chat_page()
            return
        super().do_GET()

    def serve_injected_chat_page(self) -> None:
        root = Path(self.directory).resolve()
        html_path = root / CHAT_PAGE_RELATIVE
        try:
            body = html_path.read_text(encoding="utf-8")
        except OSError as exc:
            self.send_error(HTTPStatus.NOT_FOUND, explain=f"Could not read chat page: {html.escape(str(exc))}")
            return
        env_json = safe_js_env()
        body = re.sub(
            r'(<script\s+id=["\']personaplex-env["\']\s+type=["\']application/json["\']>)(.*?)(</script>)',
            lambda match: f"{match.group(1)}{env_json}{match.group(3)}",
            body,
            count=1,
            flags=re.DOTALL,
        )
        body = body.replace(ENV_PLACEHOLDER, env_json)
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def guess_type(self, path: str) -> str:
        guessed = mimetypes.guess_type(path)[0]
        return guessed or super().guess_type(path)


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve PersonaPlex static chat with DEEPGRAM_API_KEY injection.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8771, help="Bind port. Default: 8771")
    parser.add_argument("--root", type=Path, default=default_repo_root(), help="Repository root to serve. Default: two levels above this script.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()
    page = root / CHAT_PAGE_RELATIVE
    if not page.exists():
        print(f"ERROR: expected chat page not found: {page}", file=sys.stderr)
        return 2

    handler = lambda *handler_args, **handler_kwargs: PersonaPlexHandler(  # noqa: E731
        *handler_args,
        directory=str(root),
        **handler_kwargs,
    )
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    env = load_runtime_env()
    key_status = "present" if env.get("DEEPGRAM_API_KEY") else "missing"
    print(f"Serving {root} at http://{args.host}:{args.port}/")
    print(f"Chat URL: http://{args.host}:{args.port}/{CHAT_PAGE_RELATIVE.as_posix()}")
    print(f"DEEPGRAM_API_KEY: {key_status}; PERSONAPLEX_WS_URL: {env['PERSONAPLEX_WS_URL']}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PersonaPlex static server")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
