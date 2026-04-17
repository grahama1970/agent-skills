#!/usr/bin/env python3
"""Distill skill - Extract Q&A pairs from PDF/URL/text into memory.

This package provides modular components for content distillation:
- config: Configuration constants and environment handling
- utils: Logging, progress, and resilience utilities
- pdf_handler: PDF extraction (fast/accurate modes)
- url_handler: URL fetching and HTML processing
- text_handler: Section detection and sentence splitting
- qra_generator: Re-export hub for QRA extraction (delegates to sub-modules)
- qra_prompts: System and user prompt templates for QRA extraction
- qra_heuristic: Rule-based fallback QRA extraction
- qra_gateway: /assistant validate() gateway routing
- qra_llm: Single-section LLM-based QRA extraction
- qra_batch: Parallel multi-section batch QRA extraction
- qra_cascade: Shadow-LEGO cascade runner integration
- summary: Document summarisation (LLM + heuristic)
- memory_ops: Memory storage operations
"""

__version__ = "2.0.0"
