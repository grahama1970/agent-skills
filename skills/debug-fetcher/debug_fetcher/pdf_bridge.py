"""PDF Bridge - Cross-skill integration between debug-fetcher and debug-pdf.

Detects when fetched content is a PDF that might need debug-pdf analysis,
and sends notifications via agent-inbox.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Common failure patterns shared between debug-fetcher and debug-pdf
SHARED_PATTERNS = {
    # Network/fetch patterns (debug-fetcher primary)
    "auth_required": "Authentication/login required",
    "access_restricted": "Access control (403 Forbidden)",
    "rate_limited": "Rate limiting detected",
    "geo_blocked": "Geographic restriction",
    "paywall_detected": "Paywall or subscription required",
    "bot_blocked": "Bot/crawler detection blocked",

    # PDF-specific patterns (debug-pdf primary)
    "scanned_no_ocr": "Scanned PDF without text layer",
    "password_protected": "Password-protected PDF",
    "corrupted_file": "Corrupted or invalid PDF",
    "watermarks": "Watermark overlays obscuring content",
    "toc_noise": "Table of contents with dotted leaders",

    # Shared patterns (both skills detect)
    "archive_org_wrap": "Wayback Machine URL wrapper",
    "empty_content": "File downloaded but empty/minimal content",
}


def is_pdf_url(url: str) -> bool:
    """Check if URL likely points to a PDF."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Check extension
    if path.endswith('.pdf'):
        return True

    # Check common PDF hosting patterns
    pdf_indicators = [
        '/pdf/',
        '/pdfs/',
        '/download/',
        'format=pdf',
        'type=pdf',
        '.pdf?',
    ]

    full_url = url.lower()
    return any(ind in full_url for ind in pdf_indicators)


def is_pdf_content(content: bytes) -> bool:
    """Check if content is a valid PDF."""
    if not content:
        return False
    return content[:5] == b'%PDF-'


def check_pdf_health(pdf_bytes: bytes) -> Dict[str, Any]:
    """Quick health check on PDF content.

    Returns dict with:
        - valid: bool - Is it a valid PDF?
        - has_text: bool - Does it have extractable text?
        - page_count: int - Number of pages
        - issues: list - Detected issues that might need debug-pdf
    """
    result = {
        "valid": False,
        "has_text": False,
        "page_count": 0,
        "issues": [],
    }

    if not is_pdf_content(pdf_bytes):
        result["issues"].append("not_pdf")
        return result

    result["valid"] = True

    try:
        # Try to use PyMuPDF if available
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        result["page_count"] = len(doc)

        # Check for text content
        total_text = 0
        for page in doc:
            text = page.get_text()
            total_text += len(text.strip())

        result["has_text"] = total_text > 100

        if not result["has_text"]:
            result["issues"].append("scanned_no_ocr")

        # Check for encryption
        if doc.is_encrypted:
            result["issues"].append("password_protected")

        doc.close()

    except ImportError:
        # PyMuPDF not available - do basic checks
        if b'/Encrypt' in pdf_bytes[:10000]:
            result["issues"].append("password_protected")
    except Exception as e:
        result["issues"].append("corrupted_file")
        result["valid"] = False

    return result


def find_inbox_tool() -> Optional[Path]:
    """Find agent-inbox tool."""
    candidates = [
        Path("/home/graham/workspace/experiments/fetcher/.agents/skills/agent-inbox/run.sh"),
        Path("/home/graham/workspace/experiments/memory/.agents/skills/agent-inbox/run.sh"),
        Path.home() / ".claude" / "skills" / "agent-inbox" / "inbox.py",
    ]

    for c in candidates:
        if c.exists():
            return c
    return None


def notify_debug_pdf(
    url: str,
    issues: List[str],
    fetch_strategy: str = "unknown",
    additional_context: str = "",
) -> bool:
    """Send notification to debug-pdf via agent-inbox.

    Args:
        url: The PDF URL that was fetched
        issues: List of detected issues
        fetch_strategy: Which strategy successfully fetched the PDF
        additional_context: Any additional context to include

    Returns:
        True if notification was sent successfully
    """
    inbox_tool = find_inbox_tool()
    if not inbox_tool:
        return False

    # Build message
    message = f"""PDF fetched but may need analysis

URL: {url}
Fetch Strategy: {fetch_strategy}
Detected Issues: {', '.join(issues) if issues else 'None'}

{additional_context}

Suggested action: Run debug-pdf analyze on this URL to identify extraction patterns.
"""

    try:
        if inbox_tool.suffix == '.py':
            cmd = ["python", str(inbox_tool), "send", "--to", "debug-pdf", "--type", "info"]
        else:
            cmd = [str(inbox_tool), "send", "--to", "debug-pdf", "--type", "info"]

        cmd.append(message)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

        return result.returncode == 0

    except Exception:
        return False


def notify_fetch_failure_for_pdf(
    url: str,
    error: str,
    strategies_tried: List[str],
) -> bool:
    """Notify debug-pdf about a PDF that couldn't be fetched.

    This helps debug-pdf track URLs that need special handling.

    Args:
        url: The failed PDF URL
        error: The error message
        strategies_tried: List of strategies that were attempted

    Returns:
        True if notification was sent successfully
    """
    if not is_pdf_url(url):
        return False

    inbox_tool = find_inbox_tool()
    if not inbox_tool:
        return False

    message = f"""PDF fetch failed - may need network-level debug

URL: {url}
Error: {error}
Strategies Tried: {', '.join(strategies_tried)}

This URL could not be fetched by debug-fetcher. If the PDF is important:
1. Check if it requires authentication (auth_required pattern)
2. Check if it's geo-restricted (geo_blocked pattern)
3. Try manual download and use debug-pdf analyze on local file
"""

    try:
        if inbox_tool.suffix == '.py':
            cmd = ["python", str(inbox_tool), "send", "--to", "debug-pdf", "--type", "request"]
        else:
            cmd = [str(inbox_tool), "send", "--to", "debug-pdf", "--type", "request"]

        cmd.append(message)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

        return result.returncode == 0

    except Exception:
        return False


def get_shared_pattern_description(pattern: str) -> str:
    """Get human-readable description for a shared pattern."""
    return SHARED_PATTERNS.get(pattern, f"Unknown pattern: {pattern}")
