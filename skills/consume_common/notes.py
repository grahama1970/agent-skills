"""HorusNotesManager - Manages Horus notes on consumed content."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class HorusNotesManager:
    """Manages notes that Horus (or other agents) take on content."""

    def __init__(self, notes_dir: Path | str):
        """Initialize the notes manager.

        Args:
            notes_dir: Directory to store notes (per-agent subdirs created automatically)
        """
        self.notes_dir = Path(notes_dir)
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def _get_notes_path(self, agent_id: str) -> Path:
        """Get the notes file path for an agent."""
        agent_dir = self.notes_dir / agent_id
        agent_dir.mkdir(exist_ok=True)
        return agent_dir / "notes.jsonl"

    def add_note(
        self,
        content_type: str,
        content_id: str,
        agent_id: str,
        position: dict[str, Any],
        note: str,
        tags: Optional[list[str]] = None,
        emotional_reaction: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Add a note to content.

        Args:
            content_type: Type of content (movie, book, youtube)
            content_id: Content identifier
            agent_id: Agent taking the note (e.g., "horus_lupercal")
            position: Position dict with type, value, context
            note: The note text
            tags: Optional list of tags
            emotional_reaction: Optional emotional response dict

        Returns:
            The created note dict
        """
        note_id = str(uuid.uuid4())
        note_entry = {
            "note_id": note_id,
            "content_type": content_type,
            "content_id": content_id,
            "agent_id": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "position": position,
            "note": note,
            "tags": tags or [],
            "emotional_reaction": emotional_reaction
        }

        notes_path = self._get_notes_path(agent_id)
        with open(notes_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(note_entry, default=str) + "\n")

        return note_entry

    def get_note(self, note_id: str, agent_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Get a specific note by ID.

        Args:
            note_id: Note identifier
            agent_id: Optional agent ID to narrow search

        Returns:
            Note dict or None if not found
        """
        if agent_id:
            # Search in specific agent's notes
            notes_path = self._get_notes_path(agent_id)
            if not notes_path.exists():
                return None
            with open(notes_path, "r", encoding="utf-8") as f:
                for line in f:
                    note = json.loads(line.strip())
                    if note.get("note_id") == note_id:
                        return note
        else:
            # Search all agents
            for agent_dir in self.notes_dir.iterdir():
                if agent_dir.is_dir():
                    notes_path = agent_dir / "notes.jsonl"
                    if notes_path.exists():
                        with open(notes_path, "r", encoding="utf-8") as f:
                            for line in f:
                                note = json.loads(line.strip())
                                if note.get("note_id") == note_id:
                                    return note
        return None

    def list_notes(
        self,
        content_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        tags: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """List notes with optional filtering.

        Args:
            content_id: Filter by content ID
            agent_id: Filter by agent ID
            tags: Filter by tags (all must match)

        Returns:
            List of note dicts
        """
        results = []
        tags = set(tags or [])

        # Determine which agent dirs to search
        if agent_id:
            agent_dirs = [self.notes_dir / agent_id] if (self.notes_dir / agent_id).exists() else []
        else:
            agent_dirs = [d for d in self.notes_dir.iterdir() if d.is_dir()]

        for agent_dir in agent_dirs:
            notes_path = agent_dir / "notes.jsonl"
            if not notes_path.exists():
                continue

            with open(notes_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        note = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue

                    # Apply filters
                    if content_id and note.get("content_id") != content_id:
                        continue
                    if tags and not tags.issubset(set(note.get("tags", []))):
                        continue

                    results.append(note)

        return sorted(results, key=lambda n: n.get("timestamp", ""), reverse=True)

    def update_note(self, note_id: str, updates: dict[str, Any], agent_id: Optional[str] = None) -> bool:
        """Update a note.

        Args:
            note_id: Note identifier
            updates: Dict of fields to update
            agent_id: Optional agent ID to narrow search

        Returns:
            True if updated, False if not found
        """
        # Find the note first
        target_agent = agent_id
        if not target_agent:
            note = self.get_note(note_id)
            if not note:
                return False
            target_agent = note.get("agent_id")

        if not target_agent:
            return False

        notes_path = self._get_notes_path(target_agent)
        if not notes_path.exists():
            return False

        # Read all notes, update target, write back
        updated = False
        temp_path = notes_path.with_suffix(".tmp")

        with open(notes_path, "r", encoding="utf-8") as f_in, \
             open(temp_path, "w", encoding="utf-8") as f_out:
            for line in f_in:
                if not line.strip():
                    continue
                try:
                    note = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                if note.get("note_id") == note_id:
                    note.update(updates)
                    updated = True

                f_out.write(json.dumps(note, default=str) + "\n")

        if updated:
            temp_path.replace(notes_path)

        return updated

    def delete_note(self, note_id: str, agent_id: Optional[str] = None) -> bool:
        """Delete a note.

        Args:
            note_id: Note identifier
            agent_id: Optional agent ID to narrow search

        Returns:
            True if deleted, False if not found
        """
        # Find the note first
        target_agent = agent_id
        if not target_agent:
            note = self.get_note(note_id)
            if not note:
                return False
            target_agent = note.get("agent_id")

        if not target_agent:
            return False

        notes_path = self._get_notes_path(target_agent)
        if not notes_path.exists():
            return False

        # Read all notes, skip target, write back
        deleted = False
        temp_path = notes_path.with_suffix(".tmp")

        with open(notes_path, "r", encoding="utf-8") as f_in, \
             open(temp_path, "w", encoding="utf-8") as f_out:
            for line in f_in:
                if not line.strip():
                    continue
                try:
                    note = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                if note.get("note_id") == note_id:
                    deleted = True
                    continue

                f_out.write(json.dumps(note, default=str) + "\n")

        if deleted:
            temp_path.replace(notes_path)

        return deleted
