import json
from pathlib import Path

from book_extraction_verifier.cli import VerifyConfig, verify


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def make_fixture(root: Path, *, include_book_id: bool = True) -> tuple[Path, Path]:
    book_root = root / "book"
    fact_root = root / "fact"
    chunk_text = "Alpha hid the key. Beta saw the door."
    chapter = {
        "_key": "test_book_ch01",
        "book": "Test Book",
        "book_id": "test_book",
        "chapter_id": "test_book_ch01",
        "title": "Chapter 01",
        "text_path": str(root / "chapter_01.txt"),
        "memory_collection": "book_chapters",
    }
    chunk = {
        "_key": "test_book_ch01-c01",
        "chunk_id": "test_book_ch01-c01",
        "source_chunk_id": "c01",
        "document_id": "test_book_ch01",
        "chunk_text": chunk_text,
        "context_start_char": 0,
        "primary_start_char": 0,
        "primary_end_char": len(chunk_text),
        "context_end_char": len(chunk_text),
        "memory_collection": "book_chunks",
    }
    record = {
        "_key": "test_book_ch01-c01-r001",
        "memory_collection": "persona_memory",
        "persona_id": "test_persona",
        "persona_ids": ["test_persona"],
        "book": "Test Book",
        "chapter": "Chapter 01",
        "chapter_id": "test_book_ch01",
        "chunk_id": "c01",
        "question_text": "Who hid the key?",
        "answer_text": "Alpha.",
        "claim_text": "Alpha hid the key.",
        "evidence_text": "Alpha hid the key.",
        "retrieval_text": "Who hid the key? Alpha.",
        "tags": ["persona:test_persona", "book:test_book"],
        "tom": None,
    }
    if include_book_id:
        record["book_id"] = "test_book"
        record["source_ref"] = {"book_id": "test_book", "chapter_id": "test_book_ch01", "chunk_id": "c01"}
    edge = {
        "_key": "edge1",
        "_from": "persona_memory/test_book_ch01-c01-r001",
        "_to": "persona_memory/test_book_ch01-c01-r001",
        "persona_id": "test_persona",
    }
    write_jsonl(book_root / "chapters.jsonl", [chapter])
    write_jsonl(book_root / "chunks.jsonl", [chunk])
    write_jsonl(book_root / "accepted_records.jsonl", [record])
    write_jsonl(book_root / "persona_memory_edges.jsonl", [edge])
    (book_root / "memory_upsert_report.json").write_text("{}", encoding="utf-8")
    chapter_dir = fact_root / "chapter_01"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "aggregate_report.json").write_text(
        json.dumps(
            {
                "accepted": True,
                "completed_chunks": 1,
                "accepted_chunks": 1,
                "failed_chunks": 0,
                "total_records": 1,
            }
        ),
        encoding="utf-8",
    )
    return book_root, fact_root


def test_verify_accepts_well_formed_fixture(tmp_path: Path) -> None:
    book_root, fact_root = make_fixture(tmp_path)
    out_root = tmp_path / "out"

    report = verify(
        VerifyConfig(
            book_id="test_book",
            book="Test Book",
            persona_id="test_persona",
            book_root=book_root,
            fact_root=fact_root,
            out_root=out_root,
            fixture_path=None,
            memory_url="http://127.0.0.1:8601",
            require_memory=False,
            allow_needs_repair=False,
            k=10,
        )
    )

    assert report["critical_checks_passed"] is True
    assert report["record_summary"]["quote_modes"]["exact"] == 1
    assert (out_root / "sanity_report.json").exists()
    assert (out_root / "repair_queue.jsonl").read_text() == ""


def test_verify_emits_repair_queue_for_missing_book_id(tmp_path: Path) -> None:
    book_root, fact_root = make_fixture(tmp_path, include_book_id=False)
    out_root = tmp_path / "out"

    report = verify(
        VerifyConfig(
            book_id="test_book",
            book="Test Book",
            persona_id="test_persona",
            book_root=book_root,
            fact_root=fact_root,
            out_root=out_root,
            fixture_path=None,
            memory_url="http://127.0.0.1:8601",
            require_memory=False,
            allow_needs_repair=True,
            k=10,
        )
    )

    assert report["critical_checks_passed"] is False
    assert report["critical_checks"]["record_schema_ok"] is False
    repairs = [json.loads(line) for line in (out_root / "repair_queue.jsonl").read_text().splitlines()]
    assert repairs
    assert repairs[0]["kind"] == "record_schema"
