"""ContentRegistry - Manages registry of consumed content."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class ContentRegistry:
    """Manages a registry of ingested content (movies, books, videos)."""

    def __init__(self, registry_path: Path | str):
        """Initialize the registry.

        Args:
            registry_path: Path to the registry JSON file
        """
        self.registry_path = Path(registry_path)
        self._data: dict[str, Any] = {"contents": {}, "metadata": {}}
        self._load()

    def _load(self) -> None:
        """Load registry from disk."""
        if self.registry_path.exists():
            with open(self.registry_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            self._save()

    def _save(self) -> None:
        """Save registry to disk."""
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, default=str)

    def add_content(self, content: dict[str, Any]) -> str:
        """Add content to the registry.

        Args:
            content: Content metadata dict

        Returns:
            content_id: Unique identifier for the content
        """
        content_id = str(uuid.uuid4())
        content["content_id"] = content_id
        content["ingested_at"] = datetime.now(timezone.utc).isoformat()
        content["consume_count"] = 0
        content["last_consumed"] = None

        self._data["contents"][content_id] = content
        self._save()
        return content_id

    def get_content(self, content_id: str) -> Optional[dict[str, Any]]:
        """Get content by ID.

        Args:
            content_id: Content identifier

        Returns:
            Content dict or None if not found
        """
        return self._data["contents"].get(content_id)

    def update_content(self, content_id: str, updates: dict[str, Any]) -> bool:
        """Update content metadata.

        Args:
            content_id: Content identifier
            updates: Dict of fields to update

        Returns:
            True if updated, False if not found
        """
        if content_id not in self._data["contents"]:
            return False

        self._data["contents"][content_id].update(updates)
        self._save()
        return True

    def delete_content(self, content_id: str) -> bool:
        """Delete content from registry.

        Args:
            content_id: Content identifier

        Returns:
            True if deleted, False if not found
        """
        if content_id not in self._data["contents"]:
            return False

        del self._data["contents"][content_id]
        self._save()
        return True

    def list_content(self, content_type: Optional[str] = None) -> list[dict[str, Any]]:
        """List all content, optionally filtered by type.

        Args:
            content_type: Filter by content type (movie, book, youtube)

        Returns:
            List of content dicts
        """
        contents = list(self._data["contents"].values())
        if content_type:
            contents = [c for c in contents if c.get("type") == content_type]
        return contents

    def record_consumption(
        self,
        content_id: str,
        duration: Optional[float] = None,
        notes: Optional[list[str]] = None
    ) -> bool:
        """Record a consumption event.

        Args:
            content_id: Content identifier
            duration: Duration consumed (seconds for video, chars for text)
            notes: List of note IDs added during this session

        Returns:
            True if recorded, False if content not found
        """
        if content_id not in self._data["contents"]:
            return False

        content = self._data["contents"][content_id]
        content["consume_count"] = content.get("consume_count", 0) + 1
        content["last_consumed"] = datetime.now(timezone.utc).isoformat()

        if duration is not None:
            content["last_duration"] = duration

        if notes:
            content["note_ids"] = content.get("note_ids", []) + notes

        self._save()
        return True

    def search_content(self, query: str) -> list[dict[str, Any]]:
        """Search content by title or metadata.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching content dicts
        """
        query = query.lower()
        results = []
        for content in self._data["contents"].values():
            if query in content.get("title", "").lower():
                results.append(content)
            elif any(query in str(v).lower() for v in content.get("metadata", {}).values()):
                results.append(content)
        return results
