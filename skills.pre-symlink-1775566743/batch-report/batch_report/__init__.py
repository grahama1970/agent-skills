"""Batch Report - Post-run analysis and reporting for batch processing jobs.

This package provides modular components for analyzing batch job outputs:
- config: Constants and paths
- utils: Common utilities (JSON loading, YAML config, agent inbox)
- manifest_parser: Manifest file parsing and quality analysis
- analysis: Timing analysis, failure patterns, quality gates
- markdown_generator: Report generation in markdown format
"""
from batch_report.config import BatchFormat

__all__ = ["BatchFormat"]
