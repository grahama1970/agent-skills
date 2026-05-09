#!/usr/bin/env python3
"""URL fetching and processing for doc2qra skill.

Provides HTTP fetching with proper headers and HTML to text conversion.
"""

from __future__ import annotations

import subprocess

import httpx

from .html_handler import extract_html_text, looks_like_html


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
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            timeout=30,
            follow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
    except httpx.HTTPError as e:
        # Fallback to curl for sites that block httpx (e.g. Wikipedia)
        try:
            result = subprocess.run(
                ["curl", "-sL", "-A",
                 "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
                 "--max-time", "30", url],
                capture_output=True, text=True, timeout=35,
            )
            if result.returncode == 0 and result.stdout.strip():
                html = result.stdout
            else:
                raise RuntimeError(f"Failed to fetch {url}: {e}")
        except (subprocess.SubprocessError, OSError):
            raise RuntimeError(f"Failed to fetch {url}: {e}")

    if looks_like_html(html):
        return extract_html_text(html)
    return html
