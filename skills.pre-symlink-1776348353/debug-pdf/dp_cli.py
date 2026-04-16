"""
CLI commands for debug-pdf.

Commands: main (analyze URL), batch, fidelity, combine,
verify-ordering, recall, learn, detectors.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import fitz
import typer
from loguru import logger

from dp_app import app
from dp_config import (
    SKILL_DIR, DATA_DIR, SESSIONS_DIR, FIXTURES_DIR,
    TASK_MONITOR_AVAILABLE, DebugPdfTaskClient,
)
from dp_registry import PAGE_DETECTORS, DOC_DETECTORS, PATTERNS
from dp_core import (
    download_pdf, analyze_pdf, generate_fixture,
    run_extractor_on_repro, send_to_inbox, memory_recall,
    memory_learn, save_session,
)


@app.command()
def main(
    url: str = typer.Option(..., "--url", help="URL of the failed PDF"),
    repro: bool = typer.Option(True, "--repro/--no-repro", help="Generate reproduction fixture"),
    send_inbox: bool = typer.Option(False, "--send-inbox", help="Send results to extractor inbox"),
):
    """Analyze a single failed PDF URL."""
    # Use unique temp file to avoid race conditions
    tmp_pdf = SKILL_DIR / f"temp_failed_{uuid4().hex}.pdf"

    # Check for Wayback URL pattern
    original_url = None
    if is_wayback_url(url):
        original_url = extract_original_url(url)
        logger.info(f"Detected Archive.org Wayback URL. Original: {original_url}")

    try:
        # URL validation happens in download_pdf
        download_success, download_patterns = download_pdf(url, tmp_pdf)

        if not download_success:
            # Even if download failed, we detected patterns
            if download_patterns:
                report = {
                    "pages": 0,
                    "is_scanned": False,
                    "patterns": download_patterns,
                    "cursed_content": [(p, f"Detected during download: {url}") for p in download_patterns],
                    "file_size_kb": 0
                }
                session_id = save_session(url, report, None)
                msg = f"DEBUG-PDF ANALYSIS [{session_id}]\n"
                msg += f"URL: {url}\n"
                msg += f"Download blocked - Patterns: {', '.join(download_patterns)}\n"
                print(msg)
                if send_inbox:
                    send_to_inbox(msg)
                raise typer.Exit(0)  # Not an error, we detected patterns
            logger.error("Failed to download PDF")
            raise typer.Exit(1)

        report = analyze_pdf(tmp_pdf)

        # Add download-detected patterns
        for p in download_patterns:
            if p not in report["patterns"]:
                report["patterns"].append(p)

        # Add archive_org_wrap pattern if detected
        if original_url:
            report["patterns"].append("archive_org_wrap")
            report["cursed_content"].append(("archive_org_wrap", f"Original URL: {original_url}"))
        logger.info(f"Analysis complete: {len(report.get('patterns', []))} patterns detected")

        fixture_path = None
        if repro:
            fixture_name = f"repro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            fixture_path = FIXTURES_DIR / fixture_name
            fixture_path = generate_fixture(report, fixture_path)

        session_id = save_session(url, report, fixture_path)

        # Build result message
        msg = f"DEBUG-PDF ANALYSIS [{session_id}]\n"
        msg += f"URL: {url}\n"
        msg += f"Pages: {report['pages']}\n"
        msg += f"Scanned: {report['is_scanned']}\n"
        msg += f"Patterns: {', '.join(report['patterns']) if report['patterns'] else 'None'}\n"

        if fixture_path:
            msg += f"\nFixture: {fixture_path.name}\n"

            if EXTRACTOR_RUN:
                verif = run_extractor_on_repro(fixture_path)
                msg += f"Verification: {'PASS' if verif['success'] else 'FAIL'}\n"
                if not verif['success'] and verif.get('error'):
                    msg += f"Error: {verif['error']}\n"

        print(msg)

        if send_inbox:
            send_to_inbox(msg)

    finally:
        if tmp_pdf.exists():
            tmp_pdf.unlink()


@app.command()
def batch(
    file: Path = typer.Option(..., "--file", help="File containing URLs (one per line)"),
    output: Path = typer.Option(None, "--output", help="Output JSON report path"),
    send_inbox: bool = typer.Option(False, "--send-inbox", help="Send summary to inbox"),
    json_stream: bool = typer.Option(False, "--json-stream", help="Output NDJSON per PDF (streaming progress)"),
    task_monitor: bool = typer.Option(True, "--task-monitor/--no-task-monitor", help="Enable/disable task-monitor integration"),
):
    """Analyze multiple failed PDF URLs from a file.

    Use --json-stream for NDJSON output (one JSON object per line) for real-time
    monitoring of long-running batch jobs.

    Task-monitor integration writes progress to debug_pdf_task_state.json
    which can be viewed via task-monitor TUI.
    """
    if not file.exists():
        logger.error(f"URL file not found: {file}")
        raise typer.Exit(1)

    # Validate output path parent if provided
    if output:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            if not os.access(str(output.parent), os.W_OK):
                raise PermissionError("No write permission")
        except Exception as e:
            logger.error(f"Cannot write to output directory {output.parent}: {e}")
            raise typer.Exit(1)

    urls = [line.strip() for line in file.read_text().splitlines() if line.strip() and not line.startswith("#")]

    if not json_stream:
        logger.info(f"Processing {len(urls)} URLs...")

    # Initialize task monitor
    monitor = None
    if task_monitor and TASK_MONITOR_AVAILABLE and DebugPdfTaskClient:
        task_name = f"batch-{len(urls)}"
        monitor = DebugPdfTaskClient(task_name, total_pdfs=len(urls), description=f"Batch PDF analysis ({len(urls)} URLs)")

    results = []
    pattern_counts = {}

    for i, url in enumerate(urls, 1):
        if not json_stream:
            logger.info(f"[{i}/{len(urls)}] {url}")
        # Use unique temp file to avoid race conditions
        tmp_pdf = SKILL_DIR / f"temp_{i}_{uuid4().hex}.pdf"

        result_entry = {
            "url": url,
            "patterns": [],
            "pages": 0,
            "fixture": None,
            "success": False,
            "error": None,
        }

        try:
            # Validate URL before attempting download
            if not is_valid_url(url):
                result_entry["patterns"] = ["invalid_url"]
                result_entry["error"] = "Invalid URL"
                results.append(result_entry)

                if monitor:
                    monitor.update(url=url, download_success=False, patterns_detected=["invalid_url"], error="Invalid URL")

                if json_stream:
                    print(json.dumps(result_entry), flush=True)
                continue

            download_success, download_patterns = download_pdf(url, tmp_pdf)

            if download_success:
                report = analyze_pdf(tmp_pdf)
                # Add download-detected patterns
                for p in download_patterns:
                    if p not in report.get("patterns", []):
                        report["patterns"].append(p)
                fixture_name = f"batch_{i}_{datetime.now().strftime('%H%M%S')}.pdf"
                fixture_path = FIXTURES_DIR / fixture_name
                fixture_path = generate_fixture(report, fixture_path)

                result_entry = {
                    "url": url,
                    "patterns": report.get("patterns", []),
                    "pages": report.get("pages", 0),
                    "fixture": str(fixture_path) if fixture_path else None,
                    "success": True,
                    "error": None,
                }

                for p in report.get("patterns", []):
                    pattern_counts[p] = pattern_counts.get(p, 0) + 1

                if monitor:
                    monitor.update(
                        url=url,
                        download_success=True,
                        patterns_detected=report.get("patterns", []),
                        pages=report.get("pages", 0),
                        fixture_generated=fixture_path is not None,
                    )
            else:
                # Download failed but may have detected patterns
                detected_patterns = download_patterns if download_patterns else ["download_failed"]
                result_entry = {
                    "url": url,
                    "patterns": detected_patterns,
                    "pages": 0,
                    "fixture": None,
                    "success": False,
                    "error": "Download failed",
                }
                for p in download_patterns:
                    pattern_counts[p] = pattern_counts.get(p, 0) + 1

                if monitor:
                    monitor.update(
                        url=url,
                        download_success=False,
                        patterns_detected=detected_patterns,
                        error="Download failed",
                    )
        except Exception as e:
            result_entry = {
                "url": url,
                "patterns": ["analysis_error"],
                "pages": 0,
                "fixture": None,
                "success": False,
                "error": str(e),
            }

            if monitor:
                monitor.update(
                    url=url,
                    download_success=False,
                    patterns_detected=["analysis_error"],
                    error=str(e),
                )
        finally:
            if tmp_pdf.exists():
                tmp_pdf.unlink()

        results.append(result_entry)

        # Output NDJSON if requested
        if json_stream:
            print(json.dumps(result_entry), flush=True)

    # Finish task monitor
    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count

    if monitor:
        monitor.finish(success=fail_count == 0)

    # Generate report
    batch_report = {
        "timestamp": datetime.now().isoformat(),
        "total": len(urls),
        "success": success_count,
        "failed": fail_count,
        "pattern_counts": pattern_counts,
        "results": results
    }

    if output:
        output.write_text(json.dumps(batch_report, indent=2))
        if not json_stream:
            logger.info(f"Report saved to {output}")

    # Print summary (unless streaming)
    if not json_stream:
        print(f"\n=== BATCH ANALYSIS COMPLETE ===")
        print(f"Total: {batch_report['total']}")
        print(f"Success: {batch_report['success']}")
        print(f"Failed: {batch_report['failed']}")
        print(f"\nPattern Distribution:")
        for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
            print(f"  {pattern}: {count}")

    if send_inbox:
        msg = f"BATCH DEBUG-PDF: {batch_report['total']} URLs analyzed\n"
        msg += f"Patterns: {', '.join(f'{k}({v})' for k,v in pattern_counts.items())}"
        send_to_inbox(msg)


@app.command()
def fidelity(
    pdf_path: Path = typer.Argument(..., help="Path to source PDF"),
    json_path: Path = typer.Argument(..., help="Path to extracted structural JSON"),
):
    """
    Check extraction fidelity using the review-pdf skill (The Auditor).
    """
    review_skill_run = PI_SKILLS_DIR / "review-pdf" / "run.sh"
    
    if not review_skill_run.exists():
        logger.error(f"review-pdf skill not found at {review_skill_run}")
        raise typer.Exit(1)
        
    logger.info(f"Delegating fidelity check to {review_skill_run}")
    
    try:
        subprocess.run(
            [str(review_skill_run), "audit", str(pdf_path), str(json_path)],
            check=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Fidelity check failed: {e}")
        raise typer.Exit(e.returncode)


@app.command()
def combine(
    output: Path = typer.Option("combined_fixtures.pdf", "--output", help="Output combined PDF path"),
    max_pages: int = typer.Option(20, "--max-pages", help="Maximum pages in combined PDF"),
):
    """Combine all generated fixtures into one stress test PDF."""
    # Validate output path
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        if not os.access(str(output.parent), os.W_OK):
            raise PermissionError("No write permission")
    except Exception as e:
        logger.error(f"Cannot write to output directory {output.parent}: {e}")
        raise typer.Exit(1)

    fixtures = list(FIXTURES_DIR.glob("*.pdf"))

    if not fixtures:
        logger.warning("No fixtures found to combine")
        raise typer.Exit(1)

    logger.info(f"Combining {len(fixtures)} fixtures (max {max_pages} pages)...")

    combined = fitz.open()
    total_pages = 0
    included_fixtures = []

    for fixture_path in fixtures:
        if total_pages >= max_pages:
            break

        try:
            src = fitz.open(fixture_path)
            pages_to_add = min(len(src), max_pages - total_pages)
            combined.insert_pdf(src, to_page=pages_to_add - 1)
            total_pages += pages_to_add
            included_fixtures.append(fixture_path.name)
            src.close()
        except Exception as e:
            logger.warning(f"Could not include {fixture_path.name}: {e}")

    if total_pages > 0:
        # Add index page at the beginning
        index_page = combined.new_page(pno=0)
        y_pos = 72
        index_page.insert_text(
            (72, y_pos),
            f"COMBINED STRESS TEST FIXTURE",
            fontsize=16,
            fontname="helv"
        )
        y_pos += 30
        index_page.insert_text(
            (72, y_pos),
            f"Generated: {datetime.now().isoformat()}",
            fontsize=10,
            fontname="helv"
        )
        y_pos += 20
        index_page.insert_text(
            (72, y_pos),
            f"Total Pages: {total_pages + 1}",
            fontsize=10,
            fontname="helv"
        )
        y_pos += 30
        index_page.insert_text(
            (72, y_pos),
            "Included Fixtures:",
            fontsize=12,
            fontname="helv"
        )
        y_pos += 20

        for name in included_fixtures:
            index_page.insert_text((90, y_pos), f"- {name}", fontsize=9, fontname="cour")
            y_pos += 12
            if y_pos > 750:
                break

        combined.save(output)
        combined.close()

        print(f"Combined fixture saved: {output}")
        print(f"Total pages: {total_pages + 1} (including index)")
        print(f"Fixtures included: {len(included_fixtures)}")
    else:
        logger.error("No pages could be combined")
        raise typer.Exit(1)


@app.command()
def verify_ordering(
    pipeline_dir: Path = typer.Argument(..., help="Path to pipeline results root"),
):
    """Audit the spatial ordering consistency of extracted elements."""
    db_path = pipeline_dir / "pipeline.duckdb"
    if not db_path.exists():
        print(f"Error: DuckDB not found at {db_path}")
        raise typer.Exit(1)

    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        sections = con.execute("SELECT id, title FROM sections ORDER BY page_start, id").fetchall()
        print(f"Auditing {len(sections)} sections for ordering fidelity...\n")

        for sec_id, title in sections:
            elements = con.execute(
                """
                SELECT type, sort_order, page, asset_id 
                FROM merged_content 
                WHERE section_id = ? 
                ORDER BY sort_order
            """,
                [sec_id],
            ).fetchall()

            if not elements:
                continue

            print(f"Section {sec_id}: {title} ({len(elements)} elements)")
            
            last_order = -1
            inversions = 0
            for i, (etype, order, page, asset_id) in enumerate(elements):
                if order < last_order:
                    print(f"  [!] INVERSION: {etype} (order {order}) appeared after {last_order}")
                    inversions += 1
                last_order = order
            
            if inversions == 0:
                print(f"  [✅] Order consistent")
            else:
                print(f"  [❌] Found {inversions} ordering anomalies")
            print()

    except Exception as e:
        print(f"Audit failed: {e}")
    finally:
        con.close()


@app.command()
def recall(
    query: str = typer.Argument("PDF extraction failure patterns"),
):
    """Recall known patterns from memory."""
    results = memory_recall(query)
    if results:
        print(f"Found {len(results)} relevant memories:\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r.get('title', 'Untitled')}")
            print(f"   {r.get('content', '')[:200]}...")
            print()
    else:
        print("No relevant patterns found in memory.")
        print("Run analysis on PDFs to build up pattern knowledge.")


@app.command()
def learn(
    pattern: str = typer.Option(..., "--pattern", help="Pattern name to store"),
    details: str = typer.Option(..., "--details", help="Pattern details/description"),
    url: str = typer.Option(None, "--url", help="Source URL if applicable"),
):
    """Manually store a pattern to memory."""
    memory_learn(pattern, details, url)
    print(f"Stored pattern '{pattern}' to memory.")


@app.command()
def detectors():
    """List all registered detection functions."""
    print("=== Document-Level Detectors ===")
    for i, d in enumerate(DOC_DETECTORS, 1):
        print(f"  {i}. {d.__name__}")
        if d.__doc__:
            print(f"     {d.__doc__.split('.')[0]}.")

    print("\n=== Page-Level Detectors ===")
    for i, d in enumerate(PAGE_DETECTORS, 1):
        print(f"  {i}. {d.__name__}")
        if d.__doc__:
            print(f"     {d.__doc__.split('.')[0]}.")

    print(f"\nTotal: {len(DOC_DETECTORS)} doc-level, {len(PAGE_DETECTORS)} page-level")
    print("\nTo add a new detector:")
    print("  1. Create function: def detect_my_pattern(page_or_doc) -> list[tuple[str, str]]")
    print("  2. Add decorator: @register_page_detector or @register_doc_detector")
    print("  3. Add pattern description to PATTERNS dict")


if __name__ == "__main__":
    app()

