"""extract - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import trafilatura
from loguru import logger

from extract_html.normalize import NormMode, normalize_text


@dataclass
class TrafilaturaResult:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "metadata": self.metadata
        }


def extract_trafilatura(html: str, normalize_mode: NormMode = "nfkc") -> TrafilaturaResult:
    """
    Wraps trafilatura extraction.
    """
    try:
        # trafilatura.extract returns None on failure
        text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
        # Metadata extraction (simple)
        meta = trafilatura.extract_metadata(html)
        meta_dict = meta.as_dict() if meta else {}
        
        # Normalize
        text = normalize_text(text, normalize_mode)
        
        return TrafilaturaResult(text=text, metadata=meta_dict)
        
    except Exception as e:
        logger.warning(f"Trafilatura extraction failed: {e}")
        return TrafilaturaResult(text="", metadata={"error": str(e)})
