from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator


SKILL_ROOT = Path(__file__).parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "prepare_revision_qualification.py"
PREPARE_SCHEMA = SKILL_ROOT / "schemas" / "revision_memory_prepare_receipt.v1.schema.json"
VERIFY_SCHEMA = SKILL_ROOT / "schemas" / "revision_memory_verify_receipt.v1.schema.json"
SOURCE_COMMIT = "74ff9f50539bcd4df0d180d727a8da7fa0232f3c"
REVISION_ID = "rev_repair_a8b93ffeca8f"
COLLECTION = "project_knowledge"

REQUIRED_BY_PHASE = {
    "01": ("dream_request", "residue_links"),
    "02": ("story_contract",),
    "03": ("crew_contract", "crew_gate_receipt"),
    "04": (
        "contact_sheet_requirements",
        "contact_sheet_manifest",
        "contact_sheet_gate_receipt",
    ),
    "05": ("voice_evidence",),
    "06": ("script_contract",),
    "07": ("storyboard_packet",),
    "08": ("media_lock",),
    "09": ("video_provider_scorecard", "provider_final_gate"),
    "10": ("panel_distillation_contract", "provider_schema_receipt"),
}


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def write_revision(tmp_path: Path) -> tuple[Path, Path]:
    run_root = tmp_path / "pipeline-complete"
    revision_root = run_root / ".persona-dream" / "revisions" / REVISION_ID
    revision_root.mkdir(parents=True)

    artifacts: dict[str, dict[str, Any]] = {}
    for phase_id, artifact_ids in REQUIRED_BY_PHASE.items():
        phase_root = revision_root / f"phase_{phase_id}"
        phase_root.mkdir()
        for artifact_id in artifact_ids:
            path = phase_root / f"{artifact_id}.json"
            payload = json.dumps(
                {
                    "schema": f"fixture.{artifact_id}.v1",
                    "status": "PASS",
                    "artifact_id": artifact_id,
                    "phase_id": phase_id,
                },
                sort_keys=True,
            ).encode("utf-8")
            path.write_bytes(payload)
            artifacts[artifact_id] = {
                "phase_id": phase_id,
                "relative_path": str(path.relative_to(revision_root)),
                "sha256": sha256_bytes(payload),
                "size_bytes": len(payload),
                "kind": "json",
                "media_type": "application/json",
                "schema": None,
                "consumer_contract": None,
                "roles": ["required_evidence"],
            }

    optional_count = 318 - len(artifacts)
    for index in range(optional_count):
        phase_id = f"{(index % 10) + 1:02d}"
        phase_root = revision_root / f"phase_{phase_id}"
        artifact_id = f"phase{phase_id}.optional.{index:03d}"
        path = phase_root / f"optional_{index:03d}.txt"
        payload = f"optional artifact {index}\n".encode("utf-8")
        path.write_bytes(payload)
        artifacts[artifact_id] = {
            "phase_id": phase_id,
            "relative_path": str(path.relative_to(revision_root)),
            "sha256": sha256_bytes(payload),
            "size_bytes": len(payload),
            "kind": "text",
            "media_type": "text/plain",
            "schema": None,
            "consumer_contract": None,
            "roles": ["optional_evidence"],
        }

    manifest = {
        "schema": "persona_dream.revision_manifest.v1",
        "runId": "pipeline-complete",
        "revisionId": REVISION_ID,
        "sourceRevisionId": "rev_0001",
        "selectedThroughPhase": "10",
        "status": "FROZEN_ALL_LOCAL_GATES_PASS",
    }
    (revision_root / "revision_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index_value = {
        "schema": "persona_dream.revision_artifact_index.v1",
        "run_id": "pipeline-complete",
        "revision_id": REVISION_ID,
        "artifact_count": len(artifacts),
        "required_artifact_count": 16,
        "artifacts": artifacts,
    }
    (revision_root / "revision_artifact_index.json").write_text(
        json.dumps(index_value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run_root, revision_root


class FakeMemoryState:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, dict[str, Any]]] = {}
        self.fail_semantic = False
        self.dense_score = 0.77
        self.requests: list[tuple[str, dict[str, Any]]] = []


