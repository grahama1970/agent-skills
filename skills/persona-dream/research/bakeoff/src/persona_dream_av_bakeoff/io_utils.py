from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_text(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def extract_url_from_result(result: dict[str, Any], key: str) -> str:
    # Common fal shape: {"audio": {"url": "..."}} or {"video": {"url": "..."}}
    value = result.get(key)
    if isinstance(value, dict) and isinstance(value.get("url"), str):
        return value["url"]
    if isinstance(value, str) and value.startswith("http"):
        return value
    raise KeyError(f"Could not find {key}.url in result keys={list(result.keys())}")
