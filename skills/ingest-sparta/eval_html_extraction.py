#!/usr/bin/env python3
"""Eval: BS4 strip + /clean-text vs scillm LLM for HTML text extraction.

Tests the 3-tier pipeline:
  Tier 0: BS4 tag removal (nav, sidebar, footer, header, script, style)
  Tier 1: /clean-text normalization
  Tier 2: scillm LLM extraction (Chutes cascade → Gemini Flash → DeepSeek)

Compares:
  A) BS4-only (Tier 0+1) — deterministic, <100ms
  B) BS4 + scillm text model (Tier 0+1+2) — LLM cleanup of BS4 output

Runs 5 concurrent calls via ThreadPoolExecutor.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import httpx
import typer
from loguru import logger

app = typer.Typer()

SKILLS_DIR = Path(__file__).parent.parent
CLEAN_TEXT = SKILLS_DIR / "clean-text" / "run.sh"
SCILLM_BASE = "http://localhost:4001"
SCILLM_KEY = "sk-dev-proxy-123"


# ---------------------------------------------------------------------------
# Tier 0: BS4 tag removal (deterministic)
# ---------------------------------------------------------------------------

def bs4_strip(html: str) -> str:
    """Remove boilerplate HTML elements, return clean text."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup(
        ["script", "style", "nav", "footer", "header", "aside",
         "noscript", "iframe", "svg", "form", "button"]
    ):
        tag.decompose()

    # Remove by CSS class/id patterns
    for selector in [
        ".nav", ".navigation", ".menu", ".sidebar", ".footer",
        ".header", ".cookie", ".banner", ".breadcrumb", ".pagination",
        ".social", ".share", ".comments", ".ad", ".advertisement",
        "#nav", "#menu", "#sidebar", "#footer", "#header",
        "#cookie-banner", "#breadcrumb",
    ]:
        for el in soup.select(selector):
            el.decompose()

    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Tier 1: /clean-text normalization
# ---------------------------------------------------------------------------

def clean_text_via_skill(text: str) -> str:
    """Normalize text via /clean-text skill."""
    if not CLEAN_TEXT.exists():
        return text  # graceful degradation

    try:
        result = subprocess.run(
            ["bash", str(CLEAN_TEXT), "normalize"],
            input=text,
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        logger.debug("clean-text failed: {}", e)
    return text


# ---------------------------------------------------------------------------
# Tier 2: scillm LLM extraction
# ---------------------------------------------------------------------------

def scillm_extract(text: str, max_input: int = 8000) -> str:
    """Send pre-cleaned text to scillm for final extraction."""
    # Truncate to fit context window
    truncated = text[:max_input]

    resp = httpx.post(
        f"{SCILLM_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {SCILLM_KEY}"},
        json={
            "model": "text",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a text extraction assistant. Extract ONLY the main article/document content from the provided text. Remove any remaining navigation, menu items, cookie notices, or boilerplate. Return clean prose only. Do not add commentary.",
                },
                {"role": "user", "content": truncated},
            ],
            "max_tokens": 4096,
            "temperature": 0,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Pipeline: process one file
# ---------------------------------------------------------------------------

