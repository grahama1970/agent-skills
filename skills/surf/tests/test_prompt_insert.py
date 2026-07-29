"""Chunked composer insertion shared by the vendored browser clients.

agent-skills#1034 (ChatGPT) and #1036 (gemini/grok/perplexity/aistudio): a single
Input.insertText carrying the whole prompt stalls past the native host's
extension timeout on a heavy conversation, so nothing is submitted. These tests
drive the real prompt-insert.cjs module through node with a recording stub.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
NATIVE_DIR = SKILL_DIR / "vendor" / "surf-cli" / "native"
MODULE = NATIVE_DIR / "prompt-insert.cjs"

DRIVER = """
const { insertPromptText } = require(process.argv[2]);
const prompt = process.argv[3];
const calls = [];
const inputCdp = async (method, params, timeoutMs) => {
  calls.push({ method, text: params.text, timeoutMs });
};
insertPromptText(inputCdp, prompt).then((chunks) => {
  process.stdout.write(JSON.stringify({ chunks, calls }));
});
"""


def run_insert(tmp_path: Path, prompt: str, env: dict[str, str] | None = None) -> dict:
    driver = tmp_path / "driver.cjs"
    driver.write_text(DRIVER, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(driver), str(MODULE), prompt],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return json.loads(completed.stdout)


def test_small_prompt_is_inserted_in_one_call(tmp_path: Path) -> None:
    result = run_insert(tmp_path, "hello composer")

    assert result["chunks"] == 1
    assert [call["text"] for call in result["calls"]] == ["hello composer"]
    assert result["calls"][0]["method"] == "Input.insertText"
    assert result["calls"][0]["timeoutMs"] == 90000


def test_large_prompt_is_chunked_and_reassembles_exactly(tmp_path: Path) -> None:
    prompt = "".join(chr(ord("a") + (index % 26)) for index in range(31955))

    result = run_insert(tmp_path, prompt)

    texts = [call["text"] for call in result["calls"]]
    assert result["chunks"] == len(texts) == 6
    assert "".join(texts) == prompt
    assert max(len(text) for text in texts) <= 6000
    assert all(call["timeoutMs"] == 90000 for call in result["calls"])


def test_chunk_size_and_timeout_are_configurable(tmp_path: Path) -> None:
    result = run_insert(
        tmp_path,
        "x" * 100,
        env={"SURF_PROMPT_INSERT_CHUNK_CHARS": "40", "SURF_PROMPT_INSERT_TIMEOUT_MS": "12000"},
    )

    assert [len(call["text"]) for call in result["calls"]] == [40, 40, 20]
    assert all(call["timeoutMs"] == 12000 for call in result["calls"])


def test_webgpt_env_names_stay_supported(tmp_path: Path) -> None:
    result = run_insert(
        tmp_path,
        "y" * 90,
        env={"SURF_WEBGPT_INSERT_CHUNK_CHARS": "30", "SURF_WEBGPT_INSERT_TIMEOUT_MS": "7000"},
    )

    assert [len(call["text"]) for call in result["calls"]] == [30, 30, 30]
    assert all(call["timeoutMs"] == 7000 for call in result["calls"])


def test_every_browser_client_uses_the_shared_helper() -> None:
    clients = [
        "chatgpt-client.cjs",
        "gemini-tab-client.cjs",
        "kimi-tab-client.cjs",
        "grok-client.cjs",
        "perplexity-client.cjs",
        "aistudio-client.cjs",
    ]

    for name in clients:
        source = (NATIVE_DIR / name).read_text(encoding="utf-8")
        assert 'require("./prompt-insert.cjs")' in source, name
        assert 'inputCdp("Input.insertText", { text: prompt })' not in source, name
