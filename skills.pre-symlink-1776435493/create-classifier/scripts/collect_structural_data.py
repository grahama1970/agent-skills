#!/usr/bin/env python3
"""
Collect Structural Data — Massive-scale Miner for Structural Classifier
----------------------------------------------------------------------
Purpose:
- Scan 10k+ PDF pipeline results.
- Extract features and labels for: Header, Footnote, Reference, BodyText.
- Use Stage 04 output as a "bootstrap" labeler.
- Output JSONL for multi-modal training.

Usage:
    uv run collect_structural_data.py --roots /path/to/results1 /path/to/results2 --output structural.jsonl
"""

import os
import json
import typer
import re
from pathlib import Path
from typing import List
from loguru import logger

app = typer.Typer(help="Mine structural data for training.")

def collect_structural_data(results_roots: List[Path], output_file: Path, limit_per_root: int = 5000):
    """Scan multiple results directories and mine structural data."""
    logger.info(f"Mining structural data from {len(results_roots)} roots (limit: {limit_per_root} docs/root)")
    
    collected_count = 0
    total_docs = 0
    
    with open(output_file, 'w') as out_f:
        for root in results_roots:
            root_docs = 0
            logger.info(f"Scanning root: {root}")
            
            # Find all 04_sections.json files in this root
            # Structure: root / doc_id / 04_section_builder / json_output / 04_sections.json
            for sections_file in root.glob("*/04_section_builder/json_output/04_sections.json"):
                doc_path = sections_file.parents[2]
                profile_file = doc_path / "00_profile_detector" / "profile.json"
                
                try:
                    with open(sections_file, 'r') as f:
                        sections_data = json.load(f)
                    
                    if not isinstance(sections_data, dict) or "sections" not in sections_data:
                        continue

                    body_font_size = 11.0
                    if profile_file.exists():
                        with open(profile_file, 'r') as f:
                            profile = json.load(f)
                            # Use hierarchy.font_body_size if available, else font_body_size
                            body_font_size = profile.get("hierarchy", {}).get("font_body_size", 
                                             profile.get("font_body_size", 11.0))

                    for section in sections_data.get("sections", []):
                        blocks = section.get("blocks", [])
                        section_title = section.get("title", "")
                        
                        for block in blocks:
                            text = block.get("text") or block.get("content") or ""
                            if not text.strip():
                                continue
                                
                            bbox = block.get("bbox", [0, 0, 0, 0])
                            page_height = block.get("page_height") or 792.0
                            fsf = block.get("first_span_font") or {}
                            font_size = float(fsf.get("size")) if fsf.get("size") is not None else 0.0
                            
                            y_pos_rel = bbox[3] / page_height if page_height > 0 else 0
                            
                            current_type = block.get("block_type", "Text")
                            is_header = block.get("is_header", False)
                            
                            label = "BodyText"
                            if is_header or current_type == "SectionHeader":
                                label = "Header"
                            elif current_type == "Footnote" or (y_pos_rel > 0.85 and font_size < body_font_size * 0.9):
                                label = "Footnote"
                            elif current_type == "Reference" or "References" in section_title or re.match(r"^\[\d+\]", text.strip()):
                                label = "Reference"

                            item = {
                                "id": f"{doc_path.name}_{block.get('page', 0)}_{bbox[1]}",
                                "input": {
                                    "text": text[:500],
                                    "layout": {
                                        "bbox": bbox,
                                        "page_height": page_height,
                                        "y_pos_rel": y_pos_rel,
                                        "block_width_rel": (bbox[2] - bbox[0]) / 612.0
                                    },
                                    "font": {
                                        "size": font_size,
                                        "body_size_ref": body_font_size,
                                        "is_bold": fsf.get("bold", False),
                                        "flags": block.get("font_flags", 0)
                                    }
                                },
                                "label": label,
                                "source": doc_path.name
                            }
                            
                            if label != "BodyText" or (collected_count % 30 == 0):
                                out_f.write(json.dumps(item) + "\n")
                                collected_count += 1
                    
                    root_docs += 1
                    total_docs += 1
                    if root_docs >= limit_per_root:
                        break
                        
                    if total_docs % 500 == 0:
                        logger.info(f"Processed {total_docs} total docs, collected {collected_count} structural examples")
                        
                except Exception as e:
                    logger.warning(f"Failed to process {doc_path.name}: {e}")
                
    logger.info(f"Finished. Collected {collected_count} examples from {total_docs} docs across {len(results_roots)} roots.")

@app.command()
def main(
    roots: list[str] = typer.Option(..., help="Corpus results root directories"),
    output: Path = typer.Option(..., help="Output JSONL file"),
    limit_per_root: int = typer.Option(5000, help="Max docs per root to mine"),
):
    """Mine structural data for training."""
    collect_structural_data([Path(r) for r in roots], output, limit_per_root)


if __name__ == "__main__":
    app()
