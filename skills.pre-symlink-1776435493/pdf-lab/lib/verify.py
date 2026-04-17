"""verify — Re-extract a real PDF with tuned parameters and compare results.

Given a real PDF and a fixture used for convergence tuning, reads
fix_registry.json for tuned parameters, runs pdf_oxide extraction,
and compares against the old manifest entry. Updates manifest.jsonl
and pattern_registry.json based on results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

CORPUS_METADATA = Path("/mnt/storage12tb/extractor_corpus/metadata")
MANIFEST_PATH = CORPUS_METADATA / "manifest.jsonl"
PATTERN_REGISTRY_PATH = CORPUS_METADATA / "pattern_registry.json"


@dataclass
class VerifyResult:
    """Result of verify-real comparison."""
    real_pdf: str
    fixture_id: str
    improved: bool
    old_s00_s04_ratio: Optional[float]
    new_s00_s04_ratio: Optional[float]
    old_block_score: Optional[float]
    new_block_score: Optional[float]
    old_quality_signal: str
    new_quality_signal: str
    overrides_applied: Dict[str, Any]
    detail: str
    manifest_updated: bool
    pattern_updated: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        if self.improved:
            parts = ["IMPROVED:"]
            if self.old_s00_s04_ratio is not None and self.new_s00_s04_ratio is not None:
                parts.append(f"S00/S04 ratio {self.old_s00_s04_ratio:.1f}x -> {self.new_s00_s04_ratio:.1f}x")
            if self.old_block_score is not None and self.new_block_score is not None:
                parts.append(f"block score {self.old_block_score:.2%} -> {self.new_block_score:.2%}")
            return " ".join(parts)
        return f"NO IMPROVEMENT: {self.detail}"


def _find_manifest_entry(pdf_path: Path) -> Optional[Dict[str, Any]]:
    """Find a manifest entry matching the given PDF by filename or path."""
    if not MANIFEST_PATH.exists():
        return None
    filename = pdf_path.name
    for line in MANIFEST_PATH.read_text().strip().split("\n"):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("filename") == filename or str(pdf_path) in (
            entry.get("path", ""), entry.get("original_path", ""),
        ):
            return entry
    return None


def _run_extract(pdf_path: Path) -> Dict[str, Any]:
    """Run pdf_oxide extraction and return section/block metrics."""
    import pdf_oxide
    doc = pdf_oxide.PdfDocument(str(pdf_path))
    sections = doc.build_flat_sections().get("sections", [])
    blocks = []
    for p in range(doc.page_count()):
        blocks.extend(doc.classify_blocks(p))
    prediction = doc.predict_extraction()
    return {
        "section_count": len(sections),
        "blocks": blocks,
        "estimated_sections": prediction.get("estimated_sections", 0),
    }


def _quality_signal(ratio: Optional[float]) -> str:
    if ratio is None:
        return "UNKNOWN"
    if 0.5 <= ratio <= 2.0:
        return "GOOD"
    if 0.25 <= ratio <= 4.0:
        return "REASONABLE"
    return "POOR"


def _update_manifest(pdf_path: Path, updates: Dict[str, Any]) -> bool:
    """Update the manifest.jsonl entry for the given PDF."""
    if not MANIFEST_PATH.exists():
        return False
    filename = pdf_path.name
    lines = MANIFEST_PATH.read_text().strip().split("\n")
    updated, new_lines = False, []
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        entry = json.loads(line)
        if entry.get("filename") == filename or str(pdf_path) in (
            entry.get("path", ""), entry.get("original_path", ""),
        ):
            entry.update(updates)
            entry["verify_real_at"] = datetime.now(timezone.utc).isoformat()
            updated = True
        new_lines.append(json.dumps(entry))
    if updated:
        MANIFEST_PATH.write_text("\n".join(new_lines) + "\n")
        logger.info(f"Updated manifest entry for {filename}")
    return updated


def _update_pattern_registry(patterns: List[str], status: str, fixture_id: str) -> bool:
    """Update pattern_registry.json entries with fix status."""
    if not PATTERN_REGISTRY_PATH.exists():
        return False
    registry = json.loads(PATTERN_REGISTRY_PATH.read_text())
    pat = registry.get("patterns", {})
    updated = False
    now = datetime.now(timezone.utc).isoformat()
    for name in patterns:
        if name in pat:
            pat[name].update(fix_status=status, fix_fixture_id=fixture_id, fix_updated_at=now)
            updated = True
    if updated:
        registry["patterns"] = pat
        PATTERN_REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n")
        logger.info(f"Updated pattern_registry for patterns: {patterns}")
    return updated


def verify_real(
    real_pdf: Path,
    fixture_dir: Path,
    *,
    pattern_name: Optional[str] = None,
) -> VerifyResult:
    """Re-extract a real PDF with tuned parameters and compare against old results."""
    if not real_pdf.exists():
        raise FileNotFoundError(f"Real PDF not found: {real_pdf}")
    if not fixture_dir.exists():
        raise FileNotFoundError(f"Fixture directory not found: {fixture_dir}")

    # Load tuned parameters from fix_registry
    reg_path = fixture_dir / "fix_registry.json"
    if not reg_path.exists():
        raise FileNotFoundError(f"fix_registry.json not found in {fixture_dir}. Run 'pdf-lab tune-gt' first.")
    registry = json.loads(reg_path.read_text())
    overrides = registry.get("overrides", {})
    fixture_id = registry.get("fixture_id", fixture_dir.name)

    # Get old manifest entry for baseline
    old_entry = _find_manifest_entry(real_pdf)
    old_ratio = old_entry.get("s00_s04_ratio") if old_entry else None
    old_quality = old_entry.get("quality_signal", "UNKNOWN") if old_entry else "UNKNOWN"
    old_patterns = old_entry.get("debug_patterns", []) if old_entry else []

    # Write tune_overrides.json so extraction picks it up
    overrides_path = real_pdf.parent / "tune_overrides.json"
    wrote_overrides = bool(overrides)
    if wrote_overrides:
        overrides_path.write_text(json.dumps(overrides, indent=2))
        logger.info(f"Wrote tune_overrides.json to {overrides_path}")

    # Run extraction
    ext = _run_extract(real_pdf)
    estimated, actual = ext["estimated_sections"], ext["section_count"]
    new_ratio = round(estimated / actual, 2) if actual > 0 else None
    blocks = ext["blocks"]
    new_block_score = round(sum(1 for b in blocks if b.get("block_type", "Body") != "Body") / len(blocks), 4) if blocks else 0.0
    new_quality = _quality_signal(new_ratio)

    # Determine improvement
    improved = False
    detail_parts = []

    if old_ratio is not None and new_ratio is not None:
        old_dist, new_dist = abs(old_ratio - 1.0), abs(new_ratio - 1.0)
        if new_dist < old_dist:
            improved = True
            detail_parts.append(f"S00/S04 ratio {old_ratio:.1f}x -> {new_ratio:.1f}x")
        else:
            detail_parts.append(f"S00/S04 ratio not improved ({old_ratio:.1f}x -> {new_ratio:.1f}x)")
    elif new_ratio is not None:
        detail_parts.append(f"S00/S04 ratio {new_ratio:.1f}x (no prior baseline)")
        if 0.5 <= new_ratio <= 2.0:
            improved = True

    quality_order = {"POOR": 0, "UNKNOWN": 1, "REASONABLE": 2, "GOOD": 3}
    if quality_order.get(new_quality, 0) > quality_order.get(old_quality, 0):
        improved = True
        detail_parts.append(f"quality {old_quality} -> {new_quality}")

    detail = "; ".join(detail_parts) if detail_parts else "no measurable change"
    patterns = [pattern_name] if pattern_name else old_patterns

    # Update metadata or revert
    manifest_updated = pattern_updated = False
    if improved:
        manifest_updated = _update_manifest(real_pdf, {
            "s00_s04_ratio": new_ratio, "quality_signal": new_quality,
            "verify_real_status": "improved", "verify_real_fixture": fixture_id,
        })
        if patterns:
            pattern_updated = _update_pattern_registry(patterns, "fix_applied", fixture_id)
    else:
        if wrote_overrides and overrides_path.exists():
            overrides_path.unlink()
            logger.info("Reverted tune_overrides.json (no improvement)")
        if patterns:
            pattern_updated = _update_pattern_registry(patterns, "needs_review", fixture_id)

    return VerifyResult(
        real_pdf=str(real_pdf), fixture_id=fixture_id, improved=improved,
        old_s00_s04_ratio=old_ratio, new_s00_s04_ratio=new_ratio,
        old_block_score=None, new_block_score=new_block_score,
        old_quality_signal=old_quality, new_quality_signal=new_quality,
        overrides_applied=overrides, detail=detail,
        manifest_updated=manifest_updated, pattern_updated=pattern_updated,
    )
