from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _post(base: str, token: str, item: str, action: str, key: str) -> None:
    data = urllib.parse.urlencode(
        {"item": item, "action": action, "idempotency_key": key, "reason": "pytest"}
    ).encode("utf-8")
    request = urllib.request.Request(f"{base}/decision?token={token}", data=data, method="POST")
    urllib.request.build_opener(urllib.request.HTTPRedirectHandler()).open(request, timeout=5).read()


def _post_expect_error(base: str, token: str, item: str, action: str, key: str) -> int:
    data = urllib.parse.urlencode(
        {"item": item, "action": action, "idempotency_key": key, "reason": "pytest"}
    ).encode("utf-8")
    request = urllib.request.Request(f"{base}/decision?token={token}", data=data, method="POST")
    try:
        urllib.request.urlopen(request, timeout=5).read()
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    raise AssertionError("expected HTTP error")


def test_remote_bind_requires_explicit_allow_remote(tmp_path: Path) -> None:
    run_sh = Path("skills/monitor-opportunities/run.sh").resolve()
    port = _free_port()
    result = subprocess.run(
        [str(run_sh), "serve", "--report", str(tmp_path), "--host", "0.0.0.0", "--port", str(port)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "non-loopback serve requires --allow-remote" in result.stderr


def test_loopback_service_decisions_replay_and_visibility(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_sh = Path("skills/monitor-opportunities/run.sh").resolve()
    fixture_dir = Path("skills/monitor-opportunities/tests/fixtures/discovery").resolve()
    subprocess.run(
        [str(run_sh), "run", "--fixture-dir", str(fixture_dir), "--out", str(run_dir)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    manifest = json.loads((run_dir / "report-manifest.json").read_text(encoding="utf-8"))
    opportunity_id = manifest["opportunities"][0]["opportunity_id"]
    reject_id = manifest["opportunities"][1]["opportunity_id"]
    defer_id = manifest["outreach_packets"][0]["packet_id"]
    variant_id = manifest["resume_variants"][0]["variant_id"]
    application_id = manifest["applications"][0]["application_id"]
    port = _free_port()
    proc = subprocess.Popen(
        [str(run_sh), "serve", "--report", str(run_dir), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        assert "token=" in line
        token = line.rsplit("token=", 1)[1]
        base = f"http://127.0.0.1:{port}"
        for _ in range(20):
            try:
                urllib.request.urlopen(f"{base}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        page = urllib.request.urlopen(f"{base}/?token={token}", timeout=5).read().decode("utf-8")
        assert "Morning opportunities" in page
        assert "Shortlisted opportunities" in page
        assert "All decision forms" in page
        assert page.index("Shortlisted opportunities") < page.index("All decision forms")
        assert opportunity_id in page
        assert manifest["opportunities"][0]["title"] in page
        assert manifest["opportunities"][0]["organization"] in page
        assert "Why this is here" in page
        assert "Observed screening evidence" in page
        assert variant_id in page
        assert application_id in page
        assert "External effects are disabled" in page
        assert "AUTHORIZE_APPLICATION_PAYLOAD" in page
        assert "MARK_HUMAN_SENT_GMAIL" not in page
        assert "MARK_HUMAN_SENT_LINKEDIN" not in page

        _post(base, token, opportunity_id, "KEEP", "keep-key")
        _post(base, token, reject_id, "REJECT", "reject-key")
        _post(base, token, defer_id, "DEFER", "defer-key")
        _post(base, token, variant_id, "ACCEPT_RESUME_VARIANT", "resume-key")
        _post(base, token, variant_id, "PROPOSE_CLAIM_AMENDMENT", "amend-key")
        _post(base, token, application_id, "AUTHORIZE_APPLICATION_PAYLOAD", "payload-key")
        _post(base, token, opportunity_id, "KEEP", "keep-key")

        assert _post_expect_error(base, token, application_id, "MARK_HUMAN_SENT_GMAIL", "blocked-key") == 400
        projection = json.loads((run_dir / "decision-projection.json").read_text(encoding="utf-8"))
        projection_before_replay = projection["projection_digest"]
        assert projection["external_effects"] is False
        assert projection["items"][opportunity_id]["last_action"] == "KEEP"
        assert projection["items"][opportunity_id]["resulting_state"] == "KEPT"
        assert projection["items"][reject_id]["last_action"] == "REJECT"
        assert projection["items"][defer_id]["last_action"] == "DEFER"
        assert projection["items"][variant_id]["last_action"] == "PROPOSE_CLAIM_AMENDMENT"
        assert projection["items"][variant_id]["resulting_state"] == "CLAIM_AMENDMENT_PENDING"
        assert projection["items"][application_id]["last_action"] == "AUTHORIZE_APPLICATION_PAYLOAD"
        assert projection["items"][application_id]["resulting_state"] == "APPLICATION_PAYLOAD_AUTHORIZED_LOCAL_ONLY"
        ledger = [
            json.loads(line)
            for line in (run_dir / "decision-ledger.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert len(ledger) == 6
        assert all(row["external_effects"] is False for row in ledger)
        assert all(row["prior_report_digest"] for row in ledger)
        authorize_event = next(row for row in ledger if row["action"] == "AUTHORIZE_APPLICATION_PAYLOAD")
        assert authorize_event["application_payload"]["application_id"] == application_id
        assert authorize_event["application_payload"]["does_not_execute_submit"] is True
        assert authorize_event["application_payload"]["payload_digest"] == authorize_event["artifact_hashes"]["application_payload_digest"]
        assert authorize_event["application_payload"]["form_schema_digest"] == manifest["applications"][0]["form_schema_digest"]
        amendments = [
            json.loads(line)
            for line in (run_dir / "claim-amendments.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert len(amendments) == 1
        assert amendments[0]["status"] == "AMENDMENT_PROPOSED"
        assert amendments[0]["claim_keys"] == manifest["resume_variants"][0]["claim_keys"]
        assert amendments[0]["human_review_required"] is True
        assert amendments[0]["canonical_mutation"] is False
        reloaded = urllib.request.urlopen(f"{base}/?token={token}", timeout=5).read().decode("utf-8")
        assert f"{opportunity_id}: KEEP" in reloaded
        assert f"{reject_id}: REJECT" in reloaded
        assert f"{application_id}: AUTHORIZE_APPLICATION_PAYLOAD" in reloaded
        replay = subprocess.run(
            [str(run_sh), "replay", "--run", str(run_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        replay_payload = json.loads(replay.stdout)
        assert replay_payload["projection_digest"] == projection_before_replay
        assert manifest["artifact_accounting"]["hidden_total"] == 0
        assert manifest["artifact_accounting"]["action_worthy_total"] == manifest["artifact_accounting"]["visible_total"]
    finally:
        proc.terminate()
        proc.wait(timeout=10)
