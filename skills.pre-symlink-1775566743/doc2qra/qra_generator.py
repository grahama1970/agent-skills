"""QRA (Question, Reasoning, Answer) generation for doc2qra skill.

Re-export hub that preserves the original public API after the module
was split into focused sub-modules:

- summary.py          — LLM and heuristic document summarisation
- qra_prompts.py      — System/user prompt templates
- qra_heuristic.py    — Rule-based fallback extraction
- qra_gateway.py      — /assistant validate() gateway routing
- qra_llm.py          — Single-section LLM extraction
- qra_batch.py        — Parallel multi-section batch extraction
- qra_cascade.py      — Shadow-LEGO cascade runner integration
- grounding.py        — Grounding validation (unchanged, existing)
"""

from __future__ import annotations

# --- Summary ---
from .summary import (  # noqa: F401
    generate_summary,
    generate_summary_async,
    heuristic_summary as _heuristic_summary,
)

# --- Prompts ---
from .qra_prompts import (  # noqa: F401
    build_qra_system_prompt,
    QRA_SYSTEM_PROMPT,
    QRA_PROMPT,
)

# --- Heuristic fallback ---
from .qra_heuristic import (  # noqa: F401
    extract_qa_heuristic,
    section_heuristic_fallback as _section_heuristic_fallback,
    fallback_heuristic_extraction as _fallback_heuristic_extraction,
)

# --- Gateway ---
from .qra_gateway import (  # noqa: F401
    extract_qra_gateway,
    parse_gateway_items as _parse_gateway_items,
    is_gateway_available,
)

# --- LLM single-section ---
from .qra_llm import extract_qra_llm  # noqa: F401

# --- Batch ---
from .qra_batch import (  # noqa: F401
    extract_qra_batch,
    parse_qra_response as _parse_qra_response,
)

# --- Cascade ---
from .qra_cascade import build_qra_cascade  # noqa: F401

# --- Grounding (unchanged, re-exported for backwards compatibility) ---
from .grounding import check_grounding, validate_and_filter_qras  # noqa: F401
