"""Actual Chromium to actual HTTP server and SQLite, with independent exported-record readback."""
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from a_detection.contracts import EvidenceExport
from a_detection.io import atomic_json
from a_detection.verify import verify_export

load_dotenv(override=False)
def wait_until(page, probe, timeout_s: float = 15.0, interval_s: float = 0.1):
    """Poll a locator-based probe from Python.

    page.wait_for_function evaluates a string predicate inside the page, which
    the app's strict CSP (script-src 'self', no unsafe-eval) correctly blocks.
    Polling locator.evaluate keeps the wait CSP-safe without loosening security.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if probe():
            return
        page.wait_for_timeout(int(interval_s * 1000))
    raise AssertionError("browser condition not reached before timeout")


@contextmanager
def real_server(tmp_path, evidence_dir):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, A_DETECTION_HOME=str(tmp_path / "server"),
               A_DETECTION_POLICY=str(root / "specs/policy.json"))
    env.pop("A_DETECTION_MODEL", None)
    env.pop("A_DETECTION_MODEL_SHA256", None)
    with (evidence_dir / f"http-server-{port}.log").open("wb") as output:
        process = subprocess.Popen([sys.executable, "-m", "a_detection", "serve", "--port", str(port)],
            cwd=root, env=env, stdout=output, stderr=output, start_new_session=True)
        base = f"http://127.0.0.1:{port}"
        try:
            ready = False
            with httpx.Client(timeout=2, trust_env=False) as client:
                for _ in range(80):
                    if process.poll() is not None:
                        raise RuntimeError("Real HTTP server exited before becoming ready.")
                    try:
                        response = client.get(base + "/api/health")
                        response.raise_for_status()
                        ready = response.json()["status"] == "ok"
                        if ready:
                            break
                    except httpx.HTTPError:
                        time.sleep(0.1)
            if not ready:
                raise RuntimeError("Real HTTP server never reached its health boundary.")
            yield base
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def test_real_browser_journey(tmp_path, evidence_dir):
    # Snap-confined Chromium cannot write Playwright's /tmp artifacts dir
    # (namespaced /tmp), producing empty download files. Prefer non-snap builds;
    # CHROMIUM_PATH remains the explicit override.
    candidates = [os.environ.get("CHROMIUM_PATH"), shutil.which("google-chrome"),
                  shutil.which("chromium")]
    executable = next((c for c in candidates if c and not c.startswith("/snap")), None)
    if not executable:
        raise RuntimeError("Chromium is required for this live proof; missing browser is not a PASS.")
    with real_server(tmp_path, evidence_dir) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable,
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 1120})
            page = context.new_page()
            failures, destinations = [], []
            page.on("pageerror", lambda error: failures.append(str(error)))
            page.on("request", lambda request: destinations.append(request.url))
            response = page.goto(base)
            assert response.status == 200
            assert page.locator("#editor").evaluate("element => element.readOnly") is True
            assert page.locator("#start").is_disabled()
            page.locator("#consent").check()
            page.locator("#start").click()
            editor = page.locator("#editor")
            wait_until(page, lambda: editor.evaluate("element => !element.readOnly"))
            # A fill is an automated browser input event, never presented as human-typing proof.
            source = "def unique_in_order(values):\n    seen = set()\n    result = []\n    for value in values:\n        if value not in seen:\n            seen.add(value)\n            result.append(value)\n    return result\n# Unicode: 🧪 雪 é 𐐀\n"
            page.locator("#editor").fill(source)
            revision = page.locator("#revision")
            wait_until(page, lambda: revision.evaluate("element => element.textContent === '1'"))
            changed = source.replace("𐐀", "🌿")
            page.locator("#editor").fill(changed)
            wait_until(page, lambda: revision.evaluate("element => element.textContent === '2'"))
            page.locator("#submit").click()
            verdict = page.locator("#verdict")
            wait_until(page, lambda: verdict.evaluate(
                "element => element.textContent === 'INSUFFICIENT EVIDENCE'"))
            page.screenshot(path=str(evidence_dir / "browser-desktop.png"), full_page=True)
            with page.expect_download() as download_info:
                page.locator("#export").click()
            export_file = evidence_dir / "browser-session.json"
            download_info.value.save_as(str(export_file))
            exported = EvidenceExport.model_validate_json(export_file.read_text())
            assert exported.source == changed
            assert exported.source_sha256 == hashlib.sha256(changed.encode()).hexdigest()
            assert exported.analysis.automatic_penalty is False
            assert exported.analysis.authorship_established is False
            result = verify_export(exported)
            assert result["event_count"] == 2
            assert all(url.startswith(base) for url in destinations)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(evidence_dir / "browser-mobile.png"), full_page=True)
            assert page.locator("html").evaluate(
                "element => element.scrollWidth <= window.innerWidth")
            page.locator("#delete").click()
            status = page.locator("#status")
            wait_until(page, lambda: status.evaluate(
                "element => element.textContent.includes('Session rows deleted')"))
            assert page.locator("#editor").input_value() == ""
            assert page.locator("#export").is_disabled()
            assert not failures
            atomic_json(evidence_dir / "browser-readback.json", {
                "schema_version": "a_detection.browser_proof.v1", "status": "PASS",
                "transport": "real_loopback_http", "browser": browser.version,
                "browser_input": "AUTOMATED_NOT_HUMAN_AUTHORSHIP",
                "chromium_sandbox": "disabled_in_test_container_not_a_production_sandbox_claim",
                "independent_readback": result, "session_deleted": True,
                "external_requests": 0, "javascript_errors": [],
                "model_backed_detection": "NOT_ESTABLISHED", "human_accessibility": "NOT_ESTABLISHED"})
        finally:
            browser.close()
