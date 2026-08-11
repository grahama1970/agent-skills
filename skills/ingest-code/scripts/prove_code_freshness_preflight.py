"""Live proof for ingest-code target-scoped freshness preflight.

This script creates an isolated git fixture repository, applies a complete
Memory/GMO code projection through ingest-code, then proves:

1. unchanged target source returns CURRENT;
2. edited source before refresh returns STALE;
3. committed canonical refresh returns CURRENT;
4. a repair branch cannot activate canonical projection.

It uses only skill and Memory/GMO command boundaries. It does not access
ArangoDB or Qdrant directly.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


def utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def require_ok(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        raise SystemExit(
            json.dumps(
                {
                    "status": "failed",
                    "stage": label,
                    "returncode": result.returncode,
                    "stdout": result.stdout[-4000:],
                    "stderr": result.stderr[-4000:],
                },
                indent=2,
            )
        )


def parse_json(stdout: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    text = stdout.strip()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and not text[index + end :].strip():
            return parsed
    raise ValueError("stdout did not contain one JSON object")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "sha256": f"sha256:{sha256_file(path)}",
        "status": payload.get("status"),
        "active_generation": payload.get("active_generation") or {},
        "modification_ready": payload.get("modification_ready"),
        "absence_claims_allowed": payload.get("absence_claims_allowed"),
        "refresh_attempted": payload.get("refresh_attempted"),
    }


def git(repo: Path, *args: str) -> str:
    result = run(["git", "-C", str(repo), *args], timeout=30)
    require_ok(result, f"git {' '.join(args)}")
    return result.stdout.strip()


def create_fixture(repo: Path) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "codex@example.invalid")
    git(repo, "config", "user.name", "Codex")
    (repo / "app.py").write_text(
        "def app():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(
        ".ingest-code.json\n"
        "artifacts/\n",
        encoding="utf-8",
    )
    git(repo, "add", ".gitignore", "app.py")
    git(repo, "commit", "-m", "seed")
    return git(repo, "rev-parse", "HEAD")


def ensure_current(
    *,
    run_sh: Path,
    repo: Path,
    branch: str,
    commit: str,
    scope: str,
    memory_root: Path,
    refresh: bool = False,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    env = dict(**__import__("os").environ)
    env["MEMORY_ROOT"] = str(memory_root)
    cmd = [
        str(run_sh),
        "ensure-current",
        "--repo",
        str(repo),
        "--branch",
        branch,
        "--commit",
        commit,
        "--path",
        "app.py",
        "--scope",
        scope,
        "--json",
    ]
    if refresh:
        cmd.append("--refresh")
    result = run(cmd, env=env, timeout=240)
    payload = parse_json(result.stdout)
    return payload, result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/validation/issue1364_code_freshness") / utc_stamp())
    parser.add_argument("--memory-root", type=Path, default=Path.home() / "workspace/experiments/memory")
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    run_sh = skill_root / "run.sh"
    out = args.out.resolve()
    fixture = out / "fixture-repo"
    if fixture.exists():
        shutil.rmtree(fixture)
    scope = f"issue1364-live-{out.name.lower()}"

    seed_commit = create_fixture(fixture)
    initial_hash = sha256_file(fixture / "app.py")

    scan = run([str(run_sh), "scan", str(fixture), "--treesitter", "--scope", scope], timeout=300)
    require_ok(scan, "initial_scan")
    write_json(out / "initial-scan-command.json", {"returncode": scan.returncode, "stdout": scan.stdout, "stderr": scan.stderr})

    current_receipt, current_cmd = ensure_current(
        run_sh=run_sh,
        repo=fixture,
        branch="main",
        commit=seed_commit,
        scope=scope,
        memory_root=args.memory_root,
    )
    write_json(out / "ensure-current-current.json", current_receipt)
    if current_cmd.returncode != 0 or current_receipt.get("status") != "CURRENT":
        raise SystemExit(f"CURRENT preflight failed: {current_receipt.get('status')}")

    (fixture / "app.py").write_text("def app():\n    return 2\n", encoding="utf-8")
    stale_hash = sha256_file(fixture / "app.py")
    stale_receipt, stale_cmd = ensure_current(
        run_sh=run_sh,
        repo=fixture,
        branch="main",
        commit=seed_commit,
        scope=scope,
        memory_root=args.memory_root,
    )
    write_json(out / "ensure-current-stale.json", stale_receipt)
    if stale_cmd.returncode != 0 or stale_receipt.get("status") != "STALE":
        raise SystemExit(f"STALE preflight failed: {stale_receipt.get('status')}")

    git(fixture, "add", "app.py")
    git(fixture, "commit", "-m", "update app")
    refresh_commit = git(fixture, "rev-parse", "HEAD")
    refreshed_receipt, refreshed_cmd = ensure_current(
        run_sh=run_sh,
        repo=fixture,
        branch="main",
        commit=refresh_commit,
        scope=scope,
        memory_root=args.memory_root,
        refresh=True,
    )
    write_json(out / "ensure-current-refresh.json", refreshed_receipt)
    if refreshed_cmd.returncode != 0 or refreshed_receipt.get("status") != "CURRENT":
        raise SystemExit(f"refresh preflight failed: {refreshed_receipt.get('status')}")

    git(fixture, "checkout", "-b", "repair/issue1364")
    (fixture / "app.py").write_text("def app():\n    return 3\n", encoding="utf-8")
    git(fixture, "add", "app.py")
    git(fixture, "commit", "-m", "repair branch edit")
    repair_commit = git(fixture, "rev-parse", "HEAD")
    repair_receipt, repair_cmd = ensure_current(
        run_sh=run_sh,
        repo=fixture,
        branch="repair/issue1364",
        commit=repair_commit,
        scope=scope,
        memory_root=args.memory_root,
        refresh=True,
    )
    write_json(out / "ensure-current-repair-branch-refused.json", repair_receipt)
    if repair_cmd.returncode != 2 or repair_receipt.get("status") != "BLOCKED":
        raise SystemExit(f"repair branch refusal failed: rc={repair_cmd.returncode} status={repair_receipt.get('status')}")

    receipt_paths = {
        "current": out / "ensure-current-current.json",
        "stale": out / "ensure-current-stale.json",
        "refresh": out / "ensure-current-refresh.json",
        "repair_refused": out / "ensure-current-repair-branch-refused.json",
    }
    summary = {
        "schema": "ingest-code.issue1364_live_proof.v1",
        "status": "passed",
        "mocked": False,
        "live": True,
        "scope": scope,
        "fixture_repo": str(fixture),
        "memory_root": str(args.memory_root.resolve()),
        "initial_hash": initial_hash,
        "stale_hash": stale_hash,
        "seed_commit": seed_commit,
        "refresh_commit": refresh_commit,
        "repair_commit": repair_commit,
        "receipts": {name: receipt_summary(path) for name, path in receipt_paths.items()},
    }
    write_json(out / "proof-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
