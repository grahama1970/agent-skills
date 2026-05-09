"""PROJECT_KNOWLEDGE.md parsing for project-drift."""
from __future__ import annotations

import re
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import truncate_text

LAST_UPDATED_RE = re.compile(r"\*\*Last updated:\*\*\s*(.+)", re.IGNORECASE)
PROJECT_HEADER_RE = re.compile(r"^#\s+Project Knowledge:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")


def parse_sections(content: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in content.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def extract_last_updated(header: str) -> str | None:
    for line in header.splitlines():
        match = LAST_UPDATED_RE.search(line)
        if match:
            return match.group(1).strip()
    return None


def extract_project_name(content: str, project_root: Path) -> str:
    env_project = os.environ.get("PROJECT_KNOWLEDGE_PROJECT")
    if env_project:
        return env_project
    match = PROJECT_HEADER_RE.search(content)
    if match:
        return match.group(1).strip()
    return project_root.name


def _is_separator_row(cells: list[str]) -> bool:
    return all(set(cell.strip()) <= {"-", ":"} for cell in cells if cell.strip())


def _extract_table_claims(section: str, text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    headers: list[str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        match = TABLE_ROW_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if _is_separator_row(cells):
            continue
        if headers is None:
            headers = cells
            continue
        row = {headers[i] if i < len(headers) else f"col_{i}": cell for i, cell in enumerate(cells)}
        rendered = "; ".join(f"{k}: {v}" for k, v in row.items() if v)
        if rendered:
            claims.append({
                "section": section,
                "claim_type": "table_row",
                "text": truncate_text(rendered, max_chars=800),
            })
    return claims


def extract_claims(sections: dict[str, str]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for section, text in sections.items():
        if section == "header":
            continue
        lines = [line.rstrip() for line in text.splitlines()]
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("- [ ]") or stripped.startswith("- [x]") or stripped.startswith("- [X]"):
                checked = "[x]" in stripped.lower()
                claims.append({
                    "section": section,
                    "claim_type": "open_question" if not checked else "resolved_question",
                    "text": stripped.replace("- [ ]", "").replace("- [x]", "").replace("- [X]", "").strip(),
                })
            elif stripped.startswith("- "):
                claims.append({
                    "section": section,
                    "claim_type": "bullet",
                    "text": stripped[2:].strip(),
                })
            elif stripped.startswith("*") and stripped.endswith("*"):
                continue
        claims.extend(_extract_table_claims(section, text))
    return [claim for claim in claims if claim.get("text")]


def load_project_knowledge(project_root: Path, knowledge_file: Path | None = None, max_claims: int = 120) -> dict[str, Any]:
    env_path = os.environ.get("PROJECT_KNOWLEDGE_PATH")
    path = knowledge_file or (Path(env_path).expanduser() if env_path else project_root / "PROJECT_KNOWLEDGE.md")
    if not path.exists():
        return {
            "found": False,
            "path": str(path),
            "project": os.environ.get("PROJECT_KNOWLEDGE_PROJECT") or project_root.name,
            "last_updated": None,
            "sections": {},
            "claims": [],
            "warnings": ["PROJECT_KNOWLEDGE.md not found"],
        }
    content = path.read_text(encoding="utf-8", errors="replace")
    sections = parse_sections(content)
    claims = extract_claims(sections)
    return {
        "found": True,
        "path": str(path),
        "project": extract_project_name(content, project_root),
        "last_updated": extract_last_updated(sections.get("header", "")),
        "sections": sections,
        "claims": claims[:max_claims],
        "claim_count": len(claims),
        "warnings": [],
    }


def claims_for_prompt(knowledge: dict[str, Any], max_claims: int = 80) -> str:
    if not knowledge.get("found"):
        return "PROJECT_KNOWLEDGE.md was not found. Treat this as no_action unless evidence shows a blocking missing knowledge problem."
    lines = [
        f"Project: {knowledge.get('project')}",
        f"PROJECT_KNOWLEDGE path: {knowledge.get('path')}",
        f"Last project_knowledge update: {knowledge.get('last_updated') or 'unknown'}",
        "",
        "Current project_knowledge claims:",
    ]
    for idx, claim in enumerate(knowledge.get("claims", [])[:max_claims], start=1):
        lines.append(
            f"{idx}. section={claim.get('section')} type={claim.get('claim_type')} claim={claim.get('text')}"
        )
    if knowledge.get("claim_count", 0) > max_claims:
        lines.append(f"... {knowledge['claim_count'] - max_claims} additional claims omitted from prompt budget.")
    return "\n".join(lines)
