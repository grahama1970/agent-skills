import json
import tempfile
import unittest
from pathlib import Path

from extract_audiobook.cli import (
    build_chapter_plan,
    split_one,
    valid_jsonl,
    valid_text,
)


def _ffprobe_fixture() -> dict:
    return {
        "chapters": [
            {
                "id": 0,
                "start_time": "0.000000",
                "end_time": "10.000000",
                "tags": {"title": "Chapter 1"},
            },
            {
                "id": 1,
                "start_time": "10.000000",
                "end_time": "25.500000",
                "tags": {"title": "Chapter 2"},
            },
        ]
    }


class ExtractAudiobookTests(unittest.TestCase):
    def test_build_chapter_plan_from_ffprobe_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            chapters = build_chapter_plan(Path("/tmp/audio.m4b"), out, "test_book", _ffprobe_fixture())

            self.assertEqual(len(chapters), 2)
            self.assertEqual(chapters[0].chapter_id, "test_book_ch01")
            self.assertEqual(chapters[0].title, "Chapter 1")
            self.assertEqual(chapters[1].duration, 15.5)
            self.assertTrue(chapters[1].audio_path.endswith("audio_chapters/chapter_02.m4a"))

    def test_valid_text_and_jsonl_resume_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = root / "chapter.txt"
            jsonl = root / "chapter.jsonl"

            self.assertFalse(valid_text(text))
            self.assertFalse(valid_jsonl(jsonl))

            text.write_text("Some transcript.\n", encoding="utf-8")
            jsonl.write_text(json.dumps({"text": "Some transcript."}) + "\n", encoding="utf-8")

            self.assertTrue(valid_text(text))
            self.assertTrue(valid_jsonl(jsonl))

    def test_split_one_skips_existing_audio_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "source.m4b"
            existing = root / "audio_chapters" / "chapter_01.m4a"
            existing.parent.mkdir()
            audio.write_bytes(b"placeholder")
            existing.write_bytes(b"already here")
            chapter = build_chapter_plan(audio, root, "test_book", _ffprobe_fixture())[0]

            result = split_one(audio, chapter, force=False, limit_seconds=0)

            self.assertEqual(result, "skipped_existing")
            self.assertEqual(existing.read_bytes(), b"already here")


if __name__ == "__main__":
    unittest.main()
