"""Storage diagnostics and listing."""
from __future__ import annotations

import pathlib
from typing import Dict, Optional

from ccopy.errors import CursorCopyError
from ccopy.models import ConversationHeader, Workspace
from ccopy.sqlite_backend import (
    discover_workspaces,
    filter_headers_for_workspace,
    get_global_headers,
    get_workspace_headers,
    global_db_path,
    header_sort_key,
    match_workspace,
    sqlite_has_bubble_messages,
)
from ccopy.sqlite_db import KVDB
from ccopy.transcript import discover_cursor_projects, list_agent_transcript_files, match_cursor_project
from ccopy.utils import millis_to_iso

def diagnose_storage(user_dir: pathlib.Path, cwd: pathlib.Path) -> str:
    lines = ["# cursor-copy diagnostics", ""]
    gpath = global_db_path(user_dir)
    lines.append(f"cursor_user_dir: {user_dir}")
    lines.append(f"global_db: {gpath or '(missing)'}")
    lines.append(f"sqlite_bubble_rows: {sqlite_has_bubble_messages(user_dir)}")
    lines.append(f"cwd: {cwd.resolve()}")
    lines.append("")

    lines.append("## SQLite workspaces (workspaceStorage)")
    workspaces = discover_workspaces(user_dir)
    if not workspaces:
        lines.append("(none)")
    else:
        for w in workspaces:
            lines.append(f"- {w.workspace_id}: {w.fs_path or '(unknown)'}")
    lines.append("")

    lines.append("## Agent transcript projects (~/.cursor/projects)")
    projects = discover_cursor_projects()
    if not projects:
        lines.append("(none)")
    else:
        for project_dir, name in projects:
            transcripts = list_agent_transcript_files(project_dir)
            latest = transcripts[0] if transcripts else None
            lines.append(f"- {name}: {len(transcripts)} session(s)")
            if latest:
                lines.append(f"  latest: {latest[2]} ({pathlib.Path(latest[1]).stat().st_size} bytes)")
    matched = match_cursor_project(cwd, None)
    lines.append("")
    lines.append(f"cwd-matched project: {matched.name if matched else '(none)'}")
    if matched and not sqlite_has_bubble_messages(user_dir):
        lines.append("recommended_source: agent-transcript (SQLite has no bubbleId message rows on this install)")
    elif sqlite_has_bubble_messages(user_dir):
        lines.append("recommended_source: sqlite")
    else:
        lines.append("recommended_source: unavailable (no bubbles and no agent-transcript project for cwd)")
    return "\n".join(lines) + "\n"


def list_workspaces(user_dir: pathlib.Path) -> str:
    workspaces = discover_workspaces(user_dir)
    if not workspaces:
        return "No Cursor workspaces found."
    lines = ["# Cursor workspaces", ""]
    for i, w in enumerate(workspaces, start=1):
        lines.append(f"{i}. {w.workspace_id}")
        lines.append(f"   path: {w.fs_path or '(unknown)'}")
        if w.uri:
            lines.append(f"   uri:  {w.uri}")
    return "\n".join(lines)


def list_conversations(user_dir: pathlib.Path, workspace: Optional[Workspace]) -> str:
    gpath = global_db_path(user_dir)
    if not gpath:
        raise CursorCopyError(f"global DB not found under {user_dir}")
    with KVDB(gpath) as gdb:
        headers = get_global_headers(gdb)
    if workspace:
        headers.extend(get_workspace_headers(workspace))
        headers = filter_headers_for_workspace(headers, workspace)
    # Deduplicate by ID, preserving best timestamp.
    by_id: Dict[str, ConversationHeader] = {}
    for h in headers:
        prev = by_id.get(h.composer_id)
        if prev is None or header_sort_key(h) >= header_sort_key(prev):
            by_id[h.composer_id] = h
    rows = sorted(by_id.values(), key=header_sort_key, reverse=True)
    if not rows:
        return "No conversations found."
    lines = ["# Cursor conversations", ""]
    for h in rows[:100]:
        updated = h.last_updated_at or h.created_at
        updated_text = millis_to_iso(updated) if updated else "unknown"
        lines.append(f"- {h.composer_id}")
        lines.append(f"  name: {h.name or '(untitled)'}")
        lines.append(f"  updated: {updated_text}")
        lines.append(f"  workspace: {h.workspace_path or h.workspace_id or '(unknown)'}")
        if h.unified_mode:
            lines.append(f"  mode: {h.unified_mode}")
    return "\n".join(lines)
