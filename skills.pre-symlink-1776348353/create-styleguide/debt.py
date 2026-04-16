"""Token debt parser (STYLE_GUIDE.md section 8.2) and per-surface debt.json tracker."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


def parse_style_guide_debt(style_guide_path: Path) -> list[dict]:
    """Parse the 'Known Token Debt' table from STYLE_GUIDE.md section 8.2.

    Returns list of dicts: {id, issue, severity, resolution}
    """
    if not style_guide_path.exists():
        logger.warning(f"STYLE_GUIDE.md not found at {style_guide_path}")
        return []

    text = style_guide_path.read_text()
    items = []

    # Match markdown table rows like: | D3 | HorusStyle.qml diverges... | HIGH | Build token sync... |
    pattern = re.compile(
        r"^\|\s*(D\d+)\s*\|\s*(.+?)\s*\|\s*(CRITICAL|HIGH|MEDIUM|LOW)\s*\|\s*(.+?)\s*\|",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        items.append({
            "id": m.group(1),
            "issue": m.group(2).strip(),
            "severity": m.group(3),
            "resolution": m.group(4).strip(),
        })

    logger.info(f"Parsed {len(items)} debt items from STYLE_GUIDE.md")
    return items


def load_debt(debt_path: Path) -> list[dict]:
    """Load existing debt.json for a surface."""
    if not debt_path.exists():
        return []
    return json.loads(debt_path.read_text())


def save_debt(debt_path: Path, items: list[dict]) -> None:
    """Save debt items to debt.json."""
    debt_path.parent.mkdir(parents=True, exist_ok=True)
    debt_path.write_text(json.dumps(items, indent=2) + "\n")
    logger.info(f"Saved {len(items)} debt items to {debt_path}")


def merge_audit_debt(
    existing: list[dict],
    audit_findings: list[dict],
    audit_round: int,
) -> list[dict]:
    """Merge new findings from a /review-design audit into existing debt.

    audit_findings: list of {issue, severity, source} dicts from audit JSON.
    Returns updated list (does not mutate existing).
    """
    merged = list(existing)
    existing_issues = {item["issue"] for item in merged}

    # Find next D-number
    max_id = 0
    for item in merged:
        m = re.match(r"D(\d+)", item.get("id", ""))
        if m:
            max_id = max(max_id, int(m.group(1)))

    for finding in audit_findings:
        issue_text = finding.get("issue", "")
        if issue_text in existing_issues:
            continue
        max_id += 1
        merged.append({
            "id": f"D{max_id}",
            "issue": issue_text,
            "severity": finding.get("severity", "MEDIUM"),
            "source": finding.get("source", "audit"),
            "resolved": False,
            "discovered": datetime.now(timezone.utc).isoformat(),
            "audit_round": audit_round,
        })

    return merged
