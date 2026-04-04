"""
Ground truth builder for synthetic fixtures.

Builds ground_truth.json from trick definitions and the generated PDF.
The ground truth IS the oracle — extraction is compared against it.
"""
from __future__ import annotations

import json
from pathlib import Path

from gen_tricks_core import (
    FALSE_TABLE_TRICKS,
    MALFORMED_TABLE_TRICKS,
    CURSED_TEXT_TRICKS,
    LAYOUT_TRAP_TRICKS,
    CLASSIFICATION_TRICKS,
)
from gen_tricks_ext import (
    REQUIREMENTS_TRICKS,
    MATH_NOISE_TRICKS,
)


# Map trick names to their category
TRICK_REGISTRY: dict[str, tuple[str, dict]] = {}
for _name, _trick in FALSE_TABLE_TRICKS.items():
    TRICK_REGISTRY[_name] = ("false-tables", _trick)
for _name, _trick in MALFORMED_TABLE_TRICKS.items():
    TRICK_REGISTRY[_name] = ("malformed-tables", _trick)
for _name, _trick in CURSED_TEXT_TRICKS.items():
    TRICK_REGISTRY[_name] = ("cursed-text", _trick)
for _name, _trick in LAYOUT_TRAP_TRICKS.items():
    TRICK_REGISTRY[_name] = ("layout-traps", _trick)
for _name, _trick in REQUIREMENTS_TRICKS.items():
    TRICK_REGISTRY[_name] = ("requirements", _trick)
for _name, _trick in MATH_NOISE_TRICKS.items():
    TRICK_REGISTRY[_name] = ("math-noise", _trick)
for _name, _trick in CLASSIFICATION_TRICKS.items():
    TRICK_REGISTRY[_name] = ("classification", _trick)


def build_ground_truth(
    pdf_path: Path,
    tricks_used: list[str],
    category: str,
    source_pattern: str | None = None,
    source_file: str | None = None,
) -> dict:
    """Build ground truth JSON for a fixture PDF.

    Uses trick definitions to derive expected sections, blocks, tables,
    figures, and requirements. The PDF itself is opened to get page count
    and dimensions.
    """
    fixture_id = pdf_path.stem

    # Get page info from the PDF
    pages = []
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for i in range(doc.page_count):
            pg = doc[i]
            pages.append({
                "page_number": i,
                "width": round(pg.rect.width, 1),
                "height": round(pg.rect.height, 1),
            })
        doc.close()
    except Exception:
        pages = [{"page_number": 0, "width": 612.0, "height": 792.0}]

    sections = []
    blocks = []
    tables = []
    figures = []
    toc_entries = []
    requirements = []

    page_idx = 0

    for trick_name in tricks_used:
        cat, trick = TRICK_REGISTRY.get(trick_name, (category, {}))

        if cat == "false-tables":
            _add_false_table_gt(trick_name, trick, page_idx, blocks, tables)
        elif cat == "malformed-tables":
            _add_malformed_table_gt(trick_name, trick, page_idx, tables)
        elif cat == "cursed-text":
            _add_cursed_text_gt(trick_name, trick, page_idx, blocks)
        elif cat == "layout-traps":
            _add_layout_trap_gt(trick_name, trick, page_idx, sections, blocks, toc_entries, requirements)
        elif cat == "requirements":
            _add_requirements_gt(trick_name, trick, page_idx, requirements, tables)
        elif cat == "math-noise":
            _add_math_noise_gt(trick_name, trick, page_idx, blocks)

    # Compute assertions
    real_tables = [t for t in tables if t.get("is_real_table", True)]
    false_tables_list = [t for t in tables if not t.get("is_real_table", True)]
    real_reqs = [r for r in requirements if r.get("is_real_requirement", True)]
    false_reqs = [r for r in requirements if not r.get("is_real_requirement", True)]

    gt = {
        "version": "1.0",
        "fixture_id": fixture_id,
        "source_pattern": source_pattern,
        "source_file": source_file,
        "tricks": tricks_used,
        "pages": pages,
        "sections": sections,
        "blocks": blocks,
        "tables": tables,
        "figures": figures,
        "toc_entries": toc_entries,
        "requirements": requirements,
        "expected_profile": {
            "preset": "auto",
            "is_scanned": False,
            "has_tables": len(real_tables) > 0,
            "has_figures": len(figures) > 0,
            "has_equations": any(t in tricks_used for t in ["math-notation", "math-heavy", "subscript-superscript"]),
            "layout": "single-column",
        },
        "assertions": {
            "section_count": len(sections),
            "table_count": len(real_tables),
            "false_table_count": len(false_tables_list),
            "figure_count": len(figures),
            "requirement_count": len(real_reqs),
            "false_requirement_count": len(false_reqs),
        },
    }
    return gt


def write_ground_truth(pdf_path: Path, gt: dict) -> Path:
    """Write ground truth JSON sidecar next to the PDF."""
    gt_path = pdf_path.with_name(pdf_path.stem + "_ground_truth.json")
    gt_path.write_text(json.dumps(gt, indent=2, ensure_ascii=False))
    return gt_path


