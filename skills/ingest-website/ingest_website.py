#!/usr/bin/env python3
"""Ingest an entire website into /memory as a RAG resource.

Pipeline: /fetcher (crawl) -> /extractor (structured extraction) ->
         /doc2qra (QRA extraction) -> /taxonomy (bridge tags) -> /memory (store).
         /embedding (semantic vectors) on all paths.
This is a GLUE skill — orchestrates existing skills via subprocess.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
import typer
from bs4 import BeautifulSoup
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn
from rich.table import Table

# TaskClient for task-monitor integration
_COMMON_DIR = str(Path(__file__).resolve().parent.parent / "common")
if _COMMON_DIR not in sys.path:
    sys.path.insert(0, _COMMON_DIR)
try:
    from task_monitor import TaskClient
except ImportError:
    TaskClient = None  # type: ignore[assignment,misc]

# Batch QRA extraction via chutes-call (extracted to _qra_batch.py)
from _qra_batch import CHUTES_CALL_AVAILABLE, batch_qra_via_chutes  # noqa: E402

app = typer.Typer(help="Ingest website into /memory as RAG resource")

SKILL_DIR = Path(__file__).parent
SKILLS_ROOT = SKILL_DIR.parent
FETCHER_RUN = SKILLS_ROOT / "fetcher" / "run.sh"
EXTRACTOR_RUN = SKILLS_ROOT / "extractor" / "run.sh"
# doc2qra uses chutes-call /batch HTTP service (port 8630) — no subprocess
# Memory accessed via httpx Unix socket /run/user/1000/embry/memory.sock
# Taxonomy and embedding use HTTP services directly (not subprocess):
#   taxonomy: memory daemon /taxonomy/tag endpoint (Unix socket)
#   embedding: embry-embedding service on port 8602

# Image extensions to download
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}


def _run_skill(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a composed skill via subprocess."""
    logger.debug("Running: {}", " ".join(cmd[-6:]))
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env,
    )


def _extract_taxonomy_tags(content: str) -> list[str]:
    """Extract federated taxonomy bridge tags via memory daemon /taxonomy/tag.

    Returns list of bridge tag strings (e.g. ["Precision", "Resilience"]).
    Uses HTTP POST to memory daemon instead of subprocess (Rule 17).
    """
    from _qra_batch import _memory_client

    text_sample = content[:3000]
    try:
        client = _memory_client()
        resp = client.post("/taxonomy/tag", json={"text": text_sample, "fast": True})
        client.close()
        if resp.status_code == 200:
            data = resp.json()
            return data.get("bridge_tags", data.get("tags", []))
        logger.warning("Taxonomy tag returned {}", resp.status_code)
        return []
    except Exception as e:
        logger.warning("Taxonomy extraction error: {}", e)
        return []


def _extract_with_extractor(html_content: str, url: str, tmpdir: Path) -> Optional[str]:
    """Run /extractor on fetched HTML to get structured markdown.

    Saves raw HTML to a temp .html file, runs /extractor with --fast --no-interactive,
    returns extracted markdown. Falls back to raw content if extractor unavailable.
    """
    if not EXTRACTOR_RUN.exists():
        logger.warning("/extractor not found at {}, using raw content", EXTRACTOR_RUN)
        return None

    parsed = urlparse(url)
    safe_name = re.sub(r"[^\w\-.]", "_", parsed.path.strip("/") or "index")
    html_file = tmpdir / f"{safe_name}.html"
    html_file.write_text(html_content)

    result = _run_skill(
        [str(EXTRACTOR_RUN), str(html_file), "--fast", "--no-interactive"],
        timeout=120,
    )

    if result.returncode != 0:
        logger.warning("Extractor failed for {} (rc={}): {}", url, result.returncode, result.stderr[:200] if result.stderr else "no stderr")
        return None

    extracted = result.stdout.strip()
    if extracted:
        logger.debug("Extracted {} chars from {}", len(extracted), url)
        return extracted

    return None


