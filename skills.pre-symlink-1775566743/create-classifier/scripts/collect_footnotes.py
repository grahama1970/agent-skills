#!/usr/bin/env python3
"""
Collect Footnotes — Data Miner for Footnote Classifier Training
--------------------------------------------------------------
Purpose:
- Scan a large corpus of pipeline results (10k+ PDFs).
- Extract candidate footnote blocks and their spatial/font context.
- Output JSONL for training the multi-modal Footnote Classifier.

Usage:
    ./run.sh collect --task footnotes --source /path/to/results --output data/labels/footnotes.jsonl
"""

import os
import json
import typer
from pathlib import Path
from loguru import logger

app = typer.Typer(help="Mine footnotes for training.")

def collect_footnotes(results_dir: Path, output_file: Path, limit: int = 10000):
    """Scan results directory for Stage 04 output and mine footnotes."""
    logger.info(f"Mining footnotes from {results_dir} (limit: {limit} docs)")
    
    collected_count = 0
    doc_count = 0
    
    with open(output_file, 'w') as out_f:
        # results_dir structure: doc_id / 04_sections / json_output / sections.json
        for doc_path in results_dir.iterdir():
            if not doc_path.is_dir():
                continue
                
            sections_file = doc_path / "04_section_builder" / "json_output" / "04_sections.json"
            profile_file = doc_path / "00_profile_detector" / "profile.json"
            
            if not sections_file.exists():
                logger.debug(f"Skipping {doc_path.name}: no sections.json")
                continue
                
            try:
                with open(sections_file, 'r') as f:
                    sections = json.load(f)
                
                body_font_size = 11.0
                if profile_file.exists():
                    with open(profile_file, 'r') as f:
                        profile = json.load(f)
                        body_font_size = profile.get("hierarchy", {}).get("font_body_size", 11.0)

                for section in sections:
                    blocks = section.get("blocks", [])
                    # Stage 04b might have already marked them, or we use heuristics here
                    for block in blocks:
                        # Extract features for training
                        text = block.get("text") or block.get("content") or ""
                        bbox = block.get("bbox", [0, 0, 0, 0])
                        page_height = block.get("page_height") or 792.0
                        fsf = block.get("first_span_font") or {}
                        font_size = float(fsf.get("size")) if fsf.get("size") is not None else 0.0
                        
                        y_pos_rel = bbox[3] / page_height if page_height > 0 else 0
                        
                        # Labels: 1 = Footnote, 0 = Body Text
                        # We use a broad heuristic to capture positives and nearby negatives
                        is_likely_footnote = (y_pos_rel > 0.82 and font_size < (body_font_size * 0.95))
                        
                        # Capture context
                        item = {
                            "id": f"{doc_path.name}_{block.get('page', 0)}_{bbox[1]}",
                            "input": {
                                "text": text[:500],
                                "layout": {
                                    "bbox": bbox,
                                    "page_height": page_height,
                                    "y_pos_rel": y_pos_rel,
                                    "block_width_rel": (bbox[2] - bbox[0]) / 612.0 # Assume letter width approx
                                },
                                "font": {
                                    "size": font_size,
                                    "body_size_ref": body_font_size,
                                    "is_bold": fsf.get("bold", False)
                                }
                            },
                            "label": "footnote" if is_likely_footnote else "body_text",
                            "confidence": 0.9 if is_likely_footnote else 0.7,
                            "source": doc_path.name
                        }
                        
                        # Add to training set (sampling: all likely footnotes, some body text)
                        if is_likely_footnote or (collected_count % 10 == 0):
                            out_f.write(json.dumps(item) + "\n")
                            collected_count += 1
                
                doc_count += 1
                if doc_count >= limit:
                    break
                    
                if doc_count % 100 == 0:
                    logger.info(f"Processed {doc_count} docs, collected {collected_count} examples")
                    
            except Exception as e:
                logger.warning(f"Failed to process {doc_path.name}: {e}")
                
    logger.info(f"Finished. Collected {collected_count} examples from {doc_count} docs.")

@app.command()
def main(
    source: Path = typer.Option(..., help="Corpus results directory"),
    output: Path = typer.Option(..., help="Output JSONL file"),
    limit: int = typer.Option(10000, help="Max docs to mine"),
):
    """Mine footnotes for training."""
    collect_footnotes(source, output, limit)


if __name__ == "__main__":
    app()
