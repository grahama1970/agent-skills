#!/usr/bin/env python3
"""Distill skill - Extract Q&A pairs from PDF/URL/text into memory.

This package provides modular components for content distillation:
- config: Configuration constants and environment handling
- utils: Logging, progress, and resilience utilities
- pdf_handler: PDF extraction (fast/accurate modes)
- url_handler: URL fetching and HTML processing
- text_handler: Section detection and sentence splitting
- qra_generator: LLM-based and heuristic Q&A extraction
- memory_ops: Memory storage operations
"""

__version__ = "2.0.0"
