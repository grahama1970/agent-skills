"""Battle Skill - Patch writer wrapper around /code-runner.

Generates a TaskSpec JSON, executes code-runner, and parses result.json
into a compact PatchResult for blue-team workflows.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx  # Required dependency for consistency with battle stack.
from loguru import logger
from pydantic import BaseModel, Field

from common.file_bundler import bundle_for_review


SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parents[2]
SIBLING_CODE_RUNNER_RUN = SKILLS_DIR / "code-runner" / "run.sh"


class PatchResult(BaseModel):
    success: bool = False
    rounds: int = 0
    patch_diff: str = ""
    score: float = 0.0
    functionality_preserved: bool = False


def _safe_rel(path: str, cwd: Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = (cwd / p).resolve()
    try:
        return str(p.relative_to(cwd))
    except ValueError:
        return str(p)


def _ensure_git_repo(cwd: Path) -> None:
    if (cwd / ".git").exists():
        return
    subprocess.run(["git", "init"], cwd=str(cwd), check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=str(cwd), check=True, capture_output=True, text=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Battle Blue",
            "-c",
            "user.email=battle-blue@example.invalid",
            "commit",
            "-m",
            "battle baseline",
        ],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _editable_paths(source_cwd: Path, target_path: Path) -> list[str]:
    if target_path.is_file():
        return [str(target_path.relative_to(source_cwd))]
    extensions = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".php",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
    }
    paths: list[str] = []
    for candidate in sorted(target_path.rglob("*")):
        if ".git" in candidate.parts:
            continue
        if candidate.is_file() and candidate.suffix.lower() in extensions:
            paths.append(str(candidate.relative_to(source_cwd)))
        if len(paths) >= 30:
            break
    return paths or ["."]


def _build_prompt(
    target_path: str,
    finding: str,
    exploit_proof: str,
    target_bundle: dict[str, str],
    memory_recall: str | None,
) -> str:
    bundled = "\n\n".join(
        f"--- FILE: {p} ---\n{content}" for p, content in target_bundle.items()
    )
    memory_block = memory_recall.strip() if memory_recall else "None"

    # Load prompt template from /prompt-lab (v2 — reviewed by /review-prompt)
    _prompt_dir = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"
    _template = _prompt_dir / "patch_writer_v2.txt"
    if _template.exists():
        prompt = _template.read_text().strip()
    else:
        prompt = (
            "Patch the vulnerable file with minimal, safe changes.\n"
            "Return exactly one fenced ```python code block with the COMPLETE patched file.\n"
            "<target>{target_path}</target>\n<finding>{finding}</finding>\n"
            "<exploit>{exploit_proof}</exploit>\n<context>{memory_recall}</context>\n"
            "Bundled target file:\n{bundled_context}\n"
            "Preserve ALL existing functionality. Patch only what is necessary."
        )
    return (
        prompt
        .replace("{target_path}", target_path)
        .replace("{finding}", finding)
        .replace("{exploit_proof}", exploit_proof)
        .replace("{memory_recall}", memory_block)
        .replace("{bundled_context}", bundled)
    )


def _resolve_code_runner_run(cwd: Path) -> Path | None:
    candidates = [
        Path(value)
        for value in [
            # Explicit override for tests and nonstandard deployments.
            os.environ.get("BATTLE_CODE_RUNNER_RUN", ""),
        ]
        if value
    ]
    candidates.extend(
        [
            SIBLING_CODE_RUNNER_RUN,
            cwd / ".pi" / "skills" / "code-runner" / "run.sh",
            cwd / "skills" / "code-runner" / "run.sh",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def write_patch(
    target_path: str,
    finding: str,
    exploit_proof: str,
    test_command: str,
    max_rounds: int = 5,
) -> PatchResult:
    target = Path(target_path).resolve()
    source_cwd = target if target.is_dir() else target.parent
    _ensure_git_repo(source_cwd)
    cwd = source_cwd
    target_rel = "." if target == source_cwd else _safe_rel(str(target), cwd)
    allowlist = _editable_paths(source_cwd, target)

    # Build context bundle for target file.
    target_bundle = bundle_for_review(allowlist[:12], str(cwd))

    # Lightweight "memory recall" placeholder from local prior patch logs (if any).
    memory_recall = ""
    prior = sorted(cwd.glob("**/patch_memory*.md"))[:3]
    for p in prior:
        try:
            memory_recall += f"\n# {p.name}\n" + p.read_text(encoding="utf-8")[:1200]
        except Exception:
            continue
    if not memory_recall:
        memory_recall = "No prior patch memory found."

    prompt = _build_prompt(
        target_path=target_rel,
        finding=finding,
        exploit_proof=exploit_proof,
        target_bundle=target_bundle,
        memory_recall=memory_recall,
    )

    # DoD: tests must pass. If Red produced a concrete Docker proof, it must fail.
    dod_cmd = test_command
    if exploit_proof.strip():
        dod_cmd = (
            f"{test_command} && "
            "(! docker exec arena sh -lc '"
            + exploit_proof.replace("'", "'\"'\"'")
            + "')"
        )

    spec: dict[str, Any] = {
        "task_id": f"battle-patch-{uuid.uuid4().hex[:10]}",
        "title": f"Patch battle finding in {target_rel}",
        "cwd": str(cwd),
        "backend": "codex",
        "output_dir": "",
        "prompt": prompt,
        "allowlist": allowlist,
        "read_context": [target_rel, "tests/", "test/", "spec/", "exploit/"],
        "definition_of_done": {
            "command": dod_cmd,
            "assertion": "exit_code == 0",
        },
        "max_rounds": max_rounds,
    }

    run_sh = _resolve_code_runner_run(cwd)

    if run_sh is None:
        logger.error(
            "code-runner not found. Checked sibling {}, cwd .pi, and cwd skills.",
            SIBLING_CODE_RUNNER_RUN,
        )
        return PatchResult(success=False)

    code_runner_dir = run_sh.parent

    patch_runs_dir = SKILL_DIR / "patch-runs"
    patch_runs_dir.mkdir(parents=True, exist_ok=True)
    td_path = Path(tempfile.mkdtemp(prefix="patch_writer_", dir=str(patch_runs_dir)))
    try:
        spec_path = td_path / "spec.json"
        spec["output_dir"] = str(td_path)
        spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

        logger.info("Running code-runner for target={} rounds={}", target_rel, max_rounds)
        try:
            _ = httpx.URL("http://localhost")  # touch httpx so import is not dead.
            proc = subprocess.run(
                [str(run_sh), "run", str(spec_path), "--max-rounds", str(max_rounds)],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            logger.exception("Failed invoking code-runner: {}", e)
            return PatchResult(success=False)

        if proc.returncode != 0:
            logger.error(
                "code-runner failed rc={} stdout={} stderr={} artifacts={}",
                proc.returncode,
                proc.stdout[-2000:],
                proc.stderr[-2000:],
                td_path,
            )
            return PatchResult(success=False)

        result_path = td_path / f"{spec['task_id']}.result.json"
        if not result_path.exists():
            alt = code_runner_dir / "result.json"
            if alt.exists():
                result_path = alt
            else:
                logger.error("No result.json found after code-runner run")
                return PatchResult(success=False)

        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.exception("Failed reading result.json: {}", e)
            return PatchResult(success=False)
    finally:
        if os.getenv("BATTLE_KEEP_PATCH_RUNS") != "0":
            pass
        else:
            shutil.rmtree(td_path, ignore_errors=True)

    rounds = int(result.get("rounds_completed", result.get("rounds", 0)) or 0)
    success = bool(
        result.get("success", False)
        or result.get("dod_passed", False)
        or result.get("status") == "pass"
    )
    patch_diff = (
        result.get("patch_diff")
        or result.get("final_diff")
        or result.get("diff")
        or ""
    )
    if not patch_diff and result.get("patch_artifact"):
        patch_artifact = Path(str(result["patch_artifact"]))
        if patch_artifact.exists():
            patch_diff = patch_artifact.read_text(encoding="utf-8")
    score = float(result.get("score", result.get("best_score", 0.0)) or 0.0)

    # Receipt-truth: functionality-preservation is only PROVEN by explicit passing
    # functional assertions. Deriving it from DoD `success` alone inflates the score,
    # because the DoD can be a trivial gate (e.g. `test -d .` for a target with no test
    # harness, or a compile-only `py_compile`) that never exercises real behavior.
    # Absent real assertions the claim stays fail-closed (unproven -> False).
    final_assertions = result.get("assertions", [])
    if isinstance(final_assertions, list) and final_assertions:
        functionality_preserved = all(bool(x) for x in final_assertions)
    else:
        functionality_preserved = False

    return PatchResult(
        success=success,
        rounds=rounds,
        patch_diff=patch_diff,
        score=score,
        functionality_preserved=functionality_preserved,
    )
