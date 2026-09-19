"""Live retained proof for registered-project Q&A refresh.

Creates a disposable Git repository with a real ``origin/main``, runs the
Monitor Projects refresh against the live Memory daemon, and independently
recalls the exact governed project-memory record. The repository is synthetic;
the Memory, ArangoSearch, Qdrant semantic-sync, and lifecycle endpoints are live.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

from project_refresh import refresh_registered_projects


MEMORY_URL = "http://127.0.0.1:8601"
PROJECT_ID = "monitor-projects-agentic-eval"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        timeout=30, check=True,
    )
    return result.stdout.strip()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="monitor-projects-agentic-eval-") as directory:
        root = Path(directory)
        repo = root / "repo"
        remote = root / "origin.git"
        repo.mkdir()
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True, timeout=30)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "agentic-eval@example.invalid")
        git(repo, "config", "user.name", "agentic-eval")
        (repo / "README.md").write_text("source-backed project memory eval\n", encoding="utf-8")
        git(repo, "add", "README.md")
        git(repo, "commit", "-qm", "Prove governed project Q&A refresh")
        git(repo, "branch", "-M", "main")
        git(repo, "remote", "add", "origin", str(remote))
        git(repo, "push", "-q", "-u", "origin", "main")
        sha = git(repo, "rev-parse", "HEAD")
        registry = root / "projects.json"
        registry.write_text(json.dumps({"projects": [{
            "project_id": PROJECT_ID,
            "worktree": str(repo),
            "status": "registered",
        }]}), encoding="utf-8")

        watermarks: dict[tuple[str, str], str] = {}

        def get_watermark(path: Path, field: str) -> str | None:
            return watermarks.get((str(path), field))

        def put_watermark(path: Path, value: str, run_id: str, field: str) -> None:
            del run_id
            watermarks[(str(path), field)] = value

        results = refresh_registered_projects(
            registry, get_watermark, put_watermark,
            "agentic-eval-project-memory-refresh", MEMORY_URL, 24,
        )
        if len(results) != 1 or results[0].get("status") != "stored_verified":
            print(json.dumps({"status": "FAIL", "results": results}, indent=2))
            return 1
        expected_ref = results[0]["project_memory_refs"][0]
        timeout = httpx.Timeout(connect=3.0, read=60.0, write=10.0, pool=5.0)
        expected_key = expected_ref.split("/", 1)[1]
        item = None
        with httpx.Client(base_url=MEMORY_URL, timeout=timeout) as client:
            for _attempt in range(20):
                response = client.post("/recall", json={
                    "q": f"What changed in {PROJECT_ID} at commit {sha[:12]}?",
                    "scope": PROJECT_ID,
                    "collections": ["project_memory_active"],
                    "k": 5,
                })
                response.raise_for_status()
                recalled = response.json()
                item = next(
                    (row for row in recalled.get("items", []) if row.get("_key") == expected_key),
                    None,
                )
                if item is not None:
                    break
                time.sleep(1)
        passed = bool(
            item
            and item.get("status") == "active"
            and item.get("semantic_sync_state") == "synced"
            and item.get("scores", {}).get("bm25", 0) > 0
            and item.get("scores", {}).get("dense", 0) > 0
            and watermarks.get((str(repo.resolve()), "project_qa_last_sha")) == sha
        )
        receipt = {
            "schema": "monitor_projects.project_memory_live_eval.v1",
            "status": "PASS" if passed else "FAIL",
            "mocked": False,
            "live": ["memory-daemon", "arangodb", "arangosearch", "qdrant-semantic-sync"],
            "fixture_backed": ["disposable-git-repository"],
            "project_memory_ref": expected_ref,
            "commit_sha": sha,
            "scores": item.get("scores") if item else None,
            "semantic_sync_state": item.get("semantic_sync_state") if item else None,
            "watermark_advanced_after_readback": watermarks.get((str(repo.resolve()), "project_qa_last_sha")) == sha,
        }
        print(json.dumps(receipt, indent=2))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
