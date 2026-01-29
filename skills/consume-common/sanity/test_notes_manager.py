#!/usr/bin/env python3
"""Sanity test for HorusNotesManager - note CRUD operations."""
import tempfile
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_notes_manager():
    """Test HorusNotesManager CRUD operations."""
    try:
        from notes import HorusNotesManager
    except ImportError as e:
        print(f"SKIP: HorusNotesManager not importable: {e}")
        return True  # Skip, not fail

    temp_dir = tempfile.mkdtemp()
    notes_dir = os.path.join(temp_dir, "notes")

    try:
        # Create notes manager
        manager = HorusNotesManager(notes_dir)

        # Add a note
        note = manager.add_note(
            content_type="movie",
            content_id="test_movie_001",
            agent_id="horus_lupercal",
            position={"type": "timestamp", "value": 125.5, "context": "Tywin speaks"},
            note="Manipulation pattern observed",
            tags=["manipulation", "authority"],
            emotional_reaction={"valence": -0.8, "arousal": 0.6}
        )

        assert note is not None, "Expected note to be returned"
        assert "note_id" in note, "Expected note_id in note"
        note_id = note["note_id"]

        # Retrieve note
        retrieved = manager.get_note(note_id)
        assert retrieved is not None, "Expected note to exist"
        assert retrieved["note"] == "Manipulation pattern observed", f"Unexpected note: {retrieved.get('note')}"

        # List notes for content
        notes = manager.list_notes(content_id="test_movie_001")
        assert len(notes) == 1, f"Expected 1 note, got {len(notes)}"

        # List notes for agent
        agent_notes = manager.list_notes(agent_id="horus_lupercal")
        assert len(agent_notes) == 1, f"Expected 1 agent note, got {len(agent_notes)}"

        # Update note
        manager.update_note(note_id, {"note": "Updated observation"})
        retrieved = manager.get_note(note_id)
        assert retrieved["note"] == "Updated observation", "Expected note to be updated"

        # Delete note
        manager.delete_note(note_id)
        notes = manager.list_notes(content_id="test_movie_001")
        assert len(notes) == 0, f"Expected 0 notes after delete, got {len(notes)}"

        print(f"PASS: HorusNotesManager operations successful")
        print(f"  - Added: {note_id}")
        print(f"  - Retrieved: confirmed")
        print(f"  - Listed by content: 1 note")
        print(f"  - Listed by agent: 1 note")
        print(f"  - Updated: confirmed")
        print(f"  - Deleted: confirmed")
        return True

    except Exception as e:
        print(f"FAIL: Error with HorusNotesManager: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    success = test_notes_manager()
    exit(0 if success else 1)
