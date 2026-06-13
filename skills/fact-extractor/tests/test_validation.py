import json
import tempfile
import unittest
from pathlib import Path

from fact_extractor.cli import (
    ChunkResult,
    append_book_progress_event,
    enrich_records,
    stage_book_source,
    validate_content,
    write_aggregate,
)


def _chunk() -> dict:
    primary = "Alpha sentence. Beta sentence. Gamma sentence."
    return {
        "chunk_id": "c01",
        "document_id": "test_book_ch01",
        "source_path": "/tmp/chapter_01.txt",
        "source_sha256": "source-hash",
        "context_start_char": 0,
        "primary_start_char": 0,
        "primary_end_char": len(primary),
        "context_end_char": len(primary),
        "chunk_text": primary,
        "record_id_prefix": "test_book_ch01-c01-r",
    }


def _record(idx: int, quote: str) -> dict:
    return {
        "question": f"Question {idx}?",
        "answer": f"Answer {idx}.",
        "claim": f"Claim {idx}.",
        "evidence_quote": quote,
        "factuality": "narration_assertion",
        "tom": None,
    }


class ValidateContentTests(unittest.TestCase):
    def test_too_many_valid_records_hard_fails(self) -> None:
        content = "\n".join(
            json.dumps(_record(idx, "Alpha sentence."))
            for idx in range(1, 4)
        )

        report = validate_content(content, _chunk(), min_records=1, max_records=2)

        self.assertEqual(report["record_count"], 3)
        self.assertFalse(report["record_count_target_ok"])
        self.assertFalse(report["record_count_hard_ok"])
        self.assertFalse(report["accepted"])
        self.assertIn("density_warning:expected_1_2:got_3", report["warnings"])

    def test_fewer_than_target_but_nonzero_records_are_warning_only(self) -> None:
        content = json.dumps(_record(1, "Beta sentence."))

        report = validate_content(content, _chunk(), min_records=2, max_records=4)

        self.assertEqual(report["record_count"], 1)
        self.assertFalse(report["record_count_target_ok"])
        self.assertTrue(report["record_count_hard_ok"])
        self.assertTrue(report["accepted"])
        self.assertIn("density_warning:expected_2_4:got_1", report["warnings"])

    def test_enriched_record_carries_chapter_and_evidence_span(self) -> None:
        chunk = _chunk()
        record = _record(1, "Beta sentence.")

        enriched = enrich_records(
            [record],
            chunk,
            {"book": "Test Book", "chapter": "Chapter 01", "chapter_id": "test_book_ch01"},
        )

        self.assertEqual(enriched[0]["schema_version"], "fact-extractor-accepted-record.v1")
        self.assertEqual(enriched[0]["book"], "Test Book")
        self.assertEqual(enriched[0]["chapter"], "Chapter 01")
        self.assertEqual(enriched[0]["chapter_id"], "test_book_ch01")
        self.assertEqual(enriched[0]["chunk_id"], "c01")
        self.assertEqual(enriched[0]["evidence_start_char"], chunk["chunk_text"].find("Beta sentence."))
        self.assertEqual(
            enriched[0]["evidence_end_char"],
            chunk["chunk_text"].find("Beta sentence.") + len("Beta sentence."),
        )

    def test_quote_whitespace_exactification_repairs_line_broken_source(self) -> None:
        primary = "He knew his station\n within the Legion,\n but knowing one's station\n was the first step\n to bettering it."
        chunk = {
            **_chunk(),
            "primary_end_char": len(primary),
            "context_end_char": len(primary),
            "chunk_text": primary,
        }
        record = _record(
            1,
            "He knew his station within the Legion, but knowing one's station was the first step to bettering it.",
        )

        report = validate_content(json.dumps(record), chunk, min_records=1, max_records=2)

        self.assertTrue(report["accepted"])
        self.assertEqual(report["record_count"], 1)
        self.assertEqual(report["records"][0]["evidence_quote"], primary)
        self.assertTrue(any("evidence_quote_whitespace_exactified" in warning for warning in report["warnings"]))

    def test_aggregate_rejects_accepted_records_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            chunk_dir = out / "chunks" / "c01"
            chunk_dir.mkdir(parents=True)
            (chunk_dir / "accepted_records.jsonl").write_text(json.dumps(_record(1, "Beta sentence.")) + "\n")
            chunks = [_chunk()]
            result = ChunkResult(
                chunk_id="c01",
                accepted=True,
                record_count=1,
                elapsed_s=0,
                http_status=200,
                defects=[],
                chunk_dir=str(chunk_dir),
                accepted_attempt=1,
                attempts=1,
            )

            aggregate = write_aggregate(out, chunks, [result])

            self.assertFalse(aggregate["accepted"])
            self.assertFalse(aggregate["accepted_record_metadata_ok"])
            self.assertTrue(aggregate["accepted_record_metadata_defects"])

    def test_aggregate_rejects_zero_selected_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            aggregate = write_aggregate(Path(tmp), [], [])

            self.assertFalse(aggregate["accepted"])
            self.assertIn("zero_chunks_selected", aggregate["aggregate_defects"])

    def test_stage_book_splits_standalone_chapter_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "book.txt"
            source.write_text(
                "Front matter\nChapter 1\nOne starts.\n\nChapter 2\nTwo starts.\n",
                encoding="utf-8",
            )

            manifest = stage_book_source(source, root / "staged", "Test Book", "test_book", force=False)

            self.assertEqual(manifest["chapter_count"], 2)
            self.assertEqual(manifest["chapters"][0]["chapter_id"], "test_book_ch01")
            self.assertEqual(manifest["chapters"][1]["chapter_id"], "test_book_ch02")
            self.assertTrue((root / "staged" / "cleaned_chapters" / "chapter_01.txt").exists())
            self.assertTrue((root / "staged" / "stage_manifest.json").exists())

    def test_book_progress_jsonl_is_append_only_resume_safe_and_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            book_root = root / "book"
            ch01 = book_root / "chapter_01"
            ch02 = book_root / "chapter_02"
            ch01.mkdir(parents=True)
            ch02.mkdir(parents=True)
            for chapter_dir, prefix, count in [(ch01, "ch01", 2), (ch02, "ch02", 3)]:
                (chapter_dir / "chunks.jsonl").write_text(
                    "\n".join(json.dumps({"chunk_id": f"{prefix}_c{idx}"}) for idx in range(1, count + 1)) + "\n",
                    encoding="utf-8",
                )
            progress_path = ch01 / "progress.as_completed.jsonl"
            progress_text = "\n".join(
                [
                    json.dumps({"chunk_id": "ch01_c1", "accepted": True, "record_count": 5}),
                    json.dumps({"chunk_id": "ch01_c2", "accepted": False, "record_count": 0}),
                ]
            ) + "\n"
            progress_path.write_text(progress_text, encoding="utf-8")
            (ch01 / "aggregate_report.json").write_text(
                json.dumps(
                    {
                        "accepted": False,
                        "completed_chunks": 2,
                        "accepted_chunks": 1,
                        "failed_chunks": 1,
                        "total_records": 5,
                        "memory_writes_performed": False,
                    }
                ),
                encoding="utf-8",
            )
            before_progress_text = progress_path.read_text(encoding="utf-8")

            started = append_book_progress_event(
                book_root=book_root,
                chapter_out=ch01,
                book="Test Book",
                book_id="test_book",
                chapter="Chapter 01",
                chapter_id="test_book_ch01",
                status="started",
            )
            running = append_book_progress_event(
                book_root=book_root,
                chapter_out=ch01,
                book="Test Book",
                book_id="test_book",
                chapter="Chapter 01",
                chapter_id="test_book_ch01",
                status="running",
            )
            failed = append_book_progress_event(
                book_root=book_root,
                chapter_out=ch01,
                book="Test Book",
                book_id="test_book",
                chapter="Chapter 01",
                chapter_id="test_book_ch01",
                status="failed",
            )

            rows = [
                json.loads(line)
                for line in (book_root / "book_progress.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual([row["status"] for row in rows], ["started", "running", "failed"])
            self.assertEqual(started["total_chunks"], 2)
            self.assertEqual(running["completed_chunks"], 2)
            self.assertEqual(failed["accepted_chunks"], 1)
            self.assertEqual(failed["failed_chunks"], 1)
            self.assertEqual(failed["accepted_records"], 5)
            self.assertEqual(failed["memory_writes_performed"], False)
            self.assertEqual(failed["forbidden_writes"], ["persona_memory", "lessons", "arangodb"])
            self.assertIn("timestamp", failed)
            self.assertIn("completed_at", failed)
            self.assertEqual(progress_path.read_text(encoding="utf-8"), before_progress_text)

            append_book_progress_event(
                book_root=book_root,
                chapter_out=ch02,
                book="Test Book",
                book_id="test_book",
                chapter="Chapter 02",
                chapter_id="test_book_ch02",
                status="started",
            )
            resumed_rows = [
                json.loads(line)
                for line in (book_root / "book_progress.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(resumed_rows), 4)
            self.assertEqual(resumed_rows[-1]["chapter_id"], "test_book_ch02")
            self.assertEqual(resumed_rows[-1]["total_chunks"], 3)


if __name__ == "__main__":
    unittest.main()