def process_file(filepath: Path) -> dict:
    """Run the full pipeline on one HTML file."""
    t0 = time.time()
    raw = filepath.read_text(errors="ignore")
    raw_len = len(raw)

    # Tier 0: BS4
    t_bs4_start = time.time()
    bs4_text = bs4_strip(raw)
    t_bs4 = time.time() - t_bs4_start

    # Tier 1: /clean-text
    t_clean_start = time.time()
    cleaned = clean_text_via_skill(bs4_text)
    t_clean = time.time() - t_clean_start

    # Tier 2: scillm
    t_llm_start = time.time()
    try:
        llm_text = scillm_extract(cleaned)
        llm_ok = True
    except Exception as e:
        llm_text = f"ERROR: {e}"
        llm_ok = False
    t_llm = time.time() - t_llm_start

    # Sentence count heuristic
    def sent_count(t):
        return len(re.findall(r"[.!?](?:\s|$)", t))

    result = {
        "file": filepath.name,
        "raw_bytes": raw_len,
        "bs4_chars": len(bs4_text),
        "bs4_sentences": sent_count(bs4_text),
        "bs4_ms": round(t_bs4 * 1000),
        "cleaned_chars": len(cleaned),
        "clean_ms": round(t_clean * 1000),
        "llm_chars": len(llm_text) if llm_ok else 0,
        "llm_sentences": sent_count(llm_text) if llm_ok else 0,
        "llm_ok": llm_ok,
        "llm_ms": round(t_llm * 1000),
        "total_ms": round((time.time() - t0) * 1000),
        # First 200 chars of each for quality comparison
        "bs4_preview": bs4_text[:200],
        "llm_preview": llm_text[:200] if llm_ok else "ERROR",
    }
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@app.command()
def run(
    html_dir: Path = typer.Argument(..., help="Directory with HTML files"),
    limit: int = typer.Option(10, "--limit", help="Max files to process"),
    workers: int = typer.Option(5, "--workers", help="Concurrent workers"),
    min_size: int = typer.Option(50_000, "--min-size", help="Min file size in bytes"),
    max_size: int = typer.Option(500_000, "--max-size", help="Max file size in bytes"),
):
    """Run HTML extraction eval on files in a directory."""
    files = sorted(
        [f for f in html_dir.glob("*.html")
         if min_size <= f.stat().st_size <= max_size],
        key=lambda f: f.stat().st_size,
        reverse=True,
    )[:limit]

    logger.info("Testing {} HTML files with {} workers", len(files), workers)

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_file, f): f for f in files}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            logger.info(
                "{}: raw={}KB → bs4={}ch ({}ms) → llm={}ch ({}ms) total={}ms",
                r["file"][:12],
                r["raw_bytes"] // 1024,
                r["bs4_chars"],
                r["bs4_ms"],
                r["llm_chars"],
                r["llm_ms"],
                r["total_ms"],
            )

    # Summary
    total_bs4_ms = sum(r["bs4_ms"] for r in results)
    total_llm_ms = sum(r["llm_ms"] for r in results)
    total_wall = sum(r["total_ms"] for r in results)
    llm_ok_count = sum(1 for r in results if r["llm_ok"])

    print("\n" + "=" * 70)
    print("HTML EXTRACTION EVAL RESULTS")
    print("=" * 70)
    print(f"Files tested:      {len(results)}")
    print(f"Workers:           {workers}")
    print(f"BS4 total time:    {total_bs4_ms}ms ({total_bs4_ms/len(results):.0f}ms avg)")
    print(f"LLM total time:    {total_llm_ms}ms ({total_llm_ms/len(results):.0f}ms avg)")
    print(f"LLM success:       {llm_ok_count}/{len(results)}")
    print()

    print("Per-file comparison:")
    print(f"{'File':<14} {'Raw KB':>8} {'BS4 ch':>8} {'BS4 ms':>7} {'LLM ch':>8} {'LLM ms':>7} {'LLM OK':>6}")
    print("-" * 70)
    for r in sorted(results, key=lambda x: x["raw_bytes"], reverse=True):
        print(
            f"{r['file'][:13]:<14} {r['raw_bytes']//1024:>7}K"
            f" {r['bs4_chars']:>8} {r['bs4_ms']:>6}ms"
            f" {r['llm_chars']:>8} {r['llm_ms']:>6}ms"
            f" {'✓' if r['llm_ok'] else '✗':>5}"
        )

    print()
    print("Quality previews (first 150 chars):")
    for r in results[:3]:
        print(f"\n--- {r['file']} ---")
        print(f"  BS4:  {r['bs4_preview'][:150]}")
        print(f"  LLM:  {r['llm_preview'][:150]}")

    # Write full results
    out = Path(__file__).parent / "eval_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nFull results: {out}")


if __name__ == "__main__":
    app()
