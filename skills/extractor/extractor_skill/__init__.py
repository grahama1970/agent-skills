"""
Extractor skill package.

This package provides modular document extraction functionality.

Modules:
- config: Constants, paths, and extraction options
- utils: Resilience patterns and error formatting
- pdf_extractor: PDF extraction with preset detection
- structured_extractor: DOCX, HTML, XML extraction
- toc_checker: TOC integrity verification
- batch: Batch processing and reporting
- memory_integration: Memory skill integration
"""

__all__ = [
    "config",
    "utils",
    "pdf_extractor",
    "structured_extractor",
    "toc_checker",
    "batch",
    "memory_integration",
]
