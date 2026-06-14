import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from extract_audiobook.cli import (
    app,
    build_chapter_plan,
    split_one,
    valid_jsonl,
    valid_text,
    validate_job_artifacts,
    write_chapters_jsonl,
    write_manifest,
    write_verify_receipt,
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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_good_job(root: Path) -> Path:
    audio = root / "source.m4b"
    audio.write_bytes(b"fake source audio")
    ffprobe = _ffprobe_fixture()
    (root / "ffprobe_chapters.json").write_text(json.dumps(ffprobe), encoding="utf-8")
    chapters = build_chapter_plan(audio, root, "Test Book", "test_book", ffprobe)
    write_chapters_jsonl(chapters, root)

    actions = []
    for chapter in chapters:
        Path(chapter.audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(chapter.audio_path).write_bytes(b"fake chapter audio")
        Path(chapter.text_path).parent.mkdir(parents=True, exist_ok=True)
        Path(chapter.text_path).write_text(f"{chapter.title} text.\n", encoding="utf-8")
        _write_jsonl(
            Path(chapter.transcript_jsonl_path),
            [
                {
                    "schema_version": "extract-audiobook-transcript-segment.v1",
                    "book": chapter.book,
                    "chapter": chapter.title,
                    "chapter_id": chapter.chapter_id,
                    "chapter_index": chapter.index,
                    "segment_index": 1,
                    "start_s": 0.0,
                    "end_s": min(1.0, chapter.duration),
                    "audio_start_s": chapter.start_time,
                    "audio_end_s": chapter.start_time + min(1.0, chapter.duration),
                    "text": f"{chapter.title} text.",
                    "language": "en",
                }
            ],
        )
        actions.append({"chapter_id": chapter.chapter_id, "split": "created", "transcribe": "created"})

    write_manifest(root, audio, "Test Book", "test_book", "both", chapters, actions)
    return root


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

    def test_verify_job_artifacts_passes_minimal_good_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _write_good_job(Path(tmp))

            result = validate_job_artifacts(root)
            self.assertTrue(result["accepted"], result["failed_checks"])
            self.assertEqual(result["status"], "PASS")

            receipt = write_verify_receipt(root)
            self.assertTrue((root / "verify-receipt.json").exists())
            self.assertTrue(receipt["accepted"])

    def test_verify_job_artifacts_fails_broken_transcript_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _write_good_job(Path(tmp))
            bad_transcript = root / "transcript_jsonl" / "chapter_01.jsonl"
            row = json.loads(bad_transcript.read_text(encoding="utf-8").strip())
            row["chapter_id"] = "wrong_chapter"
            bad_transcript.write_text(json.dumps(row) + "\n", encoding="utf-8")

            result = validate_job_artifacts(root)
            self.assertFalse(result["accepted"])
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(
                any(check["name"] == "test_book_ch01.transcript_jsonl" for check in result["failed_checks"])
            )

    def test_file_maintainer_ticket_writes_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _write_good_job(Path(tmp))
            runner = CliRunner()

            result = runner.invoke(app, ["file-maintainer-ticket", "--job-dir", str(root)])

            self.assertEqual(result.exit_code, 0, result.output)
            packet = json.loads((root / "maintainer-ticket.json").read_text(encoding="utf-8"))
            self.assertEqual(packet["skill"], "extract-audiobook")
            self.assertEqual(packet["status"], "no_failed_checks")
            self.assertTrue((root / "verify-receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
