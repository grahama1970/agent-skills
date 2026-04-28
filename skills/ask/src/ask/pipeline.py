"""Learning pipeline orchestration for discovery, ingestion, extraction, and memory storage."""

#!/usr/bin/env python3
"""
/ask learn pipeline -- Main learning orchestration.

Pipeline: Memory Recall -> Dogpile Discovery -> Ingest YouTube -> extractor_qra -> Memory Learn

Uses /dogpile as the primary multi-source discovery engine (Brave, Perplexity, ArXiv,
YouTube, GitHub). Falls back to discover-books when dogpile is unavailable.
Tightly integrated with /task-monitor for progress tracking.
"""

import typer
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

app = typer.Typer(help="/ask learn -- Discover and ingest knowledge about a topic")

from loguru import logger as log

from .monitor import AskMonitor
from .skills_exec import run_skill, parse_json_output, parse_memory_output
from .persona import (
    detect_persona,
    get_persona_profile,
    ask_learning_depth,
    LEARNING_DEPTHS,
)
from .sources import (
    search_nzbgeek_books,
    download_book_nzb,
    check_downloaded_book,
    extract_book_content,
    query_feed_items,
    extract_arxiv_paper,
)
from .dogpile_parse import parse_dogpile_report
from .extract_store import extract_and_store
from .dry_run_spec import build_learn_dry_run_spec, print_execution_spec
from .run_state import AskRunState, make_run_id
from .session_writer import SessionWriter


# -------------------------------------------------------------------------
# Display / Utility
# -------------------------------------------------------------------------

def step_print(step: int, total: int, msg: str):
    """Print a progress step."""
    print(f"  [{step}/{total}] {msg}")


# -------------------------------------------------------------------------
# Main Learning Pipeline
# -------------------------------------------------------------------------