def _trigger_post_storage_hooks(scope: str, start_ts: int) -> None:
    """Trigger embedding and edge proposal after batch storage.

    Uses HTTP services (Rule 17): embedding service on 8602,
    edge proposal via memory daemon (no HTTP endpoint yet — subprocess OK).
    """
    from _qra_batch import _memory_client

    # Embedding: POST to embedding service on port 8602
    _EMBED_URL = os.environ.get("EMBEDDING_SERVICE_URL", "http://127.0.0.1:8602")
    logger.info("Triggering embedding for scope '{}'...", scope)
    try:
        client = _memory_client()
        # Recall recent docs to get texts for embedding
        resp = client.post("/recall", json={"q": f"scope:{scope}", "scope": scope, "limit": 50})
        client.close()
        if resp.status_code == 200:
            items = resp.json().get("items", resp.json().get("results", []))
            texts = [it.get("solution", it.get("playbook", ""))[:500] for it in items if it.get("solution") or it.get("playbook")]
            if texts:
                httpx.post(f"{_EMBED_URL}/embed/batch", json={"texts": texts[:50]}, timeout=60.0)
    except Exception as e:
        logger.warning("Embedding trigger skipped (non-critical): {}", e)

    # Edge proposal — no HTTP endpoint yet, subprocess is OK per Rule 17
    proposer_path = Path(os.environ.get("MEMORY_REPO_PATH", ""))
    if not proposer_path.is_dir():
        candidate = SKILLS_ROOT.parent.parent / "memory"
        if candidate.is_dir():
            proposer_path = candidate
    if proposer_path.is_dir():
        logger.info("Triggering edge proposal for scope '{}'...", scope)
        try:
            env = dict(os.environ)
            env.pop("VIRTUAL_ENV", None)
            subprocess.run(
                ["uv", "run", "python", "-m",
                 "graph_memory.lessons.proposer", "propose",
                 "--scope", scope, "--updated-since", str(start_ts),
                 "--write-limit", "50"],
                capture_output=True, text=True, timeout=120,
                cwd=str(proposer_path), env=env,
            )
        except Exception as e:
            logger.warning("Edge proposal skipped (non-critical): {}", e)


def _crawl_links(
    base_url: str,
    html: str,
    max_depth: int,
    max_pages: int,
    current_depth: int = 0,
) -> list[str]:
    """Extract same-domain links from HTML content."""
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    soup = BeautifulSoup(html, "html.parser")

    links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        if parsed.netloc == base_domain:
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if not any(clean.endswith(ext) for ext in (".pdf", ".zip", ".tar.gz")):
                links.add(clean.rstrip("/"))

    return list(links)[:max_pages]


