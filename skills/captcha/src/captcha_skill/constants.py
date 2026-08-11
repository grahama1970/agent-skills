"""Immutable integration constants for the CAPTCHA skill.

The ReCAP source binding is intentionally pinned. Updating it requires a source
review, fixture refresh, and a new deterministic receipt; runtime execution does
not fetch or auto-update upstream code.
"""

from __future__ import annotations

from pathlib import Path

RECAP_REPOSITORY = "https://github.com/ASTRAL-Group/ReCAP-Agent"
RECAP_REPOSITORY_CLONE_URL = f"{RECAP_REPOSITORY}.git"
RECAP_COMMIT = "577c7728ed159756a6cb6cbd1a58897fe288f73e"
POLICY_VERSION = "captcha.policy.v1"
DEFAULT_STORAGE_ROOT = Path("/mnt/storage12tb/skills/captcha")
DEFAULT_RECAP_ROOT = DEFAULT_STORAGE_ROOT / "vendor" / "ReCAP-Agent"
DEFAULT_OUTPUT_ROOT = DEFAULT_STORAGE_ROOT / "outputs"
SURF_CAPABILITIES_SCHEMA = "surf.capabilities.v1"
LOCAL_MODEL_API_KEY_ENV = "CAPTCHA_LOCAL_MODEL_API_KEY"
CAPTCHA_TYPES = (
    "text",
    "compact_text",
    "icon_selection",
    "icon_match",
    "slider",
    "image_grid",
    "paged",
)
CAPTCHA_ENDPOINTS = {
    "text": "/challenge/text",
    "compact_text": "/challenge/compact",
    "icon_selection": "/challenge/icon",
    "icon_match": "/challenge/icon-match",
    "slider": "/challenge/slider",
    "image_grid": "/challenge/image_grid",
    "paged": "/challenge/paged",
}
RECAP_PASSTHROUGH_ENV_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PLAYWRIGHT_BROWSERS_PATH",
    "TMPDIR",
    "XDG_CACHE_HOME",
)
RECAP_FIXED_ENV_KEYS = (
    "ACTION_DELAY_MS",
    "BROWSER_HEADLESS",
    "BROWSER_SLOW_MO",
    "BROWSER_VIEWPORT_HEIGHT",
    "BROWSER_VIEWPORT_WIDTH",
    "DYNAMIC_MAX_CALLS_DEFAULT",
    "DYNAMIC_MAX_CALLS_IMAGE_GRID",
    "DYNAMIC_MAX_CALLS_PAGED",
    "DYNAMIC_PROVIDER_URL",
    "MAX_CALLS",
    "MODEL_MAX_COMPLETION_TOKENS",
    "MODEL_TEMPERATURE",
    "MODEL_TOP_P",
    "NO_PROXY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "POST_ACTION_DELAY_MS",
    "PYTHONUNBUFFERED",
    "RUNS_DIR",
    "TEST_SEED",
    "no_proxy",
)
RECAP_SECRET_ENV_KEYS = ("OPENAI_API_KEY",)
