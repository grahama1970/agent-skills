from __future__ import annotations

import json
import socket
import subprocess
import time
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
        assert "Decision Forms" in page
        assert opportunity_id in page
        assert variant_id in page
        assert application_id in page

        _post(base, token, opportunity_id, "KEEP", "keep-key")
        _post(base, token, reject_id, "REJECT", "reject-key")
        _post(base, token, variant_id, "ACCEPT_RESUME_VARIANT", "resume-key")
        _post(base, token, application_id, "AUTHORIZE_APPLICATION_PAYLOAD", "payload-key")
        _post(base, token, opportunity_id, "KEEP", "keep-key")

        projection = json.loads((run_dir / "decision-projection.json").read_text(encoding="utf-8"))
        assert projection["external_effects"] is False
        assert projection["items"][opportunity_id]["last_action"] == "KEEP"
        assert projection["items"][reject_id]["last_action"] == "REJECT"
        assert projection["items"][variant_id]["last_action"] == "ACCEPT_RESUME_VARIANT"
        assert projection["items"][application_id]["last_action"] == "AUTHORIZE_APPLICATION_PAYLOAD"
        assert len((run_dir / "decision-ledger.jsonl").read_text(encoding="utf-8").splitlines()) == 4
        assert manifest["artifact_accounting"]["hidden_total"] == 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)
