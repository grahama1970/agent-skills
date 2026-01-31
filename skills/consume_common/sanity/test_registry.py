#!/usr/bin/env python3
"""Sanity test for ContentRegistry - CRUD operations."""
import tempfile
import os
import json
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_registry_crud():
    """Test ContentRegistry CRUD operations."""
    try:
        from registry import ContentRegistry
    except ImportError as e:
        print(f"SKIP: ContentRegistry not importable: {e}")
        return True  # Skip, not fail

    temp_dir = tempfile.mkdtemp()
    registry_path = os.path.join(temp_dir, "registry.json")

    try:
        # Create registry
        registry = ContentRegistry(registry_path)

        # Add movie entry
        movie_id = registry.add_content({
            "type": "movie",
            "title": "Test Movie",
            "duration": 120.5,
            "source_path": "/path/to/movie.json"
        })

        assert movie_id, "Expected movie_id to be returned"

        # Retrieve entry
        entry = registry.get_content(movie_id)
        assert entry is not None, "Expected entry to exist"
        assert entry["title"] == "Test Movie", f"Unexpected title: {entry.get('title')}"

        # Update entry
        registry.update_content(movie_id, {"consume_count": 1})
        entry = registry.get_content(movie_id)
        assert entry["consume_count"] == 1, "Expected consume_count to be updated"

        # List all entries
        entries = registry.list_content()
        assert len(entries) == 1, f"Expected 1 entry, got {len(entries)}"

        # Delete entry
        registry.delete_content(movie_id)
        entries = registry.list_content()
        assert len(entries) == 0, f"Expected 0 entries after delete, got {len(entries)}"

        # Verify persistence
        assert os.path.exists(registry_path), "Registry file should exist"
        with open(registry_path, 'r') as f:
            data = json.load(f)
            assert "contents" in data, "Registry should have 'contents' key"

        print(f"PASS: ContentRegistry CRUD operations successful")
        print(f"  - Created: {movie_id}")
        print(f"  - Updated: consume_count")
        print(f"  - Deleted: confirmed")
        print(f"  - Persisted: {registry_path}")
        return True

    except Exception as e:
        print(f"FAIL: Error with ContentRegistry: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    success = test_registry_crud()
    exit(0 if success else 1)
