"""
Tests for ingest-yt-history skill.

Test files are stubs created before implementation per orchestrate protocol.
Tests are marked as skip until implementation, then converted to real assertions.
"""
import io
import json
from pathlib import Path

import pytest

from src.ingest import (
    detect_music_service,
    extract_video_id,
    parse_takeout,
    parse_takeout_entry,
    strip_watched_prefix,
)
from src.find_music import find_music, MOOD_MAPPINGS

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_TAKEOUT = FIXTURES_DIR / "sample_watch_history.json"
SAMPLE_MUSIC_HISTORY = FIXTURES_DIR / "sample_music_history.jsonl"


class TestTakeoutParser:
    """Task 1: Takeout JSON Parser"""

    def test_parse_takeout_json(self):
        """Parse sample Takeout JSON, outputs valid JSONL with video_id, title, ts, url."""
        # Verify fixture exists
        assert SAMPLE_TAKEOUT.exists(), f"Fixture not found: {SAMPLE_TAKEOUT}"

        # Parse and collect results
        entries = list(parse_takeout(SAMPLE_TAKEOUT))

        # Should have parsed all 5 entries from sample
        assert len(entries) == 5

        # Check first entry (Rick Astley)
        first = entries[0]
        assert first["video_id"] == "dQw4w9WgXcQ"
        assert first["title"] == "Never Gonna Give You Up"  # "Watched " prefix stripped
        assert first["ts"] == "2025-01-15T14:30:00.000Z"
        assert first["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert first["products"] == ["YouTube"]

        # Check second entry (YouTube Music)
        second = entries[1]
        assert second["video_id"] == "CD-E-LDc384"
        assert second["title"] == "Enter Sandman"  # "Watched " prefix stripped
        assert second["products"] == ["YouTube Music"]

        # Verify all entries have required fields
        for entry in entries:
            assert "video_id" in entry
            assert "title" in entry
            assert "ts" in entry
            assert "url" in entry
            assert "products" in entry

    def test_parse_takeout_jsonl_output(self):
        """Verify JSONL output format is valid."""
        output = io.StringIO()
        entries = list(parse_takeout(SAMPLE_TAKEOUT, output))

        # Rewind and read output
        output.seek(0)
        lines = output.readlines()

        # Should have same number of lines as entries
        assert len(lines) == len(entries)

        # Each line should be valid JSON
        for line in lines:
            parsed = json.loads(line.strip())
            assert "video_id" in parsed
            assert "title" in parsed

    def test_extract_video_id(self):
        """Test video ID extraction from various URL formats."""
        # Standard YouTube URL
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

        # YouTube Music URL
        assert extract_video_id("https://music.youtube.com/watch?v=CD-E-LDc384") == "CD-E-LDc384"

        # URL with extra parameters
        assert extract_video_id("https://www.youtube.com/watch?v=abc123&t=60") == "abc123"

        # Invalid URLs
        assert extract_video_id("") is None
        assert extract_video_id("https://www.youtube.com/") is None

    def test_strip_watched_prefix(self):
        """Test stripping 'Watched ' prefix from titles."""
        assert strip_watched_prefix("Watched Never Gonna Give You Up") == "Never Gonna Give You Up"
        assert strip_watched_prefix("Never Gonna Give You Up") == "Never Gonna Give You Up"
        assert strip_watched_prefix("Watched ") == ""

    def test_parse_takeout_entry_skips_deleted(self):
        """Entries without titleUrl (deleted videos) should be skipped."""
        # Entry with no titleUrl
        entry = {
            "header": "YouTube",
            "title": "Watched Deleted Video",
            "time": "2025-01-15T00:00:00.000Z",
            "products": ["YouTube"],
        }
        assert parse_takeout_entry(entry) is None

        # Entry with empty titleUrl
        entry["titleUrl"] = ""
        assert parse_takeout_entry(entry) is None


class TestMusicServiceDetection:
    """Task 2: YouTube vs YouTube Music Detection"""

    def test_detect_music_service(self):
        """Correctly identifies music.youtube.com URLs, VEVO channels, ' - Topic' channels."""
        # Test music.youtube.com URL detection
        result = detect_music_service("https://music.youtube.com/watch?v=CD-E-LDc384")
        assert result["service"] == "youtube_music"
        assert result["is_music"] is True
        assert result["detection_method"] == "url"

        # Test regular YouTube URL (not music)
        result = detect_music_service("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result["service"] == "youtube"
        assert result["is_music"] is False

        # Test VEVO channel detection
        result = detect_music_service(
            "https://www.youtube.com/watch?v=abc123",
            channel_name="ChelseaWolfeVEVO",
        )
        assert result["service"] == "youtube_music"
        assert result["is_music"] is True
        assert result["detection_method"] == "channel"

        # Test " - Topic" channel detection
        result = detect_music_service(
            "https://www.youtube.com/watch?v=abc123",
            channel_name="Chelsea Wolfe - Topic",
        )
        assert result["service"] == "youtube_music"
        assert result["is_music"] is True
        assert result["detection_method"] == "channel"

        # Test title-based detection
        result = detect_music_service(
            "https://www.youtube.com/watch?v=abc123",
            title="Song Name (Official Audio)",
        )
        assert result["service"] == "youtube_music"
        assert result["is_music"] is True
        assert result["detection_method"] == "title"

        result = detect_music_service(
            "https://www.youtube.com/watch?v=abc123",
            title="Artist - Song (Official Music Video)",
        )
        assert result["service"] == "youtube_music"
        assert result["is_music"] is True
        assert result["detection_method"] == "title"

        # Test category-based detection (category 10 = Music)
        result = detect_music_service(
            "https://www.youtube.com/watch?v=abc123",
            category_id=10,
        )
        assert result["service"] == "youtube_music"
        assert result["is_music"] is True
        assert result["detection_method"] == "category"

        # Test non-music category
        result = detect_music_service(
            "https://www.youtube.com/watch?v=abc123",
            category_id=22,  # People & Blogs
        )
        assert result["service"] == "youtube"
        assert result["is_music"] is False

    def test_detect_vevo_channel(self):
        """VEVO channels are correctly identified as music."""
        # Various VEVO channel name formats
        vevo_channels = [
            "ChelseaWolfeVEVO",
            "MetallicaVEVO",
            "TaylorSwiftVEVO",
            "ArtistNameVevo",  # lowercase 'evo'
        ]

        for channel in vevo_channels:
            result = detect_music_service(
                "https://www.youtube.com/watch?v=test123",
                channel_name=channel,
            )
            assert result["is_music"] is True, f"Failed for channel: {channel}"
            assert result["service"] == "youtube_music"
            assert result["detection_method"] == "channel"

        # Non-VEVO channel should not be detected as music
        result = detect_music_service(
            "https://www.youtube.com/watch?v=test123",
            channel_name="TechReviews",
        )
        assert result["is_music"] is False

    def test_detect_topic_channel(self):
        """' - Topic' suffix channels are correctly identified as music."""
        # Auto-generated artist topic channels
        topic_channels = [
            "Chelsea Wolfe - Topic",
            "Metallica - Topic",
            "Taylor Swift - Topic",
            "Classical Music - Topic",
        ]

        for channel in topic_channels:
            result = detect_music_service(
                "https://www.youtube.com/watch?v=test123",
                channel_name=channel,
            )
            assert result["is_music"] is True, f"Failed for channel: {channel}"
            assert result["service"] == "youtube_music"
            assert result["detection_method"] == "channel"

        # Similar but not " - Topic" suffix
        result = detect_music_service(
            "https://www.youtube.com/watch?v=test123",
            channel_name="Topic Discussion Channel",
        )
        assert result["is_music"] is False


class TestYouTubeAPIEnrichment:
    """Task 3: YouTube API Enrichment"""

    @pytest.mark.integration
    def test_enrich_with_youtube_api(self):
        """Adds duration_seconds, category, tags to entries (requires YOUTUBE_API_KEY).

        This is an integration test that calls the real YouTube Data API.
        Requires YOUTUBE_API_KEY environment variable to be set.
        """
        import os

        from src.enrich import enrich_entries, load_env

        # Load env to get API key
        load_env()

        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            pytest.skip("YOUTUBE_API_KEY not set - skipping integration test")

        # Create test entries with known video IDs
        # Using Rick Astley - Never Gonna Give You Up (dQw4w9WgXcQ) as stable test video
        test_entries = [
            {
                "video_id": "dQw4w9WgXcQ",
                "title": "Never Gonna Give You Up",
                "ts": "2025-01-15T14:30:00.000Z",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "products": ["YouTube"],
            },
        ]

        # Enrich entries
        enriched = list(enrich_entries(test_entries, api_key=api_key))

        # Should have same number of entries
        assert len(enriched) == 1

        entry = enriched[0]

        # Check enrichment fields are present
        assert "duration_seconds" in entry, "Missing duration_seconds"
        assert "category_id" in entry, "Missing category_id"
        assert "category_name" in entry, "Missing category_name"
        assert "tags" in entry, "Missing tags"
        assert "channel_id" in entry, "Missing channel_id"
        assert "channel_title" in entry, "Missing channel_title"

        # Verify duration is reasonable (Never Gonna Give You Up is ~3:33 = 213 seconds)
        assert entry["duration_seconds"] > 200, "Duration too short"
        assert entry["duration_seconds"] < 250, "Duration too long"

        # Verify category is Music (10)
        assert entry["category_id"] == "10", f"Expected Music category (10), got {entry['category_id']}"
        assert entry["category_name"] == "Music"

        # Verify tags exist (famous video has many tags)
        assert isinstance(entry["tags"], list)
        assert len(entry["tags"]) > 0, "Expected video to have tags"

        # Verify channel info
        assert entry["channel_id"], "Missing channel_id value"
        assert "Rick Astley" in entry["channel_title"], f"Unexpected channel: {entry['channel_title']}"

    def test_enrich_without_api_key_returns_unenriched(self):
        """When API key is missing, entries are returned unenriched."""
        from src.enrich import enrich_entries

        test_entries = [
            {
                "video_id": "dQw4w9WgXcQ",
                "title": "Test Video",
                "ts": "2025-01-15T00:00:00.000Z",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "products": ["YouTube"],
            },
        ]

        # Pass empty API key explicitly
        enriched = list(enrich_entries(test_entries, api_key=""))

        # Should return entries unchanged (no enrichment fields added)
        assert len(enriched) == 1
        entry = enriched[0]
        assert entry["video_id"] == "dQw4w9WgXcQ"
        assert entry["title"] == "Test Video"
        # Should NOT have enrichment fields since no API key
        assert "duration_seconds" not in entry

    def test_parse_duration(self):
        """Test ISO 8601 duration parsing."""
        from src.enrich import parse_duration

        # Standard durations
        assert parse_duration("PT1H2M3S") == 3723  # 1h 2m 3s
        assert parse_duration("PT5M30S") == 330  # 5m 30s
        assert parse_duration("PT45S") == 45  # 45s
        assert parse_duration("PT1H") == 3600  # 1h
        assert parse_duration("PT10M") == 600  # 10m

        # Edge cases
        assert parse_duration("") == 0
        assert parse_duration("P1D") == 0  # Days not supported (prefix is PT not P)
        assert parse_duration(None) == 0


class TestFindMusicCommand:
    """Task 4: Find-Music Command (Horus Primary Interface)"""

    def test_find_music_command(self):
        """./run.sh find-music --mood melancholic returns Chelsea Wolfe, Daughter."""
        # Verify fixture exists
        assert SAMPLE_MUSIC_HISTORY.exists(), f"Fixture not found: {SAMPLE_MUSIC_HISTORY}"

        # Search for melancholic mood
        results = find_music(SAMPLE_MUSIC_HISTORY, mood="melancholic")

        # Should find matches
        assert len(results) > 0, "Should find melancholic matches"

        # Extract artist names from results
        artists = {r.get("artist", "").lower() for r in results}
        channels = {r.get("channel", "").lower() for r in results}
        all_artists = artists | channels

        # Should include Chelsea Wolfe and Daughter
        assert any("chelsea wolfe" in a for a in all_artists), \
            f"Chelsea Wolfe not found in results: {all_artists}"
        assert any("daughter" in a for a in all_artists), \
            f"Daughter not found in results: {all_artists}"

    def test_find_music_by_mood_epic(self):
        """find_music with mood=epic returns Sabaton, Two Steps From Hell."""
        results = find_music(SAMPLE_MUSIC_HISTORY, mood="epic")

        assert len(results) > 0, "Should find epic matches"

        # Extract all text for matching
        all_text = " ".join(
            f"{r.get('artist', '')} {r.get('channel', '')} {r.get('title', '')}"
            for r in results
        ).lower()

        assert "sabaton" in all_text, f"Sabaton not found in results"
        assert "two steps from hell" in all_text, f"Two Steps From Hell not found in results"

    def test_find_music_by_mood_atmospheric(self):
        """find_music with mood=atmospheric returns ambient/post-rock artists."""
        results = find_music(SAMPLE_MUSIC_HISTORY, mood="atmospheric")

        assert len(results) > 0, "Should find atmospheric matches"

        # Check that we found ambient/atmospheric entries
        all_tags = []
        for r in results:
            all_tags.extend(r.get("tags", []))
        all_tags_lower = [t.lower() for t in all_tags]

        has_atmospheric = any(
            tag in ["ambient", "atmospheric", "drone", "post-rock"]
            for tag in all_tags_lower
        )
        assert has_atmospheric, f"No atmospheric tags found in results: {all_tags_lower}"

    def test_find_music_by_artist(self):
        """find_music with artist filter returns matching entries."""
        results = find_music(SAMPLE_MUSIC_HISTORY, artist="Chelsea Wolfe")

        assert len(results) > 0, "Should find Chelsea Wolfe entries"

        # First result should be Chelsea Wolfe
        first = results[0]
        assert first.get("artist", "").lower() == "chelsea wolfe"

    def test_find_music_by_genre(self):
        """./run.sh find-music --genre doom_metal returns relevant artists."""
        results = find_music(SAMPLE_MUSIC_HISTORY, genre="doom metal")

        assert len(results) > 0, "Should find doom metal matches"

        # Check that doom metal tagged entries are returned
        all_tags = []
        for r in results:
            all_tags.extend(r.get("tags", []))
        all_tags_lower = " ".join(all_tags).lower()

        assert "doom" in all_tags_lower, f"No doom metal found in tags: {all_tags_lower}"

    def test_find_music_free_text_query(self):
        """find_music with free text query searches across fields."""
        results = find_music(SAMPLE_MUSIC_HISTORY, query="orchestral")

        assert len(results) > 0, "Should find orchestral matches"

    def test_find_music_limit(self):
        """find_music respects limit parameter."""
        results = find_music(SAMPLE_MUSIC_HISTORY, mood="melancholic", limit=2)

        assert len(results) <= 2, "Should respect limit"

    def test_find_music_no_matches(self):
        """find_music returns empty list when no matches."""
        results = find_music(SAMPLE_MUSIC_HISTORY, query="xyznonexistent123")

        assert len(results) == 0, "Should return empty list for no matches"

    def test_find_music_file_not_found(self):
        """find_music raises error for missing file."""
        with pytest.raises(FileNotFoundError):
            find_music("/nonexistent/path/history.jsonl", mood="melancholic")

    def test_mood_mappings_exist(self):
        """Verify MOOD_MAPPINGS contains expected keys."""
        assert "melancholic" in MOOD_MAPPINGS
        assert "epic" in MOOD_MAPPINGS
        assert "atmospheric" in MOOD_MAPPINGS

        # Verify melancholic contains expected keywords
        melancholic_keywords = MOOD_MAPPINGS["melancholic"]
        assert "chelsea wolfe" in melancholic_keywords
        assert "daughter" in melancholic_keywords
        assert "phoebe bridgers" in melancholic_keywords

        # Verify epic contains expected keywords
        epic_keywords = MOOD_MAPPINGS["epic"]
        assert "sabaton" in epic_keywords
        assert "two steps from hell" in epic_keywords

        # Verify atmospheric contains expected keywords
        atmospheric_keywords = MOOD_MAPPINGS["atmospheric"]
        assert "ambient" in atmospheric_keywords
        assert "post-rock" in atmospheric_keywords


class TestMonitorIntegration:
    """Task 5: task-monitor Integration"""

    def test_monitor_integration(self, tmp_path):
        """Writes to .batch_state.json, progress visible in task-monitor."""
        from src.monitor import BatchProgress

        # Create a BatchProgress tracker
        progress = BatchProgress(output_dir=tmp_path, total=100)

        # Verify state file was created
        state_file = tmp_path / ".batch_state.json"
        assert state_file.exists(), "State file should be created on init"

        # Read and verify initial state
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        assert state["completed"] == 0
        assert state["total"] == 100
        assert state["progress_pct"] == 0.0
        assert state["status"] == "running"
        assert "elapsed_seconds" in state
        assert state["stats"] == {"success": 0, "failed": 0, "skipped": 0}

    def test_batch_progress_updates(self, tmp_path):
        """Test that BatchProgress correctly updates state."""
        from src.monitor import BatchProgress

        progress = BatchProgress(output_dir=tmp_path, total=10)
        state_file = tmp_path / ".batch_state.json"

        # Record some successes
        progress.set_processing("video dQw4w9WgXcQ")
        progress.record_success("video dQw4w9WgXcQ")
        progress.record_success("video abc123")
        progress.record_failure("video failed1")
        progress.record_skip("video skipped1")

        # Read updated state
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        assert state["completed"] == 4
        assert state["total"] == 10
        assert state["progress_pct"] == 40.0
        assert state["stats"]["success"] == 2
        assert state["stats"]["failed"] == 1
        assert state["stats"]["skipped"] == 1
        assert state["status"] == "running"

    def test_batch_progress_complete(self, tmp_path):
        """Test batch completion state."""
        from src.monitor import BatchProgress

        progress = BatchProgress(output_dir=tmp_path, total=5)
        state_file = tmp_path / ".batch_state.json"

        # Process all items
        for i in range(5):
            progress.record_success(f"item_{i}")

        # Mark complete
        progress.complete()

        # Verify final state
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        assert state["completed"] == 5
        assert state["progress_pct"] == 100.0
        assert state["status"] == "completed"
        assert state["current_item"] == ""

    def test_batch_progress_atomic_write(self, tmp_path):
        """Test that writes are atomic (no temp files left behind)."""
        from src.monitor import BatchProgress

        progress = BatchProgress(output_dir=tmp_path, total=100)

        # Perform many updates
        for i in range(50):
            progress.record_success(f"item_{i}")

        # Check no temp files left behind
        temp_files = list(tmp_path.glob(".batch_state_*.tmp"))
        assert len(temp_files) == 0, f"Temp files should be cleaned up: {temp_files}"

        # State file should exist
        assert (tmp_path / ".batch_state.json").exists()

    def test_batch_progress_from_state_file(self, tmp_path):
        """Test loading existing progress from state file."""
        from src.monitor import BatchProgress

        # Create initial progress
        progress = BatchProgress(output_dir=tmp_path, total=100)
        progress.record_success("item_1")
        progress.record_success("item_2")
        progress.record_failure("item_3")

        # Load from state file
        state_file = tmp_path / ".batch_state.json"
        loaded = BatchProgress.from_state_file(state_file)

        assert loaded is not None
        assert loaded.completed == 3
        assert loaded.total == 100
        assert loaded.stats["success"] == 2
        assert loaded.stats["failed"] == 1

    def test_batch_progress_task_monitor_format(self, tmp_path):
        """Verify state file matches task-monitor expected format."""
        from src.monitor import BatchProgress

        progress = BatchProgress(output_dir=tmp_path, total=1000)
        progress.update(current_item="processing video dQw4w9WgXcQ")

        # Simulate some progress
        for _ in range(145):
            progress.update(increment_completed=True, result="success")
        for _ in range(3):
            progress.update(increment_completed=True, result="failed")
        for _ in range(2):
            progress.update(increment_completed=True, result="skipped")

        progress.update(current_item="processing video dQw4w9WgXcQ")

        # Read state
        with open(tmp_path / ".batch_state.json", encoding="utf-8") as f:
            state = json.load(f)

        # Verify task-monitor required fields
        assert "completed" in state and state["completed"] == 150
        assert "total" in state and state["total"] == 1000
        assert "current_item" in state
        assert "stats" in state
        assert state["stats"]["success"] == 145
        assert state["stats"]["failed"] == 3
        assert state["stats"]["skipped"] == 2
        assert "elapsed_seconds" in state
        assert "progress_pct" in state and state["progress_pct"] == 15.0
        assert "status" in state and state["status"] == "running"


class TestSyncMemory:
    """Task 7: Sync-Memory Command"""

    def test_sync_memory(self):
        """sync_to_memory creates memory-compatible entries with taxonomy fields."""
        from src.sync_memory import sync_to_memory

        # Use the sample music history fixture
        assert SAMPLE_MUSIC_HISTORY.exists(), f"Fixture not found: {SAMPLE_MUSIC_HISTORY}"

        # Sync to memory format
        entries = list(sync_to_memory(SAMPLE_MUSIC_HISTORY, music_only=False))

        # Should have entries
        assert len(entries) > 0, "Should produce memory entries"

        # Check first entry structure
        first = entries[0]

        # Required memory fields
        assert "problem" in first, "Missing problem field"
        assert "solution" in first, "Missing solution field"
        assert "category" in first, "Missing category field"
        assert "tags" in first, "Missing tags field"
        assert "bridge_attributes" in first, "Missing bridge_attributes field"
        assert "collection_tags" in first, "Missing collection_tags field"

        # Category should be "music"
        assert first["category"] == "music", f"Expected category 'music', got {first['category']}"

        # Problem should start with "Music: "
        assert first["problem"].startswith("Music: "), f"Problem should start with 'Music: ', got: {first['problem']}"

        # Tags should be a list
        assert isinstance(first["tags"], list), "Tags should be a list"

        # bridge_attributes should be a list
        assert isinstance(first["bridge_attributes"], list), "bridge_attributes should be a list"

        # collection_tags should be a dict
        assert isinstance(first["collection_tags"], dict), "collection_tags should be a dict"

    def test_sync_memory_format_entry(self):
        """format_memory_entry creates correct entry format."""
        from src.sync_memory import format_memory_entry

        entry = {
            "video_id": "test123",
            "title": "Carrion Flowers",
            "artist": "Chelsea Wolfe",
            "channel": "Chelsea Wolfe",
            "tags": ["doom", "dark folk", "haunting"],
            "products": ["YouTube Music"],
        }

        result = format_memory_entry(entry)

        # Check problem format
        assert result["problem"] == "Music: Chelsea Wolfe - Carrion Flowers"

        # Check category
        assert result["category"] == "music"

        # Check tags include artist name (normalized)
        assert "chelsea_wolfe" in result["tags"], f"Expected 'chelsea_wolfe' in tags, got: {result['tags']}"

        # Check tags include original tags (normalized)
        assert "doom" in result["tags"], f"Expected 'doom' in tags, got: {result['tags']}"
        assert "dark_folk" in result["tags"], f"Expected 'dark_folk' in tags, got: {result['tags']}"

    def test_sync_memory_extract_taxonomy(self):
        """extract_taxonomy extracts bridge_attributes and collection_tags."""
        from src.sync_memory import extract_taxonomy

        # Test with a melancholic entry
        entry = {
            "artist": "Daughter",
            "title": "Youth",
            "tags": ["indie folk", "melancholy", "acoustic"],
        }

        bridge_attributes, collection_tags = extract_taxonomy(entry)

        # Should have Fragility bridge (Daughter is a Fragility artist)
        assert "Fragility" in bridge_attributes, f"Expected Fragility in bridges, got: {bridge_attributes}"

        # Should have appropriate domain/thematic tags
        assert "domain" in collection_tags or "thematic_weight" in collection_tags

    def test_sync_memory_resilience_bridge(self):
        """Sabaton maps to Resilience bridge."""
        from src.sync_memory import extract_taxonomy

        entry = {
            "artist": "Sabaton",
            "title": "The Last Stand",
            "tags": ["power metal", "epic"],
        }

        bridge_attributes, collection_tags = extract_taxonomy(entry)

        assert "Resilience" in bridge_attributes, f"Expected Resilience in bridges, got: {bridge_attributes}"

    def test_sync_memory_transcendence_bridge(self):
        """Brian Eno maps to Transcendence bridge."""
        from src.sync_memory import extract_taxonomy

        entry = {
            "artist": "Brian Eno",
            "title": "An Ending (Ascent)",
            "tags": ["ambient", "drone"],
        }

        bridge_attributes, collection_tags = extract_taxonomy(entry)

        assert "Transcendence" in bridge_attributes, f"Expected Transcendence in bridges, got: {bridge_attributes}"

    def test_sync_memory_music_only_filter(self):
        """music_only=True filters out non-music entries."""
        from src.sync_memory import sync_to_memory

        # Sync with music_only=True (default)
        entries_music_only = list(sync_to_memory(SAMPLE_MUSIC_HISTORY, music_only=True))

        # Sync with music_only=False
        entries_all = list(sync_to_memory(SAMPLE_MUSIC_HISTORY, music_only=False))

        # music_only should produce fewer or equal entries
        assert len(entries_music_only) <= len(entries_all), \
            f"music_only should filter entries: {len(entries_music_only)} vs {len(entries_all)}"

    def test_sync_memory_jsonl_output(self, tmp_path):
        """sync_to_memory writes valid JSONL to output file."""
        from src.sync_memory import sync_to_memory

        output_file = tmp_path / "memory_entries.jsonl"

        with open(output_file, "w", encoding="utf-8") as f:
            entries = list(sync_to_memory(SAMPLE_MUSIC_HISTORY, output=f, music_only=False))

        # Verify output file exists and has content
        assert output_file.exists(), "Output file should exist"

        # Verify each line is valid JSON
        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == len(entries), "Output lines should match entries"

        for line in lines:
            parsed = json.loads(line.strip())
            assert "problem" in parsed
            assert "solution" in parsed
            assert "category" in parsed

    def test_sync_memory_file_not_found(self):
        """sync_to_memory raises error for missing file."""
        from src.sync_memory import sync_to_memory

        with pytest.raises(FileNotFoundError):
            list(sync_to_memory("/nonexistent/path/history.jsonl"))
