from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "webgpt_ready_loop.py"
SPEC = importlib.util.spec_from_file_location("webgpt_ready_loop", MODULE)
assert SPEC is not None and SPEC.loader is not None
loop = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = loop
SPEC.loader.exec_module(loop)


def test_rejects_nonterminal_or_contradictory_approval() -> None:
    candidate = "sha256:" + "a" * 64
    packet = "sha256:" + "b" * 64
    example = f"Do not deploy.\n```text\nVERDICT: ready-to-deploy\nCANDIDATE_DIGEST: {candidate}\nPACKET_DIGEST: {packet}\nBLOCKING_FINDINGS: none\n```"
    assert loop.classify_response(example, candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is False
    conflict = f"VERDICT: ready-to-deploy\nCANDIDATE_DIGEST: {candidate}\nPACKET_DIGEST: {packet}\nBLOCKING_FINDINGS: none\nVERDICT: blocked"
    assert loop.classify_response(conflict, candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is False
    trailing = f"VERDICT: ready-to-deploy\nCANDIDATE_DIGEST: {candidate}\nPACKET_DIGEST: {packet}\nBLOCKING_FINDINGS: none\n- P1: still blocked"
    assert loop.classify_response(trailing, candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is False


def test_classify_requires_evidence_bound_ready_verdict() -> None:
    candidate = "sha256:" + "a" * 64
    packet = "sha256:" + "b" * 64
    ready = f"VERDICT: ready-to-deploy\nCANDIDATE_DIGEST: {candidate}\nPACKET_DIGEST: {packet}\nBLOCKING_FINDINGS: none"
    assert loop.classify_response(ready, candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is True
    assert loop.classify_response(f'Do not deploy. The requested token was "{loop.READY_PHRASE}". P1 blockers remain.')["ready_to_deploy"] is False
    assert loop.classify_response(ready + "\nP1 blocker", candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is False
    assert loop.classify_response(ready.replace(candidate, "sha256:" + "c" * 64), candidate_digest=candidate, packet_digest=packet)["ready_to_deploy"] is False


def test_candidate_digest_tracks_raw_bytes_and_untracked_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    p = repo / "skills/project-watchdog/scripts/raw.bin"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"a\xff\n")
    subprocess.run(["git", "add", "skills/project-watchdog/scripts/raw.bin"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=repo, check=True)
    first = loop.candidate_manifest(repo)["candidate_digest"]
    p.write_bytes(b"a\xfe\n")
    second = loop.candidate_manifest(repo)["candidate_digest"]
    (repo / "skills/project-watchdog/workflows").mkdir(parents=True)
    (repo / "skills/project-watchdog/workflows/new.workflow.js").write_text("console.log('x')\n", encoding="utf-8")
    third = loop.candidate_manifest(repo)["candidate_digest"]
    assert first != second
    assert second != third


def test_packet_binds_candidate_and_preserves_evidence(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    prior = tmp_path / "prior.md"
    prior.write_text("Inspect /home/graham/workspace/experiments/agent-skills/secret.py and /tmp/foo", encoding="utf-8")
    (repo / "skills/project-watchdog/scripts").mkdir(parents=True)
    tracked = repo / "skills/project-watchdog/scripts/webgpt_ready_loop.py"
    tracked.write_text("print('x')\n", encoding="utf-8")
    subprocess.run(["git", "add", "skills/project-watchdog/scripts/webgpt_ready_loop.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=repo, check=True)
    tracked.write_text("print('x')\n    indented = True\n", encoding="utf-8")
    (repo / "skills/project-watchdog/tests").mkdir(parents=True)
    (repo / "skills/project-watchdog/tests/test_new.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    real_run = loop.run_cmd

    def fake_run(argv, *, cwd, timeout=600, output_limit=4000):
        if argv[:2] == ["crontab", "-l"]:
            return {"returncode": 1, "stdout": "", "stderr": "crontab read failed", "stdout_truncated": False, "stderr_truncated": False}
        return real_run(argv, cwd=cwd, timeout=timeout, output_limit=output_limit)

    monkeypatch.setattr(loop, "run_cmd", fake_run)
    monkeypatch.setattr(loop, "collect_proof_results", lambda repo, output_dir, candidate_digest: {"candidate_digest": candidate_digest, "command": ["pytest"], "returncode": 0, "log_sha256": "sha256:" + "c" * 64, "qualifies_candidate": True})
    packet, digest = loop.build_packet(repo, prior_response=prior, output=tmp_path / "packet.md")
    text = packet.read_text(encoding="utf-8")

    assert digest.startswith("sha256:")
    assert "candidate_digest" in text
    assert "skills > project-watchdog > scripts > webgpt_ready_loop.py" in text
    assert "+    indented = True" in text
    assert "skills > project-watchdog > tests > test_new.py" in text
    assert "crontab_returncode" in text and "1" in text
    assert "/home/graham" not in text
    assert "/tmp/foo" not in text
    assert "ready-to-deploy" in text


def test_missing_expected_digests_cannot_approve() -> None:
    text = "VERDICT: ready-to-deploy\nBLOCKING_FINDINGS: none"
    assert loop.classify_response(text)["ready_to_deploy"] is False


def test_failed_current_ask_cannot_reuse_old_response(tmp_path: Path) -> None:
    root = tmp_path / "out"
    old = root / "ask-tau-old/node-artifacts/handler-webgpt/response.md"
    old.parent.mkdir(parents=True)
    old.write_text("VERDICT: ready-to-deploy\nCANDIDATE_DIGEST: sha256:" + "a" * 64 + "\nPACKET_DIGEST: sha256:" + "b" * 64 + "\nBLOCKING_FINDINGS: none\n", encoding="utf-8")
    current = root / "bad.json"
    current.write_text("not json", encoding="utf-8")
    assert loop.latest_webgpt_response(current, root) is None


def test_main_plan_only_writes_receipt(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    packet = tmp_path / "out" / "packet-1.md"
    packet.parent.mkdir()
    packet.write_text("packet", encoding="utf-8")
    monkeypatch.setattr(loop, "build_packet", lambda *a, **k: (packet, "sha256:" + "a" * 64))

    rc = loop.main(["--repo", str(repo), "--output-root", str(tmp_path / "out")])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["ready_to_deploy"] is False
    assert "--execute" in out["next_command"]
    assert (tmp_path / "out" / "loop-receipt.json").is_file()
