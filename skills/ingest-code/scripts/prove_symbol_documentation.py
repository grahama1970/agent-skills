#!/usr/bin/env python3
"""Prove provenance-safe symbol documentation metadata on real files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import ingest_code  # noqa: E402
from code_graph_artifact import write_code_graph_bundle  # noqa: E402
from symbol_summary import make_derived_summary, summary_evidence  # noqa: E402


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _setup_repo(root: Path) -> Path:
    repo = root / "fixture-repo"
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src" / "documented.py").write_text(
        "def documented_loader(path):\n"
        "    \"\"\"Load one text file into a source packet.\"\"\"\n"
        "    return {'body': path.read_text()}\n",
        encoding="utf-8",
    )
    (repo / "src" / "undocumented.py").write_text(
        "def build_index(path):\n"
        "    payload = {'body': path.read_text()}\n"
        "    return payload\n",
        encoding="utf-8",
    )
    (repo / "src" / "generated_api_pb2.py").write_text(
        "# generated file\n"
        "class Api:\n"
        "    pass\n",
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "agent@example.invalid")
    _git(repo, "config", "user.name", "Agent")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _by_name(records: list[Any]) -> dict[str, Any]:
    return {record.symbol_name: record for record in records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/ingest-code-symbol-documentation-proof"))
    args = parser.parse_args()

    out = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    repo = _setup_repo(out)
    source_files = sorted((repo / "src").glob("*.py"))
    before_hashes = {path.name: _sha256_file(path) for path in source_files}

    records = []
    for path in source_files:
        records.extend(ingest_code._scan_treesitter_symbol_records_for_file(path, repo, "code"))
    records_by_name = _by_name(records)

    missing = records_by_name["build_index"]
    evidence = summary_evidence(missing)
    derived = make_derived_summary(
        text="Builds an index from one path by reading text and returning a payload.",
        evidence=evidence,
        generator="deterministic-proof",
        model="none",
        prompt="Summarize build_index from symbol facts.",
        created_at="2026-08-09T15:45:00Z",
        limitations=["unreviewed synthetic proof summary"],
    )
    current_summary_record = replace(missing, derived_summary=derived)
    stale_summary_record = replace(missing, content_hash="changed-source-hash", derived_summary=derived)

    bundle_records = [
        records_by_name["documented_loader"],
        current_summary_record,
        stale_summary_record,
        records_by_name["Api"],
    ]
    bundle = write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch=ingest_code._current_branch(repo),
        commit=ingest_code._current_commit(repo),
        scan_roots=[repo],
        files=source_files,
        symbols=bundle_records,
        edges=[],
    )
    after_hashes = {path.name: _sha256_file(path) for path in source_files}
    symbol_rows = _jsonl(Path(bundle["path"]) / "symbols.jsonl")
    docs = [row["memory_document"] for row in symbol_rows]
    documented_doc = next(doc for doc in docs if doc["symbol_name"] == "documented_loader")
    current_doc = next(doc for doc in docs if doc["symbol_name"] == "build_index" and doc["content_hash"] == missing.content_hash)
    stale_doc = next(doc for doc in docs if doc["symbol_name"] == "build_index" and doc["content_hash"] == "changed-source-hash")
    generated_doc = next(doc for doc in docs if doc["symbol_name"] == "Api")

    assertions = {
        "source_files_unchanged": before_hashes == after_hashes,
        "scanner_preserves_authored_docstring": documented_doc["source_docstring"] == "Load one text file into a source packet.",
        "authored_docstring_not_duplicated_in_retrieval_text": documented_doc["text"].count("Load one text file into a source packet.") == 1,
        "missing_public_io_requires_documentation": current_doc["documentation_need"] == "required"
        and "external_io" in current_doc["documentation_need_reasons"],
        "current_derived_summary_used_as_unreviewed_purpose": current_doc["purpose_source"] == "derived"
        and current_doc["derived_summary"]["status"] == "derived_unreviewed",
        "stale_derived_summary_rejected": stale_doc["purpose_source"] == "none" and stale_doc["derived_summary"] is None,
        "generated_file_is_exempt": generated_doc["source_docstring_status"] == "generated_file"
        and generated_doc["documentation_need"] == "exempt",
        "bundle_readback_has_evidence_hashes": all(
            row.get("summary_evidence", {}).get("evidence_sha256", "").startswith("sha256:")
            and row.get("retrieval_text_sha256", "").startswith("sha256:")
            for row in symbol_rows
        ),
    }
    summary = {
        "schema": "ingest-code.symbol_documentation_proof.v1",
        "mocked": False,
        "live": True,
        "repo": str(repo),
        "bundle_path": bundle["path"],
        "bundle_checksums_sha256": _sha256_file(Path(bundle["checksums"])),
        "source_hashes_before": before_hashes,
        "source_hashes_after": after_hashes,
        "symbols_read_back": len(symbol_rows),
        "assertions": assertions,
    }
    summary["status"] = "pass" if all(assertions.values()) else "fail"
    _write_json(out / "proof-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
