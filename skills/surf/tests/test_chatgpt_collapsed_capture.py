"""Backend-API upgrade for collapsed ChatGPT DOM captures.

2026-08-18: ChatGPT collapses long code blocks ("Show more") and the collapsed
portion is absent from the DOM, so sentinel-proven captures truncated three
complete answers (18.8k/17.2k/2.5k chars) to 1.1-3.0k -- cut mid-JSON with the
sentinel intact, because the sentinel renders after the collapsed block. These
tests drive the real upgradeCollapsedDomCapture through node with a scripted
cdp stub: an upgrade is accepted only when the API text carries the SAME
sentinel and is strictly longer; every failure mode falls open to the DOM
capture.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
MODULE = SKILL_DIR / "vendor" / "surf-cli" / "native" / "chatgpt-client.cjs"

DRIVER = """
const { upgradeCollapsedDomCapture } = require(process.argv[2]);
const scenario = JSON.parse(process.argv[3]);
const cdp = async (expression) => {
  const e = String(expression);
  if (e.includes("__pending")) return { result: { value: true } };
  if (e.trim() === "window.__surfBackendApiText") {
    return { result: { value: scenario.apiValue === null ? "" : scenario.apiValue } };
  }
  return { result: { value: true } };
};
upgradeCollapsedDomCapture(cdp, scenario.result).then((out) => {
  process.stdout.write(JSON.stringify(out));
});
"""


def run(tmp_path: Path, scenario: dict) -> dict:
    driver = tmp_path / "driver.cjs"
    driver.write_text(DRIVER, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(driver), str(MODULE), json.dumps(scenario)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


SENT = "<<<WEBGPT_DONE:test>>>"


def test_collapsed_capture_is_upgraded_to_full_api_text(tmp_path: Path) -> None:
    dom = '{"cases": [' + SENT
    api = '{"cases": ["full", "content", "here"]}' + "\n" + SENT
    out = run(tmp_path, {"apiValue": api,
                         "result": {"text": dom, "sentinel": SENT, "hasSentinel": True}})
    assert out["text"] == api
    assert out["source"] == "backend-api"
    assert out["domTruncationDetected"] is True
    assert out["domChars"] == len(dom) and out["apiChars"] == len(api)


def test_shorter_api_text_never_replaces_the_dom_capture(tmp_path: Path) -> None:
    dom = "a complete answer with detail " * 4 + SENT
    out = run(tmp_path, {"apiValue": "tiny " + SENT,
                         "result": {"text": dom, "sentinel": SENT, "hasSentinel": True}})
    assert out["text"] == dom
    assert "domTruncationDetected" not in out


def test_api_text_with_a_different_sentinel_is_rejected(tmp_path: Path) -> None:
    dom = "partial " + SENT
    out = run(tmp_path, {"apiValue": "x" * 500 + "<<<WEBGPT_DONE:other>>>",
                         "result": {"text": dom, "sentinel": SENT, "hasSentinel": True}})
    assert out["text"] == dom


def test_api_unavailable_falls_open_to_dom(tmp_path: Path) -> None:
    dom = "partial " + SENT
    out = run(tmp_path, {"apiValue": None,
                         "result": {"text": dom, "sentinel": SENT, "hasSentinel": True}})
    assert out["text"] == dom


def test_unproven_capture_is_never_upgraded(tmp_path: Path) -> None:
    out = run(tmp_path, {"apiValue": "x" * 500 + SENT,
                         "result": {"text": "draft", "sentinel": SENT, "hasSentinel": False}})
    assert out["text"] == "draft"
