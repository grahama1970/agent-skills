"""pipeline - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from extract_html.cleaning import clean_html, CleaningMode, focus_main_container, slice_html_for_tokens
from extract_html.extract import extract_trafilatura, TrafilaturaResult
from extract_html.normalize import normalize_text, NormMode
from extract_html.sectionify import build_section_hierarchy
from extract_html.schematron import schematron_extract_json
from extract_html.tables import extract_html_tables_to_json
from extract_html.media import discover_images, filter_media_by_pixels, load_image_bytes, to_media_context
from extract_html.vision_client import extract_text_batched
from extract_html.validate import validate_or_errors
from extract_html.util import write_text_file, write_json_file


@dataclass(frozen=True)
class AttemptPlan:
    cleaning_mode: CleaningMode
    focus_main: bool
    html_slice_chars: Optional[int]
    prompt_strict: bool
    prompt_repair: bool


def _build_attempt_plans(max_attempts: int) -> list[AttemptPlan]:
    plans: list[AttemptPlan] = [
        AttemptPlan(CleaningMode.CONSERVATIVE, False, None, False, False),
        AttemptPlan(CleaningMode.FOCUSED_MAIN, True, 140_000, True, True),
        AttemptPlan(CleaningMode.AGGRESSIVE_BOILERPLATE, True, 100_000, True, True),
    ]
    return plans[:max_attempts]


def _format_errors_for_repair(errors: list[dict[str, Any]]) -> str:
    lines = []
    for e in errors[:25]:
        lines.append(f"- path={e.get('path')} error={e.get('message')}")
    return "Fix the JSON to satisfy these schema validation errors:\n" + "\n".join(lines)


def _write_debug(
    debug_dir: Optional[Path],
    attempt_id: str,
    cleaned_html: str,
    tf: TrafilaturaResult,
    raw_model_output: str,
    meta: Dict[str, Any],
    suffix: str = "",
) -> None:
    if debug_dir is None:
        return
    adir = debug_dir / f"{attempt_id}{suffix}"
    adir.mkdir(parents=True, exist_ok=True)

    write_text_file(adir / "cleaned.html", cleaned_html)
    write_json_file(adir / "trafilatura.json", tf.to_dict())
    write_text_file(adir / "model_output.txt", raw_model_output)
    write_json_file(adir / "meta.json", meta)


def run_pipeline(
    *,
    html_path: Path,
    raw_html: str,
    json_schema: Dict[str, Any],
    ollama_base_url: str,
    model: str,
    timeout_s: float,
    max_attempts: int,
    max_html_chars: int,
    normalize_mode: NormMode,
    include_sections: bool,
    emit_sections: bool,

    extract_tables: bool,
    max_tables: int,

    extract_media_text: bool,
    min_image_px: int,
    max_image_px: int,
    min_image_dim: int,
    fetch_remote_media: bool,
    vision_api_base: Optional[str],
    vision_api_key: Optional[str],
    vision_model: str,
    vision_concurrency: int,

    debug_dir: Optional[Path],
) -> Dict[str, Any]:
    plans = _build_attempt_plans(max_attempts=max_attempts)
    last_err: str | None = None

    raw_html = normalize_text(raw_html, normalize_mode)

    for i, plan in enumerate(plans, start=1):
        attempt_id = f"attempt_{i:02d}"
        logger.info(
            "Attempt {}/{}: cleaning_mode={} focus_main={} slice_chars={} strict={} repair={}",
            i, len(plans),
            plan.cleaning_mode.value, plan.focus_main, plan.html_slice_chars,
            plan.prompt_strict, plan.prompt_repair,
        )

        cleaned = clean_html(raw_html, mode=plan.cleaning_mode)
        cleaned = normalize_text(cleaned, normalize_mode)

        if len(cleaned) > max_html_chars:
            cleaned = cleaned[:max_html_chars]
            logger.warning("Cleaned HTML truncated to max_html_chars={}", max_html_chars)

        if plan.focus_main:
            cleaned = focus_main_container(cleaned)
            cleaned = normalize_text(cleaned, normalize_mode)

        if plan.html_slice_chars is not None:
            cleaned = slice_html_for_tokens(cleaned, plan.html_slice_chars)

        section_outline = build_section_hierarchy(cleaned) if include_sections else None
        tf = extract_trafilatura(cleaned, normalize_mode=normalize_mode)

        # Deterministic HTML tables
        tables_json = extract_html_tables_to_json(cleaned, max_tables=max_tables) if extract_tables else {"tables": []}

        # Media text extraction (images only here; keeps src + alt)
        media_json = {"media_text": []}
        if extract_media_text:
            discovered = discover_images(cleaned, html_path=html_path)
            media_items = filter_media_by_pixels(
                discovered,
                fetch_remote=fetch_remote_media,
                min_area=min_image_px,
                max_area=max_image_px,
                min_dim=min_image_dim,
            )

            # Prepare bytes for qualifying images
            qualifying = []
            for it in media_items:
                if it.status != "ok":
                    continue
                b = load_image_bytes(it.src_resolved, fetch_remote=fetch_remote_media)
                if not b:
                    continue
                qualifying.append({"id": it.src_resolved, "bytes": b, "alt": it.alt})

            extracted_map: Dict[str, str] = {}
            if qualifying:
                if not (vision_api_base and vision_api_key):
                    logger.warning("extract_media_text enabled but vision_api_base/api_key not set; skipping OCR.")
                else:
                    extracted_map = asyncio.run(
                        extract_text_batched(
                            api_base=vision_api_base,
                            api_key=vision_api_key,
                            model=vision_model,
                            images=qualifying,
                            concurrency=vision_concurrency,
                            timeout_s=timeout_s,
                        )
                    )

            media_json = to_media_context(media_items, extracted_map)

        raw_model_out = schematron_extract_json(
            cleaned_html=cleaned,
            trafilatura=tf,
            json_schema=json_schema,
            ollama_base_url=ollama_base_url,
            model=model,
            timeout_s=timeout_s,
            strict=plan.prompt_strict,
            repair_instructions=None,
            section_outline=section_outline,
            tables_json=tables_json,
            media_json=media_json,
        )

        try:
            # Simple JSON extraction from markdown fences if present
            content = raw_model_out.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            obj = json.loads(content)
        except Exception as e:
            last_err = f"{attempt_id}: JSON parse error: {e}"
            _write_debug(debug_dir, attempt_id, cleaned, tf, raw_model_out, {
                "parse_error": str(e),
                "section_outline": section_outline,
                "tables_json": tables_json,
                "media_json": media_json,
            })
            continue

        if emit_sections and section_outline is not None:
            obj.setdefault("sections", section_outline.get("sections"))

        ok, errors = validate_or_errors(json_schema, obj)
        if ok:
            _write_debug(debug_dir, attempt_id, cleaned, tf, raw_model_out, {
                "status": "ok",
                "section_outline": section_outline,
                "tables_json": tables_json,
                "media_json": media_json,
            })
            return obj

        last_err = f"{attempt_id}: schema validation failed with {len(errors)} errors"
        logger.warning(last_err)

        if plan.prompt_repair:
            repair_text = _format_errors_for_repair(errors)
            raw_model_out_2 = schematron_extract_json(
                cleaned_html=cleaned,
                trafilatura=tf,
                json_schema=json_schema,
                ollama_base_url=ollama_base_url,
                model=model,
                timeout_s=timeout_s,
                strict=True,
                repair_instructions=repair_text,
                section_outline=section_outline,
                tables_json=tables_json,
                media_json=media_json,
            )
            try:
                content = raw_model_out_2.strip()
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                obj2 = json.loads(content)
            except Exception as e:
                last_err = f"{attempt_id}: repair JSON parse error: {e}"
                _write_debug(debug_dir, attempt_id, cleaned, tf, raw_model_out_2, {
                    "schema_errors": errors,
                    "repair_parse_error": str(e),
                    "section_outline": section_outline,
                    "tables_json": tables_json,
                    "media_json": media_json,
                }, suffix="_repair")
                continue

            if emit_sections and section_outline is not None:
                obj2.setdefault("sections", section_outline.get("sections"))

            ok2, errors2 = validate_or_errors(json_schema, obj2)
            if ok2:
                _write_debug(debug_dir, attempt_id, cleaned, tf, raw_model_out_2, {
                    "status": "ok_after_repair",
                    "section_outline": section_outline,
                    "tables_json": tables_json,
                    "media_json": media_json,
                }, suffix="_repair")
                return obj2

            last_err = f"{attempt_id}: repair validation failed with {len(errors2)} errors"
            _write_debug(debug_dir, attempt_id, cleaned, tf, raw_model_out_2, {
                "schema_errors": errors,
                "schema_errors_after_repair": errors2,
                "section_outline": section_outline,
                "tables_json": tables_json,
                "media_json": media_json,
            }, suffix="_repair")

    raise RuntimeError(last_err or "Failed to produce schema-valid JSON.")