def learn(
    topic: str,
    scope: str = "ask",
    collection: str = "behavioral",
    youtube_urls: Optional[list[str]] = None,
    books_only: bool = False,
    youtube_only: bool = False,
    max_books: int = 5,
    max_videos: int = 3,
    dry_run: bool = False,
    monitor: Optional[AskMonitor] = None,
    depth: Optional[str] = None,
    interactive: bool = False,
    persona_template: Optional[str] = None,
    persona_bridge: Optional[str] = None,
    persona_id: Optional[str] = None,
    run_state: Optional[AskRunState] = None,
) -> dict:
    """
    Learn about a topic by discovering, ingesting, and extracting knowledge.

    Args:
        topic: Topic to learn about
        scope: Memory scope to store in
        collection: Taxonomy collection for bridge tagging
        youtube_urls: Specific YouTube URLs to ingest
        books_only: Only discover and process books
        youtube_only: Only process YouTube content
        max_books: Maximum books to discover
        max_videos: Maximum YouTube videos to process
        dry_run: Preview without storing
        monitor: Optional AskMonitor for task-monitor integration
        depth: Learning depth ('quick', 'standard', 'deep') - overrides max_* settings
        interactive: If True, use /interview to ask about learning depth

    Returns:
        dict with summary of what was learned.
    """
    # -----------------------------------------------------------------------
    # Session Tracking (identical for personas and humans)
    # -----------------------------------------------------------------------
    session = SessionWriter(scope=scope, persona_id=persona_id)
    session.add_turn("user", f"/ask learn {topic}", metadata={
        "command": "learn",
        "scope": scope,
        "collection": collection,
        "depth": depth,
        "dry_run": dry_run,
    })

    # -----------------------------------------------------------------------
    # Persona Detection & Depth Selection
    # -----------------------------------------------------------------------
    is_persona = detect_persona(topic)

    if interactive and depth is None:
        if run_state:
            run_state.step_started("interactive_depth")
        print(f"\n  Detected {'persona' if is_persona else 'topic'}: {topic}")
        depth = ask_learning_depth(topic, is_persona=is_persona)
        print(f"  Selected depth: {depth}")
        if run_state:
            run_state.step_finished("interactive_depth", depth=depth)

    if depth and depth in LEARNING_DEPTHS:
        depth_config = LEARNING_DEPTHS[depth]
        max_videos = depth_config["max_videos"]
        max_books = depth_config["max_books"]
        print(f"\n  Learning depth: {depth} ({depth_config['estimated_time']})")
        print(f"    Max videos: {max_videos}, Max books: {max_books}")

    if is_persona:
        existing_profile = get_persona_profile(topic, scope)
        if existing_profile:
            log.info("Found existing persona profile for '%s'", topic)
            print(f"\n  Found existing persona profile for {topic}")

    stats = {
        "topic": topic,
        "scope": scope,
        "collection": collection,
        "is_persona": is_persona,
        "depth": depth or "default",
        "memory_existing": 0,
        "dogpile_sections": 0,
        "books_discovered": 0,
        "youtube_ingested": 0,
        "qra_extracted": 0,
        "stored": 0,
        "web_fetched": 0,
        "books_downloaded": 0,
        "movies_discovered": 0,
        "feeds_queried": 0,
        "arxiv_extracted": 0,
        "errors": [],
        "bridges_extracted": [],
    }
    total_steps = 7
    start_time = time.time()

    if monitor is None:
        monitor = AskMonitor(topic=topic, scope=scope, depth=depth or "quick")

    print(f"\n\u2500\u2500 /ask learn: \"{topic}\" \u2500\u2500")
    print(f"   scope={scope}  collection={collection}  depth={depth or 'default'}")
    if depth and depth in LEARNING_DEPTHS:
        print(f"   {monitor.get_eta_display()}")
    if dry_run:
        print("   [DRY RUN \u2014 no changes will be stored]")
    print()

    # =====================================================================
    # Step 1: Memory First -- check what we already know
    # =====================================================================
    monitor.start_step("memory_check")
    if run_state:
        run_state.step_started("learn_memory_check", scope=scope)
    step_print(1, total_steps, "Checking memory for existing knowledge...")
    log.info("Step 1: Memory recall for topic=%r scope=%r", topic, scope)

    recall_result = run_skill("memory", [
        "recall",
        "--q", f"{topic} {collection}",
        "--scope", scope,
        "--k", "5",
    ], timeout=30)

    if recall_result["returncode"] == 0:
        items = parse_memory_output(recall_result["stdout"])
        stats["memory_existing"] = len(items)
        if items:
            print(f"    Found {len(items)} existing knowledge items")
            for item in items[:3]:
                problem = item.get("problem", "")[:60]
                print(f"      - {problem}")
        else:
            print("    No existing knowledge \u2014 starting fresh")
        log.info("Memory recall: %d existing items", len(items))
        monitor.complete_step("memory_check", success=True)
        if run_state:
            run_state.step_finished("learn_memory_check", returncode=0, items_count=len(items))
    else:
        log.warning("Memory recall failed: code=%d stderr=%s",
                     recall_result["returncode"], recall_result["stderr"][:100])
        print(f"    Memory unavailable: {recall_result['stderr'][:80]}")
        monitor.log_error("memory_check", recall_result["stderr"][:200])
        monitor.complete_step("memory_check", success=False)
        if run_state:
            run_state.step_finished("learn_memory_check", returncode=recall_result["returncode"], error=recall_result["stderr"][:200])

    # =====================================================================
    # Step 2: Dogpile Discovery (multi-source deep research)
    # =====================================================================
    books_to_process = []
    dogpile_content = {}
    dogpile_youtube_urls = []
    dogpile_web_urls = []
    monitor.start_step("dogpile")
    if run_state:
        run_state.step_started("learn_discovery", youtube_only=youtube_only)

    if not youtube_only:
        step_print(2, total_steps, f"Deep research via /dogpile: \"{topic}\"...")
        log.info("Step 2: Dogpile discovery for topic=%r", topic)

        dogpile_result = run_skill("dogpile", [
            "search", topic,
            "--no-interactive",
        ], timeout=600)

        dogpile_success = False
        if dogpile_result["returncode"] == 0 and dogpile_result["stdout"].strip():
            report_text = dogpile_result["stdout"]
            log.info("Dogpile returned %d bytes of content", len(report_text))

            parsed = parse_dogpile_report(report_text)

            dogpile_youtube_urls = parsed["youtube_urls"]
            if dogpile_youtube_urls:
                print(f"    Found {len(dogpile_youtube_urls)} YouTube videos:")
                for yt in dogpile_youtube_urls[:5]:
                    print(f"      - {yt['title'][:60]}")
                log.info("Dogpile found %d YouTube URLs", len(dogpile_youtube_urls))

            dogpile_content = parsed["content_sections"]
            section_names = list(dogpile_content.keys())
            if section_names:
                print(f"    Content sections: {', '.join(section_names)}")
                log.info("Dogpile content sections: %s", section_names)

            if parsed["arxiv_papers"]:
                print(f"    ArXiv papers: {len(parsed['arxiv_papers'])}")
                for paper in parsed["arxiv_papers"][:3]:
                    print(f"      - {paper[:60]}")

            if parsed["synthesis"]:
                print(f"    Codex synthesis: {len(parsed['synthesis'])} chars")

            dogpile_web_urls = parsed.get("web_urls", [])
            if dogpile_web_urls:
                print(f"    Web URLs for fetching: {len(dogpile_web_urls)}")
                for web in dogpile_web_urls[:3]:
                    print(f"      - {web['domain']}: {web['title'][:40]}")
                log.info("Dogpile found %d web URLs for fetching", len(dogpile_web_urls))

            dogpile_success = bool(dogpile_content or dogpile_youtube_urls)
            stats["dogpile_sections"] = len(dogpile_content)

        elif dogpile_result.get("skipped"):
            log.warning("Dogpile skill not found, will use discover-books")
            print("    /dogpile not available \u2014 using discover-books")
        else:
            log.warning("Dogpile failed (code=%d): %s",
                        dogpile_result["returncode"],
                        dogpile_result["stderr"][:200] if dogpile_result["stderr"] else "unknown")
            print("    Dogpile failed \u2014 using discover-books")
            monitor.log_error("dogpile", dogpile_result["stderr"][:200] if dogpile_result["stderr"] else "unknown")

        # Always use discover-books for personas (not just as fallback)
        if max_books > 0 and (is_persona or not dogpile_success):
            log.info("Using discover-books for topic=%r max_books=%d", topic, max_books)
            print(f"    Searching for books about {topic}...")

            book_result = run_skill("discover-books", [
                "search-subject", topic,
                "--limit", str(max_books),
                "--json",
            ], timeout=30)

            if book_result["returncode"] == 0 and book_result["stdout"].strip():
                book_data = parse_json_output(book_result["stdout"])
                if book_data and isinstance(book_data, dict):
                    results = book_data.get("results", [])
                    stats["books_discovered"] = len(results)
                    if results:
                        print(f"    Found {len(results)} books:")
                        for b in results[:max_books]:
                            title = b.get("title", "Unknown")[:50]
                            author = b.get("authors", "Unknown")[:30]
                            print(f"      - {title} by {author}")
                            books_to_process.append(b)

            if not books_to_process:
                author_result = run_skill("discover-books", [
                    "by-author", topic,
                    "--limit", str(max_books),
                    "--json",
                ], timeout=30)

                if author_result["returncode"] == 0 and author_result["stdout"].strip():
                    author_data = parse_json_output(author_result["stdout"])
                    if author_data and isinstance(author_data, dict):
                        results = author_data.get("results", [])
                        stats["books_discovered"] = len(results)
                        for b in results[:max_books]:
                            books_to_process.append(b)
                            print(f"      - {b.get('title', 'Unknown')[:50]}")

        # Query pre-ingested RSS feeds
        feed_items = []
        feed_limit = 5 if depth == "deep" else 3
        print(f"    Querying RSS feed items about {topic}...")

        feed_results = query_feed_items(topic, limit=feed_limit)
        if feed_results:
            stats["feeds_queried"] = len(feed_results)
            print(f"    Found {len(feed_results)} relevant RSS items:")
            for item in feed_results[:3]:
                title = item.get("title", "")[:50]
                source = item.get("source_key", "unknown")
                print(f"      - [{source}] {title}")
            feed_items = feed_results
            log.info("RSS feed query found %d items for topic '%s'", len(feed_results), topic)
        else:
            print("    No relevant RSS feed items found")

        # Extract ArXiv papers (standard/deep mode)
        arxiv_papers = parsed.get("arxiv_papers", []) if dogpile_success else []
        arxiv_max = LEARNING_DEPTHS.get(depth or "quick", {}).get("arxiv_papers", 0)

        if arxiv_papers and arxiv_max > 0 and depth in ("standard", "deep"):
            papers_to_extract = arxiv_papers[:arxiv_max]
            print(f"    Extracting {len(papers_to_extract)} ArXiv papers...")

            for paper in papers_to_extract:
                arxiv_id = paper.get("arxiv_id", "")
                title = paper.get("title", "")[:50]
                if arxiv_id:
                    print(f"      Extracting: {title} ({arxiv_id})...")
                    extract_result = extract_arxiv_paper(
                        arxiv_id, scope=scope, context=topic, skip_interview=True,
                    )
                    if extract_result.get("success"):
                        stats["arxiv_extracted"] += 1
                        qra_count = extract_result.get("qra_count", 0)
                        print(f"        Extracted {qra_count} QRA pairs")
                    else:
                        print(f"        Failed: {extract_result.get('error', 'unknown')[:40]}")
                        monitor.log_error("arxiv", f"{arxiv_id}: {extract_result.get('error', '')[:100]}")

            log.info("ArXiv extraction: %d papers extracted", stats["arxiv_extracted"])
        elif arxiv_papers:
            print(f"    Found {len(arxiv_papers)} ArXiv papers (skipping extraction - depth={depth})")

        monitor.update_stats(books_discovered=stats["books_discovered"], feeds_queried=stats["feeds_queried"], arxiv_extracted=stats["arxiv_extracted"])
        monitor.complete_step("dogpile", success=dogpile_success or bool(books_to_process) or bool(feed_items) or bool(stats["arxiv_extracted"]))
        if run_state:
            run_state.step_finished(
                "learn_discovery",
                dogpile_success=dogpile_success,
                dogpile_sections=stats["dogpile_sections"],
                books_discovered=stats["books_discovered"],
                feeds_queried=stats["feeds_queried"],
                arxiv_extracted=stats["arxiv_extracted"],
            )
    else:
        step_print(2, total_steps, "Skipping discovery (--youtube-only)")
        feed_items = []
        monitor.complete_step("dogpile", success=True)
        if run_state:
            run_state.step_finished("learn_discovery", skipped=True)

    # =====================================================================
    # Step 3: Download Books (ops-nzbgeek/ingest-book) - deep learning only
    # =====================================================================
    downloaded_books = []
    monitor.start_step("download_books")
    if run_state:
        run_state.step_started("learn_download_books")

    download_books_enabled = (
        (is_persona and max_books > 0)  # Personas always download discovered books
        or (depth == "deep" and LEARNING_DEPTHS.get("deep", {}).get("download_books", False))
    )

    if download_books_enabled and books_to_process and not youtube_only:
        step_print(3, total_steps, f"Downloading books via NZBGeek ({len(books_to_process)} discovered)...")
        log.info("Step 3: Book download, %d books discovered", len(books_to_process))

        monitor.start_substeps(len(books_to_process), "Downloading books")

        for book_info in books_to_process[:max_books]:
            title = book_info.get("title", "Unknown")
            author = book_info.get("authors", "")
            search_term = f"{title} {author}".strip()

            monitor.advance_substep(title[:30])
            print(f"    Searching NZBGeek for: {title[:50]}...")

            existing_path = check_downloaded_book(title)
            if existing_path:
                print(f"      Already downloaded: {existing_path}")
                content = extract_book_content(existing_path)
                if content:
                    downloaded_books.append({
                        "title": title, "author": author,
                        "path": existing_path, "content": content[:20000],
                        "source": "readarr_library",
                    })
                    stats["books_downloaded"] = stats.get("books_downloaded", 0) + 1
                    print(f"      Extracted {len(content)} chars")
                continue

            nzb_results = search_nzbgeek_books(search_term, limit=3)

            if nzb_results:
                best_result = None
                for nzb in nzb_results:
                    nzb_title = nzb.get("title", "").lower()
                    if "audiobook" not in nzb_title and "audio" not in nzb_title:
                        best_result = nzb
                        break
                if not best_result:
                    best_result = nzb_results[0]

                nzb_link = best_result.get("link", "")
                nzb_title = best_result.get("title", title)

                if nzb_link:
                    print(f"      Found: {nzb_title[:50]}")
                    download_result = download_book_nzb(nzb_link, nzb_title)

                    if download_result.get("success"):
                        print("      Download initiated via SABnzbd")
                        stats["books_downloaded"] = stats.get("books_downloaded", 0) + 1
                    else:
                        print(f"      Download failed: {download_result.get('error', 'unknown')[:50]}")
                        monitor.log_error("download_books", f"{title}: {download_result.get('error', '')[:100]}")
                else:
                    print("      No download link available")
            else:
                print("      Not found on NZBGeek")

        monitor.update_stats(books_downloaded=stats.get("books_downloaded", 0))
        monitor.complete_step("download_books", success=True)
        if run_state:
            run_state.step_finished("learn_download_books", books_downloaded=stats.get("books_downloaded", 0))
    else:
        if not download_books_enabled:
            step_print(3, total_steps, "Skipping book download (requires deep mode or persona)")
        else:
            step_print(3, total_steps, "No books to download")
        monitor.complete_step("download_books", success=True)
        if run_state:
            run_state.step_finished("learn_download_books", skipped=True)

    # =====================================================================
    # Step 4: Ingest YouTube Transcripts
    # =====================================================================
    transcripts = []
    monitor.start_step("ingest_youtube")
    if run_state:
        run_state.step_started("learn_ingest_youtube", books_only=books_only)

    if not books_only:
        all_youtube_urls = list(youtube_urls or [])

        if is_persona and depth in ("standard", "deep"):
            print(f"    Searching for more lectures by {topic}...")
            search_max = 10 if depth == "deep" else 5

            search_result = run_skill("ingest-youtube", [
                "search", f'"{topic}" lecture',
                "-n", str(search_max),
                "--no-interactive",
            ], timeout=60)

            if search_result["returncode"] == 0 and search_result["stdout"].strip():
                search_output = search_result["stdout"]
                found_urls = re.findall(r'https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]+', search_output)
                found_urls += re.findall(r'https?://youtu\.be/[a-zA-Z0-9_-]+', search_output)

                existing_ids = {url.split("v=")[-1].split("&")[0] for url in all_youtube_urls if "v=" in url}
                for url in found_urls:
                    vid_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
                    if vid_id not in existing_ids:
                        all_youtube_urls.append(url)
                        existing_ids.add(vid_id)

                new_count = len(all_youtube_urls) - len(dogpile_youtube_urls) - len(youtube_urls or [])
                if new_count > 0:
                    print(f"    Found {new_count} additional lectures via search")
                    log.info("YouTube search found %d additional videos for persona", new_count)

        seen_urls = set(all_youtube_urls)
        for yt in dogpile_youtube_urls:
            url = yt["url"]
            if url not in seen_urls:
                all_youtube_urls.append(url)
                seen_urls.add(url)

        step_print(4, total_steps, f"Ingesting YouTube content ({len(all_youtube_urls)} URLs)...")
        log.info("Step 4: YouTube ingestion, %d URLs (%d from dogpile, %d manual)",
                 len(all_youtube_urls), len(dogpile_youtube_urls), len(youtube_urls or []))

        if all_youtube_urls:
            urls_to_process = all_youtube_urls[:max_videos]
            monitor.start_substeps(len(urls_to_process), "YouTube transcripts")

            for url in urls_to_process:
                print(f"    Processing: {url}")
                monitor.advance_substep(url[:50])
                log.debug("Ingesting YouTube URL: %s", url)
                yt_result = run_skill("ingest-youtube", [url], timeout=120)

                stdout = yt_result.get("stdout", "").strip()
                yt_data = parse_json_output(stdout) if stdout else None

                if yt_data and isinstance(yt_data, dict):
                    full_text = yt_data.get("full_text", "")
                    yt_errors = yt_data.get("errors", [])

                    if yt_errors:
                        for yt_err in yt_errors[:3]:
                            log.warning("YouTube error for %s: %s", url, str(yt_err)[:120])

                    if full_text:
                        transcripts.append({"source": url, "text": full_text[:10000], "type": "youtube"})
                        stats["youtube_ingested"] += 1
                        status = "partial" if yt_result["returncode"] != 0 else "full"
                        print(f"      Got transcript ({len(full_text)} chars, {status})")
                        log.info("YouTube transcript: %d chars from %s (code=%d)",
                                 len(full_text), url, yt_result["returncode"])
                    else:
                        err_summary = yt_errors[0] if yt_errors else "no transcript text"
                        print(f"      No transcript: {str(err_summary)[:60]}")
                        log.warning("YouTube had no full_text: errors=%s", yt_errors)
                        stats["errors"].append(f"youtube:{url}:no_transcript")
                        monitor.log_error("ingest_youtube", f"{url}: {str(err_summary)[:100]}")
                elif stdout and len(stdout) > 100:
                    transcripts.append({"source": url, "text": stdout[:10000], "type": "youtube"})
                    stats["youtube_ingested"] += 1
                    print(f"      Got transcript ({len(stdout)} chars, raw text)")
                    log.info("YouTube raw text: %d chars from %s", len(stdout), url)
                else:
                    err = yt_result["stderr"][:80] if yt_result["stderr"] else "unknown error"
                    print(f"      Failed: {err}")
                    log.error("YouTube ingestion failed for %s: code=%d err=%s",
                              url, yt_result["returncode"], err)
                    stats["errors"].append(f"youtube:{url}:{err}")
                    monitor.log_error("ingest_youtube", f"{url}: {err}")
        else:
            print("    No YouTube URLs discovered or provided")
            if not dogpile_content:
                print("    Tip: use --youtube <url> to provide specific lecture URLs")

        monitor.update_stats(youtube_ingested=stats["youtube_ingested"])
        monitor.complete_step("ingest_youtube", success=True)
        if run_state:
            run_state.step_finished("learn_ingest_youtube", youtube_ingested=stats["youtube_ingested"])
    else:
        step_print(4, total_steps, "Skipping YouTube (--books-only)")
        monitor.complete_step("ingest_youtube", success=True)
        if run_state:
            run_state.step_finished("learn_ingest_youtube", skipped=True)

    # =====================================================================
    # Step 5: Fetch Web Content (blogs, articles)
    # =====================================================================
    web_content = []
    monitor.start_step("fetch_web")
    if run_state:
        run_state.step_started("learn_fetch_web")

    max_web_pages = 5 if depth == "deep" else 3
    if dogpile_web_urls and not books_only:
        step_print(5, total_steps, f"Fetching web content ({len(dogpile_web_urls)} URLs)...")
        log.info("Step 5: Fetching %d web URLs", len(dogpile_web_urls))

        urls_to_fetch = dogpile_web_urls[:max_web_pages]
        monitor.start_substeps(len(urls_to_fetch), "Web articles")

        for web_info in urls_to_fetch:
            url = web_info["url"]
            monitor.advance_substep(url[:50])
            title = web_info["title"]
            domain = web_info.get("domain", "unknown")

            print(f"    Fetching: {domain} - {title[:40]}...")
            log.debug("Fetching web URL: %s", url)

            fetch_result = run_skill("fetcher", [url, "--format", "markdown"], timeout=60)

            if fetch_result["returncode"] == 0 and fetch_result["stdout"].strip():
                content = fetch_result["stdout"].strip()
                if len(content) > 200:
                    web_content.append({
                        "source": url, "title": title,
                        "text": content[:10000], "type": "web", "domain": domain,
                    })
                    stats["web_fetched"] += 1
                    print(f"      Got content ({len(content)} chars)")
                    log.info("Web fetched: %d chars from %s", len(content), url)
                else:
                    print(f"      Content too short ({len(content)} chars)")
            else:
                err = fetch_result["stderr"][:60] if fetch_result["stderr"] else "fetch failed"
                print(f"      Failed: {err}")
                log.warning("Web fetch failed for %s: %s", url, err)

        monitor.update_stats(web_fetched=stats["web_fetched"])
        monitor.complete_step("fetch_web", success=True)
        if run_state:
            run_state.step_finished("learn_fetch_web", web_fetched=stats["web_fetched"])
    else:
        step_print(5, total_steps, "No web URLs to fetch")
        monitor.complete_step("fetch_web", success=True)
        if run_state:
            run_state.step_finished("learn_fetch_web", skipped=True)

    # =====================================================================
    # Step 5b: Movie Discovery (fictional personas only)
    # =====================================================================
    if persona_template == "fictional" and not books_only and not youtube_only:
        bridge_for_search = persona_bridge or "Fragility"  # default bridge for fictional
        print(f"\n    Discovering movies for fictional persona (bridge: {bridge_for_search})...")
        log.info("Discovering movies for fictional persona '%s' via bridge '%s'", topic, bridge_for_search)

        movie_result = run_skill("discover-movies", [
            "bridge", bridge_for_search,
            "--limit", "3",
            "--json",
        ], timeout=60)

        if movie_result["returncode"] == 0 and movie_result["stdout"].strip():
            movie_data = parse_json_output(movie_result["stdout"])
            if movie_data:
                movies = movie_data.get("results", []) if isinstance(movie_data, dict) else movie_data
                if isinstance(movies, list):
                    stats["movies_discovered"] = len(movies[:3])
                    for movie in movies[:3]:
                        title = movie.get("title", "Unknown")
                        year = movie.get("year", "")
                        print(f"      Movie: {title} ({year})")
                        log.info("Discovered movie for persona: %s (%s)", title, year)
        elif not movie_result.get("skipped"):
            log.warning("Movie discovery failed: %s",
                        movie_result["stderr"][:100] if movie_result["stderr"] else "unknown")
            print("    Movie discovery unavailable")

    # =====================================================================
    # Steps 6-7: Extract QRA + Store (delegated to extract_store module)
    # =====================================================================
    if run_state:
        run_state.step_started("learn_extract_store", dry_run=dry_run)
    extract_and_store(
        topic=topic,
        scope=scope,
        collection=collection,
        depth=depth,
        is_persona=is_persona,
        dry_run=dry_run,
        monitor=monitor,
        stats=stats,
        dogpile_content=dogpile_content,
        books_to_process=books_to_process,
        transcripts=transcripts,
        web_content=web_content,
        downloaded_books=downloaded_books,
        feed_items=feed_items,
        total_steps=total_steps,
    )
    if run_state:
        run_state.step_finished("learn_extract_store", qra_extracted=stats["qra_extracted"], stored=stats["stored"])

    # =====================================================================
    # Summary
    # =====================================================================
    elapsed = time.time() - start_time

    print(f"\n\u2500\u2500 Learning Complete ({elapsed:.1f}s) \u2500\u2500")
    print(f"   Topic:       {topic}")
    print(f"   Scope:       {scope}")
    print(f"   Collection:  {collection}")
    print(f"   Persona:     {'yes' if is_persona else 'no'}")
    print(f"   Existing:    {stats['memory_existing']} items already known")
    print(f"   Dogpile:     {stats['dogpile_sections']} content sections")
    print(f"   Books:       {stats['books_discovered']} discovered")
    if stats.get("movies_discovered"):
        print(f"   Movies:      {stats['movies_discovered']} discovered")
    print(f"   YouTube:     {stats['youtube_ingested']} transcripts ingested")
    print(f"   Web:         {stats['web_fetched']} articles fetched")
    print(f"   Extracted:   {stats['qra_extracted']} QRA pairs")
    print(f"   Stored:      {stats['stored']} items")
    if stats.get("bridges_extracted"):
        print(f"   Bridges:     {', '.join(stats['bridges_extracted'])}")
    if stats["errors"]:
        print(f"   Errors:      {len(stats['errors'])}")
        for err in stats["errors"][:3]:
            print(f"     - {err[:80]}")
    print()

    log.info("Learn complete: topic=%r elapsed=%.1fs stored=%d errors=%d",
             topic, elapsed, stats["stored"], len(stats["errors"]))

    success = len(stats["errors"]) == 0
    monitor.finish(success=success)

    # Write session transcript (identical for personas and humans)
    session.add_turn("assistant", f"Learning complete for '{topic}'", metadata={
        "stored": stats["stored"],
        "qra_extracted": stats["qra_extracted"],
        "dogpile_sections": stats["dogpile_sections"],
        "youtube_ingested": stats["youtube_ingested"],
        "books_discovered": stats["books_discovered"],
        "web_fetched": stats["web_fetched"],
        "errors": len(stats["errors"]),
        "elapsed": elapsed,
        "success": success,
    })
    session_path = session.write()
    if session_path:
        stats["session_path"] = str(session_path)
    if run_state:
        run_state.event("session_written", session_path=stats.get("session_path", ""))

    return stats


