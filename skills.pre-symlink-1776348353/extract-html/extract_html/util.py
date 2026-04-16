"""util - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

def read_text_file(path: Union[str, Path]) -> str:
    return Path(path).read_text(encoding="utf-8")

def write_text_file(path: Union[str, Path], content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")

def read_json_file(path: Union[str, Path]) -> Any:
    return json.loads(read_text_file(path))

def write_json_file(path: Union[str, Path], data: Any) -> None:
    write_text_file(path, json.dumps(data, indent=2, ensure_ascii=False))
