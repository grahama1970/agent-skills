#!/usr/bin/env python3
"""Sanity test for srt library - subtitle parsing."""
import tempfile
import os


def test_srt_parse():
    """Test that srt library can parse subtitle files."""
    try:
        import srt
    except ImportError:
        print("FAIL: srt library not installed")
        print("Install with: pip install srt")
        return False

    # Create a sample SRT file
    sample_srt = """1
00:00:01,000 --> 00:00:04,000
First subtitle line

2
00:00:05,000 --> 00:00:08,000
Second subtitle line
with multiple lines

3
00:00:10,000 --> 00:00:12,000
Third subtitle
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
        f.write(sample_srt)
        temp_path = f.name

    try:
        # Parse the SRT file
        with open(temp_path, 'r', encoding='utf-8') as f:
            content = f.read()

        subtitles = list(srt.parse(content))

        # Verify we got the expected subtitles
        assert len(subtitles) == 3, f"Expected 3 subtitles, got {len(subtitles)}"

        # Verify first subtitle
        sub1 = subtitles[0]
        assert sub1.index == 1, f"Expected index 1, got {sub1.index}"
        assert "First subtitle line" in sub1.content, f"Unexpected content: {sub1.content}"

        # Verify timing
        assert sub1.start.total_seconds() == 1.0, f"Expected start 1.0s, got {sub1.start.total_seconds()}"
        assert sub1.end.total_seconds() == 4.0, f"Expected end 4.0s, got {sub1.end.total_seconds()}"

        print(f"PASS: Parsed {len(subtitles)} subtitles correctly")
        print(f"  - Subtitle 1: {sub1.start} -> {sub1.end}: {sub1.content[:30]}...")
        return True

    except Exception as e:
        print(f"FAIL: Error parsing SRT: {e}")
        return False
    finally:
        os.unlink(temp_path)


if __name__ == "__main__":
    success = test_srt_parse()
    exit(0 if success else 1)
