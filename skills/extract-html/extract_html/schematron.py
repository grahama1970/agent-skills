"""schematron - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from extract_html.extract import TrafilaturaResult


def schematron_extract_json(
    *,
    cleaned_html: str,
    trafilatura: TrafilaturaResult,
    json_schema: Dict[str, Any],
    ollama_base_url: str,
    model: str,
    timeout_s: float,
    strict: bool,
    repair_instructions: Optional[str],
    section_outline: Optional[Dict[str, Any]],
    tables_json: Optional[Dict[str, Any]],
    media_json: Optional[Dict[str, Any]],
) -> str:
    """
    Calls Ollama to extract JSON from HTML.
    Constructs a prompt with strict rules, schema, and optional context.
    """
    schema_str = json.dumps(json_schema, indent=2)
    
    # Count deterministic tables to give model concrete expectations
    n_tables = len(tables_json.get("tables", [])) if tables_json else 0

    parts = [
        "You are a precise data extraction engine. You extract structured JSON from HTML.",
        "Your output must be VALID JSON conforming to the schema below.",
        "Do not include any explanation or markdown formatting. Output raw JSON only.",
    ]

    # Explicit block-type rules so the 3B model doesn't flatten tables into paragraphs
    parts.append("\n### BLOCK TYPE RULES")
    parts.append(
        "For each content element in the HTML, emit one block with the correct type:\n"
        "- heading: Every <h1>...<h6> element. Set level = heading number (1-6).\n"
        "- table: Every <table> element. Set rows = array of row arrays (each cell a string). "
        "content = comma-separated column headers or brief description.\n"
        "- paragraph: Continuous text outside tables/headings/lists.\n"
        "- list: <ul>/<ol> list blocks. content = semicolon-joined items.\n"
        "- code: <pre>/<code> blocks.\n"
        "- image: <img> elements."
    )
    if n_tables > 0:
        parts.append(
            f"\nIMPORTANT: The HTML contains {n_tables} table(s). "
            "You MUST emit exactly one block with type=\"table\" for each HTML <table>. "
            "Copy the row data from the DETERMINISTIC HTML TABLES section below into the rows field. "
            "Do NOT convert tables into paragraph or heading blocks."
        )

    parts.append(
        "\nCOVERAGE: Extract ALL sections of the document from start to end. "
        "Do not stop early. Every heading in the DOCUMENT OUTLINE must appear as a heading block."
    )

    parts.append("\n### JSON SCHEMA")
    parts.append(schema_str)

    if repair_instructions:
        parts.append("\n### REPAIR INSTRUCTIONS")
        parts.append("Your previous output failed validation. Fix the following errors:")
        parts.append(repair_instructions)

    parts.append("\n### CONTEXT DATA")
    parts.append("(Use this data to populate the schema fields.)")

    if section_outline:
        parts.append("\nDOCUMENT OUTLINE (H1-H6) — every heading here MUST appear in your output:\n" + json.dumps(section_outline, indent=2))

    if tables_json and n_tables > 0:
        parts.append(
            f"\nDETERMINISTIC HTML TABLES ({n_tables} tables) — copy rows verbatim into type=\"table\" blocks:\n"
            + json.dumps(tables_json, indent=2)
        )

    if media_json:
        parts.append(
            "\nMEDIA TEXT EXTRACTION (images with src/alt/dims; may include OCR text):\n"
            + json.dumps(media_json, indent=2)
        )

    parts.append("\n### HTML CONTENT")
    parts.append(cleaned_html)
    
    prompt = "\n".join(parts)
    
    # Use OpenAI-compatible /v1/chat/completions (works with Ollama, SGLang, inference.net)
    base = ollama_base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    url = f"{base}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise data extraction engine."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 16000,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "html_extraction",
                "strict": True,
                "schema": json_schema,
            }
        },
    }

    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LLM inference failed: {e}")
        raise
