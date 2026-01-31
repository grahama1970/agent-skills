import re
from typing import Optional

def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    # Simple regex for basic cleanup.
    # For robust stripping, BeautifulSoup is better but implies another big dep.
    # Agents prefer fewer heavy deps if simple regex works for summaries.
    clean = re.sub('<[^<]+?>', '', text)
    return clean

def clean_summary(text: Optional[str], max_len: int = 1000) -> str:
    """
    Normalize summary:
    1. Strip HTML
    2. Collapse whitespace
    3. Truncate
    """
    if not text:
        return ""
        
    text = strip_html(text)
    # Collapse whitespace
    text = " ".join(text.split())
    
    if len(text) > max_len:
        text = text[:max_len-3] + "..."
        
    return text
