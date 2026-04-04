"""sectionify - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup


def build_section_hierarchy(html: str) -> Dict[str, Any]:
    """
    Parses H1-H6 headers to build a simple nested section outline.
    """
    soup = BeautifulSoup(html, "lxml")
    
    headers = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    
    root: Dict[str, Any] = {"sections": []}
    stack: List[Dict[str, Any]] = [root]  # Stack of active containers
    
    # Track current levels. Root is level 0 (virtual).
    # H1=1, H2=2, etc.
    
    for h in headers:
        level = int(h.name[1])
        text = h.get_text().strip()
        if not text:
            continue
            
        node = {
            "title": text,
            "level": level,
            "sections": []
        }
        
        # Pop stack until we find a parent with level < current level
        # But wait, root has no level. Let's make root level 0.
        
        while len(stack) > 1:
            parent = stack[-1]
            if parent.get("level", 0) < level:
                break
            stack.pop()
            
        stack[-1]["sections"].append(node)
        stack.append(node)
        
    return root
