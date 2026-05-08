from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "worktree_runtime.py"


def load_module_without_sys_modules_registration():
    spec = importlib.util.spec_from_file_location("worktree_runtime_unregistered", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Deliberately do not insert into sys.modules.  This reproduces the import
    # style that made @dataclass crash with: AttributeError: 'NoneType' object
    # has no attribute '__dict__'.
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=30)
    if proc.returncode != 0:
        raise AssertionError(f"{cmd!r} failed\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return proc


def make_repo(parent: Path) -> Path:
    repo = parent / "repo"
    repo.mkdir()
    run(["git", "init"], repo)
    run(["git", "config", "user.email", "test@example.invalid"], repo)
    run(["git", "config", "user.name", "Test User"], repo)
    (repo / "README.md").write_text("hello\n")
    run(["git", "add", "README.md"], repo)
    run(["git", "commit", "-m", "initial"], repo)
    return repo


def test_module_imports_when_not_registered_in_sys_modules() -> None:
    module = load_module_without_sys_modules_registration()
    assert hasattr(module, "DisposableWorktreeRuntime")
    assert hasattr(module, "create_disposable_worktree")


def test_disposable_worktree_context_creates_and_cleans_isolated_checkout() -> None:
    module = load_module_without_sys_modules_registration()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = make_repo(tmp_path)
        parent = tmp_path / "worktrees"

        with module.disposable_worktree(repo, task_id="task 1", parent_dir=parent) as runtime:
            wt_path = runtime.path
            branch = runtime.branch
            assert wt_path.exists()
            assert (wt_path / "README.md").read_text() == "hello\n"
            assert branch.startswith("code-runner/task-1-")
            (wt_path / "README.md").write_text("changed in worktree\n")
            run(["git", "status", "--porcelain"], wt_path)
            assert (repo / "README.md").read_text() == "hello\n"

        assert not wt_path.exists()
        branches = run(["git", "branch", "--list", branch], repo).stdout.strip()
        assert branches == ""


def main() -> None:
    test_module_imports_when_not_registered_in_sys_modules()
    test_disposable_worktree_context_creates_and_cleans_isolated_checkout()
    print("worktree_runtime tests passed")


if __name__ == "__main__":
    main()
