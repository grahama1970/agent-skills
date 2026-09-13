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
    packet, digest, qualified = loop.build_packet(repo, prior_response=prior, output=tmp_path / "packet.md")
    text = packet.read_text(encoding="utf-8")

    assert qualified is True
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


def test_ask_requires_verified_current_run_not_just_response_path(tmp_path: Path) -> None:
    root = tmp_path / "out"
    run = root / "ask-tau-current"
    response = run / "node-artifacts/handler-webgpt/response.md"
    response.parent.mkdir(parents=True)
    response.write_text("body", encoding="utf-8")
    missing = run / "node-artifacts/handler-webgpt/node-receipt.json"
    ask_json = root / "ask.json"
    ask_json.parent.mkdir(parents=True, exist_ok=True)
    ask_json.write_text(json.dumps({"execution": {"node_provider_receipts": [{"node_id": "handler-webgpt", "ok": True, "status": "PASS", "path": str(missing), "response_path": str(response)}]}}), encoding="utf-8")
    assert loop.latest_webgpt_response(ask_json, root) is None
    missing.write_text(json.dumps({"ok": True, "status": "PASS", "node_id": "handler-webgpt", "response_path": str(response)}), encoding="utf-8")
    assert loop.latest_webgpt_response(ask_json, root) == response


def test_failed_current_ask_cannot_reuse_old_response(tmp_path: Path) -> None:
    root = tmp_path / "out"
    old = root / "ask-tau-old/node-artifacts/handler-webgpt/response.md"
    old.parent.mkdir(parents=True)
    old.write_text("VERDICT: ready-to-deploy\nCANDIDATE_DIGEST: sha256:" + "a" * 64 + "\nPACKET_DIGEST: sha256:" + "b" * 64 + "\nBLOCKING_FINDINGS: none\n", encoding="utf-8")
    current = root / "bad.json"
    current.write_text("not json", encoding="utf-8")
    assert loop.latest_webgpt_response(current, root) is None


