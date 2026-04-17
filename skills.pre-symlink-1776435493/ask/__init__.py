"""
/ask learn -- Discover, ingest, and extract knowledge about a topic.

Re-exports all public symbols from the split modules for backward compatibility.
"""

from monitor import AskMonitor, STEP_ESTIMATES  # noqa: F401
from skills_exec import run_skill, parse_json_output, parse_memory_output, run_memory_recall  # noqa: F401
from taxonomy import extract_bridges_from_content, aggregate_bridges  # noqa: F401
from persona import (detect_persona, get_persona_profile, store_persona_profile, run_interview,  # noqa: F401
                     ask_learning_depth, discover_colleagues, is_persona_sparse,
                     LEARNING_DEPTHS, SPARSE_THRESHOLD)
from persona_routing import (extract_bridges, extract_persona_from_question,  # noqa: F401
                              find_relevant_personas, suggest_persona_consultation)
from hybrid import extract_reasoning, merge_hybrid_results, ask_hybrid, learn_back  # noqa: F401
from sources import (search_nzbgeek_books, download_book_nzb, check_downloaded_book,  # noqa: F401
                     extract_book_content, query_feed_items, extract_arxiv_paper)
from dogpile_parse import parse_dogpile_report, extract_web_urls  # noqa: F401
from pipeline import learn, main, step_print  # noqa: F401

__all__ = ["AskMonitor", "STEP_ESTIMATES", "run_skill", "parse_json_output", "parse_memory_output", "run_memory_recall", "extract_bridges_from_content", "aggregate_bridges", "detect_persona", "get_persona_profile", "store_persona_profile", "run_interview", "ask_learning_depth", "discover_colleagues", "is_persona_sparse", "LEARNING_DEPTHS", "SPARSE_THRESHOLD", "extract_bridges", "extract_persona_from_question", "find_relevant_personas", "suggest_persona_consultation", "extract_reasoning", "merge_hybrid_results", "ask_hybrid", "learn_back", "search_nzbgeek_books", "download_book_nzb", "check_downloaded_book", "extract_book_content", "query_feed_items", "extract_arxiv_paper", "parse_dogpile_report", "extract_web_urls", "learn", "main", "step_print"]  # noqa: E501
