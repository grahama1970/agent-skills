from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_bytes(path: Path, value: bytes) -> tuple[Path, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path, sha256_bytes(value)


class FakeMemoryState:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, dict[str, Any]]] = {}
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.dense_score = 0.81


@contextmanager
def fake_memory_server() -> Iterator[tuple[str, FakeMemoryState]]:
    state = FakeMemoryState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
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
                stored = state.collections.setdefault(collection, {})
                inserted = 0
                updated = 0
                for raw in payload.get("documents", []):
                    key = str(raw["_key"])
                    inserted += int(key not in stored)
                    updated += int(key in stored)
                    document = {**stored.get(key, {}), **raw}
                    text = str(document.get("retrieval_text") or "")
                    document.update(
                        {
                            "qdrant_collection": "fake-qdrant",
                            "qdrant_point_id": f"point-{key}",
                            "embedding_model": "fake-model",
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
                        "total": inserted + updated,
                        "errors": [],
                        "writeahead_path": f"/tmp/{collection}.jsonl",
                    },
                )
                return
            if self.path == "/list":
                collection = str(payload["collection"])
                documents = list(state.collections.get(collection, {}).values())
                filters = payload.get("filters") or {}
                documents = [
                    item
                    for item in documents
                    if all(item.get(key) == value for key, value in filters.items())
                ]
                documents.sort(key=lambda item: item["_key"])
                self.send_json(
                    200,
                    {
                        "collection": collection,
                        "total": len(documents),
                        "count": len(documents),
                        "offset": 0,
                        "limit": int(payload.get("limit") or 500),
                        "documents": documents,
                    },
                )
                return
            if self.path == "/recall":
                collections = payload.get("collections") or list(state.collections)
                items: list[dict[str, Any]] = []
                for collection in collections:
                    for document in state.collections.get(str(collection), {}).values():
                        if document.get("record_type") == "phase11_boundary":
                            items.append(
                                {
                                    "doc": document,
                                    "scores": {"bm25": 0.2, "graph": 0.0, "dense": state.dense_score},
                                }
                            )
                self.send_json(200, {"found": bool(items), "items": items})
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


