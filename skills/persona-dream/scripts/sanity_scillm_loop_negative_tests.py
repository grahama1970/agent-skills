#!/usr/bin/env python3
"""Negative checks for the Persona-Dream Scillm loop sanity ladder."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sanity_scillm_subagent_loop as sanity


REPO_ROOT = sanity.REPO_ROOT
OUT_ROOT = REPO_ROOT / ".codex" / "persona-dream" / "sanity" / "negative-tests"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_preflight_remote(root: Path) -> dict[str, Any]:
    output = root / "remote-endpoint.json"
    work_dir = root / "remote-workdir"
    proc = run(
        [
            sys.executable,
            str(Path(__file__).resolve().with_name("sanity_scillm_subagent_loop.py")),
            "--backend",
            "scillm-coder",
            "--work-dir",
            str(work_dir),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        env={"SCILLM_BASE_URL": "http://example.invalid:4001"},
    )
    proof = read_json(output)
    ok = proc.returncode == 2 and isinstance(proof, dict) and proof.get("preflight", {}).get("status") == "BLOCKED"
    return {
        "name": "remote_endpoint_rejected",
        "ok": ok,
        "returncode": proc.returncode,
        "output": str(output),
        "blockers": proof.get("preflight", {}).get("blockers") if isinstance(proof, dict) else None,
    }


def run_workspace_escape(root: Path) -> dict[str, Any]:
    output = root / "workspace-escape.json"
    work_dir = Path(f"/tmp/persona-dream-negative-workspace-{now_stamp()}")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    proc = run(
        [
            sys.executable,
            str(Path(__file__).resolve().with_name("sanity_scillm_subagent_loop.py")),
            "--backend",
            "scillm-coder",
            "--work-dir",
            str(work_dir),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
    )
    proof = read_json(output)
    shutil.rmtree(work_dir, ignore_errors=True)
    ok = proc.returncode == 2 and isinstance(proof, dict) and proof.get("preflight", {}).get("status") == "BLOCKED"
    return {
        "name": "workspace_escape_rejected",
        "ok": ok,
        "returncode": proc.returncode,
        "output": str(output),
        "blockers": proof.get("preflight", {}).get("blockers") if isinstance(proof, dict) else None,
    }


def write_bad_agent(path: Path, *, mode: str, target_role: str) -> None:
    if mode == "invalid_json":
        if target_role == "explorer":
            body = 'print("not-json")'
        else:
            body = 'print("{\\"verdict\\": \\"PASS\\", \\"findings\\": \\"not-a-list\\"}")'
    elif mode == "mutate":
        body = textwrap.dedent(
            """
            from pathlib import Path

            target = Path("sample-target/src/time/parse_duration.py")
            target.write_text(target.read_text() + "\\n# reviewer mutation\\n")
            print('{"verdict": "PASS", "findings": []}')
            """
        ).strip()
    else:
        raise ValueError(mode)
    write_text(path, "#!/usr/bin/env python3\n" + body + "\n")
    path.chmod(0o755)


def run_bad_agent_case(root: Path, *, role: str, mode: str, expected_stop_reason: str | list[str]) -> dict[str, Any]:
    case = root / f"{role}-{mode}"
    if case.exists():
        shutil.rmtree(case)
    repo = case / "repo"
    repo.mkdir(parents=True)
    sanity.init_fixture_repo(repo)
    bad_agent = case / f"{role}_{mode}.py"
    write_bad_agent(bad_agent, mode=mode, target_role=role)
    explorer_cmd = [sys.executable, str(sanity.FIXTURE_DIR / "explorer_agent.py")]
    reviewer_cmd = [sys.executable, str(sanity.FIXTURE_DIR / "code_reviewer_agent.py")]
    if role == "explorer":
        explorer_cmd = [sys.executable, str(bad_agent)]
    elif role == "reviewer":
        reviewer_cmd = [sys.executable, str(bad_agent)]
    else:
        raise ValueError(role)
    agent_config = repo / ".loop" / f"agents.{mode}.toml"
    sanity.write_text(
        agent_config,
        textwrap.dedent(
            f"""
            [explorer]
            cmd = {json.dumps(explorer_cmd)}
            writes = false
            timeout_seconds = 60

            [coder]
            cmd = ["{sys.executable}", "{sanity.FIXTURE_DIR / 'coder_agent.py'}"]
            writes = true
            timeout_seconds = 60

            [code-reviewer]
            cmd = {json.dumps(reviewer_cmd)}
            writes = false
            timeout_seconds = 60
            """
        ).strip()
        + "\n",
    )
    node = sanity.write_node(repo, agent_config, mode)
    proc = run([sys.executable, str(sanity.NODE_RUNNER), "--node", str(node), "--repo", str(repo), "--print-json"], cwd=repo)
    node_result = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    expected = [expected_stop_reason] if isinstance(expected_stop_reason, str) else expected_stop_reason
    ok = proc.returncode != 0 and node_result.get("stop_reason") in expected
    return {
        "name": f"{role}_{mode}_rejected",
        "ok": ok,
        "returncode": proc.returncode,
        "stop_reason": node_result.get("stop_reason"),
        "expected_stop_reason": expected,
        "status": node_result.get("status"),
        "final_receipt": node_result.get("final_receipt"),
    }


def run_invalid_receipt_validator(root: Path) -> dict[str, Any]:
    receipt = root / "invalid-receipt.json"
    sanity.atomic_json(receipt, {"schema": "loop.final_receipt.v1", "final_verdict": "PASS"})
    proc = run([sys.executable, str(sanity.VALIDATE_RECEIPT), str(receipt), "--print-summary"], cwd=REPO_ROOT)
    return {
        "name": "invalid_receipt_validator_rejected",
        "ok": proc.returncode != 0,
        "returncode": proc.returncode,
        "receipt": str(receipt),
        "stdout": proc.stdout[-1000:],
        "stderr": proc.stderr[-1000:],
    }


def main() -> int:
    root = OUT_ROOT / now_stamp()
    root.mkdir(parents=True, exist_ok=True)
    results = [
        run_preflight_remote(root),
        run_workspace_escape(root),
        run_bad_agent_case(root, role="explorer", mode="invalid_json", expected_stop_reason=["AGENT_FAILED", "REQUIRED_CHANGED_GLOB_MISSING"]),
        run_bad_agent_case(root, role="explorer", mode="mutate", expected_stop_reason="AGENT_FAILED"),
        run_bad_agent_case(root, role="reviewer", mode="invalid_json", expected_stop_reason="INVALID_REVIEWER_OUTPUT"),
        run_bad_agent_case(root, role="reviewer", mode="mutate", expected_stop_reason="REVIEWER_EDITED_FILES"),
        run_invalid_receipt_validator(root),
    ]
    proof = {
        "schema": "persona_dream.sanity_scillm_loop_negative_tests.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "results": results,
        "pass": all(item["ok"] for item in results),
    }
    out = root / "negative-tests.json"
    sanity.atomic_json(out, proof)
    print(json.dumps({"proof": str(out), "pass": proof["pass"], "results": results}, indent=2))
    return 0 if proof["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