def _extract_image_urls(html: str, base_url: str) -> list[str]:
    """Extract image URLs from HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    images = set()
    for img in soup.find_all("img", src=True):
        src = urljoin(base_url, img["src"])
        parsed = urlparse(src)
        ext = Path(parsed.path).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            images.add(src)
    return list(images)


def _fetch_url(url: str) -> tuple[Optional[str], Optional[str]]:
    """Fetch a single URL using /fetcher or httpx fallback.

    Returns (raw_html, markdown_content). raw_html is needed for link
    discovery via BeautifulSoup; markdown_content is the extracted text
    for downstream processing. Either may be None on failure.
    """
    if FETCHER_RUN.exists():
        env = dict(os.environ)
        env.pop("VIRTUAL_ENV", None)
        env["FETCHER_EMIT_MARKDOWN"] = "1"

        with tempfile.TemporaryDirectory(prefix="ingest_website_") as tmpdir:
            cmd = [str(FETCHER_RUN), "get", url, "--out", tmpdir]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, env=env,
            )

            # Get raw HTML from downloads/ dir (needed for link discovery)
            raw_html = None
            downloads = Path(tmpdir) / "downloads"
            if downloads.exists():
                html_files = list(downloads.glob("*.html")) or list(downloads.glob("*"))
                if html_files:
                    raw_html = html_files[0].read_text(errors="replace")

            # Get markdown from markdown/ dir (for content extraction)
            markdown = None
            for subdir in ("markdown", "fit_markdown", "text_blobs"):
                d = Path(tmpdir) / subdir
                if d.exists():
                    files = list(d.glob("*.md")) or list(d.glob("*"))
                    if files:
                        markdown = files[0].read_text()
                        break

            if raw_html or markdown:
                return raw_html, markdown or raw_html

    # Fallback: direct httpx fetch (returns HTML for both)
    logger.info("Fetching directly via httpx: {}", url)
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
        return resp.text, resp.text
    except Exception as e:
        # SSL errors are not httpx.HTTPError — catch broadly, retry without verify
        if "SSL" in str(e) or "certificate" in str(e).lower():
            logger.warning("SSL error, retrying without verification: {}", e)
            try:
                resp = httpx.get(url, follow_redirects=True, timeout=30.0, verify=False)
                resp.raise_for_status()
                return resp.text, resp.text
            except Exception as e2:
                logger.error("Failed to fetch {} (even without SSL verify): {}", url, e2)
                return None, None
        logger.error("Failed to fetch {}: {}", url, e)
        return None, None


def _download_image(url: str, output_dir: Path) -> Optional[Path]:
    """Download a single image to output_dir/images/."""
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(url)
    filename = Path(parsed.path).name
    if not filename:
        return None

    dest = images_dir / filename
    if dest.exists():
        return dest

    try:
        resp = httpx.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        logger.info("  Downloaded image: {}", filename)
        return dest
    except httpx.HTTPError as e:
        logger.warning("  Failed to download image {}: {}", url, e)
        return None


def _run_doc2qra(
    content_path: Path,
    scope: str,
    dry_run: bool = False,
) -> dict:
    """Extract QRAs via chutes-call /batch HTTP service (port 8630).

    Reads the file, sends content to the chutes-call batch endpoint for
    LLM-based QRA extraction, then stores results to memory via daemon.
    Falls back gracefully if services are unavailable.
    """
    from _qra_batch import QRA_SYSTEM_PROMPT, _memory_client

    try:
        text = content_path.read_text()[:3000]
    except Exception as e:
        logger.error("Cannot read {}: {}", content_path, e)
        return {"extracted": 0, "stored": 0}

    if dry_run:
        return {"extracted": 0, "stored": 0, "dry_run": True}

    # Call chutes-call /batch HTTP service
    _CHUTES_URL = os.environ.get("CHUTES_CALL_URL", "http://localhost:8630")
    payload = {
        "requests": [{
            "messages": [
                {"role": "system", "content": QRA_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    "Extract all grounded knowledge items from this text. "
                    "Every answer must be supported by the source text.\n\n"
                    f"Text:\n{text}\n\nJSON:"
                )},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "temperature": 0.1,
        }],
        "concurrency": 1,
        "tenacious": True,
        "caller": "ingest-website",
    }

    try:
        resp = httpx.post(f"{_CHUTES_URL}/batch", json=payload, timeout=120.0)
        if resp.status_code != 200:
            logger.warning("chutes-call /batch returned {}", resp.status_code)
            return {"extracted": 0, "stored": 0}
        results = resp.json()
    except Exception as e:
        logger.warning("chutes-call /batch failed for {}: {}", content_path.name, e)
        return {"extracted": 0, "stored": 0}

    # Parse LLM response and store QRAs to memory
    stored = 0
    if results and isinstance(results, list) and results[0].get("ok"):
        try:
            content_str = results[0].get("content", "")
            data = json.loads(content_str) if isinstance(content_str, str) else content_str
            items = data.get("items", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, TypeError):
            items = []

        if items:
            client = _memory_client()
            try:
                for item in items:
                    q = item.get("question", "")
                    a = item.get("answer", "")
                    r = item.get("reasoning", "")
                    if not q or not a:
                        continue
                    solution = f"**Reasoning:** {r}\n\n**Answer:** {a}" if r else a
                    try:
                        mem_resp = client.post("/learn", json={
                            "problem": q, "solution": solution,
                            "scope": scope, "tags": ["qra"],
                        })
                        if mem_resp.status_code == 200:
                            stored += 1
                    except Exception:
                        pass
            finally:
                client.close()

    return {"extracted": stored, "stored": stored}


def _save_markdown(url: str, content: str, output_dir: Path) -> Path:
    """Save fetched content as a markdown file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").replace("/", "_") or "index"
    filename = f"{parsed.netloc}_{path_parts}.md"
    filename = re.sub(r"[^\w\-.]", "_", filename)
    dest = output_dir / filename
    dest.write_text(content)
    return dest