def make_compilation_inputs(tmp_path: Path):
    import sys

    skill_root = Path(__file__).resolve().parents[1]
    scripts = skill_root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from phase11_canonical_common import ActiveContext, CompilationInputs, ProviderSnapshotResult, canonical_sha256

    run_root = tmp_path / "pipeline-complete"
    revision_id = "rev_fixture"
    revision_root = run_root / ".persona-dream" / "revisions" / revision_id
    revision_root.mkdir(parents=True)
    artifacts: dict[str, dict[str, Any]] = {}
    locked_assets: list[dict[str, Any]] = []
    urls: dict[str, str] = {}
    for number in range(1, 5):
        panel_id = f"sb_{number:03d}"
        for role in ("start_frame", "end_frame"):
            artifact_id = f"{panel_id}.{role}"
            relative = f"phase_07_storyboard_live_tau/generated_storyboard_frames/{panel_id}_{role}.png"
            path, digest = write_bytes(revision_root / relative, b"PNG" + artifact_id.encode())
            artifacts[artifact_id] = {
                "phase_id": "07",
                "relative_path": relative,
                "sha256": digest,
                "size_bytes": path.stat().st_size,
                "kind": "image",
                "media_type": "image/png",
                "roles": ["accepted_frame"],
            }
            locked_assets.append(
                {
                    "asset_id": artifact_id,
                    "panel_id": panel_id,
                    "frame_role": role,
                    "sha256": digest,
                    "path": relative,
                }
            )
            urls[artifact_id] = f"https://example.invalid/repo/{relative}"

    for identity, suffix in (("embry", "01-embry_character_sheet.jpg"), ("kai", "02-kai_character_sheet.png")):
        relative = f"phase_07_storyboard_live_tau/references/{suffix}"
        path, digest = write_bytes(revision_root / relative, b"IMAGE" + identity.encode())
        artifact_id = f"phase07.reference.{identity}"
        artifacts[artifact_id] = {
            "phase_id": "07",
            "relative_path": relative,
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "kind": "image",
            "media_type": "image/jpeg" if suffix.endswith("jpg") else "image/png",
            "roles": ["identity_reference"],
        }
        urls[artifact_id] = f"https://example.invalid/repo/{relative}"

    index_path = write_json(
        revision_root / "revision_artifact_index.json",
        {
            "schema": "persona_dream.revision_artifact_index.v1",
            "run_id": run_root.name,
            "revision_id": revision_id,
            "artifact_count": len(artifacts),
            "required_artifact_count": 0,
            "artifacts": artifacts,
        },
    )
    manifest_path = write_json(
        revision_root / "revision_manifest.json",
        {
            "schema": "persona_dream.revision_manifest.v1",
            "runId": run_root.name,
            "revisionId": revision_id,
            "sourceRevisionId": "rev_source",
            "status": "FROZEN_ALL_LOCAL_GATES_PASS",
        },
    )
    activation_path = write_json(
        revision_root / "revision_activation_receipt.json",
        {
            "schema": "persona_dream.revision_activation_receipt.v1",
            "status": "PASS_ACTIVE_CONSISTENT",
            "source_commit": "a" * 40,
            "memory_url": "http://127.0.0.1:8601",
            "collection": "project_knowledge",
            "memory": {"active_pointer_key": "pd_active_fixture"},
        },
    )
    pointer_path = write_json(
        run_root / ".persona-dream" / "state" / "active_revision.json",
        {
            "schemaVersion": "persona_dream.active_revision_pointer.v1",
            "runId": run_root.name,
            "revisionId": revision_id,
            "revisionManifestSha256": sha256_bytes(manifest_path.read_bytes()),
        },
    )
    context = ActiveContext(
        run_root=run_root.resolve(),
        revision_root=revision_root.resolve(),
        run_id=run_root.name,
        revision_id=revision_id,
        source_revision_id="rev_source",
        source_commit="a" * 40,
        runtime_release_id="fixture@" + "a" * 40,
        activation_transaction_id="activation-" + "b" * 32,
        activation_receipt_path=activation_path.resolve(),
        activation_receipt={
            "memory": {"active_pointer_key": "pd_active_fixture"},
            "mocked": True,
            "live": False,
        },
        artifact_index_path=index_path.resolve(),
        artifact_index=json.loads(index_path.read_text()),
        artifact_index_sha256=sha256_bytes(index_path.read_bytes()),
        revision_manifest_path=manifest_path.resolve(),
        revision_manifest_sha256=sha256_bytes(manifest_path.read_bytes()),
        local_pointer_path=pointer_path.resolve(),
        local_pointer_sha256=sha256_bytes(pointer_path.read_bytes()),
        memory_url="http://127.0.0.1:8601",
        collection="project_knowledge",
        mocked=True,
        live=False,
    )

    prompts = []
    ranges = ((0, 2.5), (2.5, 5), (5, 7.5), (7.5, 10))
    durations = (2, 3, 2, 3)
    for number, ((start, end), duration) in enumerate(zip(ranges, durations), 1):
        panel_id = f"SB_{number:03d}"
        prompt = (
            f"{panel_id} provider-distilled shot for Kling v3 Pro I2V. "
            f"Create storyboard panel {panel_id} for a 10-second surf scene, time range {start}s-{end}s. "
            "Embry and Kai hold position near the lineup. Preserve @Element1 Embry and @Element2 Kai identity continuity. "
        )
        if number == 3:
            prompt += "Kai then gives one restrained cue: 'If we paddle now, we're cutting across the lineup.' Embry remains the decision-maker. Dialogue cue: Kai quietly says, \"If we paddle now, we're cutting across the lineup.\" Keep it restrained. "
        prompt += "Avoid identity drift."
        prompts.append({"duration": str(duration), "prompt": prompt})

    elements = [
        {
            "frontal_image_url": urls["phase07.reference.embry"],
            "reference_image_urls": [urls["sb_002.start_frame"], urls["sb_004.start_frame"]],
        },
        {
            "frontal_image_url": urls["phase07.reference.kai"],
            "reference_image_urls": [urls["sb_001.start_frame"], urls["sb_003.start_frame"]],
        },
    ]
    request_input = {
        "prompt": None,
        "multi_prompt": prompts,
        "start_image_url": urls["sb_001.start_frame"],
        "duration": "10",
        "generate_audio": False,
        "end_image_url": urls["sb_004.end_frame"],
        "elements": elements,
        "shot_type": "customize",
        "negative_prompt": "blur and low quality",
        "cfg_scale": 0.5,
    }
    candidate_path = write_json(
        revision_root / "phase_11_submit_return" / "preflight" / "phase11_payload_binding.json",
        {
            "schema": "persona_dream.phase11_payload_binding.v1",
            "status": "BLOCKED_AWAITING_HUMAN_APPROVAL",
            "run_id": run_root.name,
            "revision_id": revision_id,
            "provider": "fal.ai",
            "model": "fal-ai/kling-video/v3/standard/image-to-video",
            "mode": "standard",
            "input": request_input,
            "actual_provider_call_attempts": 0,
        },
    )
    phase10_path = write_json(
        revision_root / "phase_10_provider_contract" / "final_provider_payload_by_panel.json",
        {
            "schema_version": "persona-dream.final-provider-payload-by-panel.v1",
            "endpoint": "fal-ai/kling-video/v3/standard/image-to-video",
            "assembled_request_preview": {
                "model": "fal-ai/kling-video/v3/standard/image-to-video",
                "input": request_input,
                "submitted": False,
            },
            "actual_provider_call_attempts": 0,
        },
    )
    media_lock_path = write_json(
        revision_root / "phase_08_media_lock" / "storyboard_media_lock_manifest.json",
        {"schema": "persona_dream.storyboard_media_lock_manifest.v1", "assets": locked_assets},
    )
    from phase11_payload_binding import build_payload_binding

    binding = build_payload_binding(
        context=context,
        phase10_payload_path=phase10_path,
        media_lock_path=media_lock_path,
        publication_commit="0" * 40,
    )
    write_json(candidate_path, binding)
    request_input = dict(binding["input"])
    urls = {
        record["artifact_id"]: record["public_url"]
        for record in [
            binding["media_roles"]["global_start_anchor"],
            binding["media_roles"]["global_end_anchor"],
            *binding["media_roles"]["continuity_only"],
            *[pack["frontal"] for pack in binding["media_roles"]["character_element_packs"]],
        ]
    }
    provider_root = revision_root / "phase_11_submit_return" / "preflight"
    schema_body = b"fixture fal schema response"
    pricing_body = b"fixture fal pricing response"
    write_bytes(provider_root / "provider_schema_response.body", schema_body)
    write_bytes(provider_root / "provider_pricing_response.body", pricing_body)
    input_schema = {
        "start_image_url": {"required": True},
        "end_image_url": {"required": False},
        "multi_prompt": {},
        "elements": {},
        "generate_audio": {},
        "duration": {"enum": list(range(3, 16))},
    }
    provider_snapshot_value = {
        "schema": "persona_dream.phase11_provider_source_snapshot.v1",
        "status": "PASS_PROVIDER_SOURCE_SNAPSHOT",
        "provider_id": "kling",
        "endpoint": "fal-ai/kling-video/v3/standard/image-to-video",
        "mode": "standard",
        "run_id": run_root.name,
        "revision_id": revision_id,
        "activation_transaction_id": context.activation_transaction_id,
        "retrieved_at": "2026-07-15T10:00:00+00:00",
        "ttl_seconds": 86400,
        "retrieval": {
            "command": [
                "skills/persona-dream/run.sh",
                "capture-phase11-provider-source-snapshot",
                "--run-root",
                "<RUN_ROOT>",
            ],
            "provider_generation_call_attempted": False,
            "actual_provider_call_attempts": 0,
        },
        "phase10_endpoint_migration": {
            "status": "NOT_REQUIRED",
            "from_endpoint": "fal-ai/kling-video/v3/standard/image-to-video",
            "to_endpoint": "fal-ai/kling-video/v3/standard/image-to-video",
            "phase10_payload_sha256": sha256_bytes(phase10_path.read_bytes()),
            "candidate_binding_sha256": sha256_bytes(candidate_path.read_bytes()),
            "reason": "Fixture already uses the canonical Standard endpoint.",
        },
        "schema_source": {
            "requested_url": "https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api",
            "final_url": "https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api",
            "http_status": 200,
            "content_type": "text/html",
            "body_relative_path": "provider_schema_response.body",
            "remote_content_sha256": sha256_bytes(schema_body),
            "normalized_schema_sha256": canonical_sha256(input_schema),
            "input_schema": input_schema,
        },
        "pricing_source": {
            "requested_url": "https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video",
            "final_url": "https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video",
            "http_status": 200,
            "content_type": "text/html",
            "body_relative_path": "provider_pricing_response.body",
            "remote_content_sha256": sha256_bytes(pricing_body),
            "currency": "USD",
            "usd_per_second_audio_off": 0.084,
            "usd_per_second_audio_on": 0.126,
            "usd_per_second_voice_control": 0.154,
            "duration_seconds": 10,
            "maximum_expected_cost_usd": 0.84,
        },
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }
    provider_snapshot_path = write_json(
        provider_root / "provider_source_snapshot.json",
        provider_snapshot_value,
    )
    validation_path = write_json(
        run_root / "validation.json",
        {
            "schema": "persona_dream.complete_pipeline_report_validation.v1",
            "status": "PASS",
            "passed_step_count": 15,
            "step_count": 15,
            "first_blocker": None,
        },
    )
    approval_root = revision_root / "phase_11_submit_return" / "preflight" / "approvals"
    transition_path = revision_root / "phase_11_submit_return" / "preflight" / "provider_media_transition_manifest.json"
    return CompilationInputs(
        context=context,
        phase10_payload_path=phase10_path.resolve(),
        phase10_payload=json.loads(phase10_path.read_text()),
        candidate_binding_path=candidate_path.resolve(),
        candidate_binding=json.loads(candidate_path.read_text()),
        media_lock_path=media_lock_path.resolve(),
        media_lock=json.loads(media_lock_path.read_text()),
        provider_snapshot=ProviderSnapshotResult(
            provider_snapshot_value,
            provider_snapshot_path.resolve(),
            sha256_bytes(provider_snapshot_path.read_bytes()),
            (),
        ),
        transition_manifest_path=transition_path.resolve(),
        transition_manifest=None,
        approval_root=approval_root.resolve(),
        validation_path=validation_path.resolve(),
        current=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    ), request_input, urls




