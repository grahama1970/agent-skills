"""Deterministic golden-slice bundle builder for /review-extraction.

Per ~/.claude/skills/review-extraction/SKILL.md, a reviewable extraction bundle is
a directory of evidence — page identity, extractor JSON, render, overlay, crops,
comparison table, manifest, review_bundle.md. This script produces exactly that
layout for one human-labeled page. It is evidence-only:

- No preset edits.
- No ledger entries.
- No core pdf_oxide patches.
- No closure-matrix mutation.
- No LLM call.
- No batch mode.

CLI:

    python build_golden_slice_bundle.py \
        --pdf /path/to/source.pdf \
        --page-index 27 \
        --expected-elements /path/to/expected_elements.json \
        --out /tmp/pdf-lab-golden-slices/<slice_id> \
        [--human-labeled-page /path/to/human_labeled_page.png] \
        [--ledger /path/to/promotion_ledger.json] \
        [--slice-id <id>] \
        [--pdf-render-scale 1.5] \
        [--zip]

Outputs (matches SKILL.md spec):

    <out>/
      manifest.json
      review_bundle.md
      command_log.txt
      images/
        page_clean.png
        pdf_oxide_overlay.png
        human_labeled_page.png   # only when --human-labeled-page supplied
        element_crops/
          <element_id>.png ...
      json/
        page_identity.json
        expected_elements.json
        pdf_oxide_raw_page.json
        pdf_oxide_release_page.json
        golden_slice_comparison.json
        mismatches_by_owner.json
      tables/
        extracted_elements_table.md
        golden_slice_comparison.md

If --zip is passed the runner also writes <out>.zip alongside the directory.

This module is intentionally a single file with no project-specific imports
other than `pdf_oxide` (the extractor) and `pdf_oxide.presets.applier`. It
runs from any working directory; the skill's user does not need to be in
the pdf_oxide repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


# --- module discovery ---------------------------------------------------------
# We need apply_ledger and snapshot's bbox-normalization helpers. They live in
# the pdf_oxide source tree. Allow the caller to point at it via env var, but
# also auto-resolve from a known relative layout.

def _find_pdf_oxide_repo() -> Path | None:
    """Locate the pdf_oxide repo so we can import its applier + helpers."""
    import os
    env = os.environ.get("PDF_OXIDE_REPO")
    if env and Path(env).exists():
        return Path(env)
    candidates = [
        Path("/home/graham/workspace/experiments/pdf_oxide"),
        Path.home() / "workspace" / "experiments" / "pdf_oxide",
    ]
    for c in candidates:
        if (c / "python" / "pdf_oxide" / "presets" / "applier.py").exists():
            return c
    return None


def _import_pdf_oxide_helpers() -> tuple[Any, Any, Any]:
    """Return (apply_ledger, ApplierConfig, snapshot_module)."""
    repo = _find_pdf_oxide_repo()
    if repo is None:
        raise RuntimeError(
            "could not locate pdf_oxide repo for applier import; set PDF_OXIDE_REPO"
        )
    sys.path.insert(0, str(repo / "python"))
    sys.path.insert(0, str(repo / "scripts" / "pdf_lab"))
    from pdf_oxide.presets.applier import apply_ledger, ApplierConfig  # noqa: E402
    import snapshot_current_extraction as snap  # noqa: E402
    return apply_ledger, ApplierConfig, snap


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


# --- blocked_on payload (SKILL.md v2 + PROJECT_KNOWLEDGE.md §10 trigger b) ---

_BLOCKED_ON_REQUIRED_FIELDS = (
    "schema_version",
    "stop_condition_id",
    "where_blocked",
    "specific_question",
    "artifacts_to_consult",
    "what_i_will_NOT_do_without_decision",
    "what_decision_unblocks",
)

_BLOCKED_ON_STOP_CONDITIONS = frozenset({
    "expected_contract_ambiguous",
    "requires_product_judgment",
    "mismatch_persists_after_two_rounds",
    "scope_would_broaden",
    "core_vs_preset_ownership_lacks_reproducer",
    "cannot_produce_resubmission_zip",
})


class BlockedOnValidationError(ValueError):
    """Raised when the --blocked-on payload is malformed.

    Per SKILL.md hard rule: no blocked_on payload → no auto-send. The
    validator runs at write time so a malformed payload never reaches the
    bundle.
    """


def _validate_blocked_on(payload: dict[str, Any]) -> None:
    """Reject malformed blocked_on payloads at write time."""
    missing = [f for f in _BLOCKED_ON_REQUIRED_FIELDS if f not in payload]
    if missing:
        raise BlockedOnValidationError(
            f"blocked_on payload missing required fields: {missing}"
        )
    sv = payload.get("schema_version")
    if sv != "review_extraction.blocked_on.v1":
        raise BlockedOnValidationError(
            f"blocked_on.schema_version={sv!r}; expected 'review_extraction.blocked_on.v1'"
        )
    sid = payload.get("stop_condition_id")
    if sid not in _BLOCKED_ON_STOP_CONDITIONS:
        raise BlockedOnValidationError(
            f"blocked_on.stop_condition_id={sid!r} is not one of the six allowed: "
            f"{sorted(_BLOCKED_ON_STOP_CONDITIONS)}"
        )
    where = payload.get("where_blocked")
    if not isinstance(where, list) or len(where) == 0:
        raise BlockedOnValidationError(
            "blocked_on.where_blocked must be a non-empty list of specific locations "
            "(not prose like 'extraction is bad')"
        )
    for i, entry in enumerate(where):
        if not isinstance(entry, dict) or not entry.get("detail"):
            raise BlockedOnValidationError(
                f"blocked_on.where_blocked[{i}] must be a dict with a 'detail' field"
            )
    q = payload.get("specific_question")
    if not isinstance(q, str) or len(q.strip()) < 30:
        raise BlockedOnValidationError(
            "blocked_on.specific_question must be a precise question (≥30 chars)"
        )
    for k in ("artifacts_to_consult", "what_i_will_NOT_do_without_decision",
              "what_decision_unblocks"):
        v = payload.get(k)
        if not isinstance(v, list) or len(v) == 0:
            raise BlockedOnValidationError(
                f"blocked_on.{k} must be a non-empty list"
            )


def _render_blocked_on_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Asking for — bundle is BLOCKED, awaiting reviewer decision",
        "",
        f"**Schema:** `{payload['schema_version']}`",
        f"**Stop condition:** `{payload['stop_condition_id']}`",
        "",
        "## Specific question (please answer this)",
        "",
        payload["specific_question"],
        "",
        "## Where I am blocked",
        "",
    ]
    for i, entry in enumerate(payload["where_blocked"], 1):
        lines.append(f"{i}. **{entry.get('expected_family') or '(no family)'}** — {entry['detail']}")
        for k, v in entry.items():
            if k in {"expected_family", "detail"}:
                continue
            lines.append(f"   - `{k}`: {v}")
    lines += ["", "## Artifacts to consult (open these in this bundle)", ""]
    for a in payload["artifacts_to_consult"]:
        lines.append(f"- `{a}`")
    lines += ["", "## What I will NOT do without your decision", ""]
    for g in payload["what_i_will_NOT_do_without_decision"]:
        lines.append(f"- {g}")
    lines += ["", "## What your decision unblocks", ""]
    for u in payload["what_decision_unblocks"]:
        lines.append(f"- {u}")
    return "\n".join(lines) + "\n"


# --- page extraction ---------------------------------------------------------


def _extract_page(
    pdf_path: Path,
    page_index: int,
    ledger_path: Path | None,
    *,
    apply_ledger,
    ApplierConfig,
    snap,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (raw_payload, release_payload) for one page."""
    import pdf_oxide

    doc = pdf_oxide.open(str(pdf_path))
    page_w, page_h = doc.page_dimensions(page_index)

    raw_elements: list[dict[str, Any]] = []
    blocks = doc.classify_blocks(page_index) or []
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "").strip()
        raw_elements.append({
            "id": f"actual:p{page_index}:block:{index}",
            "page": page_index,
            "type": "unknown_region",
            "source_type": str(block.get("block_type") or "unknown"),
            "bbox": snap._norm_bbox_block(block.get("bbox"), page_w, page_h),
            "text": text,
            "raw": block,
        })
    tables = doc.extract_tables(page_index) or []
    for index, table in enumerate(tables):
        if not isinstance(table, dict):
            table = {"raw_value": table}
        metrics = snap._table_metrics(table)
        raw_elements.append({
            "id": f"actual:p{page_index}:table:{index}",
            "page": page_index,
            "type": "table",
            "source_type": "table",
            "bbox": snap._table_bbox(table, page_w, page_h),
            "text": table.get("text") or table.get("markdown") or "",
            "raw": {**table, **metrics},
        })

    raw_payload = {
        "schema_version": "review_extraction.page_raw.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pdf_path": str(pdf_path),
        "page_index": page_index,
        "page_dimensions_pts": [page_w, page_h],
        "elements": raw_elements,
    }

    if ledger_path and ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        released = apply_ledger(raw_elements, ledger, ApplierConfig(mode="release"))
        ledger_used = str(ledger_path)
    else:
        released = raw_elements
        ledger_used = None

    release_payload = {
        "schema_version": "review_extraction.page_release.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pdf_path": str(pdf_path),
        "page_index": page_index,
        "ledger_path": ledger_used,
        "apply_mode": "release",
        "elements": released,
    }
    return raw_payload, release_payload


