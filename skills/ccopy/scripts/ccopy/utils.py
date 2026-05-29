"""ccopy shared helpers."""

from __future__ import annotations

import json
import os
import pathlib
import platform
import time
from typing import Any, List, Optional

from ccopy.errors import CursorCopyError


def decode_bytes(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def parse_json_value(value: Any) -> Any:
    text = decode_bytes(value)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def coerce_ts(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except Exception:
        return 0


def millis_to_iso(ms: int) -> str:
    try:
        if ms > 10_000_000_000:
            seconds = ms / 1000.0
        else:
            seconds = float(ms)
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(seconds))
    except Exception:
        return str(ms)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [normalize_text(v) for v in value]
        return "\n".join(p for p in parts if p).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "value", "markdown"):
            if key in value:
                text = normalize_text(value.get(key))
                if text:
                    return text
        if "children" in value:
            return normalize_text(value.get("children"))
        return ""
    return str(value).strip()


def cursor_user_dirs(explicit: Optional[pathlib.Path] = None) -> List[pathlib.Path]:
    if explicit:
        return [explicit.expanduser()]

    home = pathlib.Path.home()
    system = platform.system()
    candidates: List[pathlib.Path] = []
    if system == "Darwin":
        candidates.append(home / "Library" / "Application Support" / "Cursor" / "User")
    elif system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(pathlib.Path(appdata) / "Cursor" / "User")
        candidates.append(home / "AppData" / "Roaming" / "Cursor" / "User")
    else:
        candidates.append(home / ".config" / "Cursor" / "User")
        candidates.append(home / ".config" / "Code" / "User")

    seen: set[str] = set()
    result: List[pathlib.Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def find_user_dir(explicit: Optional[pathlib.Path] = None) -> pathlib.Path:
    candidates = cursor_user_dirs(explicit)
    existing = [p for p in candidates if p.exists()]
    for p in existing:
        if (p / "globalStorage" / "state.vscdb").exists() or (p / "workspaceStorage").exists():
            return p
    if explicit:
        raise CursorCopyError(f"Cursor user directory not found or incomplete: {explicit}")
    raise CursorCopyError(
        "Cursor user directory not found. Tried: " + ", ".join(str(p) for p in candidates)
    )
