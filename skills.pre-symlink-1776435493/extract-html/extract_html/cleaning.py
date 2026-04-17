"""cleaning - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from bs4 import BeautifulSoup, Comment


class CleaningMode(Enum):
    CONSERVATIVE = "conservative"
    FOCUSED_MAIN = "focused_main"
    AGGRESSIVE_BOILERPLATE = "aggressive_boilerplate"


def clean_html(html: str, mode: CleaningMode = CleaningMode.CONSERVATIVE) -> str:
    """
    Cleans HTML based on the selected mode.
    """
    soup = BeautifulSoup(html, "lxml")

    # Always remove scripts, styles, comments
    for element in soup(["script", "style", "noscript", "iframe", "svg", "canvas"]):
        element.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Mode-specific cleaning
    if mode == CleaningMode.AGGRESSIVE_BOILERPLATE:
        # Remove common non-content areas
        for selector in [
            "header", "footer", "nav", "aside", ".sidebar", ".menu", ".ad", ".advertisement",
            "#header", "#footer", "#nav", "#sidebar"
        ]:
            for element in soup.select(selector):
                element.decompose()

    # Return string
    return str(soup)


def focus_main_container(html: str) -> str:
    """
    Heuristically finds the main content container and returns its inner HTML.
    If no clear main container is found, returns the original HTML.
    """
    soup = BeautifulSoup(html, "lxml")
    
    # Priority list of selectors
    candidates = [
        "main", 
        "article", 
        "#main", 
        "#content", 
        ".main-content", 
        ".post-content", 
        ".article-body"
    ]
    
    for selector in candidates:
        found = soup.select_one(selector)
        if found:
            return str(found)
            
    return html


def slice_html_for_tokens(html: str, max_chars: int) -> str:
    """
    Naively slices HTML string to max_chars. 
    In a real implementation, this should be token-aware or at least block-aware.
    """
    if len(html) <= max_chars:
        return html
    return html[:max_chars]
