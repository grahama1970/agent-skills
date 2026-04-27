"""
QRA extraction and memory storage for /ask learn pipeline.

Handles the last two major steps:
- Step 6: Extract QRA pairs from all collected content via extractor
- Step 7: Store learning summary to memory with taxonomy bridges
- Post-pipeline: Persona profile storage and colleague discovery
"""

import json
import os
import re
import time
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from loguru import logger as log

from .monitor import AskMonitor
from .skills_exec import run_skill, parse_json_output
from .persona import (
    store_persona_profile,
    discover_colleagues,
    is_persona_sparse,
    LEARNING_DEPTHS,
)
from .taxonomy import extract_bridges_from_content, aggregate_bridges


# -------------------------------------------------------------------------
# Memory API Fallback
# -------------------------------------------------------------------------

def memory_api_fallback(problem: str, solution: str, scope: str, timeout: int = 120) -> bool:
    """Call memory service HTTP API directly when CLI times out.

    The memory CLI has a hard-coded 30s HTTP read timeout that's too short
    when taxonomy tagging (scillm) is slow. This fallback calls the API
    directly with a longer timeout using urllib (no extra dependencies).
    """
    api_url = os.environ.get("MEMORY_API_URL", "http://127.0.0.1:8601")
    payload = json.dumps({
        "problem": problem,
        "solution": solution,
        "scope": scope,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{api_url}/learn",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            ok = body.get("meta", {}).get("ok", False)
            log.debug("Memory API fallback: ok=%s, response=%s", ok, json.dumps(body)[:200])
            return ok
    except urllib.error.URLError as e:
        log.error("Memory API fallback failed: %s", e)
        return False
    except Exception as e:
        log.error("Memory API fallback error: %s", e)
        return False


# -------------------------------------------------------------------------
# QRA Extraction
# -------------------------------------------------------------------------

def run_extractor_qra(
    text: str,
    context: str,
    label: str,
    scope: str,
    topic: str,
    content_type: str = "article",
    dry_run: bool = False,
    all_bridge_extractions: Optional[list] = None,
    monitor: Optional[AskMonitor] = None,
    stats: Optional[dict] = None,
) -> int:
    """Store text as QRA using doc2qra with bridge extraction.

    Args:
        text: Content text to extract QRAs from
        context: Context label for the extractor
        label: Human-readable label for logging
        scope: Memory scope
        topic: Topic for bridge extraction context
        content_type: Type of content for bridge classification
        dry_run: If True, preview only
        all_bridge_extractions: Mutable list to append bridge results
        monitor: AskMonitor for error logging
        stats: Mutable stats dict for error tracking

    Returns:
        Number of QRA pairs extracted
    """
    if dry_run:
        print(f"    [dry-run] Would process: {label}")
        return 0

    if len(text.strip()) < 50:
        log.debug("Skipping too-short text: %s", label[:40])
        return 0

    log.debug("extractor qra processing: %s (%d chars)", label, len(text))

    # Extract Federated Taxonomy bridges from this content
    bridges = extract_bridges_from_content(text, content_type=content_type, topic=topic)
    if bridges and all_bridge_extractions is not None:
        all_bridge_extractions.append(bridges)
        log.debug("Content bridges for '%s': %s", label[:30], bridges)

    # Write text to temp markdown file with a heading
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(f"# {label}\n\n")
            if bridges:
                f.write(f"_Taxonomy Bridges: {', '.join(bridges)}_\n\n")
            f.write(text[:5000])
            temp_path = f.name

        doc2qra_args = ["--file", temp_path, "--scope", scope, "--json", "--batch"]
        if context:
            doc2qra_args.extend(["--context", context])
        qra_result = run_skill("doc2qra", doc2qra_args, timeout=300)

        Path(temp_path).unlink(missing_ok=True)

        if qra_result["returncode"] == 0:
            qra_data = parse_json_output(qra_result["stdout"])
            extracted = 0
            if qra_data and isinstance(qra_data, dict):
                extracted = qra_data.get("stored", 0) or qra_data.get("extracted", 0)
            bridge_info = f" [{', '.join(bridges)}]" if bridges else ""
            log.debug("doc2qra stored %d pairs from '%s'%s", extracted, label[:40], bridge_info)
            print(f"    Processed: {label[:50]}{bridge_info}")
            return extracted
        else:
            err = qra_result["stderr"][:60] if qra_result["stderr"] else "unknown"
            log.warning("doc2qra failed for '%s': %s", label[:40], err)
            print(f"    doc2qra failed: {label[:40]}")
            if monitor:
                monitor.log_error("doc2qra", f"'{label[:40]}': {err}")
            if stats is not None:
                stats["errors"].append(f"doc2qra:{label}:{err}")
            return 0

    except Exception as e:
        log.error("extractor qra exception for '%s': %s", label[:40], e)
        if stats is not None:
            stats["errors"].append(f"extractor:{label}:{e}")
        return 0


# -------------------------------------------------------------------------
# Extract + Store Pipeline Steps
# -------------------------------------------------------------------------

def extract_and_store(
    topic: str,
    scope: str,
    collection: str,
    depth: Optional[str],
    is_persona: bool,
    dry_run: bool,
    monitor: AskMonitor,
    stats: dict,
    dogpile_content: dict,
    books_to_process: list,
    transcripts: list,
    web_content: list,
    downloaded_books: list,
    feed_items: list,
    total_steps: int,
) -> list[str]:
    """Run QRA extraction and memory storage steps.

    Args:
        ... (see learn() for parameter docs)

    Returns:
        List of aggregated bridge attributes
    """
    all_bridge_extractions: list[list[str]] = []

    # =================================================================
    # Step 6: Extract QRA pairs via extractor_qra
    # =================================================================
    monitor.start_step("extractor_qra")
    doc_sources = (len(dogpile_content) + len(books_to_process)
                   + len(transcripts) + len(web_content)
                   + len(downloaded_books) + len(feed_items))
    _step_print(6, total_steps, f"Extracting knowledge (extractor_qra) from {doc_sources} sources...")
    log.info("Step 6: extractor_qra extraction, %d dogpile + %d books + %d transcripts + %d web",
             len(dogpile_content), len(books_to_process), len(transcripts), len(web_content))

    monitor.start_substeps(doc_sources, "Extracting QRA pairs")

    qra_total = 0

    # Helper for calling run_extractor_qra with shared params
    def _extract(text, context, label, content_type="article"):
        return run_extractor_qra(
            text, context, label, scope, topic,
            content_type=content_type,
            dry_run=dry_run,
            all_bridge_extractions=all_bridge_extractions,
            monitor=monitor,
            stats=stats,
        )

    # Process dogpile content sections (highest value)
    if dogpile_content:
        print(f"    Processing {len(dogpile_content)} dogpile sections...")
        priority_order = ["synthesis", "perplexity", "codex_overview", "arxiv", "web", "books"]
        processed_sections = set()

        for section_key in priority_order:
            if section_key in dogpile_content:
                text = dogpile_content[section_key]
                if text and len(text) > 50:
                    monitor.advance_substep(f"dogpile:{section_key}")
                    qra_total += _extract(
                        text, f"deep research ({section_key})",
                        f"dogpile:{section_key}",
                        content_type="dogpile"
                    )
                    processed_sections.add(section_key)

        for section_key, text in dogpile_content.items():
            if section_key not in processed_sections and text and len(text) > 50:
                monitor.advance_substep(f"dogpile:{section_key}")
                qra_total += _extract(
                    text, f"research ({section_key})",
                    f"dogpile:{section_key}",
                    content_type="dogpile"
                )

    # Process book descriptions
    for book in books_to_process:
        title = book.get("title", "Unknown")
        authors = book.get("authors", "Unknown")
        subjects = book.get("subjects", [])
        year = book.get("year", "")

        monitor.advance_substep(f"book:{title[:30]}")
        book_text = f"Book: {title} by {authors} ({year})\n"
        if subjects:
            book_text += f"Subjects: {', '.join(subjects[:10])}\n"
        book_text += f"Topic context: {topic}\n"

        qra_total += _extract(book_text, "expert knowledge", f"book:{title[:30]}", content_type="book")

    # Process YouTube transcripts
    for transcript in transcripts:
        source = transcript["source"]
        text = transcript["text"]
        monitor.advance_substep(f"youtube:{source[:30]}")
        qra_total += _extract(text, "lecture transcript", f"youtube:{source[:40]}", content_type="youtube")

    # Process web content
    for web_page in web_content:
        source = web_page["source"]
        title = web_page.get("title", "")
        text = web_page["text"]
        domain = web_page.get("domain", "web")
        monitor.advance_substep(f"web:{domain}")
        qra_total += _extract(text, f"article ({domain})", f"web:{title[:30]}", content_type="web")

    # Process downloaded book content
    for book in downloaded_books:
        title = book.get("title", "Unknown")
        author = book.get("author", "")
        content = book.get("content", "")
        if content and len(content) > 500:
            monitor.advance_substep(f"book:{title[:20]}")
            qra_total += _extract(
                content,
                f"book by {author}" if author else "book content",
                f"book:{title[:30]}",
                content_type="book"
            )

    # Process RSS feed items
    for feed_item in feed_items:
        title = feed_item.get("title", "")
        summary = feed_item.get("summary", "")
        source_key = feed_item.get("source_key", "rss")
        url = feed_item.get("url", "")

        feed_text = f"Title: {title}\n\n{summary}"
        if url:
            feed_text += f"\n\nSource: {url}"

        if feed_text and len(feed_text) > 100:
            monitor.advance_substep(f"feed:{source_key}")
            qra_total += _extract(
                feed_text,
                f"RSS feed ({source_key})",
                f"feed:{title[:30]}",
                content_type="feed"
            )

    stats["qra_extracted"] = qra_total

    aggregated_bridges = aggregate_bridges(all_bridge_extractions, min_count=1)
    stats["bridges_extracted"] = aggregated_bridges
    bridge_summary = f" | Bridges: {', '.join(aggregated_bridges)}" if aggregated_bridges else ""
    print(f"    Total QRA pairs extracted: {qra_total}{bridge_summary}")
    if aggregated_bridges:
        log.info("Aggregated taxonomy bridges: %s", aggregated_bridges)
    monitor.update_stats(qra_extracted=qra_total)
    monitor.complete_step("extractor_qra", success=True)

    # =================================================================
    # Step 7: Store synthesis to memory
    # =================================================================
    _store_summary(
        topic=topic,
        scope=scope,
        collection=collection,
        depth=depth,
        dry_run=dry_run,
        monitor=monitor,
        stats=stats,
        dogpile_content=dogpile_content,
        books_to_process=books_to_process,
        aggregated_bridges=aggregated_bridges,
        qra_total=qra_total,
        total_steps=total_steps,
    )

    # =================================================================
    # Store Persona Profile (if this is a person)
    # =================================================================
    if is_persona and stats["stored"] > 0 and not dry_run:
        _store_persona_and_colleagues(topic, scope, stats, monitor)

    return aggregated_bridges


def _store_summary(
    topic: str,
    scope: str,
    collection: str,
    depth: Optional[str],
    dry_run: bool,
    monitor: AskMonitor,
    stats: dict,
    dogpile_content: dict,
    books_to_process: list,
    aggregated_bridges: list[str],
    qra_total: int,
    total_steps: int,
) -> None:
    """Step 7: Store learning summary to memory."""
    monitor.start_step("store")
    _step_print(7, total_steps, "Storing learning summary to memory...")
    log.info("Step 7: Storing to memory, scope=%r", scope)

    has_new_content = (
        stats["dogpile_sections"] > 0
        or stats["books_discovered"] > 0
        or stats["books_downloaded"] > 0
        or stats["youtube_ingested"] > 0
        or stats["web_fetched"] > 0
        or stats["feeds_queried"] > 0
        or stats["arxiv_extracted"] > 0
    )

    if not dry_run and has_new_content:
        summary_problem = f"What has been learned about {topic}?"

        sources = []
        if stats["dogpile_sections"] > 0:
            sources.append(f"dogpile deep research ({stats['dogpile_sections']} content sections)")
        if stats["books_discovered"] > 0:
            book_names = ', '.join(b.get('title', '')[:30] for b in books_to_process[:5])
            sources.append(f"{stats['books_discovered']} books ({book_names})")
        if stats["youtube_ingested"] > 0:
            sources.append(f"{stats['youtube_ingested']} YouTube transcripts")
        if stats["web_fetched"] > 0:
            sources.append(f"{stats['web_fetched']} web articles")
        if stats["feeds_queried"] > 0:
            sources.append(f"{stats['feeds_queried']} RSS feed items")
        if stats["arxiv_extracted"] > 0:
            sources.append(f"{stats['arxiv_extracted']} ArXiv papers")

        # Build solution text with actual knowledge
        knowledge_text = ""
        for key in ("synthesis", "perplexity", "web"):
            text = dogpile_content.get(key, "").strip()
            if text and len(text) > 200:
                clean = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
                clean = re.sub(r"<[^>]+>", "", clean)
                clean = re.sub(r"\*\*([^*]*)\*\*", r"\1", clean)
                clean = re.sub(r"_([^_]*)_", r"\1", clean)
                clean = re.sub(r"&#x27;", "'", clean)
                clean = re.sub(r"&amp;", "&", clean)
                clean = re.sub(r"&quot;", '"', clean)
                clean = re.sub(r"#+ ", "", clean)
                clean = re.sub(r"^- ", "", clean, flags=re.MULTILINE)
                clean = re.sub(r"\s+", " ", clean).strip()
                knowledge_text = clean[:400]
                break

        bridge_text = f" Taxonomy bridges: {', '.join(aggregated_bridges)}." if aggregated_bridges else ""

        if knowledge_text:
            summary_solution = (
                f"Research on '{topic}': {knowledge_text} "
                f"(Sources: {'; '.join(sources)}).{bridge_text}"
            )
        else:
            summary_solution = (
                f"Learning session for '{topic}' in scope '{scope}': "
                f"Sources: {'; '.join(sources)}. "
                f"Extracted {stats['qra_extracted']} QRA pairs. "
                f"Collection: {collection}.{bridge_text}"
            )

        memory_args = [
            "learn",
            "--problem", summary_problem,
            "--solution", summary_solution,
            "--scope", scope,
        ]

        for bridge in aggregated_bridges:
            memory_args.extend(["--tag", f"bridge:{bridge}"])
        memory_args.extend(["--tag", f"collection:{collection}"])

        prev_timeout = os.environ.get("MEMORY_SERVICE_TIMEOUT")
        os.environ["MEMORY_SERVICE_TIMEOUT"] = "180"
        try:
            learn_result = run_skill("memory", memory_args, timeout=180)
        finally:
            if prev_timeout is not None:
                os.environ["MEMORY_SERVICE_TIMEOUT"] = prev_timeout
            else:
                os.environ.pop("MEMORY_SERVICE_TIMEOUT", None)

        if learn_result["returncode"] == 0:
            learn_data = parse_json_output(learn_result["stdout"])
            embedding_ok = False
            if learn_data and isinstance(learn_data, dict):
                embedding_ok = learn_data.get("meta", {}).get("embedding_created", False)
                if learn_data.get("errors"):
                    log.warning("Memory learn had errors: %s", learn_data["errors"])

            stats["stored"] = qra_total + 1
            embed_status = "with embedding" if embedding_ok else "WITHOUT embedding"
            bridge_tags = f", bridges: {aggregated_bridges}" if aggregated_bridges else ""
            print(f"    Stored learning summary to scope '{scope}' ({embed_status}{bridge_tags})")
            log.info("Memory learn: stored to scope=%r, embedding_created=%s, bridges=%s", scope, embedding_ok, aggregated_bridges)
            monitor.update_stats(items_stored=stats["stored"])
            monitor.complete_step("store", success=True)
        else:
            log.warning("Memory CLI failed (code=%d), trying direct API fallback",
                        learn_result["returncode"])
            api_ok = memory_api_fallback(summary_problem, summary_solution, scope)
            if api_ok:
                stats["stored"] = qra_total + 1
                print(f"    Stored learning summary to scope '{scope}' (via API fallback)")
                log.info("Memory API fallback: stored to scope=%r", scope)
                monitor.update_stats(items_stored=stats["stored"])
                monitor.complete_step("store", success=True)
            else:
                log.error("Memory learn failed: code=%d stderr=%s",
                           learn_result["returncode"], learn_result["stderr"][:100])
                print(f"    Memory storage failed: {learn_result['stderr'][:60]}")
                monitor.log_error("store", learn_result["stderr"][:200])
                monitor.complete_step("store", success=False)
    elif dry_run:
        print("    [dry-run] Would store learning summary")
        monitor.complete_step("store", success=True)
    else:
        print("    Nothing new to store")
        monitor.complete_step("store", success=True)


def _store_persona_and_colleagues(
    topic: str,
    scope: str,
    stats: dict,
    monitor: AskMonitor,
) -> None:
    """Store persona profile and discover colleagues if data is sparse."""
    sources_dict = {
        "dogpile_sections": stats["dogpile_sections"],
        "books": stats["books_discovered"],
        "youtube": stats["youtube_ingested"],
        "web": stats["web_fetched"],
    }
    if store_persona_profile(topic, scope, sources_dict, stats):
        print(f"\n  Stored persona profile for {topic}")
        log.info("Stored persona profile for '%s' in scope '%s'", topic, scope)
    else:
        log.warning("Failed to store persona profile for '%s'", topic)

    # Colleague Discovery for Sparse Personas
    if is_persona_sparse(stats):
        print(f"\n  Persona data is sparse ({stats['qra_extracted']} QRAs). Discovering colleagues...")
        log.info("Sparse persona '%s' -- discovering colleagues", topic)

        colleagues = discover_colleagues(topic, max_colleagues=3, timeout=60)

        if colleagues:
            stats["colleagues_discovered"] = [c["name"] for c in colleagues]
            print(f"  Found {len(colleagues)} colleague(s): {', '.join(c['name'] for c in colleagues)}")

            for colleague in colleagues:
                relationship_problem = f"Colleague relationship: {topic} \u2194 {colleague['name']}"
                relationship_solution = json.dumps({
                    "persona": topic,
                    "colleague": colleague["name"],
                    "relationship": colleague["relationship"],
                    "scope": scope,
                }, indent=2)

                result = run_skill("memory", [
                    "learn",
                    "--problem", relationship_problem,
                    "--solution", relationship_solution,
                    "--scope", scope,
                    "--tag", "colleague",
                    "--tag", "persona",
                    "--tag", topic.lower().replace(" ", "_"),
                    "--tag", colleague["name"].lower().replace(" ", "_"),
                ], timeout=30)

                if result["returncode"] == 0:
                    log.debug("Stored colleague relationship: %s \u2194 %s", topic, colleague["name"])
                else:
                    log.warning("Failed to store colleague relationship")

            print(f"  Tip: Learn about colleagues with: ./run.sh learn \"{colleagues[0]['name']}\" --scope {scope}")
        else:
            print("  No colleagues discovered via research")
            stats["colleagues_discovered"] = []


def _step_print(step: int, total: int, msg: str):
    """Print a progress step."""
    print(f"  [{step}/{total}] {msg}")