_default_scope = os.environ.get("ASK_DEFAULT_SCOPE", "ask")
_default_max_books = int(os.environ.get("ASK_MAX_BOOKS", "5"))
_default_max_videos = int(os.environ.get("ASK_MAX_VIDEOS", "3"))


@app.command()
def main(
    topic: str = typer.Argument(..., help="Topic to learn about"),
    scope: str = typer.Option(_default_scope, help="Memory scope (default: ask)"),
    collection: str = typer.Option("behavioral", help="Taxonomy collection (default: behavioral)"),
    youtube: Optional[list[str]] = typer.Option(None, help="YouTube URL(s) to ingest (can repeat)"),
    books_only: bool = typer.Option(False, "--books-only", help="Only discover and process books"),
    youtube_only: bool = typer.Option(False, "--youtube-only", help="Only process YouTube content"),
    max_books: int = typer.Option(_default_max_books, "--max-books", help="Max books to discover (default: 5)"),
    max_videos: int = typer.Option(_default_max_videos, "--max-videos", help="Max YouTube videos to process (default: 3)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without storing"),
    depth: Optional[str] = typer.Option(None, help="Learning depth (quick, standard, deep)"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="Use /interview to ask about learning preferences"),
    persona_template: Optional[str] = typer.Option(None, "--persona-template", help="Persona template type (expert, fictional, coder, etc.)"),
    persona_bridge: Optional[str] = typer.Option(None, "--persona-bridge", help="Persona's primary bridge attribute for content discovery"),
    persona_id: Optional[str] = typer.Option(None, "--persona-id", help="Persona identifier for session tracking (None for human)"),
    ask_id: Optional[str] = typer.Option(None, "--ask-id", help="Stable runtime artifact id for this learn call"),
    run_output_root: Optional[str] = typer.Option(None, "--run-output-root", help="Directory for runtime artifacts"),
    overwrite_run: bool = typer.Option(False, "--overwrite", help="Replace an existing run directory for --ask-id"),
    resume_run: bool = typer.Option(False, "--resume", help="Resume a non-terminal existing run directory for --ask-id"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    """/ask learn -- Discover and ingest knowledge about a topic."""
    if debug:
        log.enable("")

    request = {
        "command": "learn",
        "topic": topic,
        "scope": scope,
        "collection": collection,
        "youtube": youtube or [],
        "books_only": books_only,
        "youtube_only": youtube_only,
        "max_books": max_books,
        "max_videos": max_videos,
        "dry_run": dry_run,
        "depth": depth,
        "interactive": interactive,
        "persona_template": persona_template,
        "persona_bridge": persona_bridge,
        "persona_id": persona_id,
    }
    if dry_run:
        print_execution_spec(build_learn_dry_run_spec(request))
        raise typer.Exit(code=0)

    run_state = AskRunState(
        ask_id or make_run_id(f"learn {topic}"),
        output_root=run_output_root,
        overwrite=overwrite_run,
        resume=resume_run,
    )
    run_state.write_request(request)
    try:
        stats = learn(
            topic=topic,
            scope=scope,
            collection=collection,
            youtube_urls=youtube,
            books_only=books_only,
            youtube_only=youtube_only,
            max_books=max_books,
            max_videos=max_videos,
            dry_run=dry_run,
            depth=depth,
            interactive=interactive,
            persona_template=persona_template,
            persona_bridge=persona_bridge,
            persona_id=persona_id,
            run_state=run_state,
        )
    except Exception as exc:
        run_state.fail(exc)
        raise
    run_state.finish(stats, state="completed" if stats.get("stored", 0) > 0 or stats.get("memory_existing", 0) > 0 or dry_run else "no_results")

    if not (stats["stored"] > 0 or stats["memory_existing"] > 0):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
