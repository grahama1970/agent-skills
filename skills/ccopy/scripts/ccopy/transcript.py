"""Agent transcript JSONL extraction."""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional, Tuple

from ccopy.errors import CursorCopyError
from ccopy.models import ROLE_ASSISTANT, ROLE_USER, SOURCE_TRANSCRIPT, LastTurn, Message
from ccopy.utils import parse_json_value

def cursor_projects_root() -> pathlib.Path:
    return pathlib.Path.home() / ".cursor" / "projects"


def project_slug_from_path(path: pathlib.Path) -> str:
    return path.resolve().as_posix().lstrip("/").replace("/", "-")


def discover_cursor_projects() -> List[Tuple[pathlib.Path, str]]:
    root = cursor_projects_root()
    if not root.is_dir():
        return []
    rows: List[Tuple[pathlib.Path, str]] = []
    for project_dir in root.iterdir():
        if project_dir.is_dir() and (project_dir / "agent-transcripts").is_dir():
            rows.append((project_dir, project_dir.name))
    return rows


def match_cursor_project(
    cwd: pathlib.Path,
    selector: Optional[str] = None,
) -> Optional[pathlib.Path]:
    projects = discover_cursor_projects()
    if not projects:
        return None
    if selector:
        low = selector.lower()
        exact = [p for p, _ in projects if p.name == selector]
        if exact:
            return exact[0]
        matches = [p for p, name in projects if low in name.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise CursorCopyError(
                "project selector matched multiple Cursor agent-transcript projects; "
                "use a more specific --workspace value"
            )
        return None
    slug = project_slug_from_path(cwd)
    exact = cursor_projects_root() / slug
    if exact.is_dir() and (exact / "agent-transcripts").is_dir():
        return exact
    cwd_parts = [p for p in cwd.resolve().as_posix().split("/") if p]
    best: Optional[Tuple[int, pathlib.Path]] = None
    for project_dir, name in projects:
        score = 0
        pos = 0
        for part in cwd_parts:
            idx = name.find(part, pos)
            if idx < 0:
                score = -1
                break
            score += len(part)
            pos = idx + len(part)
        if score >= 0 and (best is None or score > best[0]):
            best = (score, project_dir)
    return best[1] if best else None


def list_agent_transcript_files(project_dir: pathlib.Path) -> List[Tuple[float, pathlib.Path, str]]:
    at_root = project_dir / "agent-transcripts"
    if not at_root.is_dir():
        return []
    rows: List[Tuple[float, pathlib.Path, str]] = []
    for session_dir in at_root.iterdir():
        if not session_dir.is_dir():
            continue
        main = session_dir / f"{session_dir.name}.jsonl"
        if main.is_file():
            rows.append((main.stat().st_mtime, main, session_dir.name))
    rows.sort(key=lambda row: row[0], reverse=True)
    return rows


def find_agent_transcript(
    cwd: pathlib.Path,
    workspace_selector: Optional[str],
    session_id: Optional[str],
    latest_global: bool,
) -> pathlib.Path:
    if session_id:
        if workspace_selector:
            project = match_cursor_project(cwd, workspace_selector)
            if project is None:
                raise CursorCopyError(f"no agent-transcript project matched: {workspace_selector}")
            candidate = project / "agent-transcripts" / session_id / f"{session_id}.jsonl"
            if candidate.is_file():
                return candidate
        root = cursor_projects_root()
        for path in root.glob(f"*/agent-transcripts/{session_id}/{session_id}.jsonl"):
            if path.is_file():
                return path
        raise CursorCopyError(f"agent transcript not found for session id: {session_id}")

    if latest_global:
        best: Optional[Tuple[float, pathlib.Path]] = None
        for project_dir, _ in discover_cursor_projects():
            for mtime, path, _ in list_agent_transcript_files(project_dir):
                if best is None or mtime > best[0]:
                    best = (mtime, path)
        if best is None:
            raise CursorCopyError("no agent transcripts found under ~/.cursor/projects")
        return best[1]

    project = match_cursor_project(cwd, workspace_selector)
    if project is None:
        raise CursorCopyError(
            "no ~/.cursor/projects entry matches this cwd; use --latest or --workspace <project-slug>"
        )
    transcripts = list_agent_transcript_files(project)
    if not transcripts:
        raise CursorCopyError(f"no agent transcripts found for project {project.name}")
    return transcripts[0][1]


def extract_message_text(row: Dict[str, Any]) -> str:
    message = row.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n\n".join(parts).strip()


def parse_agent_transcript_last_turn(path: pathlib.Path) -> Tuple[Message, Message]:
    pending_user: Optional[Message] = None
    pending_assistant: List[str] = []
    completed: List[Tuple[Message, Message]] = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        row = parse_json_value(line)
        if not isinstance(row, dict):
            continue
        role = row.get("role")
        text = extract_message_text(row)
        if not text:
            continue
        if role == ROLE_USER:
            if pending_user and pending_assistant:
                completed.append(
                    (
                        pending_user,
                        Message(role=ROLE_ASSISTANT, text="\n\n".join(pending_assistant)),
                    )
                )
            pending_user = Message(role=ROLE_USER, text=text)
            pending_assistant = []
        elif role == ROLE_ASSISTANT:
            pending_assistant.append(text)

    if pending_user and pending_assistant:
        completed.append(
            (
                pending_user,
                Message(role=ROLE_ASSISTANT, text="\n\n".join(pending_assistant)),
            )
        )

    if not completed:
        raise CursorCopyError(f"no complete user/assistant turn found in agent transcript: {path}")
    return completed[-1]


def build_last_turn_from_transcript(
    cwd: pathlib.Path,
    workspace_selector: Optional[str],
    session_id: Optional[str],
    latest_global: bool,
) -> LastTurn:
    transcript = find_agent_transcript(cwd, workspace_selector, session_id, latest_global)
    user_msg, assistant_msg = parse_agent_transcript_last_turn(transcript)
    session_id = transcript.parent.name
    project_dir = transcript.parents[2]
    return LastTurn(
        composer_id=session_id,
        conversation_name=session_id,
        workspace_id=project_dir.name,
        workspace_path=str(project_dir),
        user=user_msg,
        assistant=assistant_msg,
        source=SOURCE_TRANSCRIPT,
        transcript_path=str(transcript),
    )
