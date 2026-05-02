from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from os import environ
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "skills" / "governance" / "scripts" / "governance_loop.py"
RUN_SH = REPO_ROOT / "skills" / "governance" / "run.sh"
PLAN_RUN_SH = REPO_ROOT / "skills" / "plan" / "run.sh"
PLAN_PY = REPO_ROOT / "skills" / "plan" / "plan.py"


def task_hash(task: str) -> str:
    normalized = " ".join(task.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def run_governance(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), *args]
    merged_env = environ.copy()
    merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged_env.update(env)
    return subprocess.run(command, cwd=REPO_ROOT, env=merged_env, capture_output=True, text=True, timeout=60)


@pytest.fixture
def repo_file(tmp_path: Path):
    created: list[Path] = []

    def make(name: str, content: str = "read\n") -> Path:
        path = REPO_ROOT / "skills" / "governance" / "tests" / f".tmp-{name}-{tmp_path.name}.txt"
        path.write_text(content, encoding="utf-8")
        created.append(path)
        return path

    yield make

    for path in created:
        path.unlink(missing_ok=True)


def test_run_rejects_nonexistent_evidence(tmp_path: Path) -> None:
    result = run_governance([
        "run",
        "--task",
        "invalid evidence task",
        "--files-read",
        "does-not-exist",
        "--understanding-confirmed",
        "--output-dir",
        str(tmp_path / "governance"),
        "--json",
    ])

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "BLOCKED"
    evidence_check = next(check for check in report["checks"] if check["id"] == "evidence_valid")
    assert evidence_check["status"] == "FAIL"


def test_status_rejects_fake_latest_without_report(tmp_path: Path) -> None:
    task = "fake latest task"
    root = tmp_path / "governance"
    digest = task_hash(task)
    latest = root / "reports" / digest / "latest.json"
    latest.parent.mkdir(parents=True)
    latest.write_text(json.dumps({
        "schema": "governance.pre_plan_report.v1.latest",
        "task": task,
        "task_hash": digest,
        "status": "PASS",
        "report_json": str(root / "missing-report.json"),
    }))

    result = run_governance([
        "status",
        "--task",
        task,
        "--require-pass",
        "--output-dir",
        str(root),
        "--json",
    ])

    assert result.returncode == 2
    status = json.loads(result.stdout)
    assert status["status"] == "INVALID"
    assert "does not exist" in status["message"]


def test_status_marks_pass_stale_when_evidence_changes(tmp_path: Path, repo_file) -> None:
    task = "stale evidence task"
    evidence = repo_file("stale-evidence", "before\n")
    root = tmp_path / "governance"

    created = run_governance([
        "run",
        "--task",
        task,
        "--files-read",
        str(evidence),
        "--understanding-confirmed",
        "--output-dir",
        str(root),
    ])
    assert created.returncode == 0, created.stderr

    ok = run_governance(["status", "--task", task, "--require-pass", "--output-dir", str(root), "--json"])
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert json.loads(ok.stdout)["status"] == "PASS"

    evidence.write_text("after\n", encoding="utf-8")
    stale = run_governance(["status", "--task", task, "--require-pass", "--output-dir", str(root), "--json"])

    assert stale.returncode == 2
    assert json.loads(stale.stdout)["status"] == "STALE"


def test_unrelated_dirty_file_does_not_stale_pass(tmp_path: Path, repo_file) -> None:
    task = "scoped dirty task"
    evidence = repo_file("scoped-evidence")
    unrelated = repo_file("unrelated-dirty")
    unrelated.unlink(missing_ok=True)
    root = tmp_path / "governance"

    created = run_governance([
        "run",
        "--task",
        task,
        "--files-read",
        str(evidence),
        "--understanding-confirmed",
        "--output-dir",
        str(root),
    ])
    assert created.returncode == 0, created.stdout + created.stderr

    unrelated.write_text("unrelated\n", encoding="utf-8")
    ok = run_governance(["status", "--task", task, "--require-pass", "--output-dir", str(root), "--json"])

    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert json.loads(ok.stdout)["status"] == "PASS"


