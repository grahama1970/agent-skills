"""Packaged local deployment smoke for Battle frontend/backend.

This proof creates a Git-archived source package and launches the existing
Battle live HTTP/SSE adapter plus spectator preview from that packaged tree.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_FIXTURE = Path(
    "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
)
DEFAULT_INTERACTION_MANIFEST = Path(
    "local/working-frontend-backend-20260729/test-interactions-live-after-patch/live-route-unique-hash-manifest.json"
)


def prove_packaged_deployment_smoke(
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
    package_storage = out_dir / "battle-storage"

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

    backend_receipt = _run_json(
        [
            str(package_battle / "run.sh"),
            "prove-live-transport-server",
            "--fixture",
            str(fixture_path),
            "--battle-id",
            battle_id,
            "--out",
            str(backend_proof),
        ],
        cwd=package_battle,
        env=_package_env(package_root, package_storage),
    )

    _run_capture(["npm", "ci", "--prefer-offline"], cwd=package_spectator)
    _run_capture(["npm", "run", "build"], cwd=package_spectator)

    adapter_port = _free_port()
    preview_port = _free_port()
    adapter_base = f"http://127.0.0.1:{adapter_port}"
    preview_base = f"http://127.0.0.1:{preview_port}"

    adapter = subprocess.Popen(
        [
            str(package_battle / "run.sh"),
            "serve-live-transport",
            "--fixture",
            str(fixture_path),
            "--battle-id",
            battle_id,
            "--host",
            "127.0.0.1",
            "--port",
            str(adapter_port),
        ],
        cwd=package_battle,
        env=_package_env(package_root, package_storage),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    preview = subprocess.Popen(
        ["npm", "run", "preview", "--", "--port", str(preview_port)],
        cwd=package_spectator,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        health = _wait_json(f"{adapter_base}/healthz", timeout_s=45)
        _wait_http(preview_base, timeout_s=45)
        env = os.environ.copy()
        env.update(
            {
                "BATTLE_HOST": preview_base,
                "BATTLE_LIVE_TRANSPORT_BASE": adapter_base,
                "BATTLE_LIVE_TRANSPORT_PROOF_DIR": str(frontend_proof),
                "BATTLE_LIVE_TRANSPORT_TIMEOUT_MS": "120000",
            }
        )
        _run_capture(["npm", "run", "prove:pr8-live-transport"], cwd=package_spectator, env=env)

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
        )
    finally:
        _terminate(preview)
        _terminate(adapter)

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
    receipt = {
        "schema": "battle.packaged_deployment_smoke.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": "packaged_local_http_sse_adapter_plus_vite_preview",
        "battle_id": battle_id,
        "package": {
            "source_ref": package_ref,
            "source_commit": package_commit,
            "archive": str(package_archive),
            "archive_sha256": archive_sha256,
            "root": str(package_root),
            "included_paths": ["skills/battle", "skills/common"],
        },
        "launch": {
            "adapter_command": "./run.sh serve-live-transport --fixture <packaged-fixture> --battle-id battle-004 --host 127.0.0.1 --port <port>",
            "spectator_command": "npm run preview -- --port <port>",
            "adapter_base": adapter_base,
            "spectator_base": preview_base,
            "health": health,
        },
        "proofs": {
            "backend_live_transport_receipt": str(backend_proof / "live-transport-server-proof.json"),
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
                "A Git-archived local Battle package can launch the existing backend live HTTP/SSE adapter.",
                "A Git-archived local Battle package can build and preview the spectator frontend.",
                "The packaged frontend consumed the packaged adapter through the PR8 live transport proof.",
                "$test-interactions exercised the packaged frontend/backend route with zero failures and zero warnings.",
            ],
            "does_not_prove": [
                "Production infrastructure is deployed.",
                "A WebSocket endpoint exists.",
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
    (out_dir / "packaged-deployment-smoke.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if errors:
        raise RuntimeError("\n".join(errors))
    return receipt


def _write_git_archive(*, repo_root: Path, ref: str, archive_path: Path, paths: list[str]) -> str:
    with archive_path.open("wb") as handle:
        result = subprocess.run(
            ["git", "archive", "--format=tar", ref, *paths],
            cwd=repo_root,
            stdout=handle,
            stderr=subprocess.PIPE,
            text=False,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return _file_sha256(archive_path)


def _package_env(package_root: Path, package_storage: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["BATTLE_STORAGE_ROOT"] = str(package_storage)
    env["UV_PROJECT_ENVIRONMENT"] = str(package_storage / ".venv")
    env["PYTHONPATH"] = f"{package_root / 'skills'}:{package_root}:{package_root / 'skills' / 'battle' / 'src'}"
    return env


def _run_capture(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_s: int = 180,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {command}\nSTDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-4000:]}"
        )
    return result


def _run_json(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    result = _run_capture(command, cwd=cwd, env=env, timeout_s=180)
    return json.loads(result.stdout)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_json(url: str, *, timeout_s: int) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_error: str = ""
    while time.time() < deadline:
        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def _wait_http(url: str, *, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    last_error: str = ""
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if int(response.status) < 500:
                    return
        except (OSError, URLError) as exc:
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _resolve_manifest(*, battle_root: Path, manifest: Path) -> Path:
    path = manifest if manifest.is_absolute() else battle_root / manifest
    if not path.exists():
        raise RuntimeError(f"interaction manifest missing: {path}")
    return path


def _rewrite_interaction_manifest(
    *,
    source: Path,
    dest: Path,
    preview_base: str,
    adapter_base: str,
) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    data["base_url"] = f"{preview_base.rstrip('/')}/#battle"
    encoded = quote(adapter_base, safe="")
    for surface in data.get("surfaces") or []:
        path = str(surface.get("path") or "")
        if "liveBase=" in path:
            prefix, rest = path.split("liveBase=", 1)
            suffix = ""
            if "&" in rest:
                _old, suffix = rest.split("&", 1)
                suffix = "&" + suffix
            path = f"{prefix}liveBase={encoded}{suffix}"
        surface["path"] = path
    dest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _receipt_errors(
    *,
    health: dict[str, Any],
    backend_receipt: dict[str, Any],
    pr8_summary: dict[str, Any],
    interaction_results: dict[str, Any],
    visual_findings_path: Path,
    screenshot_path: Path,
) -> list[str]:
    errors: list[str] = []
    if health.get("status") != "PASS":
        errors.append("packaged adapter health did not return PASS")
    if backend_receipt.get("status") != "PASS" or backend_receipt.get("mocked") is not False:
        errors.append("packaged backend live transport proof did not pass as non-mocked")
    if pr8_summary.get("mocked") is not False or pr8_summary.get("failed"):
        errors.append("packaged PR8 live transport proof has failures")
    if interaction_results.get("failed") != 0 or interaction_results.get("warned") != 0:
        errors.append("packaged $test-interactions has failures or warnings")
    if not screenshot_path.exists() or screenshot_path.stat().st_size == 0:
        errors.append("packaged screenshot is missing or empty")
    if _line_count(visual_findings_path) != 0:
        errors.append("packaged visual findings are non-empty")
    return errors


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.open("r", encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
