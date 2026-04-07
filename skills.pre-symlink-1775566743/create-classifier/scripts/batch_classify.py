#!/usr/bin/env python3
"""
Batch S00 Classifier - Run Profile Detector on Corpus

Runs only the S00 profile detector stage on all PDFs in the inbox.
Much faster than full pipeline re-run.

Usage:
    python scripts/batch_classify.py --inbox /mnt/storage12tb/extractor_corpus/inbox --results /mnt/storage12tb/extractor_corpus/results
"""

import typer
import time
import sys
import traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# Ensure src is in python path
src_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from loguru import logger
# Import the entry point 'run' from s00_profile_detector
from extractor.pipeline.steps.s00_profile_detector import run as run_s00

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")


def process_pdf(pdf_path: Path, results_root: Path) -> tuple[str, str]:
    """Run S00 on a single PDF."""
    try:
        # Determine output directory based on PDF parent name (convention)
        # e.g. inbox/arxiv/123.pdf -> results/arxiv_123
        category = pdf_path.parent.name
        safe_stem = pdf_path.stem.replace(".", "_")
        slug = f"{category}_{safe_stem}"
        
        output_dir = results_root / slug
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if already processed
        s00_dir = output_dir / "00_profile_detector"
        profile_path = s00_dir / "profile.json"
        
        # If profile exists and is valid json, skip
        if profile_path.exists():
            try:
                import json
                with open(profile_path) as f:
                    json.load(f)
                return str(pdf_path), "skipped_exists"
            except Exception as e:
                logger.debug("invalid json profile, will re-run: {}", e)
            
        # Run S00
        # Signature: run(pdf_path: Path, output_dir: Path, verbose_preset: bool = False) -> Path
        # It expects the pipeline root output dir for this item? Or the step dir?
        # looking at s00 code: 
        # def run(pdf_path: Path, output_dir_base: Path, ...)
        #   out = output_dir_base / STEP_NAME
        # So we pass the pipeline item root (slug dir)
        
        run_s00(pdf_path, output_dir)
        
        return str(pdf_path), "success"
        
    except Exception as e:
        # logger.error(f"Failed {pdf_path}: {e}")
        return str(pdf_path), f"error: {str(e)}"


app = typer.Typer(help="Batch S00 Classifier")


@app.command()
def main(
    inbox: str = typer.Option(..., help="Input directory"),
    results: str = typer.Option(..., help="Results directory"),
    workers: int = typer.Option(16, help="Parallel workers"),
    limit: int = typer.Option(None, help="Limit number of files"),
):
    # 1. Find all PDFs
    logger.info(f"Scanning {inbox}...")
    pdfs = sorted(list(inbox.rglob("*.pdf")))
    logger.info(f"Found {len(pdfs)} PDFs in inbox")
    
    if limit:
        pdfs = pdfs[:limit]
        logger.info(f"Limiting to {limit} PDFs")
        
    # 2. Process in parallel
    success = 0
    skipped = 0
    failed = 0
    
    start_time = time.time()
    
    with ProcessPoolExecutor(max_workers=workers) as exe:
        futures = {exe.submit(process_pdf, p, results): p for p in pdfs}
        
        for i, fut in enumerate(as_completed(futures)):
            pdf_path, status = fut.result()
            
            if status == "success":
                success += 1
            elif status == "skipped_exists":
                skipped += 1
            else:
                failed += 1
                if failed <= 10: # Only log first few failures to avoid spam
                    logger.warning(f"Failed {pdf_path}: {status}")
                
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                logger.info(f"Progress: {i+1}/{len(pdfs)} (OK: {success}, Skip: {skipped}, Fail: {failed}) - {rate:.1f} pdfs/sec")
                
    logger.info("Done!")
    logger.info(f"Summary: Success={success}, Skipped={skipped}, Failed={failed}")
    logger.info(f"Total time: {time.time() - start_time:.1f}s")


if __name__ == "__main__":
    app()
