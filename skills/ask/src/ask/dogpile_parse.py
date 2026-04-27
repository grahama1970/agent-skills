"""
Dogpile report parsing for /ask learn.

Parses the markdown output from the /dogpile skill into structured
sections (YouTube URLs, web URLs, ArXiv papers, content sections).
"""

import re
from typing import Optional

from loguru import logger as log


# -------------------------------------------------------------------------
# URL Regex Patterns
# -------------------------------------------------------------------------

# Matches markdown links: [title](https://www.youtube.com/watch?v=XXXXX)
# or [title](https://youtube.com/watch?v=XXXXX)
_YT_URL_RE = re.compile(
    r"\[([^\]]*)\]\((https?://(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)[^)]*)\)"
)
# Also match youtu.be short URLs
_YT_SHORT_RE = re.compile(
    r"\[([^\]]*)\]\((https?://youtu\.be/([a-zA-Z0-9_-]+)[^)]*)\)"
)
# Match any markdown link for web URLs
_WEB_URL_RE = re.compile(
    r"\[([^\]]*)\]\((https?://[^)]+)\)"
)
# Match arXiv paper links: [title](https://arxiv.org/abs/2501.15355)
_ARXIV_URL_RE = re.compile(
    r"\[([^\]]*)\]\((https?://arxiv\.org/abs/([0-9]+\.[0-9]+))\)"
)
# Skip these domains for web fetching (social media, video sites, etc.)
_SKIP_DOMAINS = {
    "youtube.com", "youtu.be", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "tiktok.com", "reddit.com", "linkedin.com",
    "amazon.com", "goodreads.com",  # Book sites (use discover-books instead)
}


def extract_web_urls(text: str, max_urls: int = 10) -> list[dict]:
    """Extract fetchable web URLs from dogpile content.

    Filters out social media, video sites, and book retailers.
    Returns list of {title, url} dicts.
    """
    urls = []
    seen = set()

    for match in _WEB_URL_RE.finditer(text):
        title = match.group(1).strip()
        url = match.group(2).strip()

        # Skip if already seen
        if url in seen:
            continue
        seen.add(url)

        # Check domain
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]

            # Skip blocked domains
            if any(skip in domain for skip in _SKIP_DOMAINS):
                continue

            urls.append({"title": title, "url": url, "domain": domain})

            if len(urls) >= max_urls:
                break

        except Exception as exc:
            log.error("Failed to parse dogpile URL %r: %s", url, exc)
            continue

    return urls


def parse_dogpile_report(report: str) -> dict:
    """Parse a dogpile markdown report to extract structured content.

    Extracts:
    - youtube_urls: list of {title, url, video_id} from the YouTube section
    - web_urls: list of {title, url, domain} from web sections (for fetching)
    - synthesis: the Codex synthesis section text
    - perplexity: the Perplexity AI research section text
    - arxiv_papers: list of paper titles/abstracts from ArXiv section
    - content_sections: dict of section_name -> text for extractor_qra processing
    - full_report: the complete report text

    Args:
        report: Dogpile markdown report string

    Returns:
        dict with extracted structured data
    """
    result = {
        "youtube_urls": [],
        "web_urls": [],  # Fetchable blog/article URLs
        "synthesis": "",
        "perplexity": "",
        "arxiv_papers": [],
        "content_sections": {},
        "full_report": report,
    }

    if not report or not report.strip():
        return result

    # Extract YouTube URLs from the entire report (they may appear in any section)
    seen_ids = set()
    for match in _YT_URL_RE.finditer(report):
        title, url, video_id = match.groups()
        if video_id not in seen_ids and "Error" not in title:
            result["youtube_urls"].append({
                "title": title.strip(),
                "url": url.strip(),
                "video_id": video_id,
            })
            seen_ids.add(video_id)

    for match in _YT_SHORT_RE.finditer(report):
        title, url, video_id = match.groups()
        if video_id not in seen_ids and "Error" not in title:
            result["youtube_urls"].append({
                "title": title.strip(),
                "url": url.strip(),
                "video_id": video_id,
            })
            seen_ids.add(video_id)

    # Extract web URLs (blogs, articles) - excluding YouTube and social media
    result["web_urls"] = extract_web_urls(report, max_urls=10)

    # Split into sections by ## headers
    sections = re.split(r"^## ", report, flags=re.MULTILINE)

    for section in sections:
        if not section.strip():
            continue

        # Get section name from first line
        lines = section.split("\n", 1)
        section_name = lines[0].strip()
        section_body = lines[1].strip() if len(lines) > 1 else ""

        if not section_body:
            continue

        # Codex Synthesis
        if "codex synthesis" in section_name.lower() or "synthesis" in section_name.lower():
            result["synthesis"] = section_body[:5000]
            result["content_sections"]["synthesis"] = section_body[:5000]

        # Perplexity / AI Research
        elif "perplexity" in section_name.lower() or "ai research" in section_name.lower():
            result["perplexity"] = section_body[:5000]
            result["content_sections"]["perplexity"] = section_body[:5000]

        # ArXiv / Academic Papers
        elif "arxiv" in section_name.lower() or "academic" in section_name.lower():
            result["content_sections"]["arxiv"] = section_body[:5000]
            # Extract paper titles and IDs from markdown links
            for match in _ARXIV_URL_RE.finditer(section_body):
                title, abs_url, arxiv_id = match.groups()
                if arxiv_id and title.strip():
                    result["arxiv_papers"].append({
                        "title": title.strip(),
                        "arxiv_id": arxiv_id,
                        "abs_url": abs_url,
                    })

        # Codex Technical Overview
        elif "codex technical" in section_name.lower():
            result["content_sections"]["codex_overview"] = section_body[:5000]

        # Web Results (Brave)
        elif "brave" in section_name.lower() or "web results" in section_name.lower():
            result["content_sections"]["web"] = section_body[:3000]

        # YouTube / Videos
        elif "video" in section_name.lower() or "youtube" in section_name.lower():
            result["content_sections"]["youtube"] = section_body[:3000]

        # Books / Readarr
        elif "books" in section_name.lower() or "readarr" in section_name.lower():
            result["content_sections"]["books"] = section_body[:2000]

    # Filter out error content from sections
    filtered = {}
    for key, text in result["content_sections"].items():
        if _is_error_content(text):
            log.debug("Filtered error content from dogpile section '%s': %s", key, text[:80])
            continue
        filtered[key] = text
    result["content_sections"] = filtered

    log.debug("Parsed dogpile report: %d YouTube URLs, %d content sections, %d ArXiv papers",
              len(result["youtube_urls"]), len(result["content_sections"]),
              len(result["arxiv_papers"]))

    return result


def _is_error_content(text: str) -> bool:
    """Detect if a dogpile section contains an error message instead of real content."""
    if not text or len(text.strip()) < 30:
        return True
    stripped = text.strip()
    # Dogpile wraps errors as "> Error: ..." blockquotes
    if stripped.startswith("> Error:") or stripped.startswith("Error:"):
        return True
    # Python tracebacks
    if "Traceback (most recent call last):" in stripped:
        return True
    # LLM provider failures
    if "All LLM providers failed" in stripped:
        return True
    # Rate limit placeholder
    if "rate limited" in stripped.lower() and len(stripped) < 200:
        return True
    return False