class _FixtureFalSyncClient:
    def submit(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("fixture preflight must not submit")

    def get_handle(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("fixture preflight must not get a handle")

    def status(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("fixture preflight must not poll")

    def result(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("fixture preflight must not fetch a result")


class _FixtureFalRequestHandle:
    def status(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("fixture preflight must not poll")

    def get(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("fixture preflight must not fetch a result")


class _FixtureFalModule:
    __version__ = "fixture"
    SyncClient = _FixtureFalSyncClient
    SyncRequestHandle = _FixtureFalRequestHandle


class _FixtureFalImplementation:
    MAX_ATTEMPTS = 10


def fixture_fal_importer(name: str) -> Any:
    if name == "fal_client":
        return _FixtureFalModule
    if name == "fal_client.client":
        return _FixtureFalImplementation
    raise ImportError(name)


def install_adapter_preflight(inputs: Any) -> Any:
    import sys

    skill_root = Path(__file__).resolve().parents[1]
    scripts = skill_root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import phase11_canonical_common as common
    import phase11_execution_common as execution

    bootstrap = common.compile_bundle(inputs)
    common.write_compiled_bundle(
        inputs.context.revision_root / common.DEFAULT_OUTPUT_RELATIVE,
        *bootstrap,
    )
    receipt = execution.run_adapter_preflight(
        inputs,
        current=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
        poll_interval_seconds=5,
        max_polls=180,
        adapter_script_path=skill_root / "scripts" / "phase11_fal_canary_adapter.py",
        environ={"FAL_API_KEY": "fixture-secret-never-persisted"},
        importer=fixture_fal_importer,
        ffprobe_resolver=lambda _name: "/usr/bin/ffprobe",
    )
    assert receipt["status"] == "PASS_PHASE11_ADAPTER_PREFLIGHT", receipt
    assert receipt["actual_provider_call_attempts"] == 0
    return inputs
