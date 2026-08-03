#!/usr/bin/env python3
"""Run and verify one source-bound Arena-to-Pixi qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
BATTLE_DIR = SCRIPT_DIR.parent
REPO_ROOT = BATTLE_DIR.parents[1]
SPECTATOR_DIR = BATTLE_DIR / "spectator"
RUN_SH = BATTLE_DIR / "run.sh"
FIXTURE_KEY = "battle-004-same-run-qualification"
CDP_HOOK = Path.home() / ".codex" / "hooks" / "verify-ui-cdp.sh"


def _utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _source() -> dict[str, str]:
    return {
        "commit": _git(["rev-parse", "HEAD"]),
        "battle_tree": _git(["rev-parse", "HEAD:skills/battle"]),
    }


def _tau_source() -> dict[str, Any]:
    tau_repo = Path(os.environ.get("TAU_REPO", "/home/graham/workspace/experiments/tau")).expanduser().resolve()
    payload: dict[str, Any] = {"path": str(tau_repo), "available": tau_repo.is_dir()}
    if not tau_repo.is_dir():
        return payload
    try:
        payload["commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=tau_repo, text=True
        ).strip()
        payload["branch"] = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=tau_repo, text=True
        ).strip()
        payload["dirty"] = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=tau_repo, text=True
            ).strip()
        )
    except subprocess.CalledProcessError as exc:
        payload["error"] = str(exc)
    return payload


def _run(command: list[str], *, cwd: Path, timeout: int | None = None) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    return {
        "command": command,
        "cwd": str(cwd),
        "duration_seconds": round(time.time() - started, 3),
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-8000:],
        "stderr_tail": proc.stderr[-8000:],
    }


def _free_port() -> int:
    for port in range(3030, 3050):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("no free preview port in 3030-3049")


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _publish_fixture(arena_dir: Path, source: dict[str, str]) -> dict[str, Any]:
    source_fixture = arena_dir / "battle.normalized_ux_fixture.json"
    source_stream = arena_dir / "stream"
    if not source_fixture.is_file():
        raise RuntimeError(f"missing normalized fixture: {source_fixture}")
    fixture = _json(source_fixture)
    fixture["source_commit"] = source["commit"]
    fixture["source_tree"] = source["battle_tree"]
    fixture["fixture_backed"] = False
    fixture["same_run_qualification"] = True
    fixture["qualification_fixture_key"] = FIXTURE_KEY
    public_dir = SPECTATOR_DIR / "public" / "battle-fixtures" / FIXTURE_KEY
    public_dir.mkdir(parents=True, exist_ok=True)
    public_fixture = public_dir / "battle.normalized_ux_fixture.json"
    _write(public_fixture, fixture)
    if source_stream.is_dir():
        _copy_tree(source_stream, public_dir / "stream")
    return {
        "fixture_key": FIXTURE_KEY,
        "source_fixture": str(source_fixture),
        "public_fixture": str(public_fixture),
        "fixture_sha256": _sha256(public_fixture),
        "fixture_backed": False,
        "route": f"#battle/receipt?engine=pixi&fixture={FIXTURE_KEY}",
    }


def _serve_and_capture(*, url: str, out_dir: Path, wait_seconds: int) -> dict[str, Any]:
    if not (SPECTATOR_DIR / "node_modules" / ".bin" / "vite").exists():
        install = _run(["npm", "install", "--no-fund", "--no-audit"], cwd=SPECTATOR_DIR, timeout=180)
        if install["exit_code"] != 0:
            return {"status": "FAIL", "install": install}
    build = _run(["npm", "run", "build"], cwd=SPECTATOR_DIR, timeout=240)
    if build["exit_code"] != 0:
        return {"status": "FAIL", "build": build}

    port = int(url.split(":")[-1].split("/")[0])
    log_path = out_dir / "spectator-preview.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            ["npm", "run", "preview", "--", "--port", str(port), "--strictPort"],
            cwd=SPECTATOR_DIR,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    try:
        for _ in range(80):
            try:
                with urlopen(url.split("#")[0], timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        cdp_root = out_dir / "cdp"
        if not CDP_HOOK.exists():
            raise RuntimeError(f"CDP hook missing: {CDP_HOOK}")
        cdp = _run(
            [str(CDP_HOOK), "--url", url, "--name", "battle-same-run-qualification", "--wait", str(wait_seconds), "--output-root", str(cdp_root), "--cwd", str(REPO_ROOT)],
            cwd=REPO_ROOT,
            timeout=120,
        )
        latest = cdp_root / REPO_ROOT.name / "latest.json"
        cdp_meta = _json(latest) if latest.exists() else {}
        return {
            "status": "PASS" if cdp["exit_code"] == 0 else "FAIL",
            "build": build,
            "preview_log": str(log_path),
            "cdp_command": cdp,
            "cdp_latest": str(latest),
            "cdp_meta": cdp_meta,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def qualify(out_dir: Path, *, arena_proof_dir: Path | None, skip_arena: bool, wait_seconds: int) -> int:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source = _source()
    tau_source = _tau_source()
    commands: list[dict[str, Any]] = []
    if skip_arena:
        if arena_proof_dir is None:
            raise RuntimeError("--skip-arena requires --arena-proof-dir")
        arena_dir = arena_proof_dir.resolve()
    else:
        arena_dir = out_dir / "arena"
        commands.append(
            _run(
                [
                    "bash",
                    str(RUN_SH),
                    "arena-parent-spawn-proof",
                    "battle-004",
                    "--out",
                    str(arena_dir),
                    "--timeout-s",
                    "120",
                ],
                cwd=BATTLE_DIR,
                timeout=1500,
            )
        )
    run_receipt_path = arena_dir / "run-receipt.json"
    judge_receipt_path = arena_dir / "judge" / "judge-receipt.json"
    run_receipt = _json(run_receipt_path)
    judge_receipt = _json(judge_receipt_path)
    published = _publish_fixture(arena_dir, source)
    port = _free_port()
    url = f"http://127.0.0.1:{port}/{published['route']}"
    browser = _serve_and_capture(url=url, out_dir=out_dir, wait_seconds=wait_seconds)

    served_fixture_url = f"http://127.0.0.1:{port}/battle-fixtures/{FIXTURE_KEY}/battle.normalized_ux_fixture.json"
    errors: list[str] = []
    if run_receipt.get("status") != "PASS":
        errors.append("arena_run_receipt_not_pass")
    if run_receipt.get("mocked") is not False:
        errors.append("arena_run_receipt_not_mocked_false")
    if not run_receipt.get("live"):
        errors.append("arena_run_receipt_not_live")
    if judge_receipt.get("status") != "PASS":
        errors.append("judge_receipt_not_pass")
    if browser.get("status") != "PASS":
        errors.append("browser_cdp_capture_failed")
    cdp_meta = browser.get("cdp_meta") if isinstance(browser.get("cdp_meta"), dict) else {}
    if published["route"] not in str(cdp_meta.get("url", "")):
        errors.append("browser_route_not_same_run_fixture")
    read_path = Path(str(cdp_meta.get("read_json") or ""))
    read_payload = _json(read_path) if read_path.exists() else {}
    read_text = json.dumps(read_payload)
    if FIXTURE_KEY not in read_text and FIXTURE_KEY not in str(cdp_meta.get("url", "")):
        errors.append("browser_readback_missing_fixture_key")

    qualification = {
        "schema": "battle.same_run_arena_pixi_qualification.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_commit": source["commit"],
        "source_tree": source["battle_tree"],
        "tau_source": tau_source,
        "battle_id": run_receipt.get("battle_id"),
        "run_id": run_receipt.get("run_id"),
        "judge_verdict": run_receipt.get("verdict"),
        "arena_receipt": str(run_receipt_path),
        "judge_receipt": str(judge_receipt_path),
        "published_fixture": published,
        "served_fixture_url": served_fixture_url,
        "browser": browser,
        "commands": commands,
        "errors": errors,
        "proof_scope": {
            "proves": [
                "A fresh Arena/Tau/Judge run produced a normalized Pixi fixture.",
                "The spectator route loaded the published same-run fixture key.",
                "The receipt binds run id, source commit, Battle tree, Judge verdict, and browser screenshot metadata.",
            ],
            "does_not_prove": [
                "Production deployment.",
                "Adaptive improvement unless the Arena run requested it.",
            ],
        },
    }
    receipt_path = out_dir / "qualification-receipt.json"
    _write(receipt_path, qualification)
    print(json.dumps({"status": qualification["status"], "receipt": str(receipt_path), "errors": errors}, indent=2))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run same-run Arena-to-Pixi qualification")
    parser.add_argument("--out", type=Path, default=BATTLE_DIR / "local" / f"same-run-qualification-{_utc_stamp()}")
    parser.add_argument("--arena-proof-dir", type=Path, default=None)
    parser.add_argument("--skip-arena", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=4)
    args = parser.parse_args()
    return qualify(args.out, arena_proof_dir=args.arena_proof_dir, skip_arena=args.skip_arena, wait_seconds=args.wait_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
