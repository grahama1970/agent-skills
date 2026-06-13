#!/usr/bin/env python3
"""Capture and package a local HTML page for WebGPT analysis via /surf.

This script:
- serves a local HTML file over http://127.0.0.1 when --html is provided;
- uses surf-cli to open the page in Chrome;
- captures desktop/mobile screenshots and text/state reports;
- copies the HTML plus local CSS/JS/image assets into source/;
- writes a manifest and README_FOR_CHATGPT.md;
- creates a single upload-ready zip.

It intentionally uses only the Python standard library.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import html.parser
import http.server
import json
import os
import pathlib
import posixpath
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from typing import Iterable

LOCAL_SCHEMES_TO_SKIP = (
    "http:",
    "https:",
    "data:",
    "mailto:",
    "tel:",
    "javascript:",
    "blob:",
    "chrome:",
    "about:",
    "#",
)

GENERIC_ASSET_ATTRS = {
    "poster",
    "data-src",
    "data-srcset",
    "data-href",
    "data-original",
    "data-bg",
    "data-background",
}
SRC_TAGS = {"img", "script", "source", "video", "audio", "track", "iframe", "embed", "object"}
LINK_REL_ASSET_HINTS = {"stylesheet", "preload", "modulepreload", "icon", "apple-touch-icon", "manifest", "mask-icon"}
META_ASSET_HINTS = {"image", "logo", "icon", "url", "src"}

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
CSS_IMPORT_RE = re.compile(r"@import\s+(?:url\()?\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class CaptureWarning:
    area: str
    message: str


@dataclass
class CaptureContext:
    workdir: pathlib.Path
    captures_dir: pathlib.Path
    reports_dir: pathlib.Path
    source_dir: pathlib.Path
    warnings: list[CaptureWarning] = field(default_factory=list)
    commands: list[dict] = field(default_factory=list)
    source_mode: str = "visual-only"

    def warn(self, area: str, message: str) -> None:
        self.warnings.append(CaptureWarning(area=area, message=message))
        print(f"[warning:{area}] {message}", file=sys.stderr)


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def die(message: str, exit_code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def parse_size(value: str, label: str) -> tuple[int, int]:
    match = re.match(r"^\s*(\d+)\s*[xX,]\s*(\d+)\s*$", value)
    if not match:
        die(f"--{label} must look like 1440x1000")
    width, height = int(match.group(1)), int(match.group(2))
    if width < 100 or height < 100:
        die(f"--{label} dimensions are too small")
    return width, height


def ensure_dir(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_output_path() -> pathlib.Path:
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return pathlib.Path(f"/tmp/html-bundler-{stamp}.zip")


def resolve_surf_bin(surf_bin: str) -> str:
    if os.path.sep in surf_bin or surf_bin.startswith("."):
        resolved = pathlib.Path(surf_bin).expanduser().resolve()
        if not resolved.exists():
            die(
                f"surf entrypoint not found: {resolved}. "
                "Run skills/surf/sanity.sh, then pass --surf-bin skills/surf/run.sh"
            )
        return str(resolved)
    found = shutil.which(surf_bin)
    if not found:
        die(
            f"'{surf_bin}' was not found on PATH. "
            "Use skills/surf/run.sh via --surf-bin instead of bare surf."
        )
    return found


@dataclass
class CaptureOptions:
    html: pathlib.Path | None = None
    url: str | None = None
    root: pathlib.Path | None = None
    out: pathlib.Path | None = None
    surf_bin: str = "surf"
    desktop: str = "1440x1000"
    mobile: str = "390x844"
    no_mobile: bool = False
    wait_ms: int = 1500
    keep_workdir: bool = False
    no_source: bool = False
    source_entry: pathlib.Path | None = None
    max_scroll_slices: int = 12
    no_fetch: bool = False
    fetcher_bin: str = ""
    fetch_backend: str = "auto"



def run_command(
    args: list[str],
    *,
    timeout: int = 60,
    check: bool = False,
    ctx: CaptureContext | None = None,
) -> CommandResult:
    try:
        proc = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        result = CommandResult(args=args, returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
    except subprocess.TimeoutExpired as exc:
        result = CommandResult(
            args=args,
            returncode=124,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr if isinstance(exc.stderr, str) else "") + f"\nTimed out after {timeout}s",
        )

    if ctx is not None:
        ctx.commands.append(sanitize_surf_command(args, result.returncode, result.stdout, result.stderr))

    if check and result.returncode != 0:
        cmd = " ".join(args)
        die(f"command failed ({result.returncode}): {cmd}\n{result.stderr.strip()}")
    return result


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def strip_url_noise(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    raw = raw.split("#", 1)[0].split("?", 1)[0].strip()
    return raw


def is_probably_local_url(raw: str) -> bool:
    lowered = raw.strip().lower()
    if not lowered:
        return False
    return not lowered.startswith(LOCAL_SCHEMES_TO_SKIP)


def parse_srcset(value: str) -> list[str]:
    urls: list[str] = []
    for part in value.split(","):
        token = part.strip().split()
        if token:
            urls.append(token[0])
    return urls


def css_urls(css_text: str) -> set[str]:
    found: set[str] = set()
    for match in CSS_URL_RE.finditer(css_text):
        value = match.group(2).strip()
        if value:
            found.add(value)
    for match in CSS_IMPORT_RE.finditer(css_text):
        value = match.group(2).strip()
        if value:
            found.add(value)
    return found


class LocalAssetParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: set[str] = set()
        self.inline_css_chunks: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "style":
            self._in_style = True

        tag_lower = tag.lower()
        rel_tokens = {token.strip().lower() for token in attrs_dict.get("rel", "").split()}
        meta_hint = " ".join(
            attrs_dict.get(k, "") for k in ("name", "property", "itemprop")
        ).lower()

        for name, value in attrs_dict.items():
            if not value:
                continue
            if name in {"srcset", "data-srcset"}:
                self.urls.update(parse_srcset(value))
            elif name == "style":
                self.urls.update(css_urls(value))
            elif name == "src" and tag_lower in SRC_TAGS:
                self.urls.add(value)
            elif name == "href" and tag_lower == "link" and (not rel_tokens or rel_tokens & LINK_REL_ASSET_HINTS):
                self.urls.add(value)
            elif name == "content" and tag_lower == "meta" and any(hint in meta_hint for hint in META_ASSET_HINTS):
                self.urls.add(value)
            elif name in GENERIC_ASSET_ATTRS:
                self.urls.add(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style and data.strip():
            self.inline_css_chunks.append(data)
            self.urls.update(css_urls(data))


def safe_relpath(path: pathlib.Path, root: pathlib.Path) -> pathlib.Path | None:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return rel


def resolve_asset(raw_url: str, *, base_file: pathlib.Path, root_dir: pathlib.Path) -> pathlib.Path | None:
    raw_url = strip_url_noise(raw_url)
    if not is_probably_local_url(raw_url):
        return None

    # Protocol-relative URLs are external.
    if raw_url.startswith("//"):
        return None

    decoded = urllib.parse.unquote(raw_url)
    if decoded.startswith("/"):
        candidate = root_dir / decoded.lstrip("/")
    else:
        candidate = base_file.parent / decoded

    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None

    if resolved.exists() and resolved.is_file():
        return resolved
    return None


def collect_local_files(html_path: pathlib.Path, root_dir: pathlib.Path, ctx: CaptureContext) -> tuple[set[pathlib.Path], dict[str, list[str]]]:
    """Collect HTML + reachable local assets. Best-effort, static analysis only."""
    to_scan: list[pathlib.Path] = [html_path.resolve()]
    seen: set[pathlib.Path] = set()
    files: set[pathlib.Path] = set()
    unresolved: dict[str, list[str]] = {}

    while to_scan:
        current = to_scan.pop()
        if current in seen:
            continue
        seen.add(current)
        if not current.exists() or not current.is_file():
            continue
        files.add(current)

        suffix = current.suffix.lower()
        if suffix not in {".html", ".htm", ".css", ".svg"}:
            continue

        try:
            text = current.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            ctx.warn("source", f"Could not read {current}: {exc}")
            continue

        raw_urls: set[str] = set()
        if suffix in {".html", ".htm", ".svg"}:
            parser = LocalAssetParser()
            try:
                parser.feed(text)
            except Exception as exc:  # HTMLParser can be tripped by odd markup; keep going.
                ctx.warn("source", f"HTML parse warning for {current}: {exc}")
            raw_urls.update(parser.urls)
        if suffix in {".css", ".svg"}:
            raw_urls.update(css_urls(text))

        for raw in raw_urls:
            if not is_probably_local_url(raw):
                continue
            asset = resolve_asset(raw, base_file=current, root_dir=root_dir)
            if asset:
                if asset not in seen:
                    to_scan.append(asset)
            else:
                unresolved.setdefault(str(current), []).append(raw)

    return files, unresolved


def copy_source_files(files: Iterable[pathlib.Path], root_dir: pathlib.Path, source_dir: pathlib.Path, ctx: CaptureContext) -> dict[str, str]:
    copied: dict[str, str] = {}
    external_count = 0
    for path in sorted({p.resolve() for p in files}):
        rel = safe_relpath(path, root_dir)
        if rel is None:
            external_count += 1
            # Keep outside-root files, but make escaping explicit and avoid overwrites.
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", path.name) or f"asset-{external_count}"
            rel = pathlib.Path("_outside_root") / f"{external_count:02d}-{safe_name}"
        dest = source_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, dest)
            copied[str(path)] = str(dest.relative_to(source_dir.parent))
        except OSError as exc:
            ctx.warn("source", f"Could not copy {path}: {exc}")
    return copied


def resolve_fetcher_bin(fetcher_bin: str) -> str | None:
    if not fetcher_bin:
        return None
    if os.path.sep in fetcher_bin or fetcher_bin.startswith("."):
        resolved = pathlib.Path(fetcher_bin).expanduser().resolve()
        if not resolved.exists():
            ctx_msg = f"fetcher entrypoint not found: {resolved}"
            return None
        return str(resolved)
    found = shutil.which(fetcher_bin)
    return found


def fetch_via_fetcher(
    page_url: str,
    fetcher_bin: str,
    workdir: pathlib.Path,
    source_dir: pathlib.Path,
    ctx: CaptureContext,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    copied: dict[str, str] = {}
    unresolved: dict[str, list[str]] = {}
    fetch_out = workdir / "fetcher-run"
    fetch_out.mkdir(parents=True, exist_ok=True)

    result = run_command([fetcher_bin, "get", page_url, "--out", str(fetch_out)], timeout=180, ctx=ctx)
    summary_path = fetch_out / "consumer_summary.json"
    if result.returncode != 0 or not summary_path.exists():
        ctx.warn(
            "fetcher",
            "fetcher get failed or produced no consumer_summary.json; keeping urllib-only source if any.",
        )
        return copied, unresolved

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        ctx.warn("fetcher", f"Could not parse fetcher summary: {exc}")
        return copied, unresolved

    counts = summary.get("counts", {})
    if counts.get("downloaded", 0) < 1:
        ctx.warn("fetcher", f"fetcher returned no downloads: {summary.get('failure_summary', counts)}")
        return copied, unresolved

    dest_root = source_dir / "fetcher"
    for sub in ("downloads", "markdown", "fit_markdown", "text_blobs", "extracted_text", "screenshots"):
        src = fetch_out / sub
        if not src.exists():
            continue
        for path in src.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(src)
            dest = dest_root / sub / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            copied[str(path)] = str(dest.relative_to(source_dir.parent))

    summary_dest = dest_root / "consumer_summary.json"
    summary_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(summary_path, summary_dest)
    copied[str(summary_path)] = str(summary_dest.relative_to(source_dir.parent))

    walkthrough = fetch_out / "Walkthrough.md"
    if walkthrough.exists():
        wt_dest = dest_root / "Walkthrough.md"
        shutil.copy2(walkthrough, wt_dest)
        copied[str(walkthrough)] = str(wt_dest.relative_to(source_dir.parent))

    if not copied:
        ctx.warn("fetcher", "fetcher run succeeded but no artifacts were copied into source/.")
    return copied, unresolved


FETCH_USER_AGENT = "html-bundler/1.0"
MAX_FETCH_BYTES = 25 * 1024 * 1024
MAX_FETCH_FILES = 120


def is_same_origin(url: str, base_url: str) -> bool:
    left = urllib.parse.urlparse(url)
    right = urllib.parse.urlparse(base_url)
    return (left.scheme, left.netloc) == (right.scheme, right.netloc)


def resolve_remote_url(raw_url: str, base_url: str) -> str | None:
    raw_url = strip_url_noise(raw_url)
    if not raw_url or not is_probably_local_url(raw_url):
        return None
    if raw_url.startswith("//"):
        parsed = urllib.parse.urlparse(base_url)
        if not parsed.scheme:
            return None
        raw_url = f"{parsed.scheme}:{raw_url}"
    return urllib.parse.urljoin(base_url, raw_url)


def sanitize_relpath_from_url(asset_url: str) -> pathlib.Path:
    parsed = urllib.parse.urlparse(asset_url)
    path = urllib.parse.unquote(parsed.path or "/index.html")
    if path.endswith("/"):
        path = f"{path}index.html"
    path = path.lstrip("/") or "index.html"
    parts = [re.sub(r"[^A-Za-z0-9._-]+", "_", part) or "part" for part in path.split("/")]
    return pathlib.Path(*parts)


def fetch_url_bytes(url: str, *, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": FETCH_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(MAX_FETCH_BYTES + 1)
    if len(data) > MAX_FETCH_BYTES:
        die(f"Refusing to fetch asset larger than {MAX_FETCH_BYTES} bytes: {url}")
    return data


def extract_urls_from_text(text: str, suffix: str) -> set[str]:
    raw_urls: set[str] = set()
    if suffix in {".html", ".htm", ".svg", ""}:
        parser = LocalAssetParser()
        try:
            parser.feed(text)
        except Exception:
            pass
        raw_urls.update(parser.urls)
    if suffix in {".css", ".svg"}:
        raw_urls.update(css_urls(text))
    return raw_urls


def fetch_remote_source(page_url: str, source_dir: pathlib.Path, ctx: CaptureContext) -> tuple[dict[str, str], dict[str, list[str]]]:
    # Fetch same-origin HTML/CSS/JS/image assets for external URL captures.
    copied: dict[str, str] = {}
    unresolved: dict[str, list[str]] = {}

    try:
        main_bytes = fetch_url_bytes(page_url)
    except Exception as exc:
        ctx.warn("fetch", f"Could not fetch page URL: {exc}")
        return copied, unresolved

    main_dest = source_dir / sanitize_relpath_from_url(page_url)
    main_dest.parent.mkdir(parents=True, exist_ok=True)
    main_dest.write_bytes(main_bytes)
    copied[page_url] = str(main_dest.relative_to(source_dir.parent))

    queue: list[tuple[pathlib.Path, str]] = [(main_dest, page_url)]
    seen_urls: set[str] = {page_url}
    fetched_count = 1

    while queue and fetched_count < MAX_FETCH_FILES:
        current_path, current_url = queue.pop(0)
        suffix = current_path.suffix.lower()
        if suffix not in {".html", ".htm", ".css", ".svg", ""}:
            continue
        try:
            text = current_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            ctx.warn("fetch", f"Could not read fetched asset {current_path.name}: {exc}")
            continue

        for raw in extract_urls_from_text(text, suffix):
            asset_url = resolve_remote_url(raw, current_url)
            if not asset_url or asset_url in seen_urls:
                continue
            if not is_same_origin(asset_url, page_url):
                continue
            seen_urls.add(asset_url)
            dest = source_dir / sanitize_relpath_from_url(asset_url)
            if dest.exists():
                if dest.suffix.lower() in {".html", ".htm", ".css", ".svg"}:
                    queue.append((dest, asset_url))
                continue
            try:
                blob = fetch_url_bytes(asset_url)
            except Exception as exc:
                unresolved.setdefault(current_url, []).append(raw)
                ctx.warn("fetch", f"Could not fetch same-origin asset: {exc}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            copied[asset_url] = str(dest.relative_to(source_dir.parent))
            fetched_count += 1
            if dest.suffix.lower() in {".html", ".htm", ".css", ".svg", ""}:
                queue.append((dest, asset_url))

    if fetched_count >= MAX_FETCH_FILES:
        ctx.warn("fetch", f"Stopped after {MAX_FETCH_FILES} fetched files.")
    return copied, unresolved


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003 - inherited name
        return


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@contextlib.contextmanager
def local_server(directory: pathlib.Path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(directory), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def url_for_local_file(html_path: pathlib.Path, root_dir: pathlib.Path, base_url: str) -> str:
    rel = html_path.resolve().relative_to(root_dir.resolve())
    rel_posix = rel.as_posix()
    quoted = "/".join(urllib.parse.quote(part) for part in rel_posix.split("/"))
    return f"{base_url}/{quoted}"



REDACT_STDOUT_COMMANDS = {
    "tab.list",
    "read",
    "text",
    "page.text",
    "page.state",
    "go",
    "window.new",
    "network.export",
    "perf.metrics",
}


def redact_sensitive_text(text: str) -> str:
    if not text:
        return ""
    redacted = text
    redacted = re.sub(r"/(?:home|mnt|tmp|var|Users)/[^\s\"']+", "[REDACTED_PATH]", redacted)
    redacted = re.sub(r"file://[^\s\"']+", "[REDACTED_URI]", redacted)
    redacted = re.sub(r"https?://[^\s\"']+", "[REDACTED_URL]", redacted)
    return redacted


def sanitize_surf_command(args: list[str], returncode: int, stdout: str, stderr: str) -> dict[str, object]:
    surf_args = args[1:] if len(args) > 1 else args
    command = str(surf_args[0]) if surf_args else "unknown"
    record: dict[str, object] = {"command": command, "returncode": returncode}
    if command in REDACT_STDOUT_COMMANDS:
        return record
    if returncode != 0:
        preview = redact_sensitive_text((stderr or stdout or "").strip())
        if preview:
            record["error_preview"] = preview[:200]
    return record


def safe_manifest_path(path: pathlib.Path | None, root: pathlib.Path | None) -> str | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if root is not None:
        try:
            return str(resolved.relative_to(root.expanduser().resolve()))
        except ValueError:
            pass
    return resolved.name


def file_digest(path: pathlib.Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def warn_if_identical_images(ctx: CaptureContext, left: pathlib.Path, right: pathlib.Path, label: str) -> None:
    left_digest = file_digest(left)
    right_digest = file_digest(right)
    if left_digest and right_digest and left_digest == right_digest:
        ctx.warn("capture", f"{left.name} is identical to {right.name}; {label}")


def parse_scroll_info(raw: str) -> dict[str, object] | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def surf_scroll_top(ctx: CaptureContext, surf_bin: str) -> None:
    try_surf(ctx, surf_bin, ["scroll.top"], timeout=20)


def surf_scroll_by_viewport(ctx: CaptureContext, surf_bin: str) -> dict[str, object] | None:
    js = (
        "const y = Math.min("
        "document.documentElement.scrollHeight - window.innerHeight,"
        "window.scrollY + Math.max(1, Math.floor(window.innerHeight * 0.9))"
        ");"
        "window.scrollTo(0, y);"
        "return JSON.stringify({"
        "scrollTop: window.scrollY,"
        "clientHeight: window.innerHeight,"
        "scrollHeight: document.documentElement.scrollHeight,"
        "atBottom: (window.innerHeight + window.scrollY) >= (document.documentElement.scrollHeight - 2)"
        "});"
    )
    result = try_surf(ctx, surf_bin, ["js", js], timeout=30)
    return parse_scroll_info(result.stdout)


def capture_viewport_slices(
    ctx: CaptureContext,
    surf_bin: str,
    prefix: str,
    *,
    max_slices: int,
) -> list[str]:
    captured: list[str] = []
    surf_scroll_top(ctx, surf_bin)
    time.sleep(0.35)
    seen_scroll_tops: set[int] = set()
    for index in range(1, max_slices + 1):
        info = parse_scroll_info(try_surf(ctx, surf_bin, ["scroll.info"], timeout=20).stdout)
        scroll_top = int(round(float(info.get("scrollTop", 0)))) if info else 0
        if scroll_top in seen_scroll_tops and index > 1:
            break
        seen_scroll_tops.add(scroll_top)
        output = ctx.captures_dir / f"{prefix}-scroll-{index:02d}.png"
        if capture_screenshot(ctx, surf_bin, output, [], f"{prefix} scroll slice {index}"):
            captured.append(output.name)
        if info and info.get("atBottom"):
            break
        next_info = surf_scroll_by_viewport(ctx, surf_bin)
        if next_info and next_info.get("atBottom"):
            # capture final slice at bottom if we haven't already
            bottom_output = ctx.captures_dir / f"{prefix}-scroll-{index + 1:02d}.png"
            time.sleep(0.35)
            if capture_screenshot(ctx, surf_bin, bottom_output, [], f"{prefix} scroll slice bottom"):
                captured.append(bottom_output.name)
            break
        time.sleep(0.35)
    return captured


def collect_source_bundle(
    options: CaptureOptions,
    ctx: CaptureContext,
    html_path: pathlib.Path | None,
    root_dir: pathlib.Path | None,
) -> tuple[dict[str, str], dict[str, list[str]], pathlib.Path | None, pathlib.Path | None]:
    copied_files: dict[str, str] = {}
    unresolved: dict[str, list[str]] = {}

    if options.no_source:
        ctx.source_mode = "visual-only"
        return copied_files, unresolved, html_path, root_dir

    source_entry: pathlib.Path | None = None
    if html_path and root_dir:
        source_entry = html_path
    elif options.url and options.root and options.source_entry:
        root_dir = options.root.expanduser().resolve()
        source_entry = options.source_entry.expanduser()
        if not source_entry.is_absolute():
            source_entry = (root_dir / source_entry).resolve()
        else:
            source_entry = source_entry.resolve()
        if not root_dir.exists() or not root_dir.is_dir():
            die(f"root directory not found: {root_dir}")
        if not source_entry.exists() or not source_entry.is_file():
            die(f"source entry not found: {source_entry}")
        try:
            source_entry.relative_to(root_dir)
        except ValueError:
            die(f"--source-entry must be inside --root. source_entry={source_entry} root={root_dir}")
        html_path = source_entry
    elif options.url and not options.no_fetch:
        backend = (options.fetch_backend or "auto").strip().lower()
        fetcher_bin = resolve_fetcher_bin(options.fetcher_bin) if options.fetcher_bin else None

        if backend in {"auto", "urllib"}:
            copied_files, unresolved = fetch_remote_source(str(options.url), ctx.source_dir, ctx)
            if copied_files:
                ctx.source_mode = "url-fetch-urllib"

        if not copied_files and backend in {"auto", "fetcher"}:
            if fetcher_bin:
                copied_files, unresolved = fetch_via_fetcher(
                    str(options.url), fetcher_bin, ctx.workdir, ctx.source_dir, ctx
                )
                if copied_files:
                    ctx.source_mode = "url-fetch-fetcher"
            elif backend == "fetcher":
                die("fetcher backend selected but --fetcher-bin is missing. Use skills/fetcher/run.sh")
            elif backend == "auto":
                ctx.warn(
                    "fetcher",
                    "urllib source fetch produced no files; configure skills/fetcher/run.sh for fallback.",
                )

        if not copied_files:
            ctx.warn(
                "source",
                "No source/ copied. For local dev-server assets, pass --root and --source-entry.",
            )
        return copied_files, unresolved, html_path, root_dir
    elif options.url:
        ctx.source_mode = "visual-only"
        ctx.warn("source", "Source fetch disabled (--no-fetch). Visual bundle only.")
        return copied_files, unresolved, html_path, root_dir

    if source_entry and root_dir:
        files, unresolved = collect_local_files(source_entry, root_dir, ctx)
        copied_files = copy_source_files(files, root_dir, ctx.source_dir, ctx)
        if not copied_files:
            ctx.warn("source", "source/ is empty after asset collection.")
        ctx.source_mode = "local-html" if options.html else "dev-server-root"

    return copied_files, unresolved, html_path, root_dir


def write_optional_surf_report(
    ctx: CaptureContext,
    surf_bin: str,
    args: list[str],
    output: pathlib.Path,
    label: str,
    *,
    timeout: int = 60,
    fallback_args: list[str] | None = None,
) -> bool:
    result = try_surf(ctx, surf_bin, args, timeout=timeout)
    if result.returncode != 0 and fallback_args:
        fallback = try_surf(ctx, surf_bin, fallback_args, timeout=timeout)
        if fallback.returncode == 0:
            result = fallback
    if result.returncode != 0:
        ctx.warn("surf", f"{label} unavailable in this surf version; optional report skipped.")
        write_text(
            output,
            "\n".join(
                [
                    "# Optional report unavailable",
                    "",
                    f"Command: surf {' '.join(args)}",
                    f"Status: skipped (returncode {result.returncode})",
                    "Note: network export depends on surf-cli/extension version support.",
                    "",
                ]
            ),
        )
        return False
    write_text(output, result.stdout.strip() + "\n")
    return True


def build_bundle_assessment(
    *,
    manifest: dict[str, object],
    capture_names: list[str],
    source_file_count: int,
    duplicate_warnings: list[str],
    optional_reports: dict[str, bool],
) -> str:
    lines = [
        "# Bundle assessment",
        "",
        "This file summarizes capture quality before WebGPT review.",
        "",
        "## Capture context",
        "",
        f"- Capture URL: `{manifest.get('capture_url', 'unknown')}`",
        f"- Source files copied: {source_file_count}",
        f"- Desktop viewport: {manifest.get('desktop_viewport')}",
        f"- Mobile viewport: {manifest.get('mobile_viewport') or 'not captured'}",
        f"- Scroll slices: {len([n for n in capture_names if '-scroll-' in n])}",
        "",
        "## Review coverage",
        "",
    ]

    def mark(ok: bool) -> str:
        return "yes" if ok else "no"

    has_source = source_file_count > 0
    has_mobile = bool(manifest.get("mobile_viewport"))
    has_scroll = any("-scroll-" in name for name in capture_names)
    has_full_res = any("fullpage-original" in name for name in capture_names)
    lines.extend(
        [
            f"- Visual/layout review: {mark(bool(capture_names))}",
            f"- Source/code review: {mark(has_source)}",
            f"- Mobile/responsive review: {mark(has_mobile)}",
            f"- Lower-page detail review: {mark(has_scroll or has_full_res)}",
            f"- Network waterfall review: {mark(optional_reports.get('network-export', False))}",
            f"- Performance metrics review: {mark(optional_reports.get('perf-metrics', False))}",
            "",
            "## Notes",
            "",
        ]
    )

    if not has_source:
        lines.append("- `source/` is missing. Rerun with `--html` or `--url --root --source-entry` for implementation review.")
    if not has_mobile:
        lines.append("- Mobile capture was skipped. Omit `--no-mobile` for responsive review.")
    if not has_scroll:
        lines.append("- Scroll slices were not captured; lower-page detail may be limited.")
    if duplicate_warnings:
        lines.extend(f"- {item}" for item in duplicate_warnings)
    if not optional_reports.get("network-export", False):
        lines.append("- Network export is optional and was unavailable in this surf version.")

    lines.append("")
    lines.append("## Suggested WebGPT prompt")
    lines.append("")
    lines.append(
        "Analyze this webpage package. Use `captures/` for visual/layout, `source/` for implementation, "
        "`reports/` for text/state clues, and `manifest.json` for capture context. Prioritize issues by user impact."
    )
    lines.append("")
    return "\n".join(lines)


def try_surf(ctx: CaptureContext, surf_bin: str, args: list[str], *, timeout: int = 60) -> CommandResult:
    return run_command([surf_bin, *args], timeout=timeout, check=False, ctx=ctx)


def surf_required(ctx: CaptureContext, surf_bin: str, args: list[str], *, timeout: int = 60) -> CommandResult:
    return run_command([surf_bin, *args], timeout=timeout, check=True, ctx=ctx)


def set_viewport(ctx: CaptureContext, surf_bin: str, width: int, height: int) -> None:
    attempts = [
        ["emulate.viewport", "--width", str(width), "--height", str(height)],
        ["emulate.viewport", str(width), str(height)],
        ["window.resize", str(width), str(height)],
    ]
    for attempt in attempts:
        result = try_surf(ctx, surf_bin, attempt, timeout=20)
        if result.returncode == 0:
            return
    ctx.warn("surf", f"Could not set viewport to {width}x{height}; continuing with current browser size.")


def capture_screenshot(ctx: CaptureContext, surf_bin: str, output: pathlib.Path, flags: list[str], label: str) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = try_surf(ctx, surf_bin, ["screenshot", *flags, "--output", str(output)], timeout=90)
    if result.returncode != 0 or not output.exists():
        ctx.warn("surf", f"Screenshot failed for {label}: {redact_sensitive_text(result.stderr.strip() or result.stdout.strip())}")
        return False
    return True


def write_surf_report(
    ctx: CaptureContext,
    surf_bin: str,
    args: list[str],
    output: pathlib.Path,
    label: str,
    *,
    timeout: int = 60,
    fallback_args: list[str] | None = None,
) -> None:
    result = try_surf(ctx, surf_bin, args, timeout=timeout)
    if result.returncode != 0 and fallback_args:
        fallback = try_surf(ctx, surf_bin, fallback_args, timeout=timeout)
        if fallback.returncode == 0:
            result = fallback
    content = result.stdout.strip()
    if result.returncode != 0:
        ctx.warn("surf", f"{label} failed: {redact_sensitive_text(result.stderr.strip() or result.stdout.strip())}")
        content = "\n".join(
            [
                f"# Report unavailable: {label}",
                "",
                f"Command: surf {' '.join(args)}",
                f"Status: failed (returncode {result.returncode})",
            ]
        )
    write_text(output, content + "\n")


def maybe_wait_for_page(ctx: CaptureContext, surf_bin: str, wait_ms: int) -> None:
    result = try_surf(ctx, surf_bin, ["wait.load"], timeout=max(5, wait_ms // 1000 + 10))
    if result.returncode != 0:
        ctx.warn("surf", "surf wait.load failed or is unavailable; using fixed wait instead.")
    time.sleep(wait_ms / 1000)


def create_readme(manifest: dict) -> str:
    return textwrap.dedent(
        f"""
        # WebGPT webpage analysis package

        This zip was generated by the `html-bundler` skill.

        Start with `BUNDLE_ASSESSMENT.md` for capture coverage and gaps.

        ## Suggested prompt

        Analyze this local webpage package. Use the screenshots in `captures/` for visual and layout issues, `source/` for implementation issues, `reports/` for accessibility/text/state clues, `BUNDLE_ASSESSMENT.md` for capture coverage, and `manifest.json` for capture context. Review UX, accessibility, SEO, performance risks, broken/missing assets, responsive behavior, and code quality. Prioritize findings by user impact and give concrete fixes.

        ## What is included

        - `BUNDLE_ASSESSMENT.md`: bundle QA summary and review coverage.
        - `captures/`: rendered screenshots captured through `/surf`.
        - `reports/`: text/state outputs; network export is optional and may be skipped.
        - `source/`: local HTML/CSS/JS/image assets when `--html` or `--url --root --source-entry` was used.
        - `manifest.json`: redacted capture metadata and warnings.

        ## Capture URL

        `{manifest.get('capture_url', 'unknown')}`
        """
    ).strip() + "\n"


def zip_dir(source_dir: pathlib.Path, zip_path: pathlib.Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(source_dir).as_posix())


def run_capture(options: CaptureOptions) -> pathlib.Path:
    if not options.html and not options.url:
        die("Provide --html or --url")
    if options.html and options.url:
        die("Use only one of --html or --url")

    out_path = (options.out or default_output_path()).expanduser().resolve()
    surf_bin = resolve_surf_bin(options.surf_bin)
    desktop_size = parse_size(options.desktop, "desktop")
    mobile_size = parse_size(options.mobile, "mobile")

    html_path: pathlib.Path | None = None
    root_dir: pathlib.Path | None = None
    if options.html:
        html_path = options.html.expanduser().resolve()
        if not html_path.exists() or not html_path.is_file():
            die(f"HTML file not found: {html_path}")
        root_dir = (options.root.expanduser().resolve() if options.root else html_path.parent.resolve())
        if not root_dir.exists() or not root_dir.is_dir():
            die(f"root directory not found: {root_dir}")
        try:
            html_path.relative_to(root_dir)
        except ValueError:
            die(f"HTML file must be inside --root. html={html_path} root={root_dir}")
    elif options.root:
        root_dir = options.root.expanduser().resolve()
        if not root_dir.exists() or not root_dir.is_dir():
            die(f"root directory not found: {root_dir}")
    else:
        if not re.match(r"^https?://", options.url or ""):
            die("--url must start with http:// or https://")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="html-bundler-"))
    ctx = CaptureContext(
        workdir=tmp,
        captures_dir=ensure_dir(tmp / "captures"),
        reports_dir=ensure_dir(tmp / "reports"),
        source_dir=ensure_dir(tmp / "source"),
    )

    server_cm = contextlib.nullcontext(None)
    if html_path and root_dir and not options.url:
        server_cm = local_server(root_dir)

    try:
        probe = try_surf(ctx, surf_bin, ["tab.list"], timeout=20)
        if probe.returncode != 0:
            die(
                "surf is installed but not responding. Run skills/surf/sanity.sh, then retry.\n"
                + redact_sensitive_text(probe.stderr.strip() or probe.stdout.strip())
            )

        copied_files, unresolved, html_path, root_dir = collect_source_bundle(options, ctx, html_path, root_dir)
        capture_names: list[str] = []
        optional_reports: dict[str, bool] = {}

        with server_cm as base_url:
            if html_path and root_dir and base_url is not None:
                capture_url = url_for_local_file(html_path, root_dir, str(base_url))
            else:
                capture_url = str(options.url)

            open_result = try_surf(ctx, surf_bin, ["window.new", capture_url], timeout=30)
            if open_result.returncode != 0:
                ctx.warn("surf", "surf window.new failed; falling back to surf go in the active tab.")
                surf_required(ctx, surf_bin, ["go", capture_url], timeout=30)

            maybe_wait_for_page(ctx, surf_bin, options.wait_ms)

            set_viewport(ctx, surf_bin, *desktop_size)
            maybe_wait_for_page(ctx, surf_bin, max(250, min(options.wait_ms, 1000)))

            viewport_path = ctx.captures_dir / "desktop-viewport.png"
            annotated_path = ctx.captures_dir / "desktop-annotated.png"
            fullpage_map_path = ctx.captures_dir / "desktop-fullpage-map.png"
            fullpage_original_path = ctx.captures_dir / "desktop-fullpage-original.png"

            if capture_screenshot(ctx, surf_bin, viewport_path, [], "desktop viewport"):
                capture_names.append(viewport_path.name)
            if capture_screenshot(ctx, surf_bin, fullpage_map_path, ["--fullpage"], "desktop full page map"):
                capture_names.append(fullpage_map_path.name)
            if capture_screenshot(ctx, surf_bin, fullpage_original_path, ["--fullpage", "--full"], "desktop full page original"):
                capture_names.append(fullpage_original_path.name)
            if capture_screenshot(ctx, surf_bin, annotated_path, ["--annotate"], "desktop annotated"):
                capture_names.append(annotated_path.name)
                warn_if_identical_images(ctx, annotated_path, viewport_path, "annotation added no visible labels")

            capture_names.extend(
                capture_viewport_slices(ctx, surf_bin, "desktop", max_slices=max(1, options.max_scroll_slices))
            )

            write_surf_report(ctx, surf_bin, ["read", "--compact"], ctx.reports_dir / "surf-read.txt", "surf read", timeout=60)
            write_surf_report(
                ctx,
                surf_bin,
                ["text"],
                ctx.reports_dir / "page-text.txt",
                "surf text",
                timeout=30,
                fallback_args=["page.text"],
            )
            write_surf_report(ctx, surf_bin, ["page.state"], ctx.reports_dir / "page-state.txt", "surf page.state", timeout=30)
            optional_reports["network-export"] = write_optional_surf_report(
                ctx,
                surf_bin,
                ["network.export"],
                ctx.reports_dir / "network-export.txt",
                "surf network.export",
                timeout=30,
            )
            optional_reports["perf-metrics"] = write_optional_surf_report(
                ctx,
                surf_bin,
                ["perf.metrics"],
                ctx.reports_dir / "perf-metrics.txt",
                "surf perf.metrics",
                timeout=30,
            )

            if not options.no_mobile:
                set_viewport(ctx, surf_bin, *mobile_size)
                maybe_wait_for_page(ctx, surf_bin, max(250, min(options.wait_ms, 1000)))
                mobile_viewport = ctx.captures_dir / "mobile-viewport.png"
                mobile_fullpage = ctx.captures_dir / "mobile-fullpage.png"
                if capture_screenshot(ctx, surf_bin, mobile_viewport, [], "mobile viewport"):
                    capture_names.append(mobile_viewport.name)
                if capture_screenshot(ctx, surf_bin, mobile_fullpage, ["--fullpage", "--full"], "mobile full page"):
                    capture_names.append(mobile_fullpage.name)

            duplicate_warnings = [w.message for w in ctx.warnings if w.area == "capture"]
            manifest = {
                "generated_at_utc": now_iso(),
                "tool": "html-bundler",
                "capture_url": capture_url,
                "input_html": safe_manifest_path(html_path, root_dir),
                "root_dir": safe_manifest_path(root_dir, root_dir) if root_dir else None,
                "source_entry": safe_manifest_path(options.source_entry, root_dir) if options.source_entry else safe_manifest_path(html_path, root_dir),
                "output_zip": str(out_path),
                "desktop_viewport": {"width": desktop_size[0], "height": desktop_size[1]},
                "mobile_viewport": None if options.no_mobile else {"width": mobile_size[0], "height": mobile_size[1]},
                "capture_files": capture_names,
                                "source_mode": ctx.source_mode,
                "copied_files": copied_files,
                "unresolved_local_references": unresolved,
                "optional_reports": optional_reports,
                "warnings": [w.__dict__ for w in ctx.warnings],
                "surf_commands": ctx.commands,
            }
            assessment = build_bundle_assessment(
                manifest=manifest,
                capture_names=capture_names,
                source_file_count=len(copied_files),
                duplicate_warnings=duplicate_warnings,
                optional_reports=optional_reports,
            )
            write_text(tmp / "BUNDLE_ASSESSMENT.md", assessment)
            write_text(tmp / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
            write_text(tmp / "README_FOR_CHATGPT.md", create_readme(manifest))

        zip_dir(tmp, out_path)
        if ctx.warnings:
            print(f"Completed with {len(ctx.warnings)} warning(s). See BUNDLE_ASSESSMENT.md inside the zip.", file=sys.stderr)
        return out_path
    finally:
        if options.keep_workdir:
            print(f"Kept working directory: {tmp}", file=sys.stderr)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
