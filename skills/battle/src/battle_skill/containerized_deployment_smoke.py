"""Containerized local deployment smoke for Battle frontend/backend."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any

from .live_transport_server import (
    _assert_no_raw_path_leak,
    _http_json,
    _http_status,
    _http_text,
    _parse_sse_events,
    _websocket_payloads,
)
from .packaged_deployment_smoke import (
    DEFAULT_FIXTURE,
    DEFAULT_INTERACTION_MANIFEST,
    _file_sha256,
    _free_port,
    _line_count,
    _now_utc,
    _receipt_errors,
    _resolve_manifest,
    _rewrite_interaction_manifest,
    _run_capture,
    _write_git_archive,
)


def prove_containerized_deployment_smoke(
    *,
    out_dir: Path,
    repo_root: Path,
    fixture: Path = DEFAULT_FIXTURE,
    interaction_manifest: Path = DEFAULT_INTERACTION_MANIFEST,
    battle_id: str = "battle-004",
    package_ref: str = "HEAD",
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    repo_root = repo_root.resolve()
    battle_root = repo_root / "skills" / "battle"
    package_root = out_dir / "package-root"
    package_battle = package_root / "skills" / "battle"
    package_spectator = package_battle / "spectator"
    backend_proof = out_dir / "backend"
    frontend_proof = out_dir / "frontend-pr8"
    interactions_dir = out_dir / "test-interactions"
    rewritten_manifest = out_dir / "test-interactions-manifest.json"
    package_archive = out_dir / "battle-package.tar"
    build_log = out_dir / "docker-build.log"
    container_log = out_dir / "docker-container.log"

    out_dir.mkdir(parents=True, exist_ok=True)
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True)
    archive_sha256 = _write_git_archive(
        repo_root=repo_root,
        ref=package_ref,
        archive_path=package_archive,
        paths=["skills/battle", "skills/common"],
    )
    with tarfile.open(package_archive, "r") as tar:
        tar.extractall(package_root, filter="data")

    package_commit = _run_capture(["git", "rev-parse", package_ref], cwd=repo_root).stdout.strip()
    fixture_path = package_battle / fixture
    if not fixture_path.exists():
        raise RuntimeError(f"packaged fixture missing: {fixture_path}")

    image_tag = f"battle-deployment-smoke:{package_commit[:12]}-{int(time.time())}"
    build = _run_capture(
        [
            "docker",
            "build",
            "-f",
            str(package_battle / "docker" / "Dockerfile.deployment"),
            "-t",
            image_tag,
            str(package_root),
        ],
        cwd=package_root,
        timeout_s=900,
    )
    build_log.write_text(build.stdout + build.stderr, encoding="utf-8")
    image_id = _run_capture(["docker", "image", "inspect", image_tag, "--format", "{{.Id}}"], cwd=repo_root).stdout.strip()

    adapter_port = _free_port()
    websocket_port = _free_port()
    frontend_port = _free_port()
    adapter_base = f"http://127.0.0.1:{adapter_port}"
    preview_base = f"http://127.0.0.1:{frontend_port}"
    websocket_url = f"ws://127.0.0.1:{websocket_port}/battle/live/{battle_id}/ws"
    container_name = f"battle-deployment-smoke-{int(time.time())}-{os.getpid()}"

    run_command = [
        "docker",
        "run",
        "--name",
        container_name,
        "-e",
        f"BATTLE_ID={battle_id}",
        "-e",
        f"BATTLE_ADAPTER_PORT={adapter_port}",
        "-e",
        f"BATTLE_WEBSOCKET_PORT={websocket_port}",
        "-e",
        f"BATTLE_FRONTEND_PORT={frontend_port}",
        "-p",
        f"127.0.0.1:{adapter_port}:{adapter_port}",
        "-p",
        f"127.0.0.1:{websocket_port}:{websocket_port}",
        "-p",
        f"127.0.0.1:{frontend_port}:{frontend_port}",
        image_tag,
    ]
    container = subprocess.Popen(
        run_command,
        cwd=package_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        health = _wait_container_json(f"{adapter_base}/healthz", timeout_s=180, container=container)
        _wait_container_http(preview_base, timeout_s=120, container=container)
        backend_receipt = _prove_running_container_transport(
            out_dir=backend_proof,
            base_url=adapter_base,
            websocket_url=websocket_url,
            battle_id=battle_id,
            health=health,
        )

        _run_capture(["npm", "ci", "--prefer-offline"], cwd=package_spectator, timeout_s=300)
        env = os.environ.copy()
        env.update(
            {
                "BATTLE_HOST": preview_base,
                "BATTLE_LIVE_TRANSPORT_BASE": adapter_base,
                "BATTLE_LIVE_TRANSPORT_PROOF_DIR": str(frontend_proof),
                "BATTLE_LIVE_TRANSPORT_TIMEOUT_MS": "120000",
            }
        )
        _run_capture(["npm", "run", "prove:pr8-live-transport"], cwd=package_spectator, env=env, timeout_s=180)

        manifest_source = _resolve_manifest(battle_root=battle_root, manifest=interaction_manifest)
        _rewrite_interaction_manifest(
            source=manifest_source,
            dest=rewritten_manifest,
            preview_base=preview_base,
            adapter_base=adapter_base,
        )
        test_interactions = _run_capture(
            [
                str(repo_root / "skills" / "test-interactions" / "run.sh"),
                "run",
                "--manifest",
                str(rewritten_manifest),
                "--output-dir",
                str(interactions_dir),
                "--max-retries",
                "1",
            ],
            cwd=repo_root,
            timeout_s=300,
        )
    finally:
        logs = _docker_logs(container_name)
        if logs:
            container_log.write_text(logs, encoding="utf-8")
        _docker_rm(container_name)
        try:
            container.wait(timeout=10)
        except subprocess.TimeoutExpired:
            container.kill()
            container.wait(timeout=10)

    pr8_summary = json.loads((frontend_proof / "summary.json").read_text(encoding="utf-8"))
    interaction_results = json.loads((interactions_dir / "results.json").read_text(encoding="utf-8"))
    visual_findings_path = interactions_dir / "visual-findings.jsonl"
    screenshot_path = frontend_proof / "01-live-sse-adapter.png"
    screenshot_sha256 = _file_sha256(screenshot_path)
    errors = _receipt_errors(
        health=health,
        backend_receipt=backend_receipt,
        pr8_summary=pr8_summary,
        interaction_results=interaction_results,
        visual_findings_path=visual_findings_path,
        screenshot_path=screenshot_path,
    )
    if backend_receipt.get("live") != "containerized_http_sse_websocket_adapter":
        errors.append("containerized backend proof did not report containerized live mode")
    receipt = {
        "schema": "battle.containerized_deployment_smoke.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": "containerized_http_sse_websocket_adapter_plus_vite_preview",
        "battle_id": battle_id,
        "package": {
            "source_ref": package_ref,
            "source_commit": package_commit,
            "archive": str(package_archive),
            "archive_sha256": archive_sha256,
            "root": str(package_root),
            "included_paths": ["skills/battle", "skills/common"],
        },
        "container": {
            "image_tag": image_tag,
            "image_id": image_id,
            "dockerfile": str(package_battle / "docker" / "Dockerfile.deployment"),
            "entrypoint": "/app/skills/battle/docker/deployment-entrypoint.sh",
            "run_command": _redacted_command(run_command),
            "build_log": str(build_log),
            "container_log": str(container_log),
        },
        "launch": {
            "adapter_base": adapter_base,
            "spectator_base": preview_base,
            "websocket_url": websocket_url,
            "health": health,
        },
        "proofs": {
            "backend_live_transport_receipt": str(backend_proof / "containerized-live-transport-proof.json"),
            "pr8_live_transport_summary": str(frontend_proof / "summary.json"),
            "test_interactions_manifest": str(rewritten_manifest),
            "test_interactions_results": str(interactions_dir / "results.json"),
            "visual_findings": str(visual_findings_path),
            "screenshot": str(screenshot_path),
            "screenshot_sha256": screenshot_sha256,
        },
        "counts": {
            "pr8_total": len(pr8_summary.get("checks") or []),
            "pr8_failed": len(pr8_summary.get("failed") or []),
            "test_interactions_total": interaction_results.get("total"),
            "test_interactions_passed": interaction_results.get("passed"),
            "test_interactions_failed": interaction_results.get("failed"),
            "test_interactions_warned": interaction_results.get("warned"),
            "visual_findings": _line_count(visual_findings_path),
        },
        "claim_boundary": {
            "proves": [
                "A Git-archived local Battle package can build a Battle-owned container image.",
                "The container entrypoint starts the Battle backend live HTTP/SSE/WebSocket adapter.",
                "The container entrypoint serves the built spectator frontend through Vite preview.",
                "The mapped container backend served matching snapshot-first WebSocket and SSE payloads.",
                "The mapped container frontend/backend route passed PR8 and $test-interactions with zero failures and zero warnings.",
            ],
            "does_not_prove": [
                "Production infrastructure is deployed.",
                "Production WebSocket TLS, auth, fanout, compression, or reconnect behavior.",
                "Cloud, Kubernetes, DNS, certificate, ingress, or secret-management behavior.",
                "Unbounded swarm execution works.",
                "Battle or RelayForge is production ready.",
                "Six-trial qualification, factorial effects, or cross-target generalization.",
            ],
        },
        "errors": errors,
        "created_at": _now_utc(),
        "command_output": {
            "test_interactions_stdout_tail": test_interactions.stdout[-2000:],
            "test_interactions_stderr_tail": test_interactions.stderr[-2000:],
        },
    }
    (out_dir / "containerized-deployment-smoke.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if errors:
        raise RuntimeError("\n".join(errors))
    return receipt


def _prove_running_container_transport(
    *,
    out_dir: Path,
    base_url: str,
    websocket_url: str,
    battle_id: str,
    health: dict[str, Any],
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_endpoint = f"/battle/live/{battle_id}/snapshot"
    events_endpoint = f"/battle/live/{battle_id}/events"
    websocket_endpoint = f"/battle/live/{battle_id}/ws"
    snapshot = _http_json(f"{base_url}{snapshot_endpoint}")
    stream_text = _http_text(f"{base_url}{events_endpoint}", accept="text/event-stream")
    resumed_text = _http_text(
        f"{base_url}{events_endpoint}",
        accept="text/event-stream",
        headers={"Last-Event-ID": "2"},
    )
    stream_events = _parse_sse_events(stream_text)
    bad_resume_status = _http_status(
        f"{base_url}{events_endpoint}",
        headers={"Last-Event-ID": str(len(stream_events) + 10)},
    )
    websocket_payloads = _websocket_payloads(websocket_url)
    websocket_snapshot = websocket_payloads[0] if websocket_payloads else {}
    websocket_events = websocket_payloads[1:]
    resumed_events = _parse_sse_events(resumed_text)
    _assert_no_raw_path_leak(snapshot, stream_events)
    _assert_no_raw_path_leak(websocket_snapshot, websocket_events)

    errors: list[str] = []
    if health.get("status") != "PASS":
        errors.append("container health endpoint did not return PASS")
    if snapshot.get("schema") != "battle.snapshot.v1":
        errors.append("container snapshot endpoint did not return battle.snapshot.v1")
    if snapshot.get("battle_id") != battle_id:
        errors.append("container snapshot battle_id mismatch")
    if snapshot.get("last_seq") != len(stream_events):
        errors.append("container snapshot last_seq must match event count")
    if [event.get("seq") for event in stream_events] != list(range(1, len(stream_events) + 1)):
        errors.append("container SSE stream seq values are not contiguous")
    if len(resumed_events) != max(len(stream_events) - 2, 0):
        errors.append("container Last-Event-ID resume returned unexpected event count")
    if bad_resume_status != 400:
        errors.append("container future Last-Event-ID must fail closed with HTTP 400")
    if health.get("websocket_endpoint") != websocket_endpoint:
        errors.append("container health endpoint did not advertise WebSocket endpoint")
    if websocket_snapshot != snapshot:
        errors.append("container WebSocket first message did not match HTTP snapshot")
    if websocket_events != stream_events:
        errors.append("container WebSocket event payloads did not match SSE event payloads")

    receipt = {
        "schema": "battle.containerized_live_transport_proof.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": "containerized_http_sse_websocket_adapter",
        "battle_id": battle_id,
        "base_url": base_url,
        "websocket_url": websocket_url,
        "snapshot_endpoint": snapshot_endpoint,
        "sse_endpoint": events_endpoint,
        "websocket_endpoint": websocket_endpoint,
        "snapshot_schema": snapshot.get("schema"),
        "event_schema": "battle.live_event.v1",
        "event_count": len(stream_events),
        "websocket_event_count": len(websocket_events),
        "last_seq": snapshot.get("last_seq"),
        "resume_from_last_event_id": 2,
        "resumed_event_count": len(resumed_events),
        "future_last_event_id_status": bad_resume_status,
        "websocket_snapshot_first": True,
        "websocket_matches_sse_payloads": websocket_events == stream_events,
        "errors": errors,
        "claim_boundary": {
            "proves": [
                "The containerized Battle live transport adapter served battle.snapshot.v1 over HTTP.",
                "The containerized Battle live transport adapter served ordered battle.live_event.v1 records as SSE.",
                "The containerized Battle live transport adapter served the same snapshot and ordered events over WebSocket.",
                "The containerized Battle live transport adapter honored Last-Event-ID resume.",
                "The containerized Battle live transport adapter failed closed on an impossible future Last-Event-ID.",
            ],
            "does_not_prove": [
                "Production infrastructure is deployed.",
                "Production WebSocket TLS, auth, fanout, compression, or reconnect behavior.",
                "Unbounded swarm execution works.",
                "Battle or RelayForge is production ready.",
            ],
        },
    }
    (out_dir / "containerized-live-transport-proof.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "snapshot-response.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    (out_dir / "events.sse").write_text(stream_text.rstrip() + "\n", encoding="utf-8")
    (out_dir / "resume-after-2.sse").write_text(resumed_text.rstrip() + "\n", encoding="utf-8")
    (out_dir / "websocket-events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in websocket_events),
        encoding="utf-8",
    )
    if errors:
        raise RuntimeError("\n".join(errors))
    return receipt


def _wait_container_json(url: str, *, timeout_s: int, container: subprocess.Popen[str]) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        if container.poll() is not None:
            raise RuntimeError(f"container exited before health check: {container.returncode}")
        try:
            return _http_json(url)
        except Exception as exc:  # noqa: BLE001 - preserve last probe failure in timeout message
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def _wait_container_http(url: str, *, timeout_s: int, container: subprocess.Popen[str]) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        if container.poll() is not None:
            raise RuntimeError(f"container exited before frontend check: {container.returncode}")
        try:
            status = _http_status(url)
            if status < 500:
                return
        except Exception as exc:  # noqa: BLE001 - preserve last probe failure in timeout message
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def _docker_logs(container_name: str) -> str:
    result = subprocess.run(
        ["docker", "logs", container_name],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout + result.stderr


def _docker_rm(container_name: str) -> None:
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        text=True,
        capture_output=True,
        check=False,
    )


def _redacted_command(command: list[str]) -> list[str]:
    return ["<image-tag>" if item.startswith("battle-deployment-smoke:") else item for item in command]
