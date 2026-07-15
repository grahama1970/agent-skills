from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator


SKILL_ROOT = Path(__file__).parents[1]
ACTIVATION_SCRIPT = SKILL_ROOT / "scripts" / "activate_revision_qualification.py"
PREPARE_SCRIPT = SKILL_ROOT / "scripts" / "prepare_revision_qualification.py"
ACTIVATION_SCHEMA = SKILL_ROOT / "schemas" / "revision_activation_receipt.v1.schema.json"
PREPARE_TESTS = SKILL_ROOT / "tests" / "test_revision_memory_qualification.py"
RUNS_TS = SKILL_ROOT / "server" / "src" / "runs.ts"
PATHS_TS = SKILL_ROOT / "server" / "src" / "paths.ts"


def load_module(name: str, path: Path) -> ModuleType:
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MEMORY_FIXTURE = load_module("persona_dream_memory_fixture_helpers", PREPARE_TESTS)
ACTIVATION = load_module("persona_dream_activation_script", ACTIVATION_SCRIPT)
SOURCE_COMMIT = "62c255c9b8d380079ce37c39cab3ab9adada30e3"
REVISION_ID = MEMORY_FIXTURE.REVISION_ID
COLLECTION = MEMORY_FIXTURE.COLLECTION


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")




def install_storyboard_fixture(revision_root: Path) -> None:
    index_path = revision_root / "revision_artifact_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    artifacts = index["artifacts"]
    packet_entry = artifacts["storyboard_packet"]
    packet_path = revision_root / packet_entry["relative_path"]
    frame_root = revision_root / "phase_07" / "generated_storyboard_frames"
    frame_root.mkdir(parents=True, exist_ok=True)

    panels: list[dict[str, Any]] = []
    for number in range(1, 5):
        panel_id = f"sb_{number:03d}"
        panel: dict[str, Any] = {
            "panel_id": panel_id,
            "time_range": {"start_s": (number - 1) * 2.5, "end_s": number * 2.5},
        }
        for role in ("start_frame", "end_frame"):
            filename = f"{panel_id}_{role}.png"
            frame_path = frame_root / filename
            frame_bytes = b"\x89PNG\r\n\x1a\n" + f"{panel_id}:{role}".encode("ascii")
            frame_path.write_bytes(frame_bytes)
            artifact_id = f"{panel_id}.{role}"
            frame_sha256 = sha256_file(frame_path)
            artifacts[artifact_id] = {
                "phase_id": "07",
                "relative_path": str(frame_path.relative_to(revision_root)),
                "sha256": frame_sha256,
                "size_bytes": len(frame_bytes),
                "kind": "image",
                "media_type": "image/png",
                "schema": None,
                "consumer_contract": None,
                "roles": ["optional_evidence", "accepted_frame", artifact_id.replace(".", "_")],
            }
            panel[role] = {
                "accepted_frame": {
                    "path": f"/stale/checkout/{filename}",
                    "sha256": frame_sha256,
                }
            }
        panels.append(panel)

    packet = {
        "schema": "persona_dream.storyboard_packet.v1",
        "status": "PASS_PANEL_REVIEWED",
        "accepted": True,
        "panel_count": 4,
        "duration_seconds": 10,
        "source_context": {
            "core_idea": MEMORY_FIXTURE.IDEA_TEXT,
            "characters": ["Embry", "Kai"],
            "activity": "surfing at Kahaluʻu Bay over a lava reef during a summer swell",
            "social_constraint": "local surf etiquette and lineup order",
        },
        "panels": panels,
    }
    write_json(packet_path, packet)
    packet_entry["sha256"] = sha256_file(packet_path)
    packet_entry["size_bytes"] = packet_path.stat().st_size
    index["artifact_count"] = len(artifacts)
    write_json(index_path, index)
    MEMORY_FIXTURE.install_idea_lineage_fixture(revision_root)


