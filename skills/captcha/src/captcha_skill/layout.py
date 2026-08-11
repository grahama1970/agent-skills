"""Repository layout, pinned ReCAP source, readiness, and argv contracts.

Filesystem and subprocess boundaries fail closed. ReCAP source identity includes
its origin URL, exact commit, clean executable trees, required files, and a
probed dedicated virtual environment.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from pydantic import ValidationError

from .dotenv_helper import load_skill_dotenv
from .constants import (
    DEFAULT_RECAP_ROOT,
    DEFAULT_STORAGE_ROOT,
    LOCAL_MODEL_API_KEY_ENV,
    RECAP_COMMIT,
    RECAP_REPOSITORY,
)
from .errors import CaptchaSkillError, ErrorCode
from .models import (
    AuthorizationManifest,
    RecapRuntimeProbe,
    RunStatus,
    StatusReport,
    TestMode,
)

load_skill_dotenv()


def skill_root() -> Path:
    """Return ``skills/captcha`` from the installed package location."""

    return Path(__file__).resolve().parents[2]


def repository_root() -> Path:
    """Return the agent-skills repository root."""

    return skill_root().parent.parent


def surf_run_path() -> Path:
    """Return the sibling Surf runtime entry point."""

    return repository_root() / "skills" / "surf" / "run.sh"


def ask_skill_path() -> Path:
    """Return the sibling Ask skill contract path."""

    return repository_root() / "skills" / "ask" / "SKILL.md"


def ask_runtime_path() -> Path:
    """Return Ask's actual DAG consumer module path."""

    return repository_root() / "skills" / "ask" / "src" / "ask" / "ask_dag.py"


def _safe_resolve(path: Path) -> Path:
    """Resolve a filesystem path and convert failures into typed errors."""

    try:
        return path.expanduser().resolve()
    except OSError as exc:
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            f"could not resolve path: {path}",
            {"path": str(path), "error": str(exc)},
        ) from exc


