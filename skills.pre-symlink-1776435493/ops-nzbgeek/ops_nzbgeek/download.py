"""SABnzbd download module."""

import os
from pathlib import Path
from typing import Optional
import httpx
from dotenv import load_dotenv

# Load environment variables from repo root
REPO_ROOT = Path.home() / "workspace" / "experiments" / "pi-mono"
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()  # Fallback to default search

# SABnzbd API configuration
SAB_API_KEY = os.getenv("SABNZBD_API_KEY")
SAB_BASE_URL = os.getenv("SABNZBD_BASE_URL", "http://localhost:8090")


def get_requests_session() -> httpx.Client:
    """Get an httpx client with retry logic."""
    transport = httpx.HTTPTransport(retries=3)
    client = httpx.Client(transport=transport, timeout=30.0)
    return client


def add_nzb(
    nzb_url: str,
    category: Optional[str] = None,
    priority: int = 0,
    dry_run: bool = False,
) -> dict:
    """
    Add NZB to SABnzbd queue via addurl.

    Args:
        nzb_url: NZB URL to download
        category: SABnzbd category (optional)
        priority: Priority (0=normal, 1=high, 2=force)
        dry_run: If True, return API call details without executing

    Returns:
        Dict with status, nzb_id, and API response

    Raises:
        ValueError: If API key is missing
        httpx.HTTPError: If API request fails
    """
    if not SAB_API_KEY:
        raise ValueError("SABNZBD_API_KEY environment variable not set")

    params = {
        "mode": "addurl",
        "name": nzb_url,
        "apikey": SAB_API_KEY,
        "output": "json",
        "priority": priority,
    }

    if category:
        params["cat"] = category

    url = f"{SAB_BASE_URL.rstrip('/')}/api"

    if dry_run:
        return {
            "dry_run": True,
            "url": url,
            "params": {k: v if k != "apikey" else "***" for k, v in params.items()},
            "message": "Dry-run: API call would be made with above parameters",
        }

    session = get_requests_session()

    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise httpx.HTTPError(f"SABnzbd API request failed: {e}")

    # SABnzbd addurl response: {"status": true, "nzo_ids": ["SABnzbd_nzo_xyz123"]}
    if not data.get("status"):
        error = data.get("error", "Unknown error")
        raise ValueError(f"SABnzbd rejected NZB: {error}")

    nzo_ids = data.get("nzo_ids", [])
    nzb_id = nzo_ids[0] if nzo_ids else None

    return {
        "status": "queued",
        "nzb_id": nzb_id,
        "response": data,
    }


def format_download_result(result: dict) -> str:
    """
    Format download result for display.

    Args:
        result: Download result dict

    Returns:
        Formatted string
    """
    if result.get("dry_run"):
        lines = [
            "=== Dry-run mode (no download) ===",
            f"URL: {result['url']}",
            "Parameters:",
        ]
        for k, v in result["params"].items():
            lines.append(f"  {k}: {v}")
        lines.append(f"\n{result['message']}")
        return "\n".join(lines)

    status = result.get("status", "unknown")
    nzb_id = result.get("nzb_id", "unknown")

    return f"Download queued successfully\nNZB ID: {nzb_id}\nStatus: {status}"