def _add_false_table_gt(name: str, trick: dict, page: int, blocks: list, tables: list):
    """False-positive tables: text that SHOULD NOT be detected as tables."""
    content = trick.get("content", "")
    blocks.append({
        "type": "Text",
        "page": page,
        "text": content[:200],
    })
    tables.append({
        "page": page,
        "is_real_table": False,
        "has_borders": False,
    })


def _add_malformed_table_gt(name: str, trick: dict, page: int, tables: list):
    """Malformed tables: real tables with structural problems."""
    columns = trick.get("columns", [])
    rows = trick.get("rows", [])
    is_borderless = trick.get("borderless", False)
    is_single_col = trick.get("single_column", False)

    tables.append({
        "page": page,
        "rows": len(rows),
        "columns": len(columns),
        "is_real_table": not is_single_col,  # single-column "tables" (like bibliographies) aren't real tables
        "strategy": "stream" if is_borderless else "lattice",
        "has_borders": not is_borderless,
    })


def _add_cursed_text_gt(name: str, trick: dict, page: int, blocks: list):
    """Cursed text: text extraction nightmares."""
    content = trick.get("content", "")
    blocks.append({
        "type": "Text",
        "page": page,
        "text": content[:200],
    })


def _add_layout_trap_gt(name: str, trick: dict, page: int, sections: list, blocks: list, toc_entries: list, requirements: list):
    """Layout traps: structure/layout that confuses extractors."""
    if name == "deep-nesting":
        for title, level in trick.get("sections", []):
            sections.append({
                "title": title,
                "level": level,
                "page": page,
            })
    elif name == "toc-entries" or name == "toc-leaders-captured" or name == "toc-with-pagenums":
        content = trick.get("content", "")
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # TOC entries have dots and page numbers
            if "." * 3 in line or "\t" in line:
                title_part = line.split(".")[0].strip() if "." * 3 in line else line.split("\t")[0].strip()
                toc_entries.append({
                    "title": title_part,
                    "page": page,
                    "level": 1,
                })
    elif name == "requirements-doc":
        content = trick.get("content", "")
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            for modal in ("SHALL", "MUST", "WILL"):
                if modal in line.upper():
                    requirements.append({
                        "text": line[:200],
                        "page": page,
                        "is_real_requirement": True,
                        "modal": modal,
                    })
                    break
    elif name in ("footnote-sections", "page-number-sections", "partial-header", "sentence-as-header"):
        # These are NOT sections — they are traps
        blocks.append({
            "type": "Text",
            "page": page,
            "text": trick.get("content", "")[:200],
        })
    elif name == "boundary-heading-sizes":
        # These ARE real sections at 1.2x body font
        for heading, _body in [
            ("1. Overview", ""), ("2. Background", ""), ("3. Methodology", ""),
            ("4. Results", ""), ("5. Discussion", ""),
        ]:
            sections.append({"title": heading, "level": 1, "page": page})
    elif name == "code-heavy-font-skew":
        sections.append({"title": "1. Introduction", "level": 1, "page": page})
        sections.append({"title": "2. Architecture", "level": 1, "page": page})
        blocks.append({"type": "Code", "page": page, "text": "def process_data(input: str) -> dict:"})
    elif name == "section-merge-cascade":
        content = trick.get("content", "")
        for line in content.strip().split("\n"):
            line = line.strip()
            if line and not line[0].islower() and len(line) < 60 and not line.startswith("  "):
                sections.append({"title": line, "level": 1, "page": page})
    else:
        # Generic layout trap
        blocks.append({
            "type": "Text",
            "page": page,
            "text": trick.get("content", "")[:200],
        })


def _add_requirements_gt(name: str, trick: dict, page: int, requirements: list, tables: list):
    """Requirements tricks: SHALL/MUST patterns."""
    if trick.get("type") == "table":
        columns = trick.get("columns", [])
        rows = trick.get("rows", [])
        tables.append({
            "page": page,
            "rows": len(rows),
            "columns": len(columns),
            "is_real_table": True,
            "strategy": "lattice",
            "has_borders": True,
        })
        # Extract requirements from table cells
        for row in rows:
            for cell in row:
                for modal in ("SHALL", "MUST", "WILL"):
                    if modal in cell.upper():
                        is_real = name != "false-positive-shall"
                        requirements.append({
                            "text": cell[:200],
                            "page": page,
                            "is_real_requirement": is_real,
                            "modal": modal,
                        })
                        break
    else:
        content = trick.get("content", "")
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            for modal in ("SHALL", "MUST", "WILL", "SHOULD", "MAY"):
                if modal in line.upper():
                    is_real = name != "false-positive-shall"
                    requirements.append({
                        "text": line[:200],
                        "page": page,
                        "is_real_requirement": is_real,
                        "modal": modal,
                    })
                    break


def _add_math_noise_gt(name: str, trick: dict, page: int, blocks: list):
    """Math noise: equation vs text discrimination."""
    content = trick.get("content", "")
    block_type = "Equation" if name in ("inline-vs-display",) else "Text"
    blocks.append({
        "type": block_type,
        "page": page,
        "text": content[:200],
    })