def _lexical_absolute(path: Path) -> Path:
    """Normalize ``..`` without dereferencing the final virtualenv symlink."""

    try:
        return Path(os.path.abspath(os.path.expanduser(str(path))))
    except OSError as exc:
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            f"could not normalize path: {path}",
            {"path": str(path), "error": str(exc)},
        ) from exc


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _git_stdout(recap_root: Path, *args: str) -> str | None:
    if not (recap_root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(recap_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _git_head(recap_root: Path) -> str | None:
    output = _git_stdout(recap_root, "rev-parse", "HEAD")
    return output.strip() if output else None


def _git_origin(recap_root: Path) -> str | None:
    output = _git_stdout(recap_root, "remote", "get-url", "origin")
    return output.strip() if output else None


def _canonical_github_repository(value: str) -> str:
    """Normalize common GitHub clone URL forms for an exact repository check."""

    candidate = value.strip().rstrip("/")
    if candidate.startswith("git@github.com:"):
        candidate = "https://github.com/" + candidate.removeprefix("git@github.com:")
    elif candidate.startswith("ssh://git@github.com/"):
        candidate = "https://github.com/" + candidate.removeprefix(
            "ssh://git@github.com/"
        )
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    return candidate


def _repository_matches(recap_root: Path) -> bool | None:
    origin = _git_origin(recap_root)
    if origin is None:
        return None
    return _canonical_github_repository(origin) == RECAP_REPOSITORY


def _recap_source_state(recap_root: Path) -> tuple[bool | None, list[str]]:
    """Check executable upstream trees for tracked or unsafe untracked drift."""

    tracked = _git_stdout(
        recap_root,
        "status",
        "--porcelain",
        "--untracked-files=no",
        "--",
        "captcha_eval_framework",
        "dynamic_captchas",
    )
    untracked = _git_stdout(
        recap_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "captcha_eval_framework",
        "dynamic_captchas",
    )
    if tracked is None or untracked is None:
        return None, ["git source-state query failed"]

    findings = [line.strip() for line in tracked.splitlines() if line.strip()]
    executable_suffixes = {
        ".py",
        ".pyc",
        ".pth",
        ".so",
        ".dll",
        ".dylib",
        ".js",
        ".mjs",
        ".cjs",
    }
    unsafe_names = {".env", "sitecustomize.py", "usercustomize.py"}
    for raw in untracked.splitlines():
        relative = raw.strip()
        if not relative:
            continue
        candidate = Path(relative)
        if candidate.suffix.lower() in executable_suffixes or candidate.name in unsafe_names:
            findings.append(f"?? {relative}")
    return not findings, findings


def default_recap_python(recap_root: Path) -> Path:
    """Return the required dedicated ReCAP virtualenv interpreter path."""

    return _lexical_absolute(recap_root) / ".venv" / "bin" / "python"


def _probe_recap_python(recap_root: Path, recap_python: Path) -> RecapRuntimeProbe:
    """Execute an isolated interpreter identity probe through the declared venv."""

    probe_source = (
        "import json,sys; "
        "print(json.dumps({"
        "'schema_version':'captcha.recap_runtime_probe.v1',"
        "'executable':sys.executable,"
        "'prefix':sys.prefix,"
        "'base_prefix':sys.base_prefix,"
        "'version':list(sys.version_info[:3])"
        "},sort_keys=True))"
    )
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONNOUSERSITE": "1",
    }
    try:
        result = subprocess.run(
            [str(recap_python), "-I", "-c", probe_source],
            cwd=recap_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_INVALID,
            "dedicated ReCAP Python identity probe failed to start",
            {"runtime_python": str(recap_python), "error": str(exc)},
        ) from exc
    if result.returncode != 0:
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_INVALID,
            "dedicated ReCAP Python identity probe exited non-zero",
            {
                "runtime_python": str(recap_python),
                "exit_code": result.returncode,
                "stderr": result.stderr[-2000:],
            },
        )
    try:
        value = json.loads(result.stdout)
        probe = RecapRuntimeProbe.model_validate(value)
    except (json.JSONDecodeError, ValidationError) as exc:
        details: dict[str, object] = {
            "runtime_python": str(recap_python),
            "stdout": result.stdout[-2000:],
            "error": str(exc),
        }
        if isinstance(exc, ValidationError):
            details["errors"] = exc.errors(include_url=False)
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_INVALID,
            "dedicated ReCAP Python emitted an invalid identity probe",
            details,
        ) from exc

    expected_prefix = _safe_resolve(recap_root / ".venv")
    actual_prefix = _safe_resolve(Path(probe.prefix))
    if actual_prefix != expected_prefix:
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_INVALID,
            "declared ReCAP Python is not running from the checkout virtualenv",
            {"expected_prefix": str(expected_prefix), "actual_prefix": str(actual_prefix)},
        )
    if not ((3, 11, 0) <= probe.version < (3, 14, 0)):
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_INVALID,
            "ReCAP Python version must be >=3.11 and <3.14",
            {"version": list(probe.version)},
        )
    return probe