@contextmanager
def fake_memory_server() -> Iterator[tuple[str, FakeMemoryState]]:
    state = FakeMemoryState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:
            return

        def send_json(self, status: int, value: dict[str, Any]) -> None:
            payload = json.dumps(value, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            state.requests.append((self.path, payload))

            if self.path == "/upsert":
                collection = str(payload["collection"])
                documents = payload["documents"]
                skip_embedding = bool(payload.get("skip_embedding", False))
                if state.fail_semantic and not skip_embedding:
                    self.send_json(
                        500,
                        {
                            "detail": (
                                "semantic embedding failed at "
                                "http://127.0.0.1:8603/embed/batch"
                            )
                        },
                    )
                    return
                stored = state.collections.setdefault(collection, {})
                inserted = 0
                updated = 0
                for raw_document in documents:
                    key = raw_document["_key"]
                    existing = stored.get(key, {})
                    if key in stored:
                        updated += 1
                    else:
                        inserted += 1
                    document = {**existing, **raw_document}
                    if not skip_embedding:
                        text = str(document.get("retrieval_text") or "")
                        document.update(
                            {
                                "qdrant_collection": "memory_semantic",
                                "qdrant_point_id": f"point-{key}",
                                "embedding_model": "fake-embedding-model",
                                "embedding_version": "v1",
                                "text_hash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
                                "semantic_sync_state": "synced",
                            }
                        )
                    stored[key] = document
                self.send_json(
                    200,
                    {
                        "collection": collection,
                        "inserted": inserted,
                        "updated": updated,
                        "errors": [],
                        "total": len(documents),
                        "writeahead_path": f"/tmp/{collection}.jsonl",
                    },
                )
                return

            if self.path == "/list":
                collection = str(payload["collection"])
                documents = list(state.collections.get(collection, {}).values())
                filters = payload.get("filters") or {}
                documents = [
                    document
                    for document in documents
                    if all(document.get(key) == value for key, value in filters.items())
                ]
                documents.sort(key=lambda item: item["_key"])
                self.send_json(
                    200,
                    {
                        "collection": collection,
                        "total": len(documents),
                        "offset": 0,
                        "limit": 500,
                        "count": len(documents),
                        "documents": documents,
                    },
                )
                return

            if self.path == "/recall":
                collection = COLLECTION
                documents = list(state.collections.get(collection, {}).values())
                selected = [
                    document
                    for document in documents
                    if document.get("record_type") in {"revision", "phase"}
                ][:8]
                self.send_json(
                    200,
                    {
                        "found": bool(selected),
                        "items": [
                            {
                                "_key": document["_key"],
                                "_source": collection,
                                "scores": {
                                    "bm25": 0.4,
                                    "graph": 0.0,
                                    "dense": state.dense_score,
                                },
                            }
                            for document in selected
                        ],
                    },
                )
                return

            self.send_json(404, {"detail": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_command(run_root: Path, memory_url: str, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-root",
            str(run_root),
            "--revision-id",
            REVISION_ID,
            "--source-commit",
            SOURCE_COMMIT,
            "--memory-url",
            memory_url,
            "--collection",
            COLLECTION,
            "--connect-timeout",
            "1",
            "--read-timeout",
            "5",
            "--test-fixture",
            command,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def validate_schema(path: Path, schema_path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
    return value


def test_prepare_and_verify_revision_records(tmp_path: Path) -> None:
    run_root, revision_root = write_revision(tmp_path)
    with fake_memory_server() as (memory_url, state):
        prepared = run_command(run_root, memory_url, "prepare")
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        prepare_receipt = validate_schema(
            revision_root / "revision_memory_prepare_receipt.json",
            PREPARE_SCHEMA,
        )
        assert prepare_receipt["mocked"] is True
        assert prepare_receipt["live"] is False
        assert prepare_receipt["hash_validation"]["artifact_count"] == 318
        assert prepare_receipt["hash_validation"]["matched_count"] == 318
        assert prepare_receipt["records"]["returned_counts"] == {
            "revision": 1,
            "phase": 10,
            "required_artifact": 16,
            "total": 27,
        }

        verified = run_command(run_root, memory_url, "verify")
        assert verified.returncode == 0, verified.stdout + verified.stderr
        verify_receipt = validate_schema(
            revision_root / "revision_memory_verify_receipt.json",
            VERIFY_SCHEMA,
        )
        assert verify_receipt["semantic_sync"]["recall"]["max_dense"] > 0.0
        assert verify_receipt["semantic_sync"]["recall"]["matching_identity_count"] >= 1

        documents = state.collections[COLLECTION]
        assert len(documents) == 27
        revision = next(
            document
            for document in documents.values()
            if document["record_type"] == "revision"
        )
        assert revision["lifecycle_state"] == "VERIFIED"
        assert sum(document["record_type"] == "phase" for document in documents.values()) == 10
        assert sum(
            document["record_type"] == "required_artifact"
            for document in documents.values()
        ) == 16

        repeated_prepare = run_command(run_root, memory_url, "prepare")
        assert repeated_prepare.returncode == 0, repeated_prepare.stdout + repeated_prepare.stderr
        revision_after = next(
            document
            for document in documents.values()
            if document["record_type"] == "revision"
        )
        assert revision_after["lifecycle_state"] == "VERIFIED"


def test_semantic_upsert_failure_leaves_prepared_control_record(tmp_path: Path) -> None:
    run_root, revision_root = write_revision(tmp_path)
    with fake_memory_server() as (memory_url, state):
        state.fail_semantic = True
        completed = run_command(run_root, memory_url, "prepare")
        assert completed.returncode == 3
        output = json.loads(completed.stdout)
        assert output["status"] == "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED"
        assert output["details"]["control_record_persisted"] is True
        assert not (revision_root / "revision_memory_prepare_receipt.json").exists()

        documents = state.collections[COLLECTION]
        assert len(documents) == 1
        revision = next(iter(documents.values()))
        assert revision["record_type"] == "revision"
        assert revision["lifecycle_state"] == "PREPARED"
        assert "qdrant_point_id" not in revision


def test_dense_recall_is_required_before_verified_state(tmp_path: Path) -> None:
    run_root, revision_root = write_revision(tmp_path)
    with fake_memory_server() as (memory_url, state):
        prepared = run_command(run_root, memory_url, "prepare")
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        state.dense_score = 0.0
        verified = run_command(run_root, memory_url, "verify")
        assert verified.returncode == 3
        output = json.loads(verified.stdout)
        assert output["status"] == "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED"
        assert not (revision_root / "revision_memory_verify_receipt.json").exists()
        revision = next(
            document
            for document in state.collections[COLLECTION].values()
            if document["record_type"] == "revision"
        )
        assert revision["lifecycle_state"] == "PREPARED"


def test_prepare_recomputes_every_indexed_hash(tmp_path: Path) -> None:
    run_root, revision_root = write_revision(tmp_path)
    target = revision_root / "phase_02" / "story_contract.json"
    target.write_text('{"tampered":true}\n', encoding="utf-8")
    with fake_memory_server() as (memory_url, state):
        completed = run_command(run_root, memory_url, "prepare")
        assert completed.returncode == 2
        output = json.loads(completed.stdout)
        assert output["status"] == "BLOCKED_REVISION_HASH_MISMATCH"
        assert state.requests == []


def test_prepare_rejects_indexed_symlink(tmp_path: Path) -> None:
    run_root, revision_root = write_revision(tmp_path)
    target = revision_root / "phase_02" / "story_contract.json"
    outside = tmp_path / "outside.json"
    outside.write_text('{"outside":true}\n', encoding="utf-8")
    target.unlink()
    target.symlink_to(outside)
    with fake_memory_server() as (memory_url, state):
        completed = run_command(run_root, memory_url, "prepare")
        assert completed.returncode == 2
        output = json.loads(completed.stdout)
        assert output["status"] == "BLOCKED_REVISION_SYMLINK_FORBIDDEN"
        assert state.requests == []
