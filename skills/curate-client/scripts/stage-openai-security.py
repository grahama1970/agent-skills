#!/usr/bin/env python3
"""Promote successful Fetcher results into source-bound Markdown.

Fetcher artifacts are content-hash named and do not embed their source URL.
This gate reads consumer_summary.json, accepts only usable official OpenAI
results, adds provenance, and atomically emits curated Markdown plus receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ALLOWED_DOMAINS = {
    "developers.openai.com",
    "help.openai.com",
    "learn.chatgpt.com",
    "openai.com",
    "trust.openai.com",
}
ARTIFACT_KEYS = (
    "fit_markdown_path",
    "markdown_path",
    "extracted_text_path",
    "download_path",
)


@dataclass(frozen=True)
class NamedPath:
    name: str
    path: Path


def named_path(value: str) -> NamedPath:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=/path")
    name, raw = value.split("=", 1)
    if not re.fullmatch(r"[a-z0-9_-]+", name):
        raise argparse.ArgumentTypeError(f"invalid name: {name!r}")
    return NamedPath(name, Path(raw).expanduser())


def load_urls(path: Path | None) -> set[str]:
    if path is None:
        return set()
    return {
        line.strip().split("#", 1)[0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def slug(value: str, limit: int = 100) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:limit].rstrip("-") or "source"


def output_name(url: str) -> str:
    parsed = urlparse(url)
    stem = slug(f"{parsed.netloc}-{parsed.path or 'index'}")
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    return f"{stem}-{digest}.md"


def artifact_for(summary_path: Path, item: dict[str, Any]) -> tuple[Path, str] | None:
    run_root = summary_path.parent.resolve()
    for key in ARTIFACT_KEYS:
        raw = (item.get("artifacts") or {}).get(key)
        if not raw:
            continue
        candidate = Path(str(raw)).expanduser()
        if not candidate.is_absolute():
            candidate = summary_path.parent / candidate
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(run_root)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved, key
    return None


def read_text(path: Path) -> str:
    payload = path.read_bytes()
    if b"\0" in payload[:4096]:
        raise ValueError("binary artifact")
    return payload.decode("utf-8", errors="replace").strip()


def title_for(content: str, url: str) -> str:
    for line in content.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()[:220]
    tail = Path(urlparse(url).path.rstrip("/")).name or urlparse(url).netloc
    return tail.replace("-", " ").title() or "OpenAI source"


def strip_same_h1(content: str, title: str) -> str:
    lines = content.lstrip().splitlines()
    if lines and lines[0].startswith("# "):
        first = re.sub(r"\s+", " ", lines[0][2:]).strip().casefold()
        if first == re.sub(r"\s+", " ", title).strip().casefold():
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)
    return "\n".join(lines).strip()


def summarize(content: str, limit: int = 320) -> str:
    text = re.sub(r"[`*_>#\[\]()]", " ", content)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def render(
    *, title: str, content: str, url: str, final_url: str, source_id: str,
    lane: str, priority: str, retrieved_at: str, scope: str,
    artifact_kind: str, item: dict[str, Any], digest: str,
) -> str:
    metadata = [
        f"# {title}", "",
        f"- Source URL: {url}",
        f"- Final downloaded URL: {final_url}",
        f"- Canonical source ID: {source_id}",
        "- Authority: official OpenAI documentation",
        f"- Retrieval lane: {lane}",
        f"- Priority: {priority}",
        f"- Retrieved at: {retrieved_at}",
        f"- HTTP status: {item.get('status')}",
        f"- Fetch method: {item.get('method')}",
        f"- Alternate provider: {item.get('alternate_provider') or 'none'}",
        f"- Content type: {item.get('content_type')}",
        f"- Selected artifact: {artifact_kind}",
        f"- Content SHA-256: {digest}",
        f"- Memory scope: {scope}",
        "", "---", "",
    ]
    return "\n".join(metadata) + strip_same_h1(content, title) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def stage(args: argparse.Namespace) -> dict[str, Any]:
    required = load_urls(args.required_url_file)
    expected = {item.name: load_urls(item.path) for item in args.expected_url_file}
    target = args.staged_root.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))

    documents: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    blocked: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()

    try:
        for lane in args.lane:
            summary_path = lane.path.resolve(strict=True)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            lane_dir = temp / lane.name
            lane_dir.mkdir(parents=True, exist_ok=True)
            retrieved_at = str(summary.get("finished_at") or summary.get("started_at") or "unknown")
            summary_urls: set[str] = set()

            raw_items = summary.get("items")
            if not isinstance(raw_items, list):
                raise ValueError(f"{summary_path}: missing items list")

            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("original_url") or item.get("requested_url") or "").split("#", 1)[0]
                if not url:
                    warnings.append(f"{lane.name}: item missing URL")
                    continue
                summary_urls.add(url)
                is_required = url in required
                priority = "P0" if is_required else ("P1" if lane.name == "primary" else "P2")

                def reject(reason: str) -> None:
                    message = f"{url}: {reason}"
                    (blocked if is_required else warnings).append(message)
                    items.append({"url": url, "lane": lane.name, "status": "SKIP", "reason": reason})

                parsed = urlparse(url)
                if parsed.scheme != "https" or parsed.netloc.lower() not in ALLOWED_DOMAINS:
                    reject("source is not on an allowed official OpenAI domain")
                    continue
                if url in seen:
                    blocked.append(f"duplicate URL across lanes: {url}")
                    continue
                seen.add(url)
                if item.get("verdict") != "ok" or item.get("status") != 200:
                    reject(f"unusable fetch verdict={item.get('verdict')} status={item.get('status')}")
                    continue

                selected = artifact_for(summary_path, item)
                if selected is None:
                    reject("no readable emitted artifact inside the fetch run")
                    continue
                artifact_path, artifact_kind = selected
                try:
                    content = read_text(artifact_path)
                except (OSError, ValueError) as exc:
                    reject(f"unreadable artifact: {exc}")
                    continue
                if len(content) < args.minimum_chars:
                    reject(f"artifact too short: {len(content)} characters")
                    continue

                final_url = str(item.get("final_downloaded_url") or url)
                if urlparse(final_url).netloc.lower() not in ALLOWED_DOMAINS:
                    warnings.append(f"{url}: alternate/noncanonical final URL requires review: {final_url}")

                digest = hashlib.sha256(content.encode()).hexdigest()
                source_id = "openai-" + hashlib.sha256(url.encode()).hexdigest()[:16]
                title = title_for(content, url)
                filename = output_name(url)
                destination = lane_dir / filename
                destination.write_text(render(
                    title=title, content=content, url=url, final_url=final_url,
                    source_id=source_id, lane=lane.name, priority=priority,
                    retrieved_at=retrieved_at, scope=args.scope,
                    artifact_kind=artifact_kind, item=item, digest=digest,
                ), encoding="utf-8")

                documents.append({
                    "classification": "public",
                    "source_id": source_id,
                    "title": title,
                    "authority": "official_openai",
                    "retrieved_at": retrieved_at,
                    "digest": digest,
                    "url": url,
                    "path": f"knowledge/curated/{filename}",
                    "summary": summarize(content),
                    "priority": priority,
                    "retrieval_lane": lane.name,
                    "final_downloaded_url": final_url,
                    "fetch_method": str(item.get("method") or "unknown"),
                })
                items.append({
                    "url": url, "lane": lane.name, "priority": priority,
                    "status": "STAGED", "path": str(target / lane.name / filename),
                    "digest": digest, "artifact": artifact_kind,
                })

            for missing in sorted(expected.get(lane.name, set()) - summary_urls):
                message = f"{lane.name}: URL missing from fetch summary: {missing}"
                (blocked if missing in required else warnings).append(message)

        for missing in sorted(required - {item["url"] for item in items if item.get("status") == "STAGED"}):
            message = f"required P0 URL was not staged: {missing}"
            if message not in blocked:
                blocked.append(message)

        status = "FAIL" if blocked else ("PASS_WITH_WARNINGS" if warnings else "PASS")
        receipt = {
            "schema": "openai.security_staging_receipt.v1",
            "status": status,
            "scope": args.scope,
            "staged_root": str(target),
            "counts": {
                "lanes": len(args.lane), "staged": len(documents),
                "required_urls": len(required), "blocked": len(blocked),
                "warnings": len(warnings),
            },
            "blocked": blocked, "warnings": warnings, "items": items,
        }
        write_json(args.receipt_out, receipt)
        if blocked:
            return receipt

        if target.exists():
            shutil.rmtree(target)
        temp.rename(target)
        temp = None
        write_json(args.manifest_out, {
            "schema": "curate_client.source_manifest.v1",
            "client": args.scope.removeprefix("client:"),
            "scope": args.scope,
            "generated_from": [str(item.path) for item in args.lane],
            "documents": sorted(documents, key=lambda item: (item["priority"], item["title"].casefold(), item["url"])),
        })
        return receipt
    finally:
        if temp is not None and temp.exists():
            shutil.rmtree(temp, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--lane", action="append", type=named_path, required=True)
    result.add_argument("--staged-root", type=Path, required=True)
    result.add_argument("--manifest-out", type=Path, required=True)
    result.add_argument("--receipt-out", type=Path, required=True)
    result.add_argument("--required-url-file", type=Path)
    result.add_argument("--expected-url-file", action="append", type=named_path, default=[])
    result.add_argument("--scope", default="client:openai-privacy")
    result.add_argument("--minimum-chars", type=int, default=200)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        receipt = stage(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        receipt = {
            "schema": "openai.security_staging_receipt.v1",
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_json(args.receipt_out, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt["status"] != "FAIL" else 3


if __name__ == "__main__":
    raise SystemExit(main())
