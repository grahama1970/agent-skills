"""Cursor composer SQLite bubble extraction."""
from __future__ import annotations

import dataclasses
import json
import pathlib
import platform
import urllib.parse
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from ccopy.errors import CursorCopyError
from ccopy.models import (
    ASSISTANT_TYPE,
    ROLE_ASSISTANT,
    ROLE_USER,
    SOURCE_SQLITE,
    USER_TYPE,
    ConversationHeader,
    LastTurn,
    Message,
    Workspace,
)
from ccopy.formatters import find_last_complete_turn
from ccopy.sqlite_db import KVDB
from ccopy.utils import coerce_ts, normalize_text, parse_json_value

def file_uri_to_path(uri: str) -> Optional[str]:
    if not uri:
        return None
    try:
        parsed = urllib.parse.urlparse(uri)
    except Exception:
        return None
    if parsed.scheme == "file":
        path = urllib.parse.unquote(parsed.path)
        if platform.system() == "Windows" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return path
    if parsed.scheme == "vscode-remote":
        # Remote workspace path is still useful for substring matching/listing.
        return urllib.parse.unquote(parsed.path)
    return urllib.parse.unquote(parsed.path) if parsed.path else None


def read_workspace_json(workspace_dir: pathlib.Path) -> Tuple[Optional[str], Optional[str]]:
    meta = workspace_dir / "workspace.json"
    if not meta.exists():
        return None, None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    uri = data.get("folder") or data.get("workspace")
    if isinstance(uri, dict):
        uri = uri.get("external") or uri.get("path") or uri.get("fsPath")
    if not isinstance(uri, str):
        uri = None
    return uri, file_uri_to_path(uri or "")


def discover_workspaces(user_dir: pathlib.Path) -> List[Workspace]:
    ws_root = user_dir / "workspaceStorage"
    if not ws_root.exists():
        return []
    workspaces: List[Workspace] = []
    for ws_dir in sorted(ws_root.iterdir(), key=lambda p: p.name):
        if not ws_dir.is_dir():
            continue
        db = ws_dir / "state.vscdb"
        if not db.exists():
            continue
        uri, fs_path = read_workspace_json(ws_dir)
        workspaces.append(
            Workspace(
                workspace_id=ws_dir.name,
                path=ws_dir,
                db_path=db,
                uri=uri,
                fs_path=fs_path,
            )
        )
    return workspaces