def write_activation_inputs(run_root: Path, revision_root: Path) -> tuple[Path, Path, Path]:
    install_storyboard_fixture(revision_root)
    manifest_path = revision_root / "revision_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_revision_id = manifest["sourceRevisionId"]
    manifest_sha256 = sha256_file(manifest_path)

    # Mark this synthetic tree as a fixture so run-detail will only accept a
    # mocked activation receipt in the focused wiring test.
    write_json(
        run_root / "dream_revision_manifest.v1.json",
        {
            "schema": "persona_dream.revision_state.v1",
            "active_revision_id": REVISION_ID,
            "repair_enabled": True,
            "fixture": True,
        },
    )
    pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"
    lineage = MEMORY_FIXTURE.install_idea_lineage_fixture(revision_root)
    write_json(
        pointer_path,
        {
            "schemaVersion": "persona_dream.active_revision_pointer.v1",
            "runId": run_root.name,
            "revisionId": REVISION_ID,
            "revisionRoot": str(revision_root),
            "revisionManifestSha256": manifest_sha256,
            "ideaId": lineage.idea_id,
            "ideaSha256": lineage.idea_sha256,
        },
    )

    work_order_id = "repair-a8b93ffeca8f6014"
    work_order_path = (
        run_root
        / ".persona-dream"
        / "repair"
        / "work-orders"
        / f"{work_order_id}.json"
    )
    work_order = {
        "schemaVersion": "persona_dream.repair_work_order.v1",
        "workOrderId": work_order_id,
        "dedupKey": "a8b93ffeca8f6014fda3572916f787f606e4814f74cd8fe9a5ea1b66249ea3ff",
        "runId": run_root.name,
        "runRoot": str(run_root),
        "sourceRevisionId": source_revision_id,
        "targetRevisionId": REVISION_ID,
        "createdAt": "2026-07-11T15:16:04.145Z",
        "detection": {
            "earliestStalePhase": "01",
            "selectedThroughPhase": "10",
            "phaseRange": [f"{phase:02d}" for phase in range(1, 11)],
            "reasons": [{"phaseId": "01", "code": "dream_request"}],
        },
        "policy": {
            "maxAttemptsPerPhase": 3,
            "forbiddenSideEffects": [
                "external_network",
                "public_media_publication",
                "paid_provider_call",
                "provider_submission",
                "human_acceptance_fabrication",
            ],
            "stopBeforePhase": "11",
        },
        "status": "REQUESTED",
    }
    write_json(work_order_path, work_order)

    queue_path = (
        run_root
        / ".persona-dream"
        / "repair"
        / "tau-queue"
        / f"{work_order_id}.json"
    )
    write_json(
        queue_path,
        {
            "schemaVersion": "persona_dream.tau_repair_queue_item.v1",
            "status": "QUEUED",
            "queuedAt": "2026-07-11T15:16:04.145Z",
            "workOrderPath": str(work_order_path),
            "workOrder": work_order,
        },
    )
    return pointer_path, work_order_path, queue_path


