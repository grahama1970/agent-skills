from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "webgpt_ready_loop.py"
SPEC = importlib.util.spec_from_file_location("webgpt_ready_loop", MODULE)
assert SPEC is not None and SPEC.loader is not None
loop = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = loop
SPEC.loader.exec_module(loop)


def test_classify_requires_unnegated_ready_to_deploy_phrase() -> None:
    assert loop.classify_response("ready-to-deploy")["ready_to_deploy"] is True
    assert loop.classify_response("not yet ready-to-deploy")["ready_to_deploy"] is False
    assert loop.classify_response("No ready-to-deploy verdict until P1 fixes land")["ready_to_deploy"] is False


def test_build_packet_sanitizes_local_paths(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    prior = tmp_path / "prior.md"
    prior.write_text("Inspect /home/graham/workspace/experiments/agent-skills/secret.py and /tmp/foo", encoding="utf-8")
    calls = []

    def fake_run(argv, *, cwd, timeout=600):
        calls.append(argv)
        return {"returncode": 0, "stdout": "/home/graham/workspace/experiments/agent-skills/file.py", "stderr": ""}

    monkeypatch.setattr(loop, "run_cmd", fake_run)
    packet = loop.build_packet(repo, prior_response=prior, output=tmp_path / "packet.md")
    text = packet.read_text(encoding="utf-8")

    assert "/home/graham" not in text
    assert "/tmp/foo" not in text
    assert "ready-to-deploy" in text
    assert len(calls) == 2


def test_main_plan_only_writes_receipt(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(loop, "run_cmd", lambda *a, **k: {"returncode": 0, "stdout": "", "stderr": ""})

    rc = loop.main(["--repo", str(repo), "--output-root", str(tmp_path / "out")])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["ready_to_deploy"] is False
    assert "--execute" in out["next_command"]
    assert (tmp_path / "out" / "loop-receipt.json").is_file()