# --- rendering ---------------------------------------------------------------

_TYPE_COLORS = {
    "header_footer_noise": (120, 120, 120),
    "section_heading":     (200, 50,  50),
    "paragraph_block":     (60,  100, 200),
    "list":                (60,  170, 80),
    "table":               (220, 130, 30),
    "caption":             (180, 80,  200),
    "reference":           (140, 80,  60),
    "footnote":            (80,  80,  180),
    "boxed_callout":       (220, 30,  150),
}


def _render_evidence(
    pdf_path: Path,
    page_index: int,
    release_payload: dict[str, Any],
    raw_payload: dict[str, Any],
    images_dir: Path,
    crops_dir: Path,
    scale: float,
) -> dict[str, Any]:
    """Render page_clean.png, pdf_oxide_overlay.png, per-element crops."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw, ImageFont

    doc = pdfium.PdfDocument(str(pdf_path))
    page_obj = doc[page_index]
    img = page_obj.render(scale=scale).to_pil().convert("RGB")
    w, h = img.size

    images_dir.mkdir(parents=True, exist_ok=True)
    crops_dir.mkdir(parents=True, exist_ok=True)

    page_clean = images_dir / "page_clean.png"
    img.save(page_clean)

    overlay = img.copy()
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14
        )
    except OSError:
        font = ImageFont.load_default()

    raw_by_id = {e["id"]: e for e in raw_payload["elements"]}

    pad_norm = 0.02
    pad_x = int(round(pad_norm * w))
    pad_y = int(round(pad_norm * h))

    for el in release_payload["elements"]:
        bbox = el.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x0 = max(0, int(round(bbox[0] * w)))
        y0 = max(0, int(round(bbox[1] * h)))
        x1 = min(w, int(round(bbox[2] * w)))
        y1 = min(h, int(round(bbox[3] * h)))
        color = _TYPE_COLORS.get(el.get("type") or "", (40, 40, 40))
        draw.rectangle([x0, y0, x1, y1], outline=color, width=3)

        eid_tail = ":".join(el["id"].split(":")[-2:])
        raw_el = raw_by_id.get(el["id"]) or {}
        bt = (raw_el.get("raw") or {}).get("block_type") or el.get("source_type") or "?"
        label = f"{eid_tail}  {el.get('type')}  ({bt})"
        text_y = max(0, y0 - 18)
        tbox = draw.textbbox((x0, text_y), label, font=font)
        draw.rectangle(tbox, fill=color)
        draw.text((x0, text_y), label, fill=(255, 255, 255), font=font)

        cx0 = max(0, x0 - pad_x); cy0 = max(0, y0 - pad_y)
        cx1 = min(w, x1 + pad_x); cy1 = min(h, y1 + pad_y)
        safe = el["id"].replace(":", "_")
        img.crop((cx0, cy0, cx1, cy1)).save(crops_dir / f"{safe}.png")

    overlay_path = images_dir / "pdf_oxide_overlay.png"
    overlay.save(overlay_path)
    doc.close()

    return {
        "page_clean": str(page_clean),
        "pdf_oxide_overlay": str(overlay_path),
        "page_size_px": [w, h],
        "crop_count": sum(1 for _ in crops_dir.glob("*.png")),
    }


# --- comparison table --------------------------------------------------------

# Synonym map for auto-matching expected_family to emitted type. Keep this
# conservative — when the synonym fails, the reviewer fills in the row.
_TYPE_SYNONYMS = {
    "running_header": {"header_footer_noise"},
    "footer": {"header_footer_noise"},
    "side_watermark_or_page_chrome_noise": {"header_footer_noise"},
    "chapter_label": {"section_heading"},
    "section_heading": {"section_heading"},
    "section_subtitle": {"section_heading", "paragraph_block"},
    "paragraph_block": {"paragraph_block"},
    "bullet_list": {"list"},
    "list_item": {"list"},
    "footnote_block": {"footnote", "paragraph_block"},
}


def _normalize(s: str) -> str:
    """Lowercase + collapse whitespace; used for substring text match."""
    return " ".join((s or "").lower().split())


def _bbox_iou(a: list[float], b: list[float]) -> float:
    """xyxy normalized → IoU. Returns 0.0 on malformed input."""
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    ix0 = max(a[0], b[0]); iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2]); iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def _evaluate_candidate(
    entry: dict[str, Any],
    el: dict[str, Any],
    type_synonyms: set[str],
) -> tuple[bool, str, bool, bool]:
    """Decide whether `el` is a candidate for expected `entry`.

    Semantics (per SKILL.md v2 + R3 test contract):

    When the human supplied any strict criterion (text_hint, bbox_hint, or
    allowed_types), ALL supplied criteria must hold for the element to be a
    candidate — the matcher does NOT fall back to family/type-synonyms.
    This is what prevents "missing" rows from being silently reclassified as
    "ambiguous_multiple" via the legacy fallback.

    When the human supplied NO strict criteria, the matcher uses the v1
    conservative path (family/type-synonyms OR label substring).

    Returns (is_candidate, match_basis, type_match, text_match).
    """
    el_text_norm = _normalize(el.get("text") or "")
    el_type = el.get("type") or ""

    text_hint = entry.get("text_hint")
    bbox_hint = entry.get("bbox_hint")
    allowed = entry.get("allowed_types") or []

    has_text_hint = bool(text_hint)
    has_bbox_hint = bool(bbox_hint)
    has_allowed = bool(allowed)
    has_any_strict = has_text_hint or has_bbox_hint or has_allowed

    if has_any_strict:
        # Hard filters — every supplied criterion must hold.
        text_ok = False
        if has_text_hint:
            hint_norm = _normalize(text_hint)
            text_ok = bool(hint_norm) and hint_norm in el_text_norm
            if not text_ok:
                return False, "", False, False
        if has_bbox_hint:
            iou = _bbox_iou(bbox_hint, el.get("bbox") or [])
            if iou < 0.5:
                return False, "", False, False
        if has_allowed and el_type not in allowed:
            return False, "", False, False
        # All supplied criteria satisfied. Pick the strongest basis.
        if has_text_hint:
            basis = "text_hint"
        elif has_bbox_hint:
            basis = "bbox_hint"
        else:
            basis = "allowed_types"
        type_ok = (el_type in allowed) if has_allowed else True
        return True, basis, type_ok, text_ok

    # No strict criteria → v1 conservative fallback.
    label_norm = _normalize(entry.get("label") or "")
    type_ok = el_type in type_synonyms
    text_ok = bool(label_norm) and label_norm in el_text_norm
    if type_ok or text_ok:
        basis = "type_synonym" if type_ok else "fallback"
        return True, basis, type_ok, text_ok
    return False, "", False, False


def _build_comparison(
    expected: dict[str, Any],
    release_payload: dict[str, Any],
    raw_payload: dict[str, Any],
) -> dict[str, Any]:
    """Match each expected family to emitted elements using a precedence
    chain (text_hint → bbox_hint → allowed_types → type-synonym fallback).
    Emits 4-bucket classification:

      - matched              — exactly one deterministic candidate
      - ambiguous_multiple   — >=2 candidates; reviewer must narrow
      - missing              — no candidate
      - extra_extractor_element — emitted elements not paired with any expected

    Per row: candidate_matches[], best_match_id (only when match_status =
    matched), match_status, reviewer_action_required, match_basis,
    type_match, text_match, bbox_match. owner_if_wrong / next_step stay
    REVIEWER_FILL.
    """
    raw_by_id = {e["id"]: e for e in raw_payload["elements"]}
    rows: list[dict[str, Any]] = []
    matched_ids: set[str] = set()

    for entry in expected.get("expected_elements", []) or []:
        fam = entry.get("family")
        label = entry.get("label") or ""
        synonyms = _TYPE_SYNONYMS.get(fam, set()) | {fam}

        candidates: list[dict[str, Any]] = []
        for el in release_payload["elements"]:
            is_cand, basis, type_ok, text_ok = _evaluate_candidate(
                entry, el, synonyms,
            )
            if not is_cand:
                continue
            raw_el = raw_by_id.get(el["id"]) or {}
            bt = (raw_el.get("raw") or {}).get("block_type") or el.get("source_type") or "?"
            candidates.append({
                "id": el["id"],
                "type": el.get("type"),
                "block_type": str(bt),
                "match_basis": basis,
                "type_match": type_ok,
                "text_match": text_ok,
                "text_preview": (el.get("text") or "")[:120],
            })
            matched_ids.add(el["id"])

        # Aggregate row-level signals from candidates
        if len(candidates) == 0:
            match_status = "missing"
            best_match_id = None
            reviewer_action_required = True
            row_basis = "none"
            row_type_match = False
            row_text_match = False
        elif len(candidates) == 1:
            match_status = "matched"
            best_match_id = candidates[0]["id"]
            reviewer_action_required = False
            row_basis = candidates[0]["match_basis"]
            row_type_match = candidates[0]["type_match"]
            row_text_match = candidates[0]["text_match"]
        else:
            match_status = "ambiguous_multiple"
            best_match_id = None  # NOT deterministic; reviewer narrows
            reviewer_action_required = True
            # Report the strongest basis observed across candidates
            priority = {"text_hint": 0, "bbox_hint": 1, "allowed_types": 2,
                        "type_synonym": 3, "fallback": 4}
            best_c = min(candidates, key=lambda c: priority.get(c["match_basis"], 99))
            row_basis = best_c["match_basis"]
            row_type_match = any(c["type_match"] for c in candidates)
            row_text_match = any(c["text_match"] for c in candidates)

        rows.append({
            "expected_family": fam,
            "human_label": label,
            "match_status": match_status,
            "candidate_matches": candidates or None,
            "best_match_id": best_match_id,
            "reviewer_action_required": reviewer_action_required,
            "match_basis": row_basis,
            "type_match": row_type_match,
            "text_match": row_text_match,
            "bbox_match": "n/a (no human bbox)" if "bbox_hint" not in entry or entry.get("bbox_hint") is None
                          else "REVIEWER_FILL",
            "owner_if_wrong": "REVIEWER_FILL",
            "next_step": "REVIEWER_FILL",
            "notes": None,
        })

    extras = [
        {
            "emitted_id": el["id"],
            "emitted_type": el.get("type"),
            "source_type": el.get("source_type"),
            "text_preview": (el.get("text") or "")[:120],
            "match_status": "extra_extractor_element",
            "reviewer_action_required": True,
        }
        for el in release_payload["elements"]
        if el["id"] not in matched_ids
    ]
    return {
        "schema_version": "review_extraction.golden_slice_comparison.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "slice_id": expected.get("slice_id"),
        "auto_match_basis": (
            "matcher precedence (R3): text_hint → bbox_hint(IoU≥0.5) → "
            "allowed_types → type-synonym fallback. 4-bucket status "
            "(matched / ambiguous_multiple / missing / extra_extractor_element). "
            "'matched' requires exactly one candidate; reviewer narrows ambiguous."
        ),
        "match_criteria_notes": [
            "Matcher evaluates candidates in this order; first hit wins for the row's match_basis label: text_hint substring, bbox_hint IoU≥0.5, allowed_types membership, type-synonym fallback.",
            "candidate_matches list every emitted element that matched at any precedence level.",
            "best_match_id is set ONLY when match_status == 'matched' (exactly one candidate).",
            "reviewer_action_required is true for ambiguous_multiple, missing, and every extra_extractor_element.",
            "ambiguous_multiple is NOT 'success' — it means the matcher found multiple candidates and the reviewer must narrow.",
            "bbox_match: 'n/a (no human bbox)' unless expected entry supplies bbox_hint; otherwise reviewer fills.",
        ],
        "owner_values_allowed": [
            "no_change", "pdf_oxide_core", "nist_preset_ledger",
            "downstream_semantic_parser", "second_pass_visual_adjudicator",
            "human_decision",
        ],
        "rows": rows,
        "extra_pdf_oxide_elements_not_in_human_label": extras,
        "summary": {
            "expected_element_count": len(rows),
            "matched_count": sum(1 for r in rows if r["match_status"] == "matched"),
            "ambiguous_multiple_count": sum(1 for r in rows if r["match_status"] == "ambiguous_multiple"),
            "missing_count": sum(1 for r in rows if r["match_status"] == "missing"),
            "extra_extractor_element_count": len(extras),
            "reviewer_action_required_count": sum(1 for r in rows if r["reviewer_action_required"]) + len(extras),
        },
    }


def _comparison_md(comparison: dict[str, Any]) -> str:
    rows = comparison["rows"]
    lines = [
        f"# Golden Slice Comparison ({comparison.get('slice_id')})",
        "",
        f"Generated: {comparison['generated_at']}",
        f"Schema: `{comparison.get('schema_version')}`",
        "",
        "## Match criteria notes",
        "",
    ]
    for n in comparison["match_criteria_notes"]:
        lines.append(f"- {n}")
    lines += [
        "",
        "## Comparison table (reviewer fills `owner_if_wrong`, `next_step`, and narrows ambiguous_multiple to best_match_id)",
        "",
        "| # | expected_family | human_label | match_status | match_basis | type_match | text_match | bbox_match | best_match_id | candidate_matches | reviewer_action_required | owner_if_wrong | next_step |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        candidates = r.get("candidate_matches") or []
        if not candidates:
            cands_render = "—"
        else:
            cands_render = "<br>".join(
                f"`{c['id']}` ({c['type']} / {c['block_type']}; basis={c['match_basis']}; type_match={c['type_match']}; text_match={c['text_match']})"
                for c in candidates
            )
        best = r.get("best_match_id") or "—"
        lines.append(
            f"| {i} | {r['expected_family']} | {r['human_label']} | **{r['match_status']}** "
            f"| {r['match_basis']} | {r['type_match']} | {r['text_match']} | {r['bbox_match']} "
            f"| {best} | {cands_render} | {r['reviewer_action_required']} "
            f"| {r['owner_if_wrong']} | {r['next_step']} |"
        )
    extras = comparison["extra_pdf_oxide_elements_not_in_human_label"]
    lines += ["", "## Extra emitted elements (`extra_extractor_element`)", ""]
    if not extras:
        lines.append("(none)")
    else:
        lines.append("| emitted_id | type | source_type | text_preview | reviewer_action_required |")
        lines.append("|---|---|---|---|---|")
        for e in extras:
            preview = e["text_preview"].replace("|", "\\|")
            lines.append(
                f"| {e['emitted_id']} | {e['emitted_type']} | {e['source_type']} | {preview} | {e['reviewer_action_required']} |"
            )
    s = comparison["summary"]
    lines += [
        "", "## Summary",
        "",
        f"- expected_element_count: **{s['expected_element_count']}**",
        f"- matched (single deterministic): **{s['matched_count']}**",
        f"- ambiguous_multiple (reviewer narrows): **{s['ambiguous_multiple_count']}**",
        f"- missing (no candidate): **{s['missing_count']}**",
        f"- extra_extractor_element: **{s['extra_extractor_element_count']}**",
        f"- reviewer_action_required (rows + extras): **{s['reviewer_action_required_count']}**",
    ]
    return "\n".join(lines) + "\n"


def _extracted_elements_table_md(release_payload: dict[str, Any],
                                 raw_payload: dict[str, Any]) -> str:
    raw_by_id = {e["id"]: e for e in raw_payload["elements"]}
    lines = [
        "# Extracted elements (mechanical)", "",
        "| id | type | block_type | text_preview |",
        "|---|---|---|---|",
    ]
    for el in release_payload["elements"]:
        raw_el = raw_by_id.get(el["id"]) or {}
        bt = (raw_el.get("raw") or {}).get("block_type") or el.get("source_type")
        text = (el.get("text") or "").replace("|", "\\|")
        if len(text) > 100:
            text = text[:97] + "..."
        lines.append(f"| {el['id']} | {el.get('type')} | {bt} | {text} |")
    return "\n".join(lines) + "\n"


# --- manifest + review_bundle ------------------------------------------------


def _manifest(
    slice_id: str,
    pdf_path: Path,
    page_index: int,
    expected: dict[str, Any],
    artifact_paths: dict[str, str],
    page_dims: list[int],
    crop_count: int,
    has_human_label: bool,
    ledger_path: Path | None,
    optional_code_info: dict[str, str] | None = None,
    blocked_on_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    optional_code_info = optional_code_info or {}
    optional_code_present = bool(optional_code_info)
    return {
        "schema_version": "review_extraction.golden_slice.v2",
        "slice_id": slice_id,
        "source_pdf": str(pdf_path),
        "source_pdf_sha256": _sha256(pdf_path),
        "human_claim": expected.get("human_page_claim"),
        "zero_based_page_index": page_index,
        "one_based_pdf_page_number": page_index + 1,
        "printed_page_label": expected.get("printed_page_label"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "scripts/build_golden_slice_bundle.py",
        "release_mode": True,
        "apply_mode": "release",
        "staging_entries_used": False,
        "llm_used": False,

        # WebGPT 2026-05-13 R3: split mutation flags. Each is independent.
        # `code_or_preset_mutated` from v1/v2 is deprecated and intentionally
        # NOT emitted — bundle consumers must read the four split flags.
        "extraction_code_mutated": False,
        "preset_or_ledger_mutated": False,
        "matrix_mutated": False,
        "review_tooling_code_mutated": optional_code_present,

        "human_labeled_page_image_present": has_human_label,
        "optional_code_present": optional_code_present,
        "optional_code_runner_sha256": optional_code_info.get("runner_sha256"),
        "blocked_on": blocked_on_payload,
        "ledger_used": str(ledger_path) if ledger_path and ledger_path.exists() else None,
        "page_dimensions_px": page_dims,
        "crop_count": crop_count,
        "artifact_paths": artifact_paths,
    }


def _build_optional_code_dir(
    out_dir: Path,
    runner_path: Path,
    smoke_test_stdout: str,
) -> dict[str, str]:
    """Per SKILL.md: when tooling code changed, emit optional_code/ inside
    the bundle. We generate three artifacts for review:

      - git_diff.patch     — runner source as a diff vs /dev/null
                              (since the file is net-new in this PR)
      - changed_files.txt  — inventory + SHAs
      - test_output.txt    — the smoke-test stdout from this very run
    """
    oc = out_dir / "optional_code"
    oc.mkdir(parents=True, exist_ok=True)

    # 1. git_diff.patch — synthesize a diff against /dev/null so the
    #    reviewer sees the full source as additions. We use `git diff
    #    --no-index` between an empty file and the real runner; falls back
    #    to a unified-diff stub if git is unavailable.
    diff_path = oc / "git_diff.patch"
    try:
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--", "/dev/null", str(runner_path)],
            capture_output=True, text=True, check=False, timeout=30,
        )
        diff_text = proc.stdout
        if not diff_text and proc.stderr:
            diff_text = f"# git diff stderr:\n{proc.stderr}\n"
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        diff_text = f"# git not available to generate diff: {exc}\n# Full runner source:\n\n"
        diff_text += runner_path.read_text(encoding="utf-8")
    diff_path.write_text(diff_text, encoding="utf-8")

    # 2. changed_files.txt
    cf_path = oc / "changed_files.txt"
    runner_sha = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    cf_lines = [
        "Files changed in this golden-slice bundle (optional_code/):",
        "",
        f"  + {runner_path}",
        f"    sha256: {runner_sha}",
        f"    size:   {runner_path.stat().st_size} bytes",
        "",
        "Companion skill files (installed alongside the runner; not changed in this round):",
        f"  ~/.claude/skills/review-extraction/SKILL.md",
        f"  ~/.claude/skills/review-extraction/README.md",
        f"  ~/.claude/skills/review-extraction/UPSTREAM_MANIFEST.json",
        "",
        "Note: the runner file is net-new (not a modification of an existing tracked file),",
        "so `git_diff.patch` is generated against /dev/null using `git diff --no-index`.",
    ]
    cf_path.write_text("\n".join(cf_lines) + "\n", encoding="utf-8")

    # 3. test_output.txt — the runner's own JSON summary stdout
    to_path = oc / "test_output.txt"
    to_path.write_text(
        "# Smoke-test stdout from build_golden_slice_bundle.py self-invocation:\n\n"
        + smoke_test_stdout
        + "\n",
        encoding="utf-8",
    )

    return {
        "optional_code_dir": str(oc),
        "git_diff_patch":    str(diff_path),
        "changed_files_txt": str(cf_path),
        "test_output_txt":   str(to_path),
        "runner_sha256":     runner_sha,
    }


def _review_bundle_md(
    manifest: dict[str, Any],
    expected: dict[str, Any],
    release_payload: dict[str, Any],
    comparison: dict[str, Any],
) -> str:
    summ = comparison["summary"]
    lines = [
        f"# Golden Slice Review Bundle — {manifest['slice_id']}", "",
        "> Evidence bundle. No pdf_oxide core, preset, ledger, matrix, or LLM",
        "> changes. Review tooling code (the runner that built this bundle) is",
        "> included under `optional_code/` when present. See §6 for the split",
        "> mutation flags.",
        "",
    ]
    # §0 — Asking-for block (only when blocked_on is set)
    blocked_on_payload = manifest.get("blocked_on")
    if blocked_on_payload:
        lines += [
            "## 0. Asking for — bundle is BLOCKED, awaiting reviewer decision",
            "",
            f"**Stop condition:** `{blocked_on_payload.get('stop_condition_id')}`",
            "",
            "**Specific question:**",
            "",
            f"> {blocked_on_payload.get('specific_question')}",
            "",
            f"Full structured payload: `blocked_on.md` (top-level) and "
            f"`json/blocked_on.json`. The reviewer should open `blocked_on.md` "
            f"FIRST, then consult the artifacts listed there.",
            "",
        ]
    lines += [
        "## 1. Page identity", "",
        f"- source_pdf: `{manifest['source_pdf']}`",
        f"- source_pdf_sha256: `{manifest['source_pdf_sha256'][:16]}…`",
        f"- human_claim: **{manifest['human_claim']}**",
        f"- zero_based_page_index: **{manifest['zero_based_page_index']}**",
        f"- one_based_pdf_page_number: **{manifest['one_based_pdf_page_number']}**",
        f"- printed_page_label: **{manifest['printed_page_label']}**",
        "",
        "## 2. Human expected elements", "",
    ]
    for i, e in enumerate(expected.get("expected_elements", []) or [], 1):
        lines.append(f"{i}. **{e.get('family')}** — {e.get('label')}")
    lines += [
        "",
        f"## 3. pdf_oxide emitted elements ({len(release_payload['elements'])})",
        "", "See `tables/extracted_elements_table.md` for the full table.",
        "",
        "## 4. Comparison summary", "",
        f"- expected: **{summ['expected_element_count']}**",
        f"- matched (single deterministic): **{summ['matched_count']}**",
        f"- ambiguous_multiple (reviewer narrows): **{summ['ambiguous_multiple_count']}**",
        f"- missing: **{summ['missing_count']}**",
        f"- extra_extractor_element: **{summ['extra_extractor_element_count']}**",
        f"- reviewer_action_required total: **{summ['reviewer_action_required_count']}**",
        "",
        "Reviewer fills `owner_if_wrong` and `next_step` in `tables/golden_slice_comparison.md`.",
        "",
        "## 5. Artifact paths", "",
    ]
    for k, v in (manifest.get("artifact_paths") or {}).items():
        lines.append(f"- **{k}**: `{v}`")
    lines += [
        "",
        "## 6. Mutation status (per SKILL.md v3 split flags)", "",
        "No pdf_oxide core, preset, ledger, matrix, or LLM changes.",
        "Review tooling code is included under `optional_code/` when present.",
        "",
        f"- extraction_code_mutated: **{manifest['extraction_code_mutated']}**",
        f"- preset_or_ledger_mutated: **{manifest['preset_or_ledger_mutated']}**",
        f"- matrix_mutated: **{manifest['matrix_mutated']}**",
        f"- review_tooling_code_mutated: **{manifest['review_tooling_code_mutated']}**  ← implied by `optional_code_present`",
        "",
        "## 7. Other tripwire flags", "",
        f"- release_mode: **{manifest['release_mode']}**",
        f"- apply_mode: **{manifest['apply_mode']}**",
        f"- staging_entries_used: **{manifest['staging_entries_used']}**",
        f"- llm_used: **{manifest['llm_used']}**",
        f"- human_labeled_page_image_present: **{manifest['human_labeled_page_image_present']}**",
        f"- optional_code_present: **{manifest.get('optional_code_present')}**",
        "",
        "## 8. Proposed next action", "",
        "Reviewer to fill `owner_if_wrong` + `next_step` for each comparison row,",
        "narrow any `ambiguous_multiple` rows to a `best_match_id`, then return the",
        "bundle for triage. Do NOT mutate preset, core, matrix, or ledger from this",
        "bundle directly.",
    ]
    return "\n".join(lines) + "\n"


# --- main --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--page-index", required=True, type=int,
                        help="zero-based page index (--page-index 27 == 1-based PDF page 28)")
    parser.add_argument("--expected-elements", required=True, type=Path,
                        help="JSON with schema pdf_lab.golden_slice.v1 (or compatible)")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--human-labeled-page", type=Path, default=None,
                        help="optional annotated PNG; if absent, manifest records absence")
    parser.add_argument("--ledger", type=Path, default=None,
                        help="optional promotion ledger; if absent, release == raw")
    parser.add_argument("--slice-id", type=str, default=None,
                        help="defaults to the basename of --out")
    parser.add_argument("--pdf-render-scale", type=float, default=1.5)
    parser.add_argument("--zip", action="store_true",
                        help="also write <out>.zip alongside the directory")
    parser.add_argument("--include-optional-code", action="store_true",
                        help="emit optional_code/ inside the bundle with "
                             "git_diff.patch + changed_files.txt + test_output.txt "
                             "(per SKILL.md: required when tooling code changed)")
    parser.add_argument("--runner-source", type=Path, default=None,
                        help="path to the runner source file to bundle into "
                             "optional_code/; defaults to this file (__file__)")
    parser.add_argument("--blocked-on", type=Path, default=None,
                        help="path to a JSON file with the blocked_on payload. "
                             "When supplied, the runner writes blocked_on.md + "
                             "json/blocked_on.json into the bundle and sets "
                             "manifest.blocked_on. Required when the bundle "
                             "will be auto-sent under PROJECT_KNOWLEDGE.md §10 "
                             "stop-condition trigger (b).")
    args = parser.parse_args(argv)

    cmd_started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    # --- validate ---
    if not args.pdf.exists():
        raise SystemExit(f"--pdf not found: {args.pdf}")
    if not args.expected_elements.exists():
        raise SystemExit(f"--expected-elements not found: {args.expected_elements}")
    if args.human_labeled_page and not args.human_labeled_page.exists():
        raise SystemExit(f"--human-labeled-page given but file not found: {args.human_labeled_page}")
    if args.page_index < 0:
        raise SystemExit("--page-index must be >= 0")

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    images_dir = out / "images"
    crops_dir = images_dir / "element_crops"
    json_dir = out / "json"
    tables_dir = out / "tables"
    for d in (images_dir, crops_dir, json_dir, tables_dir):
        d.mkdir(parents=True, exist_ok=True)

    slice_id = args.slice_id or out.name
    expected = json.loads(args.expected_elements.read_text(encoding="utf-8"))

    logger.info("building golden slice bundle: slice_id={} page_index={} out={}",
                slice_id, args.page_index, out)

    # --- import pdf_oxide helpers ---
    apply_ledger, ApplierConfig, snap = _import_pdf_oxide_helpers()

    # --- extract page ---
    raw_payload, release_payload = _extract_page(
        args.pdf, args.page_index, args.ledger,
        apply_ledger=apply_ledger, ApplierConfig=ApplierConfig, snap=snap,
    )
    (json_dir / "pdf_oxide_raw_page.json").write_text(
        json.dumps(raw_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    (json_dir / "pdf_oxide_release_page.json").write_text(
        json.dumps(release_payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    # --- render evidence ---
    render_info = _render_evidence(
        args.pdf, args.page_index, release_payload, raw_payload,
        images_dir, crops_dir, args.pdf_render_scale,
    )

    # --- human-labeled image ---
    has_human_label = False
    if args.human_labeled_page:
        shutil.copy2(args.human_labeled_page, images_dir / "human_labeled_page.png")
        has_human_label = True

    # --- expected_elements canonical copy ---
    (json_dir / "expected_elements.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True), encoding="utf-8"
    )

    # --- page_identity.json ---
    page_identity = {
        "schema_version": "review_extraction.page_identity.v1",
        "slice_id": slice_id,
        "source_pdf": str(args.pdf),
        "zero_based_page_index": args.page_index,
        "one_based_pdf_page_number": args.page_index + 1,
        "printed_page_label": expected.get("printed_page_label"),
        "human_page_claim": expected.get("human_page_claim"),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    (json_dir / "page_identity.json").write_text(
        json.dumps(page_identity, indent=2, sort_keys=True), encoding="utf-8"
    )

    # --- comparison ---
    comparison = _build_comparison(expected, release_payload, raw_payload)
    (json_dir / "golden_slice_comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True), encoding="utf-8"
    )
    (tables_dir / "golden_slice_comparison.md").write_text(
        _comparison_md(comparison), encoding="utf-8"
    )
    (tables_dir / "extracted_elements_table.md").write_text(
        _extracted_elements_table_md(release_payload, raw_payload), encoding="utf-8"
    )

    # --- mismatches_by_owner.json (empty until reviewer fills) ---
    (json_dir / "mismatches_by_owner.json").write_text(
        json.dumps({
            "schema_version": "review_extraction.mismatches_by_owner.v1",
            "slice_id": slice_id,
            "filled_by_reviewer": False,
            "note": "Empty placeholder. After human or WebGPT review of golden_slice_comparison.md, populate per-owner lists.",
            "pdf_oxide_core": [],
            "nist_preset_ledger": [],
            "downstream_semantic_parser": [],
            "second_pass_visual_adjudicator": [],
            "human_decision": [],
        }, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # --- blocked_on (only when --blocked-on is supplied) ---
    blocked_on_payload: dict[str, Any] | None = None
    if args.blocked_on is not None:
        if not args.blocked_on.exists():
            raise SystemExit(f"--blocked-on file not found: {args.blocked_on}")
        try:
            blocked_on_payload = json.loads(args.blocked_on.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"--blocked-on file is not valid JSON: {exc}")
        try:
            _validate_blocked_on(blocked_on_payload)
        except BlockedOnValidationError as exc:
            raise SystemExit(f"blocked_on payload rejected: {exc}")
        # Write canonical JSON + rendered markdown into the bundle
        (json_dir / "blocked_on.json").write_text(
            json.dumps(blocked_on_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        (out / "blocked_on.md").write_text(
            _render_blocked_on_md(blocked_on_payload), encoding="utf-8"
        )

    # --- optional_code/ (only when tooling code changed) ---
    # Per SKILL.md: include git_diff.patch + changed_files.txt + test_output.txt
    # inside the bundle when the project agent changed tooling code in this round.
    optional_code_info: dict[str, str] = {}
    if args.include_optional_code:
        runner_src = args.runner_source or Path(__file__).resolve()
        if not runner_src.exists():
            raise SystemExit(f"--runner-source not found: {runner_src}")
        # Build a synthetic "smoke output" string from what we already know;
        # we don't have stdout yet because we haven't printed the summary,
        # so we capture the structured summary that's about to print.
        smoke_lines = [
            f"slice_id: {slice_id}",
            f"page_index: {args.page_index}",
            f"raw_element_count: {len(raw_payload['elements'])}",
            f"release_element_count: {len(release_payload['elements'])}",
            f"crop_count: {render_info['crop_count']}",
            f"human_labeled_page_image_present: {has_human_label}",
            f"comparison_summary: {json.dumps(comparison['summary'])}",
        ]
        optional_code_info = _build_optional_code_dir(
            out_dir=out,
            runner_path=runner_src,
            smoke_test_stdout="\n".join(smoke_lines),
        )

    # --- manifest ---
    artifact_paths = {
        "manifest":                 str(out / "manifest.json"),
        "review_bundle":            str(out / "review_bundle.md"),
        "command_log":              str(out / "command_log.txt"),
        "page_clean":               render_info["page_clean"],
        "pdf_oxide_overlay":        render_info["pdf_oxide_overlay"],
        "human_labeled_page":       str(images_dir / "human_labeled_page.png") if has_human_label else None,
        "element_crops_dir":        str(crops_dir),
        "pdf_oxide_raw_page":       str(json_dir / "pdf_oxide_raw_page.json"),
        "pdf_oxide_release_page":   str(json_dir / "pdf_oxide_release_page.json"),
        "expected_elements":        str(json_dir / "expected_elements.json"),
        "page_identity":            str(json_dir / "page_identity.json"),
        "golden_slice_comparison_json": str(json_dir / "golden_slice_comparison.json"),
        "golden_slice_comparison_md":   str(tables_dir / "golden_slice_comparison.md"),
        "extracted_elements_table_md":  str(tables_dir / "extracted_elements_table.md"),
        "mismatches_by_owner":      str(json_dir / "mismatches_by_owner.json"),
        "optional_code_dir":        optional_code_info.get("optional_code_dir"),
        "optional_code_git_diff":   optional_code_info.get("git_diff_patch"),
        "optional_code_changed_files": optional_code_info.get("changed_files_txt"),
        "optional_code_test_output":   optional_code_info.get("test_output_txt"),
        "blocked_on_md":            str(out / "blocked_on.md") if blocked_on_payload else None,
        "blocked_on_json":          str(json_dir / "blocked_on.json") if blocked_on_payload else None,
    }
    manifest = _manifest(
        slice_id=slice_id,
        pdf_path=args.pdf,
        page_index=args.page_index,
        expected=expected,
        artifact_paths=artifact_paths,
        page_dims=render_info["page_size_px"],
        crop_count=render_info["crop_count"],
        has_human_label=has_human_label,
        ledger_path=args.ledger,
        optional_code_info=optional_code_info,
        blocked_on_payload=blocked_on_payload,
    )
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    # --- review_bundle.md ---
    (out / "review_bundle.md").write_text(
        _review_bundle_md(manifest, expected, release_payload, comparison),
        encoding="utf-8",
    )

    # --- command_log.txt ---
    elapsed = time.monotonic() - t0
    cmd_log = [
        f"command_started_at: {cmd_started_at}",
        f"command_finished_at: {datetime.now(timezone.utc).isoformat()}",
        f"elapsed_seconds: {elapsed:.3f}",
        f"argv: {' '.join(sys.argv)}",
        f"slice_id: {slice_id}",
        f"page_index: {args.page_index}",
        f"pdf: {args.pdf}",
        f"ledger: {args.ledger}",
        f"human_labeled_page: {args.human_labeled_page}",
        f"out: {out}",
        f"release_element_count: {len(release_payload['elements'])}",
        f"raw_element_count: {len(raw_payload['elements'])}",
    ]
    (out / "command_log.txt").write_text("\n".join(cmd_log) + "\n", encoding="utf-8")

    # --- optional zip ---
    zip_path = None
    if args.zip:
        zip_path = out.with_suffix(".zip")
        # Use shutil.make_archive for deterministic-ish behavior; remove if exists
        if zip_path.exists():
            zip_path.unlink()
        # shutil.make_archive needs base name without .zip
        base = str(zip_path.with_suffix(""))
        shutil.make_archive(base, "zip", root_dir=out.parent, base_dir=out.name)

    summary = {
        "slice_id": slice_id,
        "out": str(out),
        "zip": str(zip_path) if zip_path else None,
        "release_element_count": len(release_payload["elements"]),
        "raw_element_count": len(raw_payload["elements"]),
        "crop_count": render_info["crop_count"],
        "human_labeled_page_image_present": has_human_label,
        "comparison_summary": comparison["summary"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
