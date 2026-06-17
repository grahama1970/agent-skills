#!/usr/bin/env python3
"""Generate SOURCES.md and sources/agent-skills-registry.json from skills/ and agents/."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

REPOSITORY = "grahama1970/agent-skills"
SCHEMA_VERSION = "1.0"
DEFAULT_MD = "SOURCES.md"
DEFAULT_JSON = "sources/agent-skills-registry.json"
SUMMARY_LIMIT = 240
CELL_LIMIT = 220


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def uniq(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def split_csv(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    for char in text:
        if quote:
            buf.append(char)
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            buf.append(char)
        elif char == ",":
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(char)
    parts.append("".join(buf).strip())
    return [part for part in parts if part]


def scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if not value.startswith(("'", '"')):
        value = re.sub(r"\s+#.*$", "", value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [scalar(part) for part in split_csv(value[1:-1])]
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"
    if low in {"null", "none", "~"}:
        return None
    return value


def parse_frontmatter(raw: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    lines = raw.splitlines()
    key_re = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s*(.*))?$")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        match = key_re.match(line)
        if not match:
            i += 1
            continue
        key, value = match.group(1), (match.group(2) or "").strip()
        if value in {">", "|", ">-", "|-", ">+", "|+"}:
            block: list[str] = []
            i += 1
            while i < len(lines) and not key_re.match(lines[i]):
                if not lines[i].strip().startswith("#"):
                    block.append(lines[i].strip())
                i += 1
            meta[key] = " ".join(part for part in block if part).strip()
            continue
        if value == "":
            items: list[Any] = []
            i += 1
            while i < len(lines) and not key_re.match(lines[i]):
                item = re.match(r"^\s*-\s*(.*)$", lines[i])
                if item:
                    items.append(scalar(item.group(1)))
                i += 1
            meta[key] = items if items else ""
            continue
        meta[key] = scalar(value)
        i += 1
    return meta


def split_doc(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return parse_frontmatter("".join(lines[1:i])), "".join(lines[i + 1 :])
    return {}, text


def flat(value: Any) -> str:
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value)
    return re.sub(r"\s+", " ", str(value or "")).strip()


def trunc(text: Any, limit: int) -> str:
    text = flat(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def as_list(value: Any) -> list[str]:
    if value is None or value is False:
        return []
    if isinstance(value, list):
        return uniq(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if "\n" in value:
            return uniq(line.strip(" -\t") for line in value.splitlines())
        if "," in value and not re.search(r"https?://", value):
            return uniq(scalar(part) for part in split_csv(value))
        return [value]
    return [str(value)]


def first(meta: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = meta.get(key)
        if value not in (None, "", []):
            return value
    return None


def md_summary(body: str) -> str:
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    chunks: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            if chunks:
                break
            continue
        if line.startswith("#") or line.startswith("|") or re.match(r"^[-*+]\s+", line):
            continue
        chunks.append(line)
    return trunc(" ".join(chunks), SUMMARY_LIMIT)


def summary(meta: dict[str, Any], body: str) -> str:
    value = first(meta, ["description", "purpose", "summary"])
    if value:
        return trunc(value, SUMMARY_LIMIT)
    body_summary = md_summary(body)
    if body_summary:
        return body_summary
    return trunc(first(meta, ["title", "name", "id"]) or "", SUMMARY_LIMIT)


def ident(meta: dict[str, Any], fallback: str) -> str:
    value = flat(first(meta, ["id", "name", "title"]) or fallback).lower()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value).strip("-")
    return value or fallback


def title(meta: dict[str, Any], fallback: str) -> str:
    return flat(first(meta, ["title", "name", "id"]) or fallback)


def source_file(directory: Path, names: Iterable[str]) -> Path | None:
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def content_hash(path: Path, root: Path, text: str) -> str:
    digest = hashlib.sha256()
    digest.update(rel(path, root).encode())
    digest.update(b"\0")
    digest.update(text.encode(errors="replace"))
    return digest.hexdigest()[:16]


def skill_entry(path: Path, src: Path, root: Path) -> dict[str, Any]:
    text = read(src)
    meta, body = split_doc(text)
    fallback = path.stem if path.is_file() else path.name
    sid = ident(meta, fallback)
    return {
        "id": sid,
        "type": "skill",
        "path": rel(path, root),
        "source_file": rel(src, root),
        "title": title(meta, sid),
        "summary": summary(meta, body),
        "triggers": as_list(first(meta, ["triggers", "trigger", "use_when", "use-when", "keywords"])),
        "allowed_tools": as_list(first(meta, ["allowed-tools", "allowed_tools", "tools"])),
        "related_agents": [],
        "content_hash": content_hash(src, root, text),
    }


def agent_entry(path: Path, src: Path, root: Path) -> dict[str, Any]:
    text = read(src)
    meta, body = split_doc(text)
    fallback = path.stem if path.is_file() else path.name
    aid = ident(meta, fallback)
    configured: list[str] = []
    for key in ["uses_skills", "uses-skills", "skills", "composes", "depends_on", "depends-on"]:
        configured.extend(as_list(meta.get(key)))
    mentioned = re.findall(r"skills/([A-Za-z0-9_.-]+)(?:/|\b)", text)
    return {
        "id": aid,
        "type": "agent",
        "kind": flat(first(meta, ["kind", "role", "type"]) or "agent"),
        "path": rel(path, root),
        "source_file": rel(src, root),
        "title": title(meta, aid),
        "summary": summary(meta, body),
        "uses_skills": uniq(configured + mentioned),
        "handoffs_to": as_list(first(meta, ["handoffs_to", "handoffs-to", "handoff", "delegates_to", "delegates-to"])),
        "verifier": flat(first(meta, ["verifier", "reviewer"])),
        "content_hash": content_hash(src, root, text),
    }


def discover(root: Path, dirname: str, kind: str) -> list[dict[str, Any]]:
    directory = root / dirname
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for child in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            names = ["SKILL.md", "README.md", "AGENTS.md"] if kind == "skill" else ["AGENTS.md", "AGENT.md", "README.md", "SKILL.md"]
            src = source_file(child, names)
            if src:
                out.append(skill_entry(child, src, root) if kind == "skill" else agent_entry(child, src, root))
        elif child.is_file() and child.suffix.lower() in {".md", ".yml", ".yaml"}:
            out.append(skill_entry(child, child, root) if kind == "skill" else agent_entry(child, child, root))
    return out


def registry(root: Path) -> dict[str, Any]:
    skills = discover(root, "skills", "skill")
    agents = discover(root, "agents", "agent")
    by_id = {skill["id"]: skill for skill in skills}
    by_name = {Path(skill["path"]).name: skill for skill in skills}
    for agent in agents:
        for ref in agent.get("uses_skills", []):
            skill = by_id.get(ref) or by_name.get(ref)
            if skill and agent["id"] not in skill["related_agents"]:
                skill["related_agents"].append(agent["id"])
    for skill in skills:
        skill["related_agents"] = sorted(skill["related_agents"])
    entries = sorted(skills + agents, key=lambda e: (e["type"], e["id"]))
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(f"{entry['type']}\0{entry['id']}\0{entry['content_hash']}\n".encode())
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": REPOSITORY,
        "source_roots": {"skills": "skills", "agents": "agents"},
        "content_hash": digest.hexdigest(),
        "counts": {"skills": len(skills), "agents": len(agents), "entries": len(entries)},
        "entries": entries,
    }


def esc(value: Any) -> str:
    return trunc(value, CELL_LIMIT).replace("|", "\\|") or "—"


def cell(values: Iterable[str], limit: int = 8) -> str:
    items = list(values)
    if not items:
        return "—"
    shown = ", ".join(f"`{item}`" for item in items[:limit])
    if len(items) > limit:
        shown += f", +{len(items) - limit} more"
    return esc(shown)


def render_md(data: dict[str, Any]) -> str:
    skills = [e for e in data["entries"] if e["type"] == "skill"]
    agents = [e for e in data["entries"] if e["type"] == "agent"]
    lines = [
        "# Sources",
        "",
        "<!-- GENERATED FILE: edit skills/ or agents/ and rerun scripts/generate_sources_registry.py -->",
        "",
        "This file is a generated retrieval map for ChatGPT/WebGPT-style source context.",
        "It indexes `skills/` and `agents/` so an agent can check existing capabilities before inventing new ones.",
        "",
        f"Machine-readable companion: `{DEFAULT_JSON}`.",
        "",
        "## How to use this registry",
        "",
        "1. Search this file before creating a new skill or subagent.",
        "2. Prefer an existing entry when its summary, triggers, or composed skills match the task.",
        "3. Use `source_file` paths as source handles for deeper inspection.",
        "4. Regenerate this file after changing `skills/` or `agents/`.",
        "",
        "## Registry metadata",
        "",
        f"- Repository: `{data['repository']}`",
        f"- Schema version: `{data['schema_version']}`",
        f"- Content hash: `{data['content_hash']}`",
        f"- Skill entries: `{data['counts']['skills']}`",
        f"- Agent entries: `{data['counts']['agents']}`",
        f"- Total entries: `{data['counts']['entries']}`",
        "",
        "## Skills",
        "",
        "| ID | Path | Summary | Triggers | Related agents |",
        "|---|---|---|---|---|",
    ]
    for entry in skills:
        lines.append(f"| {esc('`' + entry['id'] + '`')} | {esc('`' + entry['source_file'] + '`')} | {esc(entry.get('summary'))} | {cell(entry.get('triggers', []), 6)} | {cell(entry.get('related_agents', []), 6)} |")
    lines += ["", "## Agents and subagents", "", "| ID | Kind | Path | Uses skills | Summary |", "|---|---|---|---|---|"]
    for entry in agents:
        lines.append(f"| {esc('`' + entry['id'] + '`')} | {esc(entry.get('kind'))} | {esc('`' + entry['source_file'] + '`')} | {cell(entry.get('uses_skills', []), 8)} | {esc(entry.get('summary'))} |")
    lines += ["", "## Regenerate", "", "```bash", "python scripts/generate_sources_registry.py", "python scripts/generate_sources_registry.py --check", "```", ""]
    return "\n".join(lines)


def write(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def check(path: Path, expected: str) -> bool:
    if not path.exists():
        print(f"Missing generated file: {path}", file=sys.stderr)
        return False
    actual = path.read_text(encoding="utf-8")
    if actual == expected:
        return True
    print("\n".join(difflib.unified_diff(actual.splitlines(), expected.splitlines(), fromfile=str(path), tofile=f"{path} (expected)", lineterm="")), file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--sources-md", default=DEFAULT_MD)
    parser.add_argument("--registry-json", default=DEFAULT_JSON)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    data = registry(root)
    md = render_md(data)
    js = json.dumps(data, indent=2, sort_keys=True) + "\n"
    md_path = root / args.sources_md
    json_path = root / args.registry_json
    if args.check:
        return 0 if check(md_path, md) and check(json_path, js) else 1
    changed_md = write(md_path, md)
    changed_json = write(json_path, js)
    changed = changed_md or changed_json
    print(f"Generated {args.sources_md} and {args.registry_json} ({data['counts']['skills']} skills, {data['counts']['agents']} agents, changed={changed}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
