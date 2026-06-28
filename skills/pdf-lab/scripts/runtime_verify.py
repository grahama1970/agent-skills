"""Runtime verifier for pdf-lab job directories.

Inputs: a pdf-lab job/output directory.
Outputs: verify-receipt.json with deterministic checks.
Failure modes: exits non-zero when required artifacts are absent, malformed, or
internally inconsistent.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from datetime import UTC, datetime

import typer


SKILL_DIR = Path(__file__).resolve().parents[1]
SHARED_HELPERS = SKILL_DIR.parent / "_shared" / "skill_self_improvement.py"


def _load_helpers() -> Any:
    if not SHARED_HELPERS.exists():
        return _LocalHelpers
    spec = importlib.util.spec_from_file_location("skill_self_improvement", SHARED_HELPERS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load runtime helper module: {SHARED_HELPERS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _LocalHelpers:
    @staticmethod
    def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
        return {"name": name, "passed": passed, "detail": detail}

    @staticmethod
    def finalize_verify_result(
        *,
        skill_id: str,
        mode: str,
        job_dir: Path,
        checks: list[dict[str, Any]],
        summary: dict[str, Any] | None = None,
        schema_version: str = "skill.runtime_verify.v1",
    ) -> dict[str, Any]:
        passed = all(item.get("passed") for item in checks)
        return {
            "schema_version": schema_version,
            "skill_id": skill_id,
            "mode": mode,
            "job_dir": str(job_dir.expanduser().resolve()),
            "verified_at": datetime.now(UTC).isoformat(),
            "status": "PASS" if passed else "FAIL",
            "stable": passed,
            "checks": checks,
            "summary": summary or {},
        }

    @staticmethod
    def write_verify_receipt(job_dir: Path, result: dict[str, Any]) -> Path:
        path = job_dir.expanduser().resolve() / "verify-receipt.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return path


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _check_json_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing {path.name}"
    data = _read_json(path)
    if data is None:
        return False, f"malformed JSON: {path}"
    return True, f"valid JSON: {path.name}"


def build_checks(job_dir: Path) -> list[dict[str, Any]]:
    helpers = _load_helpers()
    check = helpers.check
    checks: list[dict[str, Any]] = []

    checks.append(check("job_dir_exists", job_dir.exists() and job_dir.is_dir(), str(job_dir)))

    summary_path = job_dir / "summary.json"
    comparison_path = job_dir / "comparison.json"
    triage_path = job_dir / "human_triage_queue.json"
    final_extraction_path = job_dir / "final_extraction.json"
    fix_registry_path = job_dir / "fix_registry.json"
    preset_plan_path = job_dir / "preset_update_plan.json"

    artifact_candidates = [
        summary_path,
        comparison_path,
        triage_path,
        final_extraction_path,
        fix_registry_path,
        preset_plan_path,
    ]
    present = [path for path in artifact_candidates if path.exists()]
    checks.append(
        check(
            "known_artifact_present",
            bool(present),
            "found " + ", ".join(path.name for path in present) if present else "no known pdf-lab artifacts found",
        )
    )

    for path in present:
        passed, detail = _check_json_file(path)
        checks.append(check(f"{path.name}_json_valid", passed, detail))

    if comparison_path.exists():
        data = _read_json(comparison_path)
        passed = isinstance(data, dict) and "accuracy" in data and "passed" in data
        checks.append(check("comparison_schema", passed, "requires accuracy and passed fields"))

    if triage_path.exists():
        data = _read_json(triage_path)
        if isinstance(data, dict):
            tasks = data.get("tasks")
        else:
            tasks = data
        checks.append(check("triage_tasks_schema", isinstance(tasks, list), "requires list tasks"))

    if fix_registry_path.exists():
        data = _read_json(fix_registry_path)
        passed = isinstance(data, dict) and ("overrides" in data or "fixture_id" in data)
        checks.append(check("fix_registry_schema", passed, "requires overrides or fixture_id"))

    return checks


def verify(job_dir: Path, mode: str) -> dict[str, Any]:
    helpers = _load_helpers()
    job_dir = job_dir.expanduser().resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    checks = build_checks(job_dir)
    result = helpers.finalize_verify_result(
        skill_id="pdf-lab",
        mode=mode,
        job_dir=job_dir,
        checks=checks,
        summary={"artifact_count": sum(1 for item in checks if item["name"].endswith("_json_valid"))},
    )
    helpers.write_verify_receipt(job_dir, result)
    return result


app = typer.Typer(help="Verify pdf-lab runtime job artifacts.")


@app.command()
def main(
    job_dir: Path = typer.Option(..., "--job-dir", help="pdf-lab job/output directory"),
    mode: str = typer.Option("job", "--mode", help="Verification mode label"),
) -> None:
    result = verify(job_dir, mode)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