def status_report(
    *,
    recap_root: Path = DEFAULT_RECAP_ROOT,
    storage_root: Path = DEFAULT_STORAGE_ROOT,
    recap_python: Path | None = None,
) -> StatusReport:
    """Report readiness without target/model network access or live effects."""

    root = skill_root()
    ask_path = ask_skill_path()
    ask_runtime = ask_runtime_path()
    surf_path = surf_run_path()
    recap = _safe_resolve(recap_root)
    storage = _safe_resolve(storage_root)
    runtime_python = _lexical_absolute(recap_python or default_recap_python(recap))

    ask_present = ask_path.is_file()
    ask_declares = False
    if ask_present:
        try:
            frontmatter = ask_path.read_text(encoding="utf-8").split("---", 2)[1]
            ask_declares = any(line.strip() == "- captcha" for line in frontmatter.splitlines())
        except (OSError, IndexError):
            ask_declares = False

    recap_present = recap.is_dir()
    repository_matches = _repository_matches(recap) if recap_present else None
    head = _git_head(recap) if recap_present else None
    commit_matches = head == RECAP_COMMIT if head is not None else None
    source_clean, source_findings = (
        _recap_source_state(recap)
        if repository_matches is True and commit_matches is True
        else (None, [])
    )
    runtime_present = False
    runtime_error: str | None = None
    if repository_matches is True and commit_matches is True and source_clean is True:
        try:
            validate_recap_runtime(recap, runtime_python)
            runtime_present = True
        except CaptchaSkillError as exc:
            runtime_error = str(exc)

    surf_present = surf_path.is_file() and os.access(surf_path, os.X_OK)
    model_key_present = bool(os.environ.get(LOCAL_MODEL_API_KEY_ENV, "").strip())
    blockers: list[str] = []
    next_actions: list[str] = []
    if not ask_present:
        blockers.append("Ask skill contract is missing.")
    elif not ask_declares:
        blockers.append("Ask does not declare captcha in its composes frontmatter.")
    if not ask_runtime.is_file():
        blockers.append("Ask DAG consumer module is missing.")
    if not surf_present:
        blockers.append("Surf run.sh is missing or not executable.")
    if not recap_present:
        blockers.append("Pinned ReCAP checkout is not installed.")
        next_actions.append(
            f"Clone {RECAP_REPOSITORY} to {recap} and checkout {RECAP_COMMIT}."
        )
    elif repository_matches is not True:
        blockers.append("ReCAP checkout origin is absent or not the approved repository.")
        next_actions.append(f"Set origin to {RECAP_REPOSITORY} after reviewing the checkout.")
    elif commit_matches is not True:
        blockers.append("ReCAP checkout is absent from git or not at the approved commit.")
        next_actions.append(f"Run: git -C {recap} checkout {RECAP_COMMIT}")
    elif source_clean is not True:
        blockers.append("ReCAP executable source trees are dirty or could not be proven clean.")
        if source_findings:
            next_actions.append("Inspect ReCAP source drift: " + "; ".join(source_findings[:5]))
    if not runtime_present:
        blockers.append(runtime_error or "Dedicated ReCAP Python runtime is missing.")
        next_actions.append(
            f"Create {recap / '.venv'} and install ReCAP requirements there."
        )
    if not model_key_present:
        blockers.append(f"{LOCAL_MODEL_API_KEY_ENV} is not set for the loopback model endpoint.")
        next_actions.append(f"Export {LOCAL_MODEL_API_KEY_ENV} without storing it in the repository.")
    if not storage.is_dir():
        blockers.append("Storage-backed captcha root is missing.")
        next_actions.append(f"Create storage directories under {storage}.")

    status = RunStatus.PASS if not blockers else RunStatus.NOT_ESTABLISHED
    return StatusReport(
        schema_version="captcha.status.v1",
        status=status,
        skill_root=str(root),
        ask_skill_present=ask_present,
        ask_declares_captcha=ask_declares,
        ask_runtime_present=ask_runtime.is_file(),
        surf_run_present=surf_present,
        recap_checkout_present=recap_present,
        recap_repository_matches=repository_matches,
        recap_commit_matches=commit_matches,
        recap_source_clean=source_clean,
        recap_runtime_present=runtime_present,
        model_api_key_present=model_key_present,
        storage_root_present=storage.is_dir(),
        blockers=blockers,
        next_actions=next_actions,
        limitations=[
            "Readiness does not execute ReCAP or contact a CAPTCHA target/model endpoint.",
            "Only synthetic dynamic CAPTCHAs on literal loopback IPs are supported.",
        ],
    )


