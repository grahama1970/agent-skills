#!/usr/bin/env python3
"""URL fetching and processing for distill skill.

Provides HTTP fetching with proper headers and HTML to text conversion.
"""

from __future__ import annotations

import re
import urllib.request
from urllib.error import URLError, HTTPError


def fetch_url(url: str) -> str:
    """Fetch URL content and convert to text.

    Args:
        url: URL to fetch

    Returns:
        Extracted text content

    Raises:
        RuntimeError: If fetch fails
    """
    try:
        # Add headers to avoid 403
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; distill-skill/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except (URLError, HTTPError) as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")

    # Try to extract text from HTML
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
    except ImportError:
        # Fallback: crude HTML stripping
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()

    return text
