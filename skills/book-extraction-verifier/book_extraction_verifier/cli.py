from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer


app = typer.Typer(no_args_is_help=True)

VECTOR_FIELDS = {"embedding", "embedding_visual", "vector"}
REQUIRED_RECORD_FIELDS = {
    "_key",
    "memory_collection",
    "persona_id",
    "persona_ids",
    "book",
    "book_id",
    "chapter",
    "chapter_id",
    "chunk_id",
    "question_text",
    "answer_text",
    "claim_text",
    "evidence_text",
    "retrieval_text",
    "tags",
}
TOM_STATES = {"belief", "intention", "emotion", "perception", "preference", "uncertainty", "evaluation"}


@dataclass(frozen=True)
class VerifyConfig:
    book_id: str
    book: str
    persona_id: str
    book_root: Path
    fact_root: Path
    out_root: Path
    fixture_path: Path | None
    memory_url: str
    require_memory: bool
    allow_needs_repair: bool
    k: int


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                rows.append({"__parse_error__": str(exc), "__line__": line_no, "__raw__": line[:200]})
                continue
            if not isinstance(row, dict):
                rows.append({"__parse_error__": "not_object", "__line__": line_no, "__raw__": line[:200]})
                continue
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chapter_num_from_id(value: str | None) -> int | None:
    match = re.search(r"_ch(\d+)", value or "")
    return int(match.group(1)) if match else None


