from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from code_runner.adapters import run_backend_tool_loop, supported_backends
from code_runner.spec import TaskSpec


def _adapter_script(path: Path, stdout: str, side_effect: str = "") -> Path:
    script = path / "adapter.py"
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "_prompt = sys.stdin.read()\n"
        f"{side_effect}\n"
        f"sys.stdout.write({stdout!r})\n"
    )
    return script


def test_native_command_adapter_writes_only_through_bounded_tools(monkeypatch, tmp_path) -> None:
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("def answer():\n    return 0\n")
    script = _adapter_script(
        tmp_path,
        "### FILE: src/app.py\n```python\ndef answer():\n    return 42\n```\n",
        "Path('adapter_leak.txt').write_text('not in source')",
    )
    monkeypatch.setenv("CODE_RUNNER_CODEX_EXEC_COMMAND", f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}")

    written, messages = run_backend_tool_loop(
        "system",
        "user",
        "codex-exec",
        str(tmp_path),
        ["src/app.py"],
        [],
        "adapter-test",
        1,
    )

    assert written == ["src/app.py"]
    assert target.read_text() == "def answer():\n    return 42\n"
    assert not (tmp_path / "adapter_leak.txt").exists()
    tool_results = [json.loads(message["content"]) for message in messages if message.get("role") == "tool"]
    assert tool_results == [{"ok": True, "path": "src/app.py"}]


def test_native_command_adapter_cannot_write_outside_allowlist(monkeypatch, tmp_path) -> None:
    target = tmp_path / "src" / "app.py"
    secret = tmp_path / "src" / "secret.py"
    target.parent.mkdir()
    target.write_text("def answer():\n    return 0\n")
    script = _adapter_script(tmp_path, "### FILE: src/secret.py\n```python\nSECRET = True\n```\n")
    monkeypatch.setenv("CODE_RUNNER_CLAUDE_CODE_COMMAND", f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}")

    written, messages = run_backend_tool_loop(
        "system",
        "user",
        "claude-code",
        str(tmp_path),
        ["src/app.py"],
        [],
        "adapter-test",
        1,
    )

    assert written == []
    assert not secret.exists()
    tool_results = [json.loads(message["content"]) for message in messages if message.get("role") == "tool"]
    assert tool_results == [{"ok": False, "error_type": "PERMISSION", "error": "write not allowed: src/secret.py"}]


def test_native_command_adapter_backends_are_validated() -> None:
    for backend in ("codex-exec", "claude-code", "gemini-cli", "opencode"):
        assert backend in supported_backends()
        spec = TaskSpec.model_validate({
            "task_id": f"{backend}-adapter-test",
            "title": "adapter test",
            "prompt": "Change only the allowlisted file using the native command adapter.",
            "backend": backend,
            "cwd": ".",
            "output_dir": f"/tmp/code-runner-{backend}-adapter-test",
            "allowlist": ["src/app.py"],
            "definition_of_done": {"command": "true", "assertion": "exit_code == 0"},
        })
        assert spec.backend == backend


def test_native_command_adapter_missing_command_fails_closed(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="codex-exec adapter requires CODE_RUNNER_CODEX_EXEC_COMMAND"):
        run_backend_tool_loop("system", "user", "codex-exec", str(tmp_path), [], [], "adapter-test", 1)