def run_activation(run_root: Path, memory_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ACTIVATION_SCRIPT),
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
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def prepare_and_verify(run_root: Path, memory_url: str) -> None:
    for command in ("prepare", "verify"):
        completed = subprocess.run(
            [
                sys.executable,
                str(PREPARE_SCRIPT),
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
        assert completed.returncode == 0, completed.stdout + completed.stderr


def load_activation_receipt(revision_root: Path) -> dict[str, Any]:
    path = revision_root / "revision_activation_receipt.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(ACTIVATION_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
    return value


def fixture_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    run_root, revision_root = MEMORY_FIXTURE.write_revision(tmp_path)
    pointer_path, work_order_path, queue_path = write_activation_inputs(
        run_root, revision_root
    )
    return run_root, revision_root, pointer_path, work_order_path, queue_path


def test_activation_is_hash_bound_live_shaped_and_idempotent(tmp_path: Path) -> None:
    run_root, revision_root, _, _, queue_path = fixture_tree(tmp_path)
    with MEMORY_FIXTURE.fake_memory_server() as (memory_url, state):
        prepare_and_verify(run_root, memory_url)
        first = run_activation(run_root, memory_url)
        assert first.returncode == 0, first.stdout + first.stderr
        receipt_path = revision_root / "revision_activation_receipt.json"
        first_bytes = receipt_path.read_bytes()
        receipt = load_activation_receipt(revision_root)

        assert receipt["status"] == "PASS_ACTIVE_CONSISTENT"
        assert receipt["mocked"] is True
        assert receipt["live"] is False
        assert receipt["actual_provider_call_attempts"] == 0
        assert receipt["provider_ready"] is False
        assert receipt["live_submit_ready"] is False
        assert json.loads(queue_path.read_text(encoding="utf-8"))["status"] == "QUEUED"

        terminal_ref = receipt["local_files"]["queue_terminal_event"]
        terminal_path = run_root / terminal_ref["relative_path"]
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        assert terminal["status"] == "COMPLETED"
        assert sha256_file(terminal_path) == terminal_ref["sha256"]

        stored = state.collections[COLLECTION]
        active = [
            document
            for document in stored.values()
            if document.get("record_type") == "active_revision_pointer"
        ]
        assert len(active) == 1
        assert active[0]["active_revision_id"] == REVISION_ID
        assert "revision_id" not in active[0]
        assert active[0]["semantic_sync_state"] == "synced"
        assert active[0]["queue_terminal_event_sha256"] == terminal_ref["sha256"]
        assert active[0]["provider_live"] is False
        assert active[0]["paid_call_authorized"] is False
        assert active[0]["submitted"] is False
        assert active[0]["provider_ready"] is False
        assert active[0]["live_submit_ready"] is False
        assert active[0]["actual_provider_call_attempts"] == 0
        assert len(
            [
                document
                for document in stored.values()
                if document.get("revision_id") == REVISION_ID
            ]
        ) == 27

        repeated = run_activation(run_root, memory_url)
        assert repeated.returncode == 0, repeated.stdout + repeated.stderr
        assert receipt_path.read_bytes() == first_bytes
        assert len(
            [
                document
                for document in stored.values()
                if document.get("record_type") == "active_revision_pointer"
            ]
        ) == 1


def test_activation_blocks_missing_and_tampered_receipt_chain(tmp_path: Path) -> None:
    run_root, revision_root, _, _, _ = fixture_tree(tmp_path)
    with MEMORY_FIXTURE.fake_memory_server() as (memory_url, _state):
        prepare_and_verify(run_root, memory_url)
        verify_path = revision_root / "revision_memory_verify_receipt.json"
        original_verify = verify_path.read_bytes()
        verify_path.unlink()
        missing = run_activation(run_root, memory_url)
        assert missing.returncode != 0
        assert json.loads(missing.stdout)["status"] == "BLOCKED_MEMORY_VERIFY_RECEIPT_MISSING"
        assert not (revision_root / "revision_activation_receipt.json").exists()

        verify_path.write_bytes(original_verify)
        prepare_path = revision_root / "revision_memory_prepare_receipt.json"
        prepare_path.write_bytes(prepare_path.read_bytes() + b"\n")
        tampered = run_activation(run_root, memory_url)
        assert tampered.returncode != 0
        assert json.loads(tampered.stdout)["status"] == "BLOCKED_MEMORY_RECEIPT_HASH_CHAIN"
        assert not (revision_root / "revision_activation_receipt.json").exists()


def test_activation_rejects_conflicting_memory_active_pointer(tmp_path: Path) -> None:
    run_root, revision_root, _, _, _ = fixture_tree(tmp_path)
    with MEMORY_FIXTURE.fake_memory_server() as (memory_url, state):
        prepare_and_verify(run_root, memory_url)
        key = ACTIVATION.active_pointer_key(run_root.name)
        state.collections[COLLECTION][key] = {
            "_key": key,
            "schema": "persona_dream.active_revision_pointer.v1",
            "record_type": "active_revision_pointer",
            "run_id": run_root.name,
            "active_revision_id": "rev_conflicting",
        }
        completed = run_activation(run_root, memory_url)
        assert completed.returncode != 0
        output = json.loads(completed.stdout)
        assert output["status"] == "BLOCKED_MEMORY_ACTIVE_REVISION_CONFLICT"
        assert not (revision_root / "revision_activation_receipt.json").exists()


def test_activation_rejects_nonqueued_historical_item(tmp_path: Path) -> None:
    run_root, revision_root, _, _, queue_path = fixture_tree(tmp_path)
    with MEMORY_FIXTURE.fake_memory_server() as (memory_url, _state):
        prepare_and_verify(run_root, memory_url)
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["status"] = "RUNNING"
        write_json(queue_path, queue)
        completed = run_activation(run_root, memory_url)
        assert completed.returncode != 0
        assert json.loads(completed.stdout)["status"] == "BLOCKED_REPAIR_QUEUE_STATE"
        assert not (revision_root / "revision_activation_receipt.json").exists()


def find_tsx() -> str | None:
    candidates = [
        shutil.which("tsx"),
        str(SKILL_ROOT.parents[2] / "pi-mono" / "node_modules" / ".bin" / "tsx"),
        str(Path.home() / "workspace" / "experiments" / "pi-mono" / "node_modules" / ".bin" / "tsx"),
    ]
    return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)


def run_detail(run_root: Path, tmp_path: Path) -> dict[str, Any]:
    tsx = find_tsx()
    if not tsx:
        pytest.skip("tsx is unavailable; production server tests exercise runs.ts")
    runner = tmp_path / "run-detail-check.ts"
    runner.write_text(
        """
import { pathToFileURL } from 'node:url'
async function main() {
const [runsPath, pathsPath, runRoot] = process.argv.slice(2)
const runs = await import(pathToFileURL(runsPath).href)
const paths = await import(pathToFileURL(pathsPath).href)
const detail = await runs.buildRunDetail(new paths.DreamPathPolicy([runRoot]), runRoot)
console.log(JSON.stringify({
  qualification: detail.revisionQualification,
  effectiveStates: detail.stages.map((stage: { effectiveState: string }) => stage.effectiveState),
  storyboardPanelCount: detail.consumers?.storyboard?.panelCount ?? 0,
  storyboardFrameCount: detail.consumers?.storyboard?.panels?.reduce(
    (count: number, panel: { startFrame?: unknown; endFrame?: unknown }) =>
      count + Number(Boolean(panel.startFrame)) + Number(Boolean(panel.endFrame)),
    0,
  ) ?? 0,
}))
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
""".strip()
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [tsx, str(runner), str(RUNS_TS), str(PATHS_TS), str(run_root)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "NO_COLOR": "1"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_run_detail_refuses_partial_activation_chain(tmp_path: Path) -> None:
    run_root, revision_root, _, _, _ = fixture_tree(tmp_path)
    with MEMORY_FIXTURE.fake_memory_server() as (memory_url, _state):
        prepare_and_verify(run_root, memory_url)
        completed = run_activation(run_root, memory_url)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        before = run_detail(run_root, tmp_path)
        assert before["qualification"]["state"] == "ACTIVE_CONSISTENT"
        assert before["qualification"]["status"] == "PASS_ACTIVE_CONSISTENT"
        assert before["qualification"]["actualProviderCallAttempts"] == 0
        assert before["qualification"]["providerReady"] is False
        assert before["qualification"]["liveSubmitReady"] is False
        assert before["effectiveStates"] == ["accepted_current"] * 10
        assert before["storyboardPanelCount"] == 4
        assert before["storyboardFrameCount"] == 8

        receipt = load_activation_receipt(revision_root)
        event_path = run_root / receipt["local_files"]["queue_terminal_event"]["relative_path"]
        event_path.unlink()
        after = run_detail(run_root, tmp_path)
        assert after["qualification"]["state"] == "LEGACY_UNQUALIFIED"
        assert "BLOCKED_ACTIVATION_REFERENCED_FILE_MISSING" in after["qualification"]["blockers"]
        assert "accepted_current" not in after["effectiveStates"]