def validate_recap_runtime(
    recap_root: Path,
    recap_python: Path,
) -> RecapRuntimeProbe:
    """Validate official pinned source and the dedicated virtualenv runtime."""

    root = _safe_resolve(recap_root)
    python_path = _lexical_absolute(recap_python)
    if not root.is_dir():
        raise CaptchaSkillError(
            ErrorCode.RECAP_CHECKOUT_MISSING,
            "ReCAP checkout does not exist",
            {"recap_root": str(root)},
        )
    repository_matches = _repository_matches(root)
    if repository_matches is not True:
        raise CaptchaSkillError(
            ErrorCode.RECAP_REPOSITORY_MISMATCH,
            "ReCAP checkout origin is absent or not the approved repository",
            {"expected": RECAP_REPOSITORY, "actual": _git_origin(root)},
        )
    head = _git_head(root)
    if head != RECAP_COMMIT:
        raise CaptchaSkillError(
            ErrorCode.RECAP_COMMIT_MISMATCH,
            "ReCAP checkout is not at the approved commit",
            {"expected": RECAP_COMMIT, "actual": head, "recap_root": str(root)},
        )
    source_clean, source_findings = _recap_source_state(root)
    if source_clean is not True:
        raise CaptchaSkillError(
            ErrorCode.RECAP_SOURCE_DIRTY,
            "ReCAP executable source trees are dirty or unprovable",
            {"findings": source_findings},
        )
    required = [
        root / "captcha_eval_framework" / "main.py",
        root / "captcha_eval_framework" / "providers" / "dynamic_provider.py",
        root / "dynamic_captchas" / "app.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise CaptchaSkillError(
            ErrorCode.RECAP_CHECKOUT_MISSING,
            "pinned ReCAP checkout is missing required files",
            {"missing": missing},
        )

    expected_bin = _lexical_absolute(root / ".venv" / "bin")
    if python_path.parent != expected_bin or python_path.name not in {"python", "python3"}:
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_MISSING,
            "ReCAP Python must be the dedicated checkout virtualenv interpreter",
            {
                "runtime_python": str(python_path),
                "expected_parent": str(expected_bin),
            },
        )
    if not (root / ".venv" / "pyvenv.cfg").is_file():
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_MISSING,
            "ReCAP virtualenv pyvenv.cfg is missing",
            {"venv": str(root / '.venv')},
        )
    if not python_path.is_file() or not os.access(python_path, os.X_OK):
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_MISSING,
            "dedicated ReCAP Python is missing or not executable",
            {"runtime_python": str(python_path)},
        )
    return _probe_recap_python(root, python_path)


def validate_storage_path(path: Path) -> Path:
    """Require live benchmark artifacts to remain on the storage-backed root."""

    resolved = _safe_resolve(path)
    storage = _safe_resolve(DEFAULT_STORAGE_ROOT)
    if not storage.is_dir():
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            "storage-backed captcha root must exist before live execution",
            {"required_root": str(storage)},
        )
    if not _is_relative_to(resolved, storage):
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            "live ReCAP artifacts must be under the storage-backed captcha root",
            {"path": str(resolved), "required_parent": str(storage)},
        )
    return resolved


def build_recap_argv(
    manifest: AuthorizationManifest,
    *,
    recap_root: Path,
    recap_python: Path,
) -> list[str]:
    """Build an argv-only ReCAP invocation from a validated manifest."""

    main_py = _safe_resolve(recap_root) / "captcha_eval_framework" / "main.py"
    runtime_python = _lexical_absolute(recap_python)
    argv = [
        str(runtime_python),
        str(main_py),
        "--provider",
        "dynamic",
        "--test-mode",
        manifest.test_mode.value,
        "--model-family",
        manifest.model_family.value,
        "--workers",
        str(manifest.workers),
        "--seed",
        str(manifest.seed),
    ]
    if manifest.test_mode is TestMode.CUSTOM:
        if manifest.captcha_name is None:
            raise CaptchaSkillError(
                ErrorCode.INVALID_MANIFEST,
                "custom mode requires captcha_name",
            )
        argv.extend(
            [
                "--captcha-name",
                manifest.captcha_name.value,
                "--test-size",
                str(manifest.test_size),
            ]
        )
    return argv