def test_declared_required_gate_failure_blocks_positive_reviewer(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    output_root = tmp_path / "out"
    candidate = "sha256:" + "a" * 64
    packet_digest = "sha256:" + "b" * 64
    monkeypatch.setattr(loop, "REQUIRED_PROOF_GATES", [
        {"name": "still-present", "pytest": ["skills/project-watchdog/tests/test_webgpt_ready_loop.py::test_classify_requires_evidence_bound_ready_verdict"]},
        {"name": "drifted-or-deleted", "pytest": ["skills/project-watchdog/tests/test_missing_gate.py::test_missing"]},
    ])
    monkeypatch.setattr(loop, "candidate_manifest", lambda repo: {"candidate_digest": candidate, "files": []})

    def fake_run(argv, *, cwd, timeout=600, output_limit=4000):
        junit = next((Path(str(part).split("=", 1)[1]) for part in argv if str(part).startswith("--junitxml=")), None)
        if any("test_missing_gate.py" in str(part) for part in argv):
            if junit:
                junit.write_text('<testsuite tests="0" failures="0" errors="1" skipped="0"></testsuite>')
            return {"returncode": 4, "stdout": "", "stderr": "ERROR: not found", "duration_seconds": 0.01}
        if junit:
            junit.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"></testsuite>')
        return {"returncode": 0, "stdout": "1 passed in 0.01s", "stderr": "", "duration_seconds": 0.01}

    monkeypatch.setattr(loop, "run_cmd", fake_run)
    monkeypatch.setattr(loop, "ask_webgpt", lambda *a, **k: {
        "status": "OK",
        "response": "response.md",
        "packet_digest": packet_digest,
        "candidate_digest": candidate,
        "verdict": {"ready_to_deploy": True},
    })

    rc = loop.main(["--repo", str(repo), "--output-root", str(output_root), "--execute"])

    out = json.loads(capsys.readouterr().out)
    json_blocks = (output_root / "packet-1.md").read_text().split("```json\n")
    proof = json.loads(json_blocks[2].split("\n```", 1)[0])
    assert rc == 1
    assert out["ready_to_deploy"] is False
    assert proof["candidate_bound_tests"]["failed_mandatory_gates"] == ["drifted-or-deleted"]
    assert proof["candidate_bound_tests"]["qualifies_candidate"] is False


def test_skipped_required_case_blocks_qualification(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    candidate = "sha256:" + "a" * 64
    monkeypatch.setattr(loop, "REQUIRED_PROOF_GATES", [
        {"name": "skipped-case", "pytest": ["skills/project-watchdog/tests/test_x.py::test_y"]},
    ])
    monkeypatch.setattr(loop, "candidate_manifest", lambda repo: {"candidate_digest": candidate, "files": []})

    def fake_run(argv, *, cwd, timeout=600, output_limit=4000):
        junit = next(Path(str(part).split("=", 1)[1]) for part in argv if str(part).startswith("--junitxml="))
        junit.write_text('<testsuite tests="1" failures="0" errors="0" skipped="1"></testsuite>')
        return {"returncode": 0, "stdout": "1 skipped in 0.01s", "stderr": "", "duration_seconds": 0.01}

    monkeypatch.setattr(loop, "run_cmd", fake_run)

    proof = loop.collect_proof_results(repo, out, candidate)

    assert proof["qualifies_candidate"] is False
    assert proof["failed_mandatory_gates"] == ["skipped-case"]
    assert proof["gates"][0]["junit"]["skipped"] == 1


def test_main_refuses_failed_required_proofs_even_with_positive_reviewer(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    packet = tmp_path / "out" / "packet-1.md"
    packet.parent.mkdir()
    packet.write_text("packet", encoding="utf-8")
    candidate = "sha256:" + "a" * 64
    packet_digest = "sha256:" + "b" * 64
    positive = {
        "status": "OK",
        "response": "response.md",
        "packet_digest": packet_digest,
        "candidate_digest": candidate,
        "verdict": {"ready_to_deploy": True},
    }
    monkeypatch.setattr(loop, "build_packet", lambda *a, **k: (packet, candidate, False))
    monkeypatch.setattr(loop, "candidate_manifest", lambda repo: {"candidate_digest": candidate, "files": []})
    monkeypatch.setattr(loop, "ask_webgpt", lambda *a, **k: positive)

    rc = loop.main(["--repo", str(repo), "--output-root", str(tmp_path / "out"), "--execute"])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["ready_to_deploy"] is False


def test_old_valid_provider_receipt_cannot_authorize_current_review(tmp_path: Path) -> None:
    root = tmp_path / "out"
    old = root / "ask-tau-old/node-artifacts/handler-webgpt"
    old.mkdir(parents=True)
    response = old / "response.md"
    receipt = old / "node-receipt.json"
    response.write_text("body", encoding="utf-8")
    receipt.write_text(json.dumps({"ok": True, "status": "PASS", "node_id": "handler-webgpt", "response_path": str(response)}), encoding="utf-8")
    ask_json = root / "current.json"
    ask_json.write_text(json.dumps({"execution": {"node_provider_receipts": [{"node_id": "handler-webgpt", "ok": True, "status": "PASS", "path": str(receipt), "response_path": str(response)}]}}), encoding="utf-8")
    future = ask_json.stat().st_mtime + 10
    __import__("os").utime(ask_json, (future, future))

    assert loop.latest_webgpt_response(ask_json, root) is None


def test_candidate_change_during_review_invalidates_approval(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    packet = tmp_path / "out" / "packet-1.md"
    packet.parent.mkdir()
    packet.write_text("packet", encoding="utf-8")
    before = "sha256:" + "a" * 64
    after = "sha256:" + "b" * 64
    packet_digest = "sha256:" + "c" * 64
    calls = {"manifest": 0}

    def fake_manifest(repo):
        calls["manifest"] += 1
        return {"candidate_digest": after, "files": []}

    monkeypatch.setattr(loop, "build_packet", lambda *a, **k: (packet, before, True))
    monkeypatch.setattr(loop, "candidate_manifest", fake_manifest)
    monkeypatch.setattr(loop, "ask_webgpt", lambda *a, **k: {
        "status": "OK", "response": "response.md", "packet_digest": packet_digest,
        "candidate_digest": before, "verdict": {"ready_to_deploy": True},
    })

    rc = loop.main(["--repo", str(repo), "--output-root", str(tmp_path / "out"), "--execute"])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["ready_to_deploy"] is False
    assert out["steps"][-1]["candidate_stable_after_review"] is False


def test_packet_roundtrip_preserves_schema_paths_and_digest(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    p = repo / "skills/project-watchdog/scripts/x.py"
    p.parent.mkdir(parents=True)
    p.write_text("print('x')\n", encoding="utf-8")
    subprocess.run(["git", "add", "skills/project-watchdog/scripts/x.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=repo, check=True)
    p.write_text("print('changed')\n", encoding="utf-8")
    monkeypatch.setattr(loop, "collect_proof_results", lambda repo, output_dir, candidate_digest: {"candidate_digest": candidate_digest, "qualifies_candidate": True})
    real_run = loop.run_cmd
    monkeypatch.setattr(loop, "run_cmd", lambda argv, **kw: {"returncode": 0, "stdout": "", "stderr": "", "duration_seconds": 0} if argv[:2] == ["crontab", "-l"] else real_run(argv, **kw))

    packet, digest, qualified = loop.build_packet(repo, prior_response=None, output=tmp_path / "packet.md")
    text = packet.read_text(encoding="utf-8")
    manifest = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])

    assert qualified is True
    assert manifest["candidate_digest"] == digest
    assert manifest["files"][0]["repo_path"] == "skills > project-watchdog > scripts > x.py"
    assert "0o100fc" not in text
    assert loop.sha256_file(packet).startswith("sha256:")


def test_main_plan_only_writes_receipt(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    packet = tmp_path / "out" / "packet-1.md"
    packet.parent.mkdir()
    packet.write_text("packet", encoding="utf-8")
    monkeypatch.setattr(loop, "build_packet", lambda *a, **k: (packet, "sha256:" + "a" * 64, False))

    rc = loop.main(["--repo", str(repo), "--output-root", str(tmp_path / "out")])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["ready_to_deploy"] is False
    assert "--execute" in out["next_command"]
    assert (tmp_path / "out" / "loop-receipt.json").is_file()
