"""GitHub Copilot provider for code-review skill.

Contains:
- GitHub CLI authentication checking
- Copilot-specific functionality
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

# Handle both import modes
try:
    from ..config import get_timeout
except ImportError:
    from config import get_timeout


def check_gh_auth() -> dict:
    """Check GitHub CLI authentication status.

    Uses `gh auth token` for reliable auth check (returns token if authenticated).
    Uses `gh api user` to get username (reliable JSON output).

    Returns dict with:
        authenticated: bool
        user: Optional[str]
        error: Optional[str]
    """
    result = {
        "authenticated": False,
        "user": None,
        "error": None,
    }

    # Check if gh CLI is installed
    if not shutil.which("gh"):
        result["error"] = "gh CLI not found. Install: https://cli.github.com/"
        return result

    # Check auth via gh auth status (catches invalid GH_TOKEN)
    try:
        status_result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=get_timeout(),
        )
        stderr = status_result.stderr + status_result.stdout
        if "Token is invalid" in stderr or "Failed to log in" in stderr:
            result["error"] = (
                "GH_TOKEN is invalid. Either unset it (unset GH_TOKEN) "
                "or re-authenticate: gh auth login"
            )
            return result
        if status_result.returncode != 0:
            result["error"] = "Not logged in. Run: gh auth login"
            return result

        # Get username via API (reliable JSON)
        user_result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=get_timeout(),
        )
        if user_result.returncode == 0:
            result["user"] = user_result.stdout.strip()

        result["authenticated"] = True

    except Exception as e:
        result["error"] = str(e)

    return result
