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


def test_classify_requires_evidence_bound_ready_verdict() -> None:
    candidate = "sha256:" + "a" * 64
    packet = "sha256:" + "b" * 64
    ready = f"VERDICT: ready-to-deploy\nCANDIDATE_DIGEST: {candidate}\nPACKET_DIGEST: {packet}\nBLOCKING_FINDINGS: none"
    assert loop.classify_response(ready, candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is True
    assert loop.classify_response(f'Do not deploy. The requested token was "{loop.READY_PHRASE}". P1 blockers remain.')["ready_to_deploy"] is False
    assert loop.classify_response(ready + "\nP1 blocker", candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is False
    assert loop.classify_response(ready.replace(candidate, "sha256:" + "c" * 64), candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is False


def test_packet_binds_candidate_and_preserves_evidence(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    prior = tmp_path / "prior.md"
    prior.write_text("Inspect /home/graham/workspace/experiments/agent-skills/secret.py and /tmp/foo", encoding="utf-8")
    calls = []

    def fake_run(argv, *, cwd, timeout=600):
        calls.append(argv)
        if argv[:2] == ["git", "status"]:
            return {"returncode": 0, "stdout": " M skills/project-watchdog/scripts/webgpt_ready_loop.py\n?? skills/project-watchdog/tests/test_new.py\n", "stderr": ""}
        if argv[:2] == ["git", "diff"]:
            return {"returncode": 0, "stdout": "diff --git a/skills/project-watchdog/scripts/webgpt_ready_loop.py\n+    indented = True\n", "stderr": ""}
        if argv[:2] == ["crontab", "-l"]:
            return {"returncode": 1, "stdout": "", "stderr": "crontab read failed"}
        return {"returncode": 0, "stdout": "3 passed", "stderr": ""}

    (repo / "skills/project-watchdog/scripts").mkdir(parents=True)
    (repo / "skills/project-watchdog/scripts/webgpt_ready_loop.py").write_text("print('x')\n", encoding="utf-8")
    (repo / "skills/project-watchdog/tests").mkdir(parents=True)
    (repo / "skills/project-watchdog/tests/test_new.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(loop, "run_cmd", fake_run)
    packet, digest = loop.build_packet(repo, prior_response=prior, output=tmp_path / "packet.md")
    text = packet.read_text(encoding="utf-8")

    assert digest.startswith("sha256:")
    assert "candidate_digest" in text
    assert "skills > project-watchdog > scripts > webgpt_ready_loop.py" in text
    assert "+    indented = True" in text
    assert "crontab_returncode" in text and "1" in text
    assert "/home/graham" not in text
    assert "/tmp/foo" not in text
    assert "ready-to-deploy" in text
    assert len(calls) >= 4


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