def test_selected_skill_doc_change_stales_pass(tmp_path: Path, repo_file) -> None:
    task = "skill doc stale task"
    evidence = repo_file("skill-doc-evidence")
    skill_name = f".tmp-governance-skill-{tmp_path.name}"
    skill_dir = REPO_ROOT / "skills" / skill_name
    skill_doc = skill_dir / "SKILL.md"
    root = tmp_path / "governance"

    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_doc.write_text("# Temporary skill\n", encoding="utf-8")
        created = run_governance([
            "run",
            "--task",
            task,
            "--files-read",
            str(evidence),
            "--skill",
            skill_name,
            "--understanding-confirmed",
            "--output-dir",
            str(root),
        ])
        assert created.returncode == 0, created.stdout + created.stderr

        skill_doc.write_text("# Temporary skill\nchanged\n", encoding="utf-8")
        stale = run_governance(["status", "--task", task, "--require-pass", "--output-dir", str(root), "--json"])

        assert stale.returncode == 2
        assert json.loads(stale.stdout)["status"] == "STALE"
    finally:
        skill_doc.unlink(missing_ok=True)
        try:
            skill_dir.rmdir()
        except OSError:
            pass


def test_run_sh_refuses_repo_local_artifact_root() -> None:
    env = environ.copy()
    env["GOVERNANCE_ARTIFACT_ROOT"] = str(REPO_ROOT / "skills" / "governance" / "artifacts")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [str(RUN_SH), "doctor"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 2
    assert "inside the repository" in result.stderr


def test_plan_run_sh_refuses_repo_local_uv_env() -> None:
    env = environ.copy()
    env["PLAN_UV_ENV"] = str(REPO_ROOT / "skills" / "plan" / ".venv-test")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [str(PLAN_RUN_SH), "--validate", "missing.yaml"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 2
    assert "inside the repository" in result.stderr


def test_tmp_only_evidence_blocks_without_test_override(tmp_path: Path) -> None:
    task = "tmp only evidence task"
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("scratch\n", encoding="utf-8")

    result = run_governance([
        "run",
        "--task",
        task,
        "--files-read",
        str(evidence),
        "--understanding-confirmed",
        "--output-dir",
        str(tmp_path / "governance"),
        "--json",
    ])

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "BLOCKED"
    assert any(check["id"] == "evidence_valid" and check["status"] == "FAIL" for check in report["checks"])


@pytest.mark.parametrize(
    ("args", "expected_action"),
    [
        ([], "Do not plan yet"),
        (["--unknown", "missing requirement"], "Resolve unknowns"),
        (["--needs-interview"], "Use /interview"),
        (["--needs-research"], "Use /dogpile"),
    ],
)
def test_blocking_flags_return_expected_actions(tmp_path: Path, repo_file, args: list[str], expected_action: str) -> None:
    task = f"blocking flag task {expected_action}"
    evidence = repo_file(expected_action.replace("/", "").replace(" ", "-"))
    command = [
        "run",
        "--task",
        task,
        "--files-read",
        str(evidence),
        "--output-dir",
        str(tmp_path / "governance"),
        "--json",
        *args,
    ]
    if args:
        command.append("--understanding-confirmed")

    result = run_governance(command)

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "BLOCKED"
    assert any(expected_action in action for action in report["required_next_actions"])


def test_status_rejects_latest_pointing_to_mismatched_task(tmp_path: Path, repo_file) -> None:
    task = "original report task"
    other_task = "different requested task"
    evidence = repo_file("mismatch-evidence")
    root = tmp_path / "governance"

    created = run_governance([
        "run",
        "--task",
        task,
        "--files-read",
        str(evidence),
        "--understanding-confirmed",
        "--output-dir",
        str(root),
    ])
    assert created.returncode == 0, created.stdout + created.stderr

    original_latest = json.loads((root / "reports" / task_hash(task) / "latest.json").read_text(encoding="utf-8"))
    forged_latest = root / "reports" / task_hash(other_task) / "latest.json"
    forged_latest.parent.mkdir(parents=True)
    forged_latest.write_text(json.dumps(original_latest), encoding="utf-8")

    result = run_governance(["status", "--task", other_task, "--require-pass", "--output-dir", str(root), "--json"])

    assert result.returncode == 2
    status = json.loads(result.stdout)
    assert status["status"] == "INVALID"
    assert "does not match" in status["message"]


def test_status_rejects_pass_report_with_failed_check(tmp_path: Path, repo_file) -> None:
    task = "forged failed check task"
    evidence = repo_file("failed-check-evidence")
    root = tmp_path / "governance"

    created = run_governance([
        "run",
        "--task",
        task,
        "--files-read",
        str(evidence),
        "--understanding-confirmed",
        "--output-dir",
        str(root),
    ])
    assert created.returncode == 0, created.stdout + created.stderr

    latest = json.loads((root / "reports" / task_hash(task) / "latest.json").read_text(encoding="utf-8"))
    report_path = Path(latest["report_json"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["checks"][0]["status"] = "FAIL"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = run_governance(["status", "--task", task, "--require-pass", "--output-dir", str(root), "--json"])

    assert result.returncode == 2
    status = json.loads(result.stdout)
    assert status["status"] == "INVALID"
    assert "deterministic checks" in status["message"]


def test_status_rejects_expired_pass(tmp_path: Path, repo_file) -> None:
    task = "expired pass task"
    evidence = repo_file("expired-evidence")
    root = tmp_path / "governance"

    created = run_governance([
        "run",
        "--task",
        task,
        "--files-read",
        str(evidence),
        "--understanding-confirmed",
        "--output-dir",
        str(root),
    ])
    assert created.returncode == 0, created.stdout + created.stderr

    latest = json.loads((root / "reports" / task_hash(task) / "latest.json").read_text(encoding="utf-8"))
    report_path = Path(latest["report_json"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["created_at"] = "20000101T000000Z"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = run_governance(["status", "--task", task, "--require-pass", "--output-dir", str(root), "--json"])

    assert result.returncode == 2
    status = json.loads(result.stdout)
    assert status["status"] == "STALE"
    assert "older" in status["message"]


def test_uri_evidence_requires_digest_and_repo_file(tmp_path: Path, repo_file) -> None:
    root = tmp_path / "governance"
    evidence = repo_file("uri-evidence")
    digest_uri = "https://example.test/evidence.txt?sha256=" + ("a" * 64)

    missing_digest = run_governance([
        "run",
        "--task",
        "uri missing digest task",
        "--files-read",
        str(evidence),
        "--files-read",
        "https://example.test/evidence.txt",
        "--understanding-confirmed",
        "--output-dir",
        str(root),
        "--json",
    ])
    assert missing_digest.returncode == 2
    assert any(check["id"] == "evidence_valid" and check["status"] == "FAIL" for check in json.loads(missing_digest.stdout)["checks"])

    uri_only = run_governance([
        "run",
        "--task",
        "uri only task",
        "--files-read",
        digest_uri,
        "--understanding-confirmed",
        "--output-dir",
        str(root),
        "--json",
    ])
    assert uri_only.returncode == 2
    assert any(check["id"] == "repo_file_evidence" and check["status"] == "FAIL" for check in json.loads(uri_only.stdout)["checks"])

    with_repo_file = run_governance([
        "run",
        "--task",
        "uri with repo file task",
        "--files-read",
        str(evidence),
        "--files-read",
        digest_uri,
        "--understanding-confirmed",
        "--output-dir",
        str(root),
    ])
    assert with_repo_file.returncode == 0, with_repo_file.stdout + with_repo_file.stderr


def test_wrappers_do_not_shell_source_env() -> None:
    assert 'source "$PROJECT_ROOT/.env"' not in RUN_SH.read_text(encoding="utf-8")
    assert 'source "$PROJECT_ROOT/.env"' not in PLAN_RUN_SH.read_text(encoding="utf-8")


def test_direct_plan_py_requires_governance_pass(tmp_path: Path) -> None:
    task = "direct plan governance gate task"
    root = tmp_path / "governance"
    evidence = tmp_path / "plan-evidence.txt"
    evidence.write_text("read\n")
    env = environ.copy()
    env["GOVERNANCE_ARTIFACT_ROOT"] = str(root)
    env["GOVERNANCE_ALLOW_TMP_EVIDENCE"] = "1"
    env["UV_PROJECT_ENVIRONMENT"] = str(tmp_path / "plan-venv")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    missing = subprocess.run(
        ["uv", "run", "--project", "skills/plan", "python", str(PLAN_PY), task],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert missing.returncode == 2
    assert "Governance status: MISSING" in missing.stdout

    created = run_governance([
        "run",
        "--task",
        task,
        "--files-read",
        str(evidence),
        "--understanding-confirmed",
    ], env=env)
    assert created.returncode == 0, created.stdout + created.stderr

    allowed = subprocess.run(
        ["uv", "run", "--project", "skills/plan", "python", str(PLAN_PY), task],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert f"Goal: {task}" in allowed.stdout