def unique_key_check(rows: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    keys = [str(row.get("_key")) for row in rows if isinstance(row, dict) and row.get("_key")]
    counts: dict[str, int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    return len(keys), len(counts), [key for key, count in counts.items() if count > 1][:20]


def primary_text(chunk: dict[str, Any]) -> str:
    context_start = int(chunk["context_start_char"])
    primary_start = int(chunk["primary_start_char"])
    primary_end = int(chunk["primary_end_char"])
    return str(chunk["chunk_text"])[primary_start - context_start : primary_end - context_start]


def quote_in_primary(quote: str, primary: str) -> tuple[bool, str]:
    if quote in primary:
        return True, "exact"
    if normalize_ws(quote) and normalize_ws(quote) in normalize_ws(primary):
        return True, "whitespace_normalized"
    return False, "missing"


def record_chunk_key(record: dict[str, Any]) -> str | None:
    if record.get("chunk_record_id"):
        return str(record["chunk_record_id"])
    source_ref = record.get("source_ref") if isinstance(record.get("source_ref"), dict) else {}
    if source_ref.get("chunk_record_id"):
        return str(source_ref["chunk_record_id"])
    chunk_id = record.get("chunk_id") or source_ref.get("chunk_id")
    chapter_id = record.get("chapter_id") or source_ref.get("chapter_id")
    if chunk_id and chapter_id and not str(chunk_id).startswith(str(chapter_id)):
        return f"{chapter_id}-{chunk_id}"
    return str(chunk_id) if chunk_id else None


def add_repair(
    repairs: list[dict[str, Any]],
    kind: str,
    target: str,
    command: str,
    reason: str,
    verification: str,
) -> None:
    repairs.append(
        {
            "kind": kind,
            "target": target,
            "reason": reason,
            "default_command": command,
            "verification_command": verification,
            "created_at": now(),
        }
    )


def artifact_summary(name: str, rows: list[dict[str, Any]], path: Path, repairs: list[dict[str, Any]]) -> dict[str, Any]:
    key_count, unique_count, duplicate_keys = unique_key_check(rows)
    parse_errors = [row for row in rows if row.get("__parse_error__")]
    vector_rows = [
        {"line": index, "_key": row.get("_key"), "fields": sorted(VECTOR_FIELDS & set(row))}
        for index, row in enumerate(rows, start=1)
        if VECTOR_FIELDS & set(row)
    ]
    missing_memory = [
        {"line": index, "_key": row.get("_key")}
        for index, row in enumerate(rows, start=1)
        if name != "persona_memory_edges" and not row.get("memory_collection")
    ]
    if parse_errors:
        add_repair(repairs, "json_parse", name, "repair invalid JSONL rows", f"{len(parse_errors)} parse errors", "rerun verifier")
    if duplicate_keys:
        add_repair(repairs, "duplicate_keys", name, "dedupe deterministic _key collisions", str(duplicate_keys[:5]), "rerun verifier")
    if vector_rows:
        add_repair(
            repairs,
            "inline_vectors",
            name,
            "remove inline embedding/vector fields and re-upsert through memory",
            f"{len(vector_rows)} rows contain vector fields",
            "rerun verifier",
        )
    return {
        "path": str(path),
        "row_count": len(rows),
        "key_count": key_count,
        "unique_key_count": unique_count,
        "duplicate_keys": duplicate_keys,
        "parse_error_count": len(parse_errors),
        "vector_field_row_count": len(vector_rows),
        "missing_memory_collection_count": len(missing_memory),
    }


def load_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    return load_jsonl(path) if path.exists() else []


def load_fixtures(config: VerifyConfig, records: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if config.fixture_path:
        return load_jsonl(config.fixture_path)
    fixtures: list[dict[str, Any]] = []
    for record in records[:3]:
        key = record.get("_key")
        query = " ".join(str(record.get(part) or "") for part in ("book", "question_text", "answer_text")).strip()
        if key and query:
            fixtures.append(
                {
                    "id": f"generated_{key}",
                    "kind": "generated",
                    "q": query,
                    "expected_key": key,
                    "require_dense": False,
                    "require_graph": False,
                }
            )
    for edge in edges[:1]:
        from_key = str(edge.get("_from", "")).split("/")[-1]
        record = next((row for row in records if row.get("_key") == from_key), None)
        if record:
            fixtures.append(
                {
                    "id": f"generated_graph_{from_key}",
                    "kind": "graph",
                    "q": f"{record.get('question_text')} {record.get('answer_text')}",
                    "expected_key": from_key,
                    "require_dense": False,
                    "require_graph": True,
                }
            )
    return fixtures


def run_recall_checks(config: VerifyConfig, fixtures: list[dict[str, Any]], repairs: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    health: dict[str, Any] = {"skipped": not config.require_memory}
    recall_rows: list[dict[str, Any]] = []
    if not config.require_memory:
        return health, recall_rows
    try:
        client = httpx.Client(base_url=config.memory_url, timeout=httpx.Timeout(20.0, connect=3.0))
        response = client.get("/health")
        health = {"status_code": response.status_code, **response.json()}
    except Exception as exc:
        health = {"error": str(exc)}
        add_repair(repairs, "memory_health", config.memory_url, "restart or inspect memory daemon", str(exc), "GET /health returns ok=true")
        return health, recall_rows

    for fixture in fixtures:
        payload = {
            "q": fixture["q"],
            "k": config.k,
            "collections": ["persona_memory"],
            "tags": [f"persona:{config.persona_id}", f"book:{config.book_id}"],
        }
        row: dict[str, Any] = {
            "fixture_id": fixture.get("id"),
            "kind": fixture.get("kind"),
            "request": payload,
            "expected_key": fixture.get("expected_key"),
        }
        try:
            response = client.post("/recall", json=payload)
            row["http_status"] = response.status_code
            data = response.json()
            items = data.get("items") or []
            expected_items = [item for item in items if item.get("_key") == fixture.get("expected_key")]
            top = items[0] if items else {}
            expected = expected_items[0] if expected_items else {}
            row.update(
                {
                    "found": data.get("found"),
                    "confidence": data.get("confidence"),
                    "meta": data.get("meta", {}),
                    "returned_top_keys": [item.get("_key") for item in items[: config.k]],
                    "top_key": top.get("_key"),
                    "top_scores": top.get("scores"),
                    "expected_scores": expected.get("scores"),
                    "expected_rank": (items.index(expected) + 1) if expected else None,
                    "expected_found_in_top_k": bool(expected),
                    "expected_has_persona_tag": f"persona:{config.persona_id}" in (expected.get("tags") or []) if expected else False,
                    "expected_has_book_tag": f"book:{config.book_id}" in (expected.get("tags") or []) if expected else False,
                }
            )
            dense_ok = (not fixture.get("require_dense")) or bool(
                (expected.get("scores") or {}).get("dense", 0) > 0
                or (top.get("scores") or {}).get("dense", 0) > 0
                or data.get("meta", {}).get("used_dense")
            )
            graph_ok = (not fixture.get("require_graph")) or bool(
                (expected.get("scores") or {}).get("graph", 0) > 0
                or (top.get("scores") or {}).get("graph", 0) > 0
            )
            failures: list[str] = []
            if not data.get("found"):
                failures.append("found_false")
            if not expected:
                failures.append("expected_key_not_in_top_k")
            if expected and not row["expected_has_persona_tag"]:
                failures.append("missing_persona_tag_on_expected")
            if expected and not row["expected_has_book_tag"]:
                failures.append("missing_book_tag_on_expected")
            if not dense_ok:
                failures.append("dense_requirement_failed")
            if not graph_ok:
                failures.append("graph_requirement_failed")
            row["failures"] = failures
            row["passed"] = not failures
            if failures:
                add_repair(
                    repairs,
                    "recall_check",
                    str(fixture.get("id")),
                    f"inspect memory upsert, Qdrant sync, graph edges, and tags for {fixture.get('expected_key')}",
                    ",".join(failures),
                    f"rerun recall fixture {fixture.get('id')}",
                )
        except Exception as exc:
            row["passed"] = False
            row["error"] = str(exc)
            add_repair(repairs, "recall_exception", str(fixture.get("id")), "repair memory daemon or recall request", str(exc), "rerun recall fixture")
        recall_rows.append(row)
    return health, recall_rows


def verify(config: VerifyConfig) -> dict[str, Any]:
    repairs: list[dict[str, Any]] = []
    config.out_root.mkdir(parents=True, exist_ok=True)

    chapters_path = config.book_root / "chapters.jsonl"
    chunks_path = config.book_root / "chunks.jsonl"
    records_path = config.book_root / "accepted_records.jsonl"
    edges_path = config.book_root / "persona_memory_edges.jsonl"

    chapters = load_jsonl(chapters_path)
    chunks = load_jsonl(chunks_path)
    records = load_jsonl(records_path)
    edges = load_optional_jsonl(edges_path)

    artifact_checks = {
        "chapters": artifact_summary("chapters", chapters, chapters_path, repairs),
        "chunks": artifact_summary("chunks", chunks, chunks_path, repairs),
        "accepted_records": artifact_summary("accepted_records", records, records_path, repairs),
        "persona_memory_edges": artifact_summary("persona_memory_edges", edges, edges_path, repairs),
    }

    chunk_by_id = {chunk.get("chunk_id"): chunk for chunk in chunks if isinstance(chunk, dict)}
    chapter_ids = {chapter.get("chapter_id") for chapter in chapters if isinstance(chapter, dict)}
    record_keys = {record.get("_key") for record in records if isinstance(record, dict)}

    record_defects = []
    for line_no, record in enumerate(records, start=1):
        missing = sorted(field for field in REQUIRED_RECORD_FIELDS if field not in record or record.get(field) in (None, ""))
        tags = record.get("tags") or []
        missing_tags = [tag for tag in (f"persona:{config.persona_id}", f"book:{config.book_id}") if tag not in tags]
        if record.get("memory_collection") != "persona_memory":
            missing.append("memory_collection=persona_memory")
        if record.get("persona_id") != config.persona_id:
            missing.append("persona_id")
        if record.get("book_id") != config.book_id:
            missing.append("book_id")
        if missing or missing_tags:
            defect = {"line": line_no, "_key": record.get("_key"), "missing_or_bad": missing, "missing_tags": missing_tags}
            record_defects.append(defect)
            if len(record_defects) <= 100:
                add_repair(
                    repairs,
                    "record_schema",
                    str(record.get("_key") or f"line:{line_no}"),
                    "repair accepted_records.jsonl metadata/enrichment then re-upsert persona_memory",
                    json.dumps(defect, sort_keys=True),
                    "rerun verifier artifact checks",
                )

    aggregate_reports = []
    aggregate_defects = []
    for chapter_id in sorted(chapter_ids):
        chapter_no = chapter_num_from_id(str(chapter_id))
        path = config.fact_root / f"chapter_{chapter_no:02d}" / "aggregate_report.json" if chapter_no else config.fact_root / "unknown" / "aggregate_report.json"
        row: dict[str, Any] = {"chapter_id": chapter_id, "path": str(path), "exists": path.exists()}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                row.update(
                    {
                        "accepted": data.get("accepted"),
                        "completed_chunks": data.get("completed_chunks"),
                        "accepted_chunks": data.get("accepted_chunks"),
                        "failed_chunks": data.get("failed_chunks"),
                        "total_records": data.get("total_records"),
                        "aggregate_defects": data.get("aggregate_defects") or data.get("defects") or [],
                        "failed_chunk_ledger_count": len(data.get("failed_chunk_ledger") or []),
                    }
                )
                if data.get("accepted") is not True or (data.get("failed_chunks") or 0) != 0:
                    aggregate_defects.append(row)
            except Exception as exc:
                row["parse_error"] = str(exc)
                aggregate_defects.append(row)
        else:
            aggregate_defects.append(row)
        aggregate_reports.append(row)

    for defect in aggregate_defects:
        chapter_no = chapter_num_from_id(str(defect.get("chapter_id")))
        command = (
            f"skills/fact-extractor/run.sh repair-chapter --out {config.fact_root}/chapter_{chapter_no:02d} "
            f"--book '{config.book}' --chapter 'Chapter {chapter_no:02d}' --chapter-id {defect.get('chapter_id')} "
            f"--persona-id {config.persona_id} --concurrency 1 --timeout 360"
            if chapter_no
            else "repair missing chapter id"
        )
        add_repair(repairs, "chapter_aggregate", str(defect.get("chapter_id")), command, json.dumps(defect), "merge, re-upsert, rerun verifier")

    quote_modes = {"exact": 0, "whitespace_normalized": 0, "missing": 0, "missing_chunk": 0}
    quote_defects = []
    for line_no, record in enumerate(records, start=1):
        chunk_key = record_chunk_key(record)
        chunk = chunk_by_id.get(chunk_key)
        if not chunk:
            quote_modes["missing_chunk"] += 1
            quote_defects.append({"line": line_no, "_key": record.get("_key"), "chunk_key": chunk_key, "reason": "missing_chunk"})
            continue
        ok, mode = quote_in_primary(str(record.get("evidence_text") or record.get("evidence_quote") or ""), primary_text(chunk))
        quote_modes[mode] += 1
        if not ok:
            quote_defects.append({"line": line_no, "_key": record.get("_key"), "chunk_key": chunk_key, "reason": "quote_not_in_primary"})

    for defect in quote_defects[:100]:
        chapter_id = str(defect.get("chunk_key") or "").split("-c")[0]
        chapter_no = chapter_num_from_id(chapter_id)
        command = (
            f"skills/fact-extractor/run.sh repair-chapter --out {config.fact_root}/chapter_{chapter_no:02d} "
            f"--book '{config.book}' --chapter 'Chapter {chapter_no:02d}' --chapter-id {chapter_id} "
            f"--persona-id {config.persona_id} --concurrency 1 --timeout 360"
            if chapter_no
            else "repair source record chunk_id"
        )
        add_repair(repairs, "quote_grounding", str(defect.get("_key")), command, str(defect.get("reason")), "rerun verifier quote checks")

    tom_records = [record for record in records if record.get("tom")]
    tom_defects = []
    for record in tom_records:
        tom = record.get("tom") if isinstance(record.get("tom"), dict) else {}
        state = tom.get("mental_state")
        tags = record.get("tom_tags") or []
        missing = []
        if state not in TOM_STATES:
            missing.append("tom.mental_state")
        if record.get("tom_state_type") != state:
            missing.append("tom_state_type")
        for required in ["tom", "tom_holder:", "tom_state:", "tom_target:"]:
            if required == "tom":
                if "tom" not in tags:
                    missing.append("tom_tags:tom")
            elif not any(str(tag).startswith(required) for tag in tags):
                missing.append(f"tom_tags:{required}")
        if missing:
            defect = {"_key": record.get("_key"), "missing_or_bad": missing}
            tom_defects.append(defect)
            if len(tom_defects) <= 100:
                add_repair(repairs, "tom_metadata", str(record.get("_key")), "backfill tom_tags/tom_state_type and re-upsert", json.dumps(defect), "rerun ToM checks")

    edge_defects = []
    for edge in edges:
        from_key = str(edge.get("_from", "")).removeprefix("persona_memory/")
        to_key = str(edge.get("_to", "")).removeprefix("persona_memory/")
        bad = []
        if from_key not in record_keys:
            bad.append("_from")
        if to_key not in record_keys:
            bad.append("_to")
        if edge.get("persona_id") != config.persona_id:
            bad.append("persona_id")
        if bad:
            edge_defects.append({"_key": edge.get("_key"), "bad": bad})
    for defect in edge_defects[:100]:
        add_repair(repairs, "edge_integrity", str(defect.get("_key")), "rebuild persona_memory_edges.jsonl and re-upsert", json.dumps(defect), "rerun edge checks")

    fixtures = load_fixtures(config, records, edges)
    health, recall_rows = run_recall_checks(config, fixtures, repairs)

    upsert_reports = []
    for path in sorted(config.book_root.glob("memory*_report.json")):
        row: dict[str, Any] = {"path": str(path), "exists": path.exists()}
        try:
            row["json"] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            row["parse_error"] = str(exc)
            add_repair(repairs, "upsert_report_parse", str(path), "regenerate upsert report", str(exc), "rerun verifier")
        upsert_reports.append(row)

    critical = {
        "artifacts_exist": chapters_path.exists() and chunks_path.exists() and records_path.exists(),
        "artifact_keys_unique": all(artifact_checks[name]["key_count"] == artifact_checks[name]["unique_key_count"] for name in ("chapters", "chunks", "accepted_records")),
        "no_parse_errors": all(check["parse_error_count"] == 0 for check in artifact_checks.values()),
        "no_inline_vectors": all(check["vector_field_row_count"] == 0 for check in artifact_checks.values()),
        "record_schema_ok": len(record_defects) == 0,
        "chapter_aggregate_ok": len(aggregate_defects) == 0,
        "quotes_grounded_ok": len(quote_defects) == 0,
        "tom_metadata_ok": len(tom_defects) == 0,
        "edge_integrity_ok": len(edge_defects) == 0 and len(edges) > 0,
        "memory_health_ok": (health.get("ok") is True) if config.require_memory else True,
        "upsert_reports_exist": bool(upsert_reports) if config.require_memory else True,
        "recall_checks_ok": (bool(recall_rows) and all(row.get("passed") for row in recall_rows)) if config.require_memory else True,
    }
    critical_passed = all(critical.values())
    outcome = "accepted" if critical_passed else ("needs_repair" if repairs else "blocked")
    report = {
        "schema_version": "book-extraction-verifier-result.v1",
        "generated_at": now(),
        "outcome": outcome,
        "critical_checks_passed": critical_passed,
        "book_id": config.book_id,
        "book": config.book,
        "persona_id": config.persona_id,
        "artifact_root": str(config.book_root),
        "fact_root": str(config.fact_root),
        "verifier_root": str(config.out_root),
        "sanity_report": str(config.out_root / "sanity_report.json"),
        "recall_checks": str(config.out_root / "recall_checks.jsonl"),
        "repair_queue": str(config.out_root / "repair_queue.jsonl"),
        "critical_checks": critical,
        "artifact_checks": artifact_checks,
        "aggregate_summary": {
            "aggregate_report_count": len(aggregate_reports),
            "aggregate_defect_count": len(aggregate_defects),
            "reports": aggregate_reports,
        },
        "record_summary": {
            "record_count": len(records),
            "record_schema_defect_count": len(record_defects),
            "quote_modes": quote_modes,
            "quote_defect_count": len(quote_defects),
        },
        "tom_summary": {
            "tom_record_count": len(tom_records),
            "tom_defect_count": len(tom_defects),
            "edge_count": len(edges),
            "edge_defect_count": len(edge_defects),
        },
        "memory_summary": {
            "health": health,
            "upsert_reports": upsert_reports,
            "recall_check_count": len(recall_rows),
            "recall_pass_count": sum(1 for row in recall_rows if row.get("passed")),
        },
        "repair_count": len(repairs),
    }
    write_jsonl(config.out_root / "recall_checks.jsonl", recall_rows)
    write_jsonl(config.out_root / "repair_queue.jsonl", repairs)
    (config.out_root / "sanity_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    write_markdown_summary(config.out_root / "sanity_report.md", report, recall_rows)
    return report


def write_markdown_summary(path: Path, report: dict[str, Any], recall_rows: list[dict[str, Any]]) -> None:
    lines = [
        f"# Book Extraction Verifier: {report['book']}",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Outcome: {report['outcome']}",
        f"- Critical checks passed: {report['critical_checks_passed']}",
        f"- Book root: `{report['artifact_root']}`",
        f"- Fact root: `{report['fact_root']}`",
        f"- Verifier root: `{report['verifier_root']}`",
        "",
        "## Counts",
        "",
    ]
    for name, check in report["artifact_checks"].items():
        lines.append(
            f"- {name}: rows={check['row_count']}, unique_keys={check['unique_key_count']}, "
            f"vectors={check['vector_field_row_count']}, parse_errors={check['parse_error_count']}"
        )
    lines.extend(
        [
            f"- aggregate reports: {report['aggregate_summary']['aggregate_report_count']}, aggregate defects: {report['aggregate_summary']['aggregate_defect_count']}",
            f"- quote modes: {report['record_summary']['quote_modes']}",
            f"- ToM records: {report['tom_summary']['tom_record_count']}, ToM defects: {report['tom_summary']['tom_defect_count']}, edges: {report['tom_summary']['edge_count']}, edge defects: {report['tom_summary']['edge_defect_count']}",
            f"- recall checks: {report['memory_summary']['recall_pass_count']}/{report['memory_summary']['recall_check_count']} passed",
            f"- repair queue rows: {report['repair_count']}",
            "",
            "## Critical Checks",
            "",
        ]
    )
    for key, value in report["critical_checks"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Recall Checks", ""])
    for row in recall_rows:
        lines.append(
            f"- {row.get('fixture_id')}: passed={row.get('passed')}, expected={row.get('expected_key')}, "
            f"rank={row.get('expected_rank')}, top={row.get('top_key')}, failures={row.get('failures')}"
        )
    lines.extend(["", "## Required Next Step", ""])
    if report["critical_checks_passed"]:
        lines.append("No critical verifier repairs are queued by this run.")
    else:
        lines.append("Critical checks did not all pass. Execute or patch rows in `repair_queue.jsonl`, then rerun this verifier.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.command("verify-book")
def verify_book_command(
    book_id: Annotated[str, typer.Option("--book-id")],
    book: Annotated[str, typer.Option("--book")],
    persona_id: Annotated[str, typer.Option("--persona-id")],
    book_root: Annotated[Path, typer.Option("--book-root", exists=True, file_okay=False, readable=True)],
    fact_root: Annotated[Path, typer.Option("--fact-root", exists=True, file_okay=False, readable=True)],
    out_root: Annotated[Path | None, typer.Option("--out-root")] = None,
    fixture_path: Annotated[Path | None, typer.Option("--fixture-path", exists=True, dir_okay=False, readable=True)] = None,
    memory_url: Annotated[str, typer.Option("--memory-url")] = "http://127.0.0.1:8601",
    require_memory: Annotated[bool, typer.Option("--require-memory/--skip-memory")] = False,
    allow_needs_repair: Annotated[bool, typer.Option("--allow-needs-repair")] = False,
    k: Annotated[int, typer.Option("--k", min=1)] = 10,
) -> None:
    output_root = out_root or Path("/mnt/storage12tb/skills/book-extraction-verifier/outputs") / book_id
    report = verify(
        VerifyConfig(
            book_id=book_id,
            book=book,
            persona_id=persona_id,
            book_root=book_root,
            fact_root=fact_root,
            out_root=output_root,
            fixture_path=fixture_path,
            memory_url=memory_url,
            require_memory=require_memory,
            allow_needs_repair=allow_needs_repair,
            k=k,
        )
    )
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    if not report["critical_checks_passed"] and not allow_needs_repair:
        raise typer.Exit(1)


@app.command("doctor")
def doctor_command() -> None:
    typer.echo(json.dumps({"ok": True, "skill": "book-extraction-verifier", "memory_writes_performed": False}, indent=2))


if __name__ == "__main__":
    app()