@app.command()
def ingest(
    url: Optional[str] = typer.Argument(None, help="Base URL to crawl"),
    urls: Optional[Path] = typer.Option(None, "--urls", help="File with one URL per line"),
    scope: str = typer.Option("research", "--scope", help="Memory scope"),
    images: bool = typer.Option(False, "--images", help="Download images"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Save pages locally"),
    max_pages: int = typer.Option(50, "--max-pages", help="Max pages to fetch"),
    depth: int = typer.Option(2, "--depth", help="Max crawl depth"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch only, skip memory"),
    no_qra: bool = typer.Option(False, "--no-qra", help="Skip QRA extraction"),
    delay: int = typer.Option(500, "--delay", help="Delay between requests (ms)"),
):
    """Crawl website and store as RAG resource."""
    if not url and not urls:
        logger.error("Provide either a URL argument or --urls FILE")
        raise typer.Exit(1)

    console = Console()

    # Task-monitor integration
    monitor = None
    if TaskClient is not None:
        monitor = TaskClient(
            "ingest-website",
            total=max_pages,
            description=f"Ingest website: {url or str(urls)}",
            state_dir=str(SKILL_DIR),
        )

    # Metrics accumulators
    stats = {
        "fetched": 0, "fetch_fail": 0, "extracted": 0, "extract_fail": 0,
        "qras": 0, "chunks": 0, "store_fail": 0, "images": 0,
        "tags": {"Precision": 0, "Resilience": 0, "Fragility": 0,
                 "Corruption": 0, "Loyalty": 0, "Stealth": 0},
        "pages_with_tags": 0, "total_words": 0,
    }

    # Record start time for post-storage hooks (updated_since filter)
    start_ts = int(time.time())

    # Collect URLs to process
    target_urls: list[str] = []
    if urls and urls.exists():
        target_urls = [
            line.strip() for line in urls.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    elif url:
        target_urls = [url]

    if not target_urls:
        logger.error("No URLs to process")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]PHASE 1: CRAWL[/bold cyan]  target={target_urls[0][:60]}")

    # Phase 1: Crawl — fetch base URL and discover links
    all_urls = set()
    fetched_content: dict[str, str] = {}

    with Progress(
        SpinnerColumn(), TextColumn("[bold]{task.description}"),
        BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
        console=console, transient=True,
    ) as progress:
        seed_task = progress.add_task("Seeding", total=len(target_urls))
        for base_url in target_urls:
            progress.update(seed_task, description=f"Seed: {urlparse(base_url).path[:40]}")
            raw_html, content = _fetch_url(base_url)
            if not content:
                stats["fetch_fail"] += 1
                if monitor:
                    monitor.fail(item=f"CRAWL: {base_url[:60]}")
                progress.advance(seed_task)
                continue

            fetched_content[base_url] = content
            all_urls.add(base_url)
            stats["fetched"] += 1
            if monitor:
                monitor.update(item=f"CRAWL: {base_url[:60]}", phase="crawl",
                               fetched=stats["fetched"], fetch_fail=stats["fetch_fail"])

            if not urls and depth > 0:
                link_source = raw_html or content
                discovered = _crawl_links(base_url, link_source, depth, max_pages)
                console.print(f"  [dim]Discovered {len(discovered)} links from {base_url}[/dim]")
                for link_url in discovered:
                    if link_url not in all_urls and len(all_urls) < max_pages:
                        all_urls.add(link_url)
            progress.advance(seed_task)

        # Fetch discovered pages
        unfetched = [u for u in all_urls if u not in fetched_content]
        if unfetched:
            crawl_task = progress.add_task("Crawling", total=len(unfetched))
            for i, page_url in enumerate(unfetched):
                if i > 0:
                    time.sleep(delay / 1000.0)
                short_path = urlparse(page_url).path[:50]
                progress.update(crawl_task, description=f"Fetch: {short_path}")
                _, content = _fetch_url(page_url)
                if content:
                    fetched_content[page_url] = content
                    stats["fetched"] += 1
                    if monitor:
                        monitor.update(item=f"CRAWL: {short_path}", phase="crawl",
                                       fetched=stats["fetched"], fetch_fail=stats["fetch_fail"])
                else:
                    stats["fetch_fail"] += 1
                    if monitor:
                        monitor.fail(item=f"CRAWL: {short_path}")
                progress.advance(crawl_task)

    total_pages = len(fetched_content)
    if monitor:
        # total = pages to extract + pages to store
        monitor.set_total(total_pages * 2)
        monitor.heartbeat(item=f"CRAWL done: {total_pages} pages")
    domain = urlparse(list(fetched_content.keys())[0]).netloc if fetched_content else "unknown"
    console.print(f"  [green]{stats['fetched']} fetched[/green], "
                  f"[red]{stats['fetch_fail']} failed[/red] from {domain}")

    # Phase 2: Download images (optional)
    if images and output_dir:
        console.print(f"\n[bold cyan]PHASE 2: IMAGES[/bold cyan]")
        for page_url, content in fetched_content.items():
            img_urls = _extract_image_urls(content, page_url)
            for img_url in img_urls:
                if _download_image(img_url, output_dir):
                    stats["images"] += 1
        console.print(f"  [green]{stats['images']} images[/green] to {output_dir}/images/")

    # Phase 3: Extract — run /extractor on fetched HTML for structured content
    console.print(f"\n[bold cyan]PHASE 3: EXTRACT[/bold cyan]  {total_pages} pages via /extractor")
    extracted_content: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="ingest_website_extract_") as extract_tmpdir:
        extract_tmpdir_path = Path(extract_tmpdir)
        with Progress(
            SpinnerColumn(), TextColumn("[bold]{task.description}"),
            BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
            console=console, transient=True,
        ) as progress:
            ext_task = progress.add_task("Extracting", total=total_pages)
            for page_url, raw_content in fetched_content.items():
                short_path = urlparse(page_url).path[:50]
                progress.update(ext_task, description=f"Extract: {short_path}")
                extracted = _extract_with_extractor(raw_content, page_url, extract_tmpdir_path)
                if extracted:
                    extracted_content[page_url] = extracted
                    stats["extracted"] += 1
                else:
                    extracted_content[page_url] = raw_content
                    stats["extract_fail"] += 1
                if monitor:
                    monitor.update(item=f"EXTRACT: {short_path}", phase="extract",
                                   extracted=stats["extracted"], extract_fail=stats["extract_fail"])
                progress.advance(ext_task)
        console.print(f"  [green]{stats['extracted']} extracted[/green], "
                      f"[yellow]{stats['extract_fail']} fallback to raw[/yellow]")

    # Phase 4: Save markdown locally (optional)
    saved_files: list[Path] = []
    if output_dir:
        for page_url, content in extracted_content.items():
            saved = _save_markdown(page_url, content, output_dir)
            saved_files.append(saved)
        logger.info("Saved: {} markdown files to {}", len(saved_files), output_dir)

    # Phase 5: QRA extraction + memory storage
    total_qras = 0
    used_no_qra_path = False
    if not dry_run:
        mode_label = "chunks (--no-qra)" if no_qra else "QRAs (doc2qra)"
        console.print(f"\n[bold cyan]PHASE 5: STORE[/bold cyan]  {mode_label} -> scope={scope}")
        with tempfile.TemporaryDirectory(prefix="ingest_website_qra_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            with Progress(
                SpinnerColumn(), TextColumn("[bold]{task.description}"),
                BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                console=console, transient=True,
            ) as progress:
                store_task = progress.add_task("Storing", total=len(extracted_content))
                _qra_batch_done = False
                for page_url, content in extracted_content.items():
                    parsed = urlparse(page_url)
                    safe_name = re.sub(r"[^\w\-.]", "_", parsed.path.strip("/") or "index")
                    tmp_file = tmpdir_path / f"{safe_name}.md"
                    tmp_file.write_text(content)
                    short_path = parsed.path[:50]

                    if no_qra:
                        used_no_qra_path = True
                        if True:  # memory service via Unix socket
                            plain_text = content
                            try:
                                data = json.loads(content)
                                if isinstance(data, dict):
                                    doc = data.get("document", data)
                                    plain_text = doc.get("full_text", "") or content
                            except (json.JSONDecodeError, ValueError):
                                pass

                            bridge_tags = _extract_taxonomy_tags(plain_text)
                            for bt in bridge_tags:
                                if bt in stats["tags"]:
                                    stats["tags"][bt] += 1
                            if bridge_tags:
                                stats["pages_with_tags"] += 1

                            source_tags = [f"source:{domain}", "ingested_web"]
                            all_tags = bridge_tags + source_tags

                            words = plain_text.split()
                            stats["total_words"] += len(words)
                            chunk_size = 500
                            chunks = []
                            for ci in range(0, len(words), chunk_size):
                                chunks.append(" ".join(words[ci : ci + chunk_size]))

                            # Store chunks concurrently (5 workers) via memory daemon HTTP
                            page_chunks = _store_chunks_concurrent(
                                chunks, page_url, scope, all_tags,
                            )
                            total_qras += page_chunks
                            stats["chunks"] += page_chunks
                            tag_str = ",".join(bridge_tags) if bridge_tags else "none"
                            progress.update(store_task,
                                            description=f"Store: {short_path} ({page_chunks}ch [{tag_str}])")
                    else:
                        # QRA path: batch via chutes-call (fast) or sequential subprocess (fallback)
                        if CHUTES_CALL_AVAILABLE and not _qra_batch_done:
                            # Do batch QRA for ALL pages at once (first iteration only)
                            progress.update(store_task, description="QRA: batch via chutes-call")
                            batch_stored, batch_stats = batch_qra_via_chutes(
                                extracted_content, scope, domain,
                                progress_cb=lambda url, n: progress.update(
                                    store_task, description=f"QRA: {urlparse(url).path[:40]} ({n} QRAs)"),
                            )
                            total_qras += batch_stored
                            stats["qras"] += batch_stored
                            _qra_batch_done = True
                            # Advance progress for all remaining pages
                            progress.update(store_task, completed=len(extracted_content))
                            break  # All pages processed in batch
                        elif not _qra_batch_done:
                            progress.update(store_task, description=f"QRA: {short_path}")
                            result = _run_doc2qra(tmp_file, scope, dry_run=False)
                            extracted_n = result.get("extracted", 0) or result.get("stored", 0) or 0
                            total_qras += extracted_n
                            stats["qras"] += extracted_n

                    progress.advance(store_task)
                    if monitor:
                        active_tags = {t: c for t, c in stats["tags"].items() if c > 0}
                        monitor.update(
                            item=f"STORE: {urlparse(page_url).path[:50]}",
                            phase="store", domain=domain, scope=scope,
                            chunks=stats["chunks"], qras=stats["qras"],
                            total_qras=total_qras, total_words=stats["total_words"],
                            pages_with_tags=stats["pages_with_tags"],
                            taxonomy=active_tags,
                        )
                    time.sleep(max(1.0, delay / 1000.0))

        if used_no_qra_path and total_qras > 0:
            console.print(f"\n[bold cyan]PHASE 6: POST-HOOKS[/bold cyan]  embedding + edge proposal")
            _trigger_post_storage_hooks(scope, start_ts)

    # Final summary table
    elapsed = time.time() - start_ts
    summary = Table(title="Ingestion Summary", show_header=False, border_style="cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Value")
    summary.add_row("Domain", domain)
    summary.add_row("Scope", scope)
    summary.add_row("Pages fetched", f"{stats['fetched']} ({stats['fetch_fail']} failed)")
    summary.add_row("Pages extracted", f"{stats['extracted']} ({stats['extract_fail']} fallback)")
    if no_qra:
        summary.add_row("Chunks stored", str(total_qras))
        summary.add_row("Total words", f"{stats['total_words']:,}")
    else:
        summary.add_row("QRAs stored", str(total_qras))
    if stats["images"]:
        summary.add_row("Images", str(stats["images"]))
    if saved_files:
        summary.add_row("Saved to", str(output_dir))
    # Taxonomy coverage
    active_tags = [t for t, c in stats["tags"].items() if c > 0]
    if active_tags:
        tag_detail = ", ".join(f"{t}:{stats['tags'][t]}" for t in active_tags)
        summary.add_row("Taxonomy tags", tag_detail)
        pct = stats["pages_with_tags"] / total_pages * 100 if total_pages else 0
        summary.add_row("Tag coverage", f"{stats['pages_with_tags']}/{total_pages} pages ({pct:.0f}%)")
    summary.add_row("Duration", f"{elapsed:.1f}s ({elapsed/60:.1f}min)")
    console.print()
    console.print(summary)

    if monitor:
        monitor.finish()


# -- Memory daemon client (shared with _qra_batch.py) ----------------------


def _store_chunks_concurrent(
    chunks: list[str], page_url: str, scope: str, tags: list[str],
    max_workers: int = 5,
) -> int:
    """Store chunks concurrently via memory daemon HTTP (not subprocess).

    Uses ThreadPoolExecutor with a shared httpx client to POST /learn
    directly, eliminating ~2s subprocess overhead per chunk.
    Returns number of successfully stored chunks.
    """
    if not chunks:
        return 0

    from _qra_batch import _memory_client
    client = _memory_client()
    stored = 0

    def _store_one(chunk: str) -> bool:
        try:
            resp = client.post("/learn", json={
                "problem": f"Content from {page_url}",
                "solution": chunk,
                "scope": scope,
                "tags": tags,
            })
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("Chunk store failed: {}", exc)
            return False

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_store_one, c): c for c in chunks}
            for fut in as_completed(futures):
                if fut.result():
                    stored += 1
    finally:
        client.close()

    return stored


# -- Report command (extracted to _report.py) ------------------------------

from _report import report_command  # noqa: E402

app.command(name="report")(report_command)


if __name__ == "__main__":
    app()