def is_relative_to_path(child: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def match_workspace(workspaces: Sequence[Workspace], selector: Optional[str], cwd: pathlib.Path) -> Optional[Workspace]:
    if selector:
        selector_low = selector.lower()
        exact = [w for w in workspaces if w.workspace_id == selector]
        if exact:
            return exact[0]
        matches = []
        for w in workspaces:
            haystacks = [w.workspace_id, w.uri or "", w.fs_path or "", str(w.path)]
            if any(selector_low in h.lower() for h in haystacks):
                matches.append(w)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise CursorCopyError(
                "workspace selector matched multiple workspaces; use the exact hash from --list-workspaces"
            )
        raise CursorCopyError(f"workspace selector matched nothing: {selector}")

    # Prefer the deepest workspace folder containing cwd.
    local_matches: List[Workspace] = []
    for w in workspaces:
        if not w.fs_path:
            continue
        if w.uri and w.uri.startswith("vscode-remote:"):
            continue
        try:
            ws_path = pathlib.Path(w.fs_path)
        except Exception:
            continue
        if ws_path.exists() and is_relative_to_path(cwd, ws_path):
            local_matches.append(w)
    if local_matches:
        local_matches.sort(key=lambda w: len(str(w.fs_path or "")), reverse=True)
        return local_matches[0]
    return None


def global_db_path(user_dir: pathlib.Path) -> Optional[pathlib.Path]:
    db = user_dir / "globalStorage" / "state.vscdb"
    return db if db.exists() else None


def read_workspace_composer_metadata(workspace: Workspace) -> Dict[str, Any]:
    with KVDB(workspace.db_path) as db:
        data = db.get_json("composer.composerData", tables=("ItemTable", "cursorDiskKV"))
        return data if isinstance(data, dict) else {}


def coerce_ts(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except Exception:
        return 0


def workspace_identifier_fields(raw: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    ident = raw.get("workspaceIdentifier") or raw.get("workspace") or {}
    if not isinstance(ident, dict):
        return None, None, None
    ws_id = ident.get("id") if isinstance(ident.get("id"), str) else None
    uri = ident.get("uri")
    uri_external = None
    uri_path = None
    if isinstance(uri, dict):
        uri_external = uri.get("external") or uri.get("uri")
        uri_path = uri.get("fsPath") or uri.get("path") or file_uri_to_path(uri_external or "")
    elif isinstance(uri, str):
        uri_external = uri
        uri_path = file_uri_to_path(uri)
    return ws_id, uri_external, uri_path


def header_from_raw(raw: Dict[str, Any], source: str, fallback_workspace_id: Optional[str] = None) -> Optional[ConversationHeader]:
    composer_id = raw.get("composerId") or raw.get("id") or raw.get("composer_id")
    if not isinstance(composer_id, str) or not composer_id:
        return None
    ws_id, ws_uri, ws_path = workspace_identifier_fields(raw)
    return ConversationHeader(
        composer_id=composer_id,
        name=str(raw.get("name") or raw.get("title") or ""),
        workspace_id=ws_id or fallback_workspace_id,
        workspace_uri=ws_uri,
        workspace_path=ws_path,
        created_at=coerce_ts(raw.get("createdAt") or raw.get("created_at")),
        last_updated_at=coerce_ts(raw.get("lastUpdatedAt") or raw.get("updatedAt") or raw.get("last_updated_at")),
        unified_mode=str(raw.get("unifiedMode") or raw.get("mode") or ""),
        source=source,
    )


def get_global_headers(global_db: KVDB) -> List[ConversationHeader]:
    headers: List[ConversationHeader] = []
    data = global_db.get_json("composer.composerHeaders", tables=("ItemTable", "cursorDiskKV"))
    if isinstance(data, dict):
        composers = data.get("allComposers") or data.get("composers") or data.get("headers") or []
        if isinstance(composers, dict):
            composers = list(composers.values())
        if isinstance(composers, list):
            for raw in composers:
                if isinstance(raw, dict):
                    header = header_from_raw(raw, source="global:composer.composerHeaders")
                    if header:
                        headers.append(header)
    return headers


def get_workspace_headers(workspace: Workspace) -> List[ConversationHeader]:
    data = read_workspace_composer_metadata(workspace)
    headers: List[ConversationHeader] = []
    composers = data.get("allComposers") if isinstance(data, dict) else None
    if isinstance(composers, dict):
        composers = list(composers.values())
    if isinstance(composers, list):
        for raw in composers:
            if isinstance(raw, dict):
                header = header_from_raw(raw, source="workspace:composer.composerData", fallback_workspace_id=workspace.workspace_id)
                if header:
                    # Preserve workspace path if legacy header has no new workspaceIdentifier.
                    if not header.workspace_path and workspace.fs_path:
                        header = dataclasses.replace(header, workspace_path=workspace.fs_path, workspace_id=workspace.workspace_id)
                    headers.append(header)
    return headers


def selected_ids_for_workspace(workspace: Workspace) -> List[str]:
    data = read_workspace_composer_metadata(workspace)
    ids: List[str] = []
    if isinstance(data, dict):
        for key in ("selectedComposerIds", "lastFocusedComposerIds"):
            raw = data.get(key)
            if isinstance(raw, list):
                ids.extend([x for x in raw if isinstance(x, str)])
            elif isinstance(raw, str):
                ids.append(raw)
    # Cursor 3.x tab/view entries can contain composerIds even when composerData has
    # already migrated. Scrape them as a fallback.
    with KVDB(workspace.db_path) as db:
        for key, value in db.iter_item_keys_like("workbench.panel.composerChatViewPane.%", table="ItemTable"):
            data = parse_json_value(value)
            for found in find_composer_ids(data):
                ids.append(found)
    return dedupe(ids)


def find_composer_ids(obj: Any) -> Iterator[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {"composerId", "composer_id", "id"} and isinstance(v, str) and looks_like_composer_id(v):
                yield v
            else:
                yield from find_composer_ids(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from find_composer_ids(item)


def looks_like_composer_id(value: str) -> bool:
    if not value or len(value) < 8:
        return False
    if value.startswith("task-") or value.startswith("task_"):
        return True
    return "-" in value or len(value) >= 16


def dedupe(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def filter_headers_for_workspace(headers: Sequence[ConversationHeader], workspace: Workspace) -> List[ConversationHeader]:
    result: List[ConversationHeader] = []
    for h in headers:
        if h.workspace_id and h.workspace_id == workspace.workspace_id:
            result.append(h)
            continue
        if workspace.fs_path and h.workspace_path:
            try:
                if pathlib.Path(workspace.fs_path) == pathlib.Path(h.workspace_path):
                    result.append(h)
                    continue
            except Exception:
                pass
        if workspace.uri and h.workspace_uri and workspace.uri == h.workspace_uri:
            result.append(h)
            continue
    return result


def header_sort_key(h: ConversationHeader) -> Tuple[int, int]:
    return (h.last_updated_at or h.created_at or 0, h.created_at or 0)


def choose_conversation(
    global_db: KVDB,
    user_dir: pathlib.Path,
    workspace: Optional[Workspace],
    composer_id: Optional[str],
    latest_global: bool,
) -> ConversationHeader:
    if composer_id:
        return ConversationHeader(composer_id=composer_id, source="explicit")

    global_headers = get_global_headers(global_db)
    workspace_headers: List[ConversationHeader] = []
    if workspace:
        workspace_headers = get_workspace_headers(workspace)

    by_id: Dict[str, ConversationHeader] = {}
    for h in workspace_headers + global_headers:
        prev = by_id.get(h.composer_id)
        if prev is None or header_sort_key(h) >= header_sort_key(prev):
            # Prefer more specific workspace fields when merging.
            if prev and not h.workspace_id and prev.workspace_id:
                h = dataclasses.replace(h, workspace_id=prev.workspace_id)
            if prev and not h.workspace_path and prev.workspace_path:
                h = dataclasses.replace(h, workspace_path=prev.workspace_path)
            by_id[h.composer_id] = h

    if workspace and not latest_global:
        selected = selected_ids_for_workspace(workspace)
        for cid in selected:
            if cid in by_id:
                return by_id[cid]
        ws_headers = filter_headers_for_workspace(list(by_id.values()), workspace)
        if ws_headers:
            return sorted(ws_headers, key=header_sort_key, reverse=True)[0]
        if selected:
            return ConversationHeader(composer_id=selected[0], workspace_id=workspace.workspace_id, workspace_path=workspace.fs_path, source="workspace:selected")
        # Legacy workspace headers may lack global index matches; use newest if present.
        if workspace_headers:
            return sorted(workspace_headers, key=header_sort_key, reverse=True)[0]
        raise CursorCopyError(
            "matched a Cursor workspace, but found no conversations for it. Try --latest or --list-conversations."
        )

    if by_id:
        return sorted(by_id.values(), key=header_sort_key, reverse=True)[0]

    # Last ditch: derive composer IDs from global composerData:* keys.
    inferred: List[ConversationHeader] = []
    for key, _ in global_db.iter_key_prefix("composerData:", table="cursorDiskKV"):
        cid = key.split(":", 1)[1]
        inferred.append(ConversationHeader(composer_id=cid, source="global:composerData-prefix"))
    if inferred:
        return inferred[0]

    raise CursorCopyError("no Cursor conversations found in globalStorage/state.vscdb")


def load_conversation_data(global_db: KVDB, composer_id: str) -> Dict[str, Any]:
    data = global_db.get_json(f"composerData:{composer_id}", tables=("cursorDiskKV", "ItemTable"))
    if isinstance(data, dict):
        return data
    # Some older DBs have JSON blobs under keys with suffixes. Try to find a close match.
    for key, value in global_db.iter_key_prefix(f"composerData:{composer_id}", table="cursorDiskKV"):
        parsed = parse_json_value(value)
        if isinstance(parsed, dict):
            return parsed
    raise CursorCopyError(f"conversation data not found for composerId {composer_id}")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [normalize_text(v) for v in value]
        return "\n".join(p for p in parts if p).strip()
    if isinstance(value, dict):
        # Common rich-text leaves; keep this conservative to avoid dumping metadata.
        for key in ("text", "content", "value", "markdown"):
            if key in value:
                text = normalize_text(value.get(key))
                if text:
                    return text
        if "children" in value:
            return normalize_text(value.get("children"))
        return ""
    return str(value).strip()


def message_text_from_bubble(bubble: Dict[str, Any]) -> str:
    for key in ("text", "markdown", "content"):
        text = normalize_text(bubble.get(key))
        if text:
            return text
    # Some assistant payloads store visible code or chunks separately.
    for key in ("codeBlocks", "suggestedCodeBlocks"):
        blocks = bubble.get(key)
        if isinstance(blocks, list):
            rendered: List[str] = []
            for block in blocks:
                if isinstance(block, dict):
                    code = normalize_text(block.get("code") or block.get("text") or block.get("content"))
                    if code:
                        rendered.append(code)
            if rendered:
                return "\n\n".join(rendered).strip()
    return ""


def role_from_type(value: Any) -> Optional[str]:
    try:
        t = int(value)
    except Exception:
        return None
    if t == USER_TYPE:
        return ROLE_USER
    if t == ASSISTANT_TYPE:
        return ROLE_ASSISTANT
    return None


def ordered_messages(global_db: KVDB, composer_id: str, data: Dict[str, Any]) -> List[Message]:
    headers = data.get("fullConversationHeadersOnly") or data.get("conversationHeaders") or []
    conversation_map = data.get("conversationMap") if isinstance(data.get("conversationMap"), dict) else {}
    messages: List[Message] = []

    if isinstance(headers, dict):
        headers = list(headers.values())

    if isinstance(headers, list) and headers:
        for header in headers:
            if not isinstance(header, dict):
                continue
            bubble_id = header.get("bubbleId") or header.get("id") or header.get("messageId")
            bubble_type = header.get("type")
            bubble: Dict[str, Any] = {}
            if isinstance(bubble_id, str):
                raw_bubble = global_db.get_json(f"bubbleId:{composer_id}:{bubble_id}", tables=("cursorDiskKV", "ItemTable"))
                if isinstance(raw_bubble, dict):
                    bubble = raw_bubble
                elif isinstance(conversation_map.get(bubble_id), dict):
                    bubble = conversation_map[bubble_id]
            if bubble and bubble.get("type") is not None:
                bubble_type = bubble.get("type")
            role = role_from_type(bubble_type)
            if not role:
                continue
            text = message_text_from_bubble(bubble) if bubble else ""
            if not text and isinstance(bubble_id, str) and isinstance(conversation_map.get(bubble_id), dict):
                text = message_text_from_bubble(conversation_map[bubble_id])
            if not text:
                continue
            created_at = coerce_ts((bubble or header).get("createdAt") or (bubble or header).get("timestamp"))
            messages.append(Message(role=role, text=text, bubble_id=bubble_id if isinstance(bubble_id, str) else None, created_at=created_at))
    elif conversation_map:
        # Legacy fallback. Conversation map ordering is less reliable, but dict order is
        # insertion ordered for modern Python and often mirrors persisted JSON order.
        for bubble_id, bubble in conversation_map.items():
            if not isinstance(bubble, dict):
                continue
            role = role_from_type(bubble.get("type"))
            if not role:
                continue
            text = message_text_from_bubble(bubble)
            if text:
                messages.append(Message(role=role, text=text, bubble_id=str(bubble_id), created_at=coerce_ts(bubble.get("createdAt"))))
    else:
        # Last resort: scan bubble entries by prefix/rowid.
        for key, value in global_db.iter_key_prefix(f"bubbleId:{composer_id}:", table="cursorDiskKV"):
            bubble = parse_json_value(value)
            if not isinstance(bubble, dict):
                continue
            role = role_from_type(bubble.get("type"))
            text = message_text_from_bubble(bubble)
            if role and text:
                messages.append(Message(role=role, text=text, bubble_id=key.rsplit(":", 1)[-1], created_at=coerce_ts(bubble.get("createdAt"))))
    return messages
def sqlite_has_bubble_messages(user_dir: pathlib.Path) -> bool:
    gpath = global_db_path(user_dir)
    if not gpath:
        return False
    with KVDB(gpath) as gdb:
        for _ in gdb.iter_key_prefix("bubbleId:", table="cursorDiskKV"):
            return True
    return False


def build_last_turn_sqlite(
    user_dir: pathlib.Path,
    workspace_selector: Optional[str],
    composer_id: Optional[str],
    latest_global: bool,
    cwd: pathlib.Path,
) -> LastTurn:
    gpath = global_db_path(user_dir)
    if not gpath:
        raise CursorCopyError(f"global DB not found: {user_dir / 'globalStorage' / 'state.vscdb'}")
    workspaces = discover_workspaces(user_dir)
    workspace = match_workspace(workspaces, workspace_selector, cwd)

    with KVDB(gpath) as gdb:
        header = choose_conversation(gdb, user_dir, workspace, composer_id, latest_global=latest_global or workspace is None)
        data = load_conversation_data(gdb, header.composer_id)
        messages = ordered_messages(gdb, header.composer_id, data)
        user_msg, assistant_msg = find_last_complete_turn(messages)
        name = header.name or str(data.get("name") or data.get("title") or "")
        ws_id = header.workspace_id or (workspace.workspace_id if workspace else None)
        ws_path = header.workspace_path or (workspace.fs_path if workspace else None)
        return LastTurn(
            composer_id=header.composer_id,
            conversation_name=name,
            workspace_id=ws_id,
            workspace_path=ws_path,
            user=user_msg,
            assistant=assistant_msg,
            source=SOURCE_SQLITE,
        )
