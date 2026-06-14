import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from fact_extractor.cli import (
    ChunkResult,
    app,
    append_book_progress_event,
    enrich_records,
    stage_book_source,
    summarize_book_progress,
    validate_content,
    validate_job_artifacts,
    write_verify_receipt,
    write_aggregate,
    write_chunk_dicts_jsonl,
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
    def setUp(self) -> None:
        self.runner = CliRunner()

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

    def test_book_progress_summary_reports_latest_chapter_state_and_totals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            book_root = Path(tmp)
            rows = [
                {
                    "schema_version": "fact-extractor-book-progress.v1",
                    "timestamp": "2026-06-13T17:00:00+00:00",
                    "book": "Test Book",
                    "book_id": "test_book",
                    "chapter": "Chapter 01",
                    "chapter_id": "test_book_ch01",
                    "status": "started",
                    "total_chunks": 3,
                    "completed_chunks": 0,
                    "accepted_chunks": 0,
                    "failed_chunks": 0,
                    "accepted_records": 0,
                    "memory_writes_performed": False,
                    "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
                },
                {
                    "schema_version": "fact-extractor-book-progress.v1",
                    "timestamp": "2026-06-13T17:01:00+00:00",
                    "book": "Test Book",
                    "book_id": "test_book",
                    "chapter": "Chapter 01",
                    "chapter_id": "test_book_ch01",
                    "status": "accepted",
                    "total_chunks": 3,
                    "completed_chunks": 3,
                    "accepted_chunks": 3,
                    "failed_chunks": 0,
                    "accepted_records": 7,
                    "memory_writes_performed": False,
                    "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
                },
                {
                    "schema_version": "fact-extractor-book-progress.v1",
                    "timestamp": "2026-06-13T17:02:00+00:00",
                    "book": "Test Book",
                    "book_id": "test_book",
                    "chapter": "Chapter 02",
                    "chapter_id": "test_book_ch02",
                    "status": "running",
                    "total_chunks": 4,
                    "completed_chunks": 2,
                    "accepted_chunks": 1,
                    "failed_chunks": 1,
                    "accepted_records": 2,
                    "memory_writes_performed": False,
                    "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
                },
                {
                    "schema_version": "fact-extractor-book-progress.v1",
                    "timestamp": "2026-06-13T17:03:00+00:00",
                    "book": "Test Book",
                    "book_id": "test_book",
                    "chapter": "Chapter 03",
                    "chapter_id": "test_book_ch03",
                    "status": "failed",
                    "total_chunks": 2,
                    "completed_chunks": 2,
                    "accepted_chunks": 1,
                    "failed_chunks": 1,
                    "accepted_records": 3,
                    "memory_writes_performed": False,
                    "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
                },
                {
                    "schema_version": "fact-extractor-book-progress.v1",
                    "timestamp": "2026-06-13T17:04:00+00:00",
                    "book": "Test Book",
                    "book_id": "test_book",
                    "chapter": "Chapter 04",
                    "chapter_id": "test_book_ch04",
                    "status": "started",
                    "total_chunks": 5,
                    "completed_chunks": 0,
                    "accepted_chunks": 0,
                    "failed_chunks": 0,
                    "accepted_records": 0,
                    "memory_writes_performed": False,
                    "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
                },
            ]
            (book_root / "book_progress.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            summary = summarize_book_progress(book_root)

            self.assertEqual(summary["schema_version"], "fact-extractor-book-progress-summary.v1")
            self.assertEqual(summary["event_count"], 5)
            self.assertEqual(summary["chapter_count"], 4)
            self.assertEqual(summary["chapters_started"], 1)
            self.assertEqual(summary["chapters_running"], 1)
            self.assertEqual(summary["chapters_accepted"], 1)
            self.assertEqual(summary["chapters_failed"], 1)
            self.assertEqual(summary["total_chunks"], 14)
            self.assertEqual(summary["completed_chunks"], 7)
            self.assertEqual(summary["accepted_chunks"], 5)
            self.assertEqual(summary["failed_chunks"], 2)
            self.assertEqual(summary["accepted_records"], 12)
            self.assertEqual(summary["memory_writes_performed"], False)
            self.assertEqual(summary["forbidden_writes"], ["persona_memory", "lessons", "arangodb"])
            self.assertEqual(
                {chapter["chapter_id"]: chapter["status"] for chapter in summary["chapters"]},
                {
                    "test_book_ch01": "accepted",
                    "test_book_ch02": "running",
                    "test_book_ch03": "failed",
                    "test_book_ch04": "started",
                },
            )

            result = self.runner.invoke(app, ["book-progress-summary", str(book_root)])
            self.assertEqual(result.exit_code, 0, result.output)
            cli_summary = json.loads(result.output)
            self.assertEqual(cli_summary["accepted_records"], 12)
            self.assertEqual(cli_summary["chapters"][0]["event_index"], 2)

    def test_book_progress_summary_missing_jsonl_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.runner.invoke(app, ["book-progress-summary", tmp])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("missing_book_progress_jsonl", result.output)

    def test_verify_accepts_complete_extraction_job_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            chunk = _chunk()
            record = _record(1, "Beta sentence.")
            chunk_dir = out / "chunks" / "c01"
            chunk_dir.mkdir(parents=True)
            enriched = enrich_records(
                [record],
                chunk,
                {"book": "Test Book", "chapter": "Chapter 01", "chapter_id": "test_book_ch01"},
            )
            (chunk_dir / "accepted_records.jsonl").write_text(json.dumps(enriched[0]) + "\n", encoding="utf-8")
            (chunk_dir / "accepted_attempt.txt").write_text("attempt_01\n", encoding="utf-8")
            write_chunk_dicts_jsonl([chunk], out / "chunks.jsonl")
            write_aggregate(
                out,
                [chunk],
                [
                    ChunkResult(
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
                ],
            )

            receipt = write_verify_receipt(out)

            self.assertTrue(receipt["accepted"])
            self.assertFalse(receipt["failed_checks"])
            self.assertTrue((out / "verify-receipt.json").exists())

            result = self.runner.invoke(app, ["verify", "--job-dir", str(out)])
            self.assertEqual(result.exit_code, 0, result.output)

    def test_verify_rejects_broken_job_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "aggregate_report.json").write_text(
                json.dumps({"schema_version": "fact-extractor-result.v1", "accepted": False}),
                encoding="utf-8",
            )

            receipt = validate_job_artifacts(out)

            self.assertFalse(receipt["accepted"])
            self.assertTrue(receipt["failed_checks"])

            result = self.runner.invoke(app, ["verify", "--job-dir", str(out)])
            self.assertNotEqual(result.exit_code, 0)
            self.assertTrue((out / "verify-receipt.json").exists())

    def test_verify_writes_receipt_for_malformed_aggregate_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            chunk = _chunk()
            chunk_dir = out / "chunks" / "c01"
            chunk_dir.mkdir(parents=True)
            write_chunk_dicts_jsonl([chunk], out / "chunks.jsonl")
            enriched = enrich_records(
                [_record(1, "Beta sentence.")],
                chunk,
                {"book": "Test Book", "chapter": "Chapter 01", "chapter_id": "test_book_ch01"},
            )
            (out / "accepted_records.jsonl").write_text(json.dumps(enriched[0]) + "\n", encoding="utf-8")
            (chunk_dir / "accepted_records.jsonl").write_text(json.dumps(enriched[0]) + "\n", encoding="utf-8")
            (out / "status.md").write_text("# ACCEPTED_FACT_EXTRACTION_ARTIFACT\n", encoding="utf-8")
            (out / "aggregate_report.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fact-extractor-result.v1",
                        "accepted": True,
                        "completed_chunks": "not-int",
                        "accepted_chunks": {},
                        "failed_chunks": [],
                        "total_records": "bad",
                        "accepted_record_metadata_ok": True,
                        "accepted_record_metadata_defects": [],
                        "memory_writes_performed": False,
                        "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
                        "results": [{"chunk_id": "c01", "accepted": True, "record_count": "bad"}],
                    }
                ),
                encoding="utf-8",
            )

            result = self.runner.invoke(app, ["verify", "--job-dir", str(out)])

            self.assertNotEqual(result.exit_code, 0)
            receipt_path = out / "verify-receipt.json"
            self.assertTrue(receipt_path.exists())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            failed_ids = {check["id"] for check in receipt["failed_checks"]}
            self.assertIn("aggregate_completed_chunks_integer", failed_ids)
            self.assertIn("aggregate_total_records_integer", failed_ids)
            self.assertIn("chunk_c01_record_count_integer", failed_ids)

    def test_file_maintainer_ticket_includes_route_targets_failed_checks_and_repros(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "aggregate_report.json").write_text(
                json.dumps({"schema_version": "fact-extractor-result.v1", "accepted": False}),
                encoding="utf-8",
            )

            result = self.runner.invoke(app, ["file-maintainer-ticket", "--job-dir", str(out)])

            self.assertEqual(result.exit_code, 0, result.output)
            packet = json.loads((out / "maintainer-ticket.json").read_text(encoding="utf-8"))
            self.assertEqual(packet["route"], "backend_python_or_skill_runtime")
            self.assertIn("skills/fact-extractor/fact_extractor/cli.py", packet["target_paths"])
            self.assertTrue(packet["failed_checks"])
            self.assertTrue(any("verify --job-dir" in command for command in packet["repro_commands"]))


if __name__ == "__main__":
    unittest.main()
