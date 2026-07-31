"""Phase 2: Memory recall collector.

Queries the /memory skill for known Embry OS features, architecture,
competitive advantages, and known issues.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from constants import MEMORY_SKILL


def collect_memory() -> dict[str, Any]:
    """Query /memory for known Embry OS features and architecture."""
    if not MEMORY_SKILL.exists():
        return {"available": False, "error": "memory skill not found"}

    queries = [
        "embry os features architecture cascade daemons deployment",
        "embry os competitive advantages unique capabilities",
        "embry os known issues gaps missing features",
    ]
    results = []
    for q in queries:
        try:
            out = subprocess.run(
                ["bash", str(MEMORY_SKILL), "recall", "--q", q],
                capture_output=True, text=True, timeout=30,
            )
            if out.returncode == 0:
                try:
                    data = json.loads(out.stdout)
                    results.append({
                        "query": q,
                        "found": data.get("found", False),
                        "confidence": data.get("confidence", 0),
                        "count": len(data.get("items", [])),
                        "top_items": [
                            {"problem": it.get("problem", "")[:120], "solution": it.get("solution", "")[:120]}
                            for it in data.get("items", [])[:3]
                        ],
                    })
                except json.JSONDecodeError:
                    results.append({"query": q, "found": False, "raw": out.stdout[:200]})
            else:
                results.append({"query": q, "found": False, "error": out.stderr[:100]})
        except Exception as e:
            results.append({"query": q, "found": False, "error": str(e)[:100]})

    return {"available": True, "recalls": results}
