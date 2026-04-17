#!/usr/bin/env python3
"""3-way evidence matrix for table extraction quality assessment.

Follows the /create-evidence-case pattern:
  1. Deterministically collect evidence from 3 sources
  2. Agent (or VLM) arbitrates disagreements
  3. Shadow-log disagreements for /assistant classifier training

Evidence sources:
  A: /extract-tables (our pipeline)
  B: Camelot (reference pipeline)
  C: VLM reading PDF screenshot (ground truth)

Usage:
    python -m python.evidence_matrix tests/fixtures/foo.pdf
    python -m python.evidence_matrix tests/fixtures/ --output evidence_report/
    python -m python.evidence_matrix tests/fixtures/foo.pdf --vlm claude
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import typer

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_DIR / "src"))

SHADOW_LOG = SKILL_DIR / "shadow_evidence.jsonl"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CellEvidence:
    """Evidence for a single cell from all 3 sources."""
    row: int
    col: int
    extract_tables: str = ""   # Evidence A
    camelot: str = ""          # Evidence B
    vlm: str = ""              # Evidence C (ground truth)
    verdict: str = ""          # "agree" | "a_correct" | "b_correct" | "c_correct" | "unclear"
    notes: str = ""


@dataclass
class TableEvidence:
    """Evidence case for one table across all 3 sources."""
    pdf_name: str
    table_index: int
    # Shapes
    shape_a: tuple[int, int] = (0, 0)
    shape_b: tuple[int, int] = (0, 0)
    shape_c: tuple[int, int] = (0, 0)
    # Raw data grids (list of lists of strings, header row first)
    data_a: list[list[str]] = field(default_factory=list)
    data_b: list[list[str]] = field(default_factory=list)
    data_c: list[list[str]] = field(default_factory=list)
    # Bounding boxes
    bbox_a: tuple[float, float, float, float] = (0, 0, 0, 0)
    bbox_b: tuple[float, float, float, float] = (0, 0, 0, 0)
    # Per-cell evidence (only for disagreements)
    cell_diffs: list[CellEvidence] = field(default_factory=list)
    # Screenshot path
    screenshot_path: str = ""
    # Gate results
    shape_gate: str = ""  # "pass" | "fail"
    cell_gate: str = ""   # "pass" | "partial" | "fail"
    # Overall
    grade: str = ""       # A/B/C/F
    score: float = 0.0    # 0.0 - 1.0
    verdict: str = ""     # "extract_tables_correct" | "camelot_correct" | "match" | "needs_vlm"


@dataclass
class MergeCandidate:
    """Evidence for whether two contiguous tables should merge.

    Deterministic signals — agent decides using this evidence.
    """
    pdf_name: str
    table_i: int
    table_j: int
    # Deterministic signals
    col_count_match: bool = False
    col_count_i: int = 0
    col_count_j: int = 0
    y_gap: float = 0.0           # vertical gap in PDF points between tables
    x_overlap_ratio: float = 0.0  # horizontal overlap as fraction of narrower table
    width_ratio: float = 0.0     # min(w)/max(w) — 1.0 = identical widths
    header_match: bool = False    # first row of j matches first row of i
    continued_keyword: bool = False
    same_page: bool = True
    # VLM can see the gap region and decide
    gap_screenshot_b64: str = ""
    # Agent verdict
    should_merge: str = ""       # "yes" | "no" | "needs_vlm"
    confidence: float = 0.0
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Collectors (deterministic - no LLM)
# ---------------------------------------------------------------------------

def collect_extract_tables(
    pdf_path: str, pages: str = "1",
) -> list[tuple[list[list[str]], tuple]]:
    """Evidence A: Extract tables with our pipeline.

    Returns list of (data_grid, bbox) tuples.
    """
    from python.extract_tables import read_pdf

    result = read_pdf(pdf_path, pages=pages, flavor="lattice")
    tables = []
    for table in result:
        if table._data:
            tables.append((table._data, table.bbox))
        else:
            # Convert df to list of lists
            df = table.df
            if df.shape[0] > 0:
                grid = [list(df.columns)]
                for row in df.to_dicts():
                    grid.append([str(row[c]) for c in df.columns])
                tables.append((grid, table.bbox))
            else:
                tables.append(([], table.bbox))
    return tables


def collect_camelot(
    pdf_path: str, pages: str = "1",
) -> list[tuple[list[list[str]], tuple]]:
    """Evidence B: Extract tables with Camelot.

    Returns list of (data_grid, bbox) tuples.
    """
    try:
        import camelot
        cam_tables = camelot.read_pdf(pdf_path, flavor="lattice", pages=pages)
    except Exception as e:
        return [("error", str(e))]

    tables = []
    for ct in cam_tables:
        df = ct.df
        grid = []
        for i in range(len(df)):
            row = [str(df.iloc[i][c]) for c in df.columns]
            grid.append(row)
        # Camelot bbox: (x0, y0_bottom, x1, y1_top) in PDF coords
        bbox = ct._bbox if hasattr(ct, "_bbox") else (0, 0, 0, 0)
        tables.append((grid, bbox))
    return tables


def collect_screenshot(
    pdf_path: str, page_num: int, bbox: tuple, dpi: int = 200,
) -> tuple[str, bytes]:
    """Render a PDF page cropped to table bbox.

    Returns (base64_png, raw_bytes).
    """
    from python.pdf_bridge import render_page_image, get_page_dimensions
    from PIL import Image

    img = render_page_image(pdf_path, page_num, dpi=dpi)
    pdf_w, pdf_h = get_page_dimensions(pdf_path, page_num)
    scale_x = img.width / pdf_w
    scale_y = img.height / pdf_h

    x0, y0, x1, y1 = bbox
    margin = 15
    px0 = max(0, int(x0 * scale_x) - margin)
    py0 = max(0, int(y0 * scale_y) - margin)
    px1 = min(img.width, int(x1 * scale_x) + margin)
    py1 = min(img.height, int(y1 * scale_y) + margin)

    cropped = img.crop((px0, py0, px1, py1))

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    raw = buf.getvalue()
    b64 = base64.b64encode(raw).decode("ascii")
    return b64, raw


def collect_vlm_reading(
    screenshot_b64: str, backend: str = "claude",
) -> list[list[str]]:
    """Evidence C: Have a VLM read the table from the screenshot.

    Calls the Anthropic API or scillm proxy to read
    the table from the image. Returns a grid (list of lists).

    backend: "claude" | "gemini" | "codex"
    """
    if backend == "claude":
        return _vlm_claude(screenshot_b64)
    elif backend == "gemini":
        return _vlm_gemini(screenshot_b64)
    else:
        # Fallback to claude
        return _vlm_claude(screenshot_b64)


def _vlm_claude(screenshot_b64: str) -> list[list[str]]:
    """Read table from screenshot using Claude API."""
    try:
        import anthropic
    except ImportError:
        return [["ERROR: anthropic package not installed"]]

    client = anthropic.Anthropic()
    prompt = (
        "Extract the table from this image. Return ONLY a JSON array of arrays "
        "(list of rows, each row is a list of cell strings). Include the header row. "
        "Preserve exact text including numbers, percentages, and special characters. "
        "Do not add any explanation, just the JSON array."
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text = response.content[0].text.strip()
        # Extract JSON from response (may have markdown fences)
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        return [["ERROR: " + str(e)]]


def _vlm_gemini(screenshot_b64: str) -> list[list[str]]:
    """Read table from screenshot using Gemini via scillm proxy."""
    import httpx

    prompt = (
        "Extract the table from this image. Return ONLY a JSON array of arrays "
        "(list of rows, each row is a list of cell strings). Include the header row. "
        "Preserve exact text including numbers, percentages, and special characters. "
        "Do not add any explanation, just the JSON array."
    )

    try:
        resp = httpx.post(
            "http://localhost:4001/v1/chat/completions",
            headers={"Authorization": "Bearer sk-dev-proxy-123"},
            json={
                "model": "vlm",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                "max_tokens": 4096,
            },
            timeout=120.0,
        )
        if resp.status_code != 200:
            return [["ERROR: scillm HTTP " + str(resp.status_code)]]
        text = resp.json()["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        return [["ERROR: " + str(e)]]


# ---------------------------------------------------------------------------
# Evidence assembly & gates
# ---------------------------------------------------------------------------

def collect_merge_evidence(
    tables_with_bbox: list[tuple[list[list[str]], tuple]],
    pdf_path: str,
    pdf_name: str,
) -> list[MergeCandidate]:
    """Gather deterministic evidence for contiguous table merge decisions.

    Checks each adjacent pair of tables on the same page.
    The agent (or VLM) uses this evidence to decide merges.
    """
    candidates = []
    for i in range(len(tables_with_bbox) - 1):
        data_i, bbox_i = tables_with_bbox[i]
        data_j, bbox_j = tables_with_bbox[i + 1]

        if not isinstance(data_i, list) or not isinstance(data_j, list):
            continue
        if not data_i or not data_j:
            continue

        mc = MergeCandidate(pdf_name=pdf_name, table_i=i, table_j=i + 1)

        # Column counts
        mc.col_count_i = len(data_i[0]) if data_i else 0
        mc.col_count_j = len(data_j[0]) if data_j else 0
        mc.col_count_match = mc.col_count_i > 0 and mc.col_count_i == mc.col_count_j

        # Vertical gap (y1 of table i to y0 of table j)
        # bbox = (x0, y0, x1, y1) in top-left coords
        mc.y_gap = bbox_j[1] - bbox_i[3]  # positive = gap, negative = overlap

        # Width ratio
        w_i = bbox_i[2] - bbox_i[0]
        w_j = bbox_j[2] - bbox_j[0]
        if w_i > 0 and w_j > 0:
            mc.width_ratio = min(w_i, w_j) / max(w_i, w_j)

        # X overlap
        overlap_x0 = max(bbox_i[0], bbox_j[0])
        overlap_x1 = min(bbox_i[2], bbox_j[2])
        if overlap_x1 > overlap_x0 and min(w_i, w_j) > 0:
            mc.x_overlap_ratio = (overlap_x1 - overlap_x0) / min(w_i, w_j)

        # Header match
        mc.header_match = data_i[0] == data_j[0]

        # Heuristic pre-decision (agent overrides via VLM)
        if mc.col_count_match and mc.width_ratio > 0.9 and mc.x_overlap_ratio > 0.8:
            if mc.y_gap < 50:  # within ~0.7 inches
                mc.should_merge = "likely_yes"
                mc.confidence = 0.7
                mc.reasoning = "Same columns, similar width, small gap"
            else:
                mc.should_merge = "needs_vlm"
                mc.reasoning = f"Same columns but gap={mc.y_gap:.0f}pt"
        else:
            mc.should_merge = "no"
            mc.confidence = 0.8
            mc.reasoning = (
                f"cols={'match' if mc.col_count_match else 'differ'}, "
                f"width_ratio={mc.width_ratio:.2f}, x_overlap={mc.x_overlap_ratio:.2f}"
            )

        candidates.append(mc)

    return candidates


def _normalize_cell(text: str) -> str:
    """Normalize cell text for comparison."""
    import re
    t = text.strip()
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t


def _grid_to_normalized(grid: list[list[str]]) -> list[list[str]]:
    """Normalize all cells in a grid."""
    return [[_normalize_cell(c) for c in row] for row in grid]


def assemble_evidence(
    pdf_path: str,
    pages: str = "1",
    vlm_backend: str = "claude",
    skip_vlm: bool = False,
) -> list[TableEvidence]:
    """Assemble 3-way evidence for all tables in a PDF.

    This is the main entry point. Follows evidence-case pattern:
    1. Collect evidence A (extract-tables) - deterministic
    2. Collect evidence B (camelot) - deterministic
    3. Collect evidence C (VLM screenshot) - optional
    4. Run gates and score
    """
    pdf_name = Path(pdf_path).stem
    tables_a = collect_extract_tables(pdf_path, pages)
    tables_b = collect_camelot(pdf_path, pages)

    evidence_list = []
    merge_candidates = []
    n_tables = max(len(tables_a), len(tables_b))

    for ti in range(n_tables):
        ev = TableEvidence(pdf_name=pdf_name, table_index=ti)

        # Evidence A
        if ti < len(tables_a):
            data_a, bbox_a = tables_a[ti]
            ev.data_a = data_a if isinstance(data_a, list) else []
            ev.shape_a = (len(ev.data_a), len(ev.data_a[0]) if ev.data_a else 0)
            ev.bbox_a = bbox_a
        else:
            bbox_a = (0, 0, 0, 0)

        # Evidence B
        if ti < len(tables_b):
            data_b, bbox_b = tables_b[ti]
            ev.data_b = data_b if isinstance(data_b, list) else []
            ev.shape_b = (len(ev.data_b), len(ev.data_b[0]) if ev.data_b else 0)
            ev.bbox_b = bbox_b

        # Evidence C (VLM)
        if not skip_vlm and bbox_a != (0, 0, 0, 0):
            try:
                page_idx = 0  # TODO: multi-page
                b64, raw = collect_screenshot(pdf_path, page_idx, bbox_a)
                ev.data_c = collect_vlm_reading(b64, backend=vlm_backend)
                ev.shape_c = (len(ev.data_c), len(ev.data_c[0]) if ev.data_c else 0)
            except Exception as e:
                ev.data_c = [["SCREENSHOT_ERROR: " + str(e)]]
                ev.shape_c = (1, 1)

        # --- Gate 1: Shape agreement ---
        shapes = [ev.shape_a, ev.shape_b]
        if not skip_vlm:
            shapes.append(ev.shape_c)
        unique_shapes = set(shapes)
        ev.shape_gate = "pass" if len(unique_shapes) == 1 else "fail"

        # --- Gate 2: Cell-level comparison ---
        ev.cell_diffs = []
        if ev.shape_a == ev.shape_b and ev.shape_a[0] > 0:
            norm_a = _grid_to_normalized(ev.data_a)
            norm_b = _grid_to_normalized(ev.data_b)
            norm_c = _grid_to_normalized(ev.data_c) if ev.data_c and not skip_vlm else None

            total_cells = ev.shape_a[0] * ev.shape_a[1]
            match_count = 0

            for r in range(ev.shape_a[0]):
                for c in range(ev.shape_a[1]):
                    va = norm_a[r][c] if r < len(norm_a) and c < len(norm_a[r]) else ""
                    vb = norm_b[r][c] if r < len(norm_b) and c < len(norm_b[r]) else ""
                    vc = ""
                    if norm_c and r < len(norm_c) and c < len(norm_c[r]):
                        vc = norm_c[r][c]

                    if va == vb:
                        match_count += 1
                        # A and B agree — likely correct
                        if vc and vc != va:
                            ev.cell_diffs.append(CellEvidence(
                                row=r, col=c,
                                extract_tables=va, camelot=vb, vlm=vc,
                                verdict="ab_agree_c_differs",
                                notes="A+B agree, VLM differs",
                            ))
                    else:
                        # A and B disagree — need arbitration
                        cell_ev = CellEvidence(
                            row=r, col=c,
                            extract_tables=va, camelot=vb, vlm=vc,
                        )
                        if vc:
                            if vc == va:
                                cell_ev.verdict = "a_correct"
                                cell_ev.notes = "VLM confirms extract-tables"
                            elif vc == vb:
                                cell_ev.verdict = "b_correct"
                                cell_ev.notes = "VLM confirms Camelot"
                            else:
                                cell_ev.verdict = "all_differ"
                                cell_ev.notes = "All 3 sources disagree"
                        else:
                            cell_ev.verdict = "needs_vlm"
                            cell_ev.notes = "A/B disagree, no VLM to arbitrate"
                        ev.cell_diffs.append(cell_ev)

            ev.score = match_count / total_cells if total_cells > 0 else 0.0
            ev.cell_gate = "pass" if match_count == total_cells else (
                "partial" if ev.score >= 0.95 else "fail"
            )
        elif ev.shape_a != ev.shape_b:
            ev.cell_gate = "fail"
            ev.score = 0.0
        else:
            ev.cell_gate = "pass"
            ev.score = 1.0

        # --- Grade ---
        if ev.score >= 1.0:
            ev.grade = "A+"
        elif ev.score >= 0.98:
            ev.grade = "A"
        elif ev.score >= 0.95:
            ev.grade = "B"
        elif ev.score >= 0.90:
            ev.grade = "C"
        else:
            ev.grade = "F"

        # --- Verdict ---
        if ev.score >= 1.0:
            ev.verdict = "match"
        elif len(ev.cell_diffs) > 0:
            a_wins = sum(1 for d in ev.cell_diffs if d.verdict == "a_correct")
            b_wins = sum(1 for d in ev.cell_diffs if d.verdict == "b_correct")
            if a_wins > b_wins:
                ev.verdict = "extract_tables_better"
            elif b_wins > a_wins:
                ev.verdict = "camelot_better"
            else:
                ev.verdict = "needs_vlm"
        else:
            ev.verdict = "match"

        evidence_list.append(ev)

    # --- Merge evidence for contiguous tables ---
    if len(tables_a) >= 2:
        merge_candidates = collect_merge_evidence(tables_a, pdf_path, pdf_name)

    return evidence_list, merge_candidates


# ---------------------------------------------------------------------------
# Shadow logging (for /assistant classifier training)
# ---------------------------------------------------------------------------

def log_merge_evidence(candidates: list[MergeCandidate]) -> None:
    """Log merge candidates to shadow for /assistant training."""
    for mc in candidates:
        if mc.should_merge in ("likely_yes", "needs_vlm"):
            entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "type": "merge_candidate",
                "pdf": mc.pdf_name,
                "table_i": mc.table_i,
                "table_j": mc.table_j,
                "col_count_match": mc.col_count_match,
                "width_ratio": round(mc.width_ratio, 3),
                "x_overlap_ratio": round(mc.x_overlap_ratio, 3),
                "y_gap": round(mc.y_gap, 1),
                "header_match": mc.header_match,
                "should_merge": mc.should_merge,
                "confidence": round(mc.confidence, 3),
                "reasoning": mc.reasoning,
            }
            try:
                with open(SHADOW_LOG, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except OSError:
                pass


def log_evidence(evidence_list: list[TableEvidence]) -> None:
    """Log evidence to shadow_evidence.jsonl for classifier training.

    Each disagreement becomes a labeled training example:
    - input: (pdf_name, cell_position, values_from_each_source)
    - label: verdict (which source was correct)
    """
    for ev in evidence_list:
        for diff in ev.cell_diffs:
            if diff.verdict in ("a_correct", "b_correct", "all_differ"):
                entry = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "pdf": ev.pdf_name,
                    "table": ev.table_index,
                    "row": diff.row,
                    "col": diff.col,
                    "value_a": diff.extract_tables,
                    "value_b": diff.camelot,
                    "value_c": diff.vlm,
                    "verdict": diff.verdict,
                    "notes": diff.notes,
                }
                try:
                    with open(SHADOW_LOG, "a") as f:
                        f.write(json.dumps(entry) + "\n")
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def evidence_to_markdown(
    evidence_list: list[TableEvidence],
    output_dir: str,
    merge_candidates: list[MergeCandidate] | None = None,
    include_screenshots: bool = True,
) -> str:
    """Generate markdown report from evidence matrix."""
    out = Path(output_dir)
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    lines = ["# 3-Way Evidence Matrix Report\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| PDF | Table | Shape A | Shape B | Shape C | Score | Grade | Verdict |")
    lines.append("| --- | ----- | ------- | ------- | ------- | ----- | ----- | ------- |")
    for ev in evidence_list:
        lines.append(
            f"| {ev.pdf_name} | {ev.table_index} "
            f"| {ev.shape_a[0]}x{ev.shape_a[1]} "
            f"| {ev.shape_b[0]}x{ev.shape_b[1]} "
            f"| {ev.shape_c[0]}x{ev.shape_c[1]} "
            f"| {ev.score:.1%} | {ev.grade} | {ev.verdict} |"
        )
    lines.append("")

    # Detailed per-table evidence
    for ev in evidence_list:
        lines.append(f"## {ev.pdf_name} - Table {ev.table_index}\n")
        lines.append(f"- Shape gate: **{ev.shape_gate}**")
        lines.append(f"- Cell gate: **{ev.cell_gate}**")
        lines.append(f"- Score: **{ev.score:.1%}**")
        lines.append(f"- Grade: **{ev.grade}**")
        lines.append(f"- Verdict: **{ev.verdict}**\n")

        if ev.cell_diffs:
            # Only show disagreements
            real_diffs = [d for d in ev.cell_diffs if d.verdict != "ab_agree_c_differs"]
            if real_diffs:
                lines.append("### Cell Disagreements\n")
                lines.append("| Row | Col | /extract-tables (A) | Camelot (B) | VLM (C) | Verdict |")
                lines.append("| --- | --- | ------------------- | ----------- | ------- | ------- |")
                for d in real_diffs[:30]:
                    va = d.extract_tables[:35].replace("|", "\\|").replace("\n", " ")
                    vb = d.camelot[:35].replace("|", "\\|").replace("\n", " ")
                    vc = d.vlm[:35].replace("|", "\\|").replace("\n", " ") if d.vlm else "-"
                    lines.append(f"| {d.row} | {d.col} | `{va}` | `{vb}` | `{vc}` | {d.verdict} |")
                if len(real_diffs) > 30:
                    lines.append(f"| ... | ... | ({len(real_diffs) - 30} more) | | | |")
                lines.append("")

            # VLM surprises (A+B agree but C differs)
            vlm_diffs = [d for d in ev.cell_diffs if d.verdict == "ab_agree_c_differs"]
            if vlm_diffs:
                lines.append(f"### VLM Surprises ({len(vlm_diffs)} cells where A+B agree but VLM differs)\n")
                lines.append("| Row | Col | A+B Value | VLM Value |")
                lines.append("| --- | --- | --------- | --------- |")
                for d in vlm_diffs[:10]:
                    va = d.extract_tables[:35].replace("|", "\\|").replace("\n", " ")
                    vc = d.vlm[:35].replace("|", "\\|").replace("\n", " ")
                    lines.append(f"| {d.row} | {d.col} | `{va}` | `{vc}` |")
                lines.append("")
        else:
            lines.append("All cells match across sources.\n")

        # Data preview (first 5 rows of each source)
        lines.append("### Evidence A: /extract-tables\n")
        lines.append(_grid_to_md(ev.data_a, max_rows=5))
        lines.append("")

        lines.append("### Evidence B: Camelot\n")
        lines.append(_grid_to_md(ev.data_b, max_rows=5))
        lines.append("")

        if ev.data_c and ev.data_c != [[""]]:
            lines.append("### Evidence C: VLM Reading\n")
            lines.append(_grid_to_md(ev.data_c, max_rows=5))
            lines.append("")

        lines.append("---\n")

    # --- Merge candidates ---
    if merge_candidates:
        lines.append("## Contiguous Table Merge Evidence\n")
        lines.append("| PDF | Tables | Cols Match | Width Ratio | X Overlap | Y Gap | Header Match | Decision |")
        lines.append("| --- | ------ | ---------- | ----------- | --------- | ----- | ------------ | -------- |")
        for mc in merge_candidates:
            lines.append(
                f"| {mc.pdf_name} | {mc.table_i}->{mc.table_j} "
                f"| {'Y' if mc.col_count_match else 'N'} "
                f"| {mc.width_ratio:.2f} "
                f"| {mc.x_overlap_ratio:.2f} "
                f"| {mc.y_gap:.0f}pt "
                f"| {'Y' if mc.header_match else 'N'} "
                f"| {mc.should_merge} |"
            )
        lines.append("")

    return "\n".join(lines)


def _grid_to_md(grid: list[list[str]], max_rows: int = 10) -> str:
    """Convert a grid to markdown table."""
    if not grid:
        return "> (empty)\n"

    lines = []
    n_cols = max(len(r) for r in grid) if grid else 0
    if n_cols == 0:
        return "> (empty)\n"

    # Header from first row
    header = grid[0] + [""] * (n_cols - len(grid[0]))
    lines.append("| " + " | ".join(
        c.replace("\n", " ").replace("|", "\\|").strip()[:25] for c in header
    ) + " |")
    lines.append("| " + " | ".join("---" for _ in range(n_cols)) + " |")

    # Data rows
    show_rows = min(len(grid) - 1, max_rows)
    for i in range(1, show_rows + 1):
        row = grid[i] + [""] * (n_cols - len(grid[i]))
        lines.append("| " + " | ".join(
            c.replace("\n", " ").replace("|", "\\|").strip()[:30] for c in row
        ) + " |")

    if len(grid) - 1 > max_rows:
        lines.append(f"| ... ({len(grid) - 1 - max_rows} more rows) |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(
    input_path: str = typer.Argument(..., help="PDF file or directory of PDFs"),
    output: str = typer.Option("evidence_report", "--output", "-o", help="Output directory"),
    pages: str = typer.Option("1", "--pages", help="Pages to extract"),
    vlm: str = typer.Option("claude", "--vlm", help="VLM backend for ground truth (claude/gemini/none)"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="Skip VLM (2-way comparison only)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of markdown"),
) -> None:
    """3-way evidence matrix: /extract-tables vs Camelot vs VLM."""
    inp = Path(input_path)
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    skip_vlm = no_vlm or vlm == "none"

    if inp.is_dir():
        pdfs = sorted(inp.glob("*.pdf"))
    else:
        pdfs = [inp]

    all_evidence = []
    all_merge = []
    for pdf in pdfs:
        print(f"Processing {pdf.name}...")
        try:
            ev, merges = assemble_evidence(str(pdf), pages, vlm, skip_vlm=skip_vlm)
            all_evidence.extend(ev)
            all_merge.extend(merges)
        except Exception as e:
            print(f"  ERROR: {e}")

    # Log to shadow for /assistant training
    log_evidence(all_evidence)
    log_merge_evidence(all_merge)

    if json_output:
        # JSON output for automation
        import dataclasses
        out_path = out_dir / "evidence.json"
        data = {
            "tables": [dataclasses.asdict(e) for e in all_evidence],
            "merge_candidates": [dataclasses.asdict(m) for m in all_merge],
        }
        out_path.write_text(json.dumps(data, indent=2))
        print(f"JSON written to {out_path}")
    else:
        # Markdown report
        md = evidence_to_markdown(all_evidence, str(out_dir), all_merge)
        report_path = out_dir / "evidence_matrix.md"
        report_path.write_text(md)
        print(f"Report written to {report_path}")

    # Print summary
    total = len(all_evidence)
    matches = sum(1 for e in all_evidence if e.grade in ("A+", "A"))
    diffs = sum(len(e.cell_diffs) for e in all_evidence)
    merges_pending = sum(1 for m in all_merge if m.should_merge in ("likely_yes", "needs_vlm"))
    print(f"\nSummary: {matches}/{total} tables at A/A+, {diffs} cell disagreements, {merges_pending} merge candidates logged")


if __name__ == "__main__":
    typer.run(main)
