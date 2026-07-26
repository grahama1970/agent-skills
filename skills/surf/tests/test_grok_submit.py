from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GROK_SUBMIT = REPO_ROOT / "skills/surf/scripts/grok-submit.sh"
GROK_FALLBACK = REPO_ROOT / "skills/surf/scripts/grok_generic_fallback.py"


def load_grok_fallback():
    spec = importlib.util.spec_from_file_location("grok_generic_fallback", GROK_FALLBACK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_fake_surf(path: Path, *, tab_url: str, response: str = "") -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    printf '%s\\n' '[{{"id":123,"title":"Grok","url":"{tab_url}"}}]'
    ;;
  focus.state)
    printf '%s\\n' '{{"activeTabId":999,"activeTabUrl":"https://example.test/"}}'
    ;;
  grok)
    printf '%b\\n' {json.dumps(response)}
    ;;
  *)
    echo "unexpected fake surf command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def run_grok_submit(tmp_path: Path, fake_surf: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    request = tmp_path / "request.md"
    request.write_text("Say pong.", encoding="utf-8")
    output = tmp_path / "response.md"
    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_surf)
    env["SURF_GROK_NATIVE_EXACT_TAB_FIRST"] = "1"
    return subprocess.run(
        [
            "bash",
            str(GROK_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(output),
            "--sentinel",
            "<<<GROK_DONE:TEST>>>",
            *extra,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def test_grok_submit_dispatches_from_run_sh_help() -> None:
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "skills/surf/run.sh"), "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0
    assert "surf grok.submit --input request.md --output response.md" in proc.stdout


def test_grok_submit_defaults_to_atomic_native_exact_tab_transport() -> None:
    source = GROK_SUBMIT.read_text(encoding="utf-8")

    assert '${SURF_GROK_NATIVE_EXACT_TAB_FIRST:-1}' in source


def test_grok_submit_routes_attachments_through_exact_tab_native_transport() -> None:
    source = GROK_SUBMIT.read_text(encoding="utf-8")

    assert 'args+=(--files "$attach_files_csv")' in source


def test_grok_native_host_uses_backward_compatible_exact_tab_cdp_aliases() -> None:
    host = (
        REPO_ROOT / "skills/surf/vendor/surf-cli/native/host.cjs"
    ).read_text(encoding="utf-8")

    assert "requestGrokCdp" in host
    assert '{ type: "KIMI_EVALUATE", tabId, expression }' in host
    assert '{ type: "KIMI_CDP_COMMAND", tabId, method, params }' in host


def test_grok_client_sets_and_verifies_exact_tab_file_input(tmp_path: Path) -> None:
    attachment = tmp_path / "visual evidence.png"
    attachment.write_bytes(b"real attachment bytes")
    script = r"""
const client = require(process.argv[1]);
const file = process.argv[2];
const fs = require("fs");
const path = require("path");
const calls = [];
const inputCdp = async (method, params) => {
  calls.push({method, params});
  if (method === "DOM.getDocument") return {root: {nodeId: 11}};
  if (method === "DOM.querySelector") return {nodeId: 22};
  if (method === "DOM.setFileInputFiles") return {};
  throw new Error(`unexpected method ${method}`);
};
const cdp = async () => ({
  result: {value: [{name: path.basename(file), size: fs.statSync(file).size}]}
});
client.attachFiles(cdp, inputCdp, [file]).then(attachments => {
  process.stdout.write(JSON.stringify({attachments, calls}));
}).catch(error => {
  process.stderr.write(error.stack);
  process.exit(1);
});
"""
    proc = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(REPO_ROOT / "skills/surf/vendor/surf-cli/native/grok-client.cjs"),
            str(attachment),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["attachments"] == [{"name": attachment.name, "size": attachment.stat().st_size}]
    assert [call["method"] for call in result["calls"]] == [
        "DOM.getDocument",
        "DOM.querySelector",
        "DOM.setFileInputFiles",
    ]
    assert result["calls"][-1]["params"] == {
        "files": [str(attachment.resolve())],
        "nodeId": 22,
    }


def test_grok_client_does_not_accept_prompt_sentinel_as_response() -> None:
    script = r"""
const client = require(process.argv[1]);
const sentinel = "<<<GROK_DONE:TEST>>>";
const prompt = `Inspect the image.\n${sentinel}`;
const cdp = async () => ({
  result: {value: {
    bodyText: prompt,
    responseText: prompt,
    bodyLength: prompt.length,
    hasStopBtn: false,
    thinkingDone: false,
    thinkingSecs: null,
    isThinking: false,
    chipTexts: [],
    url: "https://grok.com/"
  }}
});
client.waitForResponse(cdp, 20, prompt).then(result => {
  process.stdout.write(JSON.stringify(result));
  process.exit(2);
}).catch(error => {
  process.stdout.write(error.message);
});
"""
    proc = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(REPO_ROOT / "skills/surf/vendor/surf-cli/native/grok-client.cjs"),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Response timeout" in proc.stdout


def test_grok_submit_observation_ignores_page_wide_generating_text() -> None:
    source = (
        REPO_ROOT / "skills/surf/vendor/surf-cli/native/grok-client.cjs"
    ).read_text(encoding="utf-8")

    assert "accepted: editorText.length === 0" in source
    assert "hasStopButton || generatingText || urlChanged" not in source
    assert "testId === 'chat-submit'" in source
    assert "clickTargetDeadline = Date.now() + 10000" in source
    assert 'type: "mousePressed"' in source
    assert 'type: "rawKeyDown"' in source


def test_grok_fallback_returns_iife_results_from_surf_js(tmp_path: Path) -> None:
    fake_surf = tmp_path / "surf"
    fake_surf.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" != "js" || "${2:-}" != *"return ("* ]]; then
  printf '%s\n' 'undefined'
  exit 0
fi
if [[ "$2" == *"const sentinel"* ]]; then
  printf '%s\n' '"response <<<GROK_DONE:TEST>>>"'
else
  printf '%s\n' '{"ok":true,"tag":"DIV"}'
fi
""",
        encoding="utf-8",
    )
    fake_surf.chmod(0o755)
    fallback = load_grok_fallback()

    assert fallback._focus_composer(str(fake_surf), "123")["ok"] is True
    assert fallback._latest_sentinel_text(
        str(fake_surf),
        "123",
        "<<<GROK_DONE:TEST>>>",
    ) == "response <<<GROK_DONE:TEST>>>"
    assert GROK_FALLBACK.read_text(encoding="utf-8").count("return (() =>") == 5


def test_grok_fallback_flattens_multiline_prompt_before_submit() -> None:
    fallback = load_grok_fallback()

    assert fallback._single_line_prompt(
        "Position:\nPING_RESULT: 4\n\n<<<GROK_DONE:TEST>>>\n"
    ) == "Position: PING_RESULT: 4 <<<GROK_DONE:TEST>>>"


def test_grok_fallback_confirms_composer_cleared_after_submit(tmp_path: Path) -> None:
    state = tmp_path / "composer.txt"
    state.write_text("", encoding="utf-8")
    fake_surf = tmp_path / "surf"
    fake_surf.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  type)
    printf '%s' "${{2:-}}" > {state}
    ;;
  key)
    : > {state}
    ;;
  js)
    python3 -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' {state}
    ;;
  *)
    echo "unexpected fake surf command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_surf.chmod(0o755)
    fallback = load_grok_fallback()

    evidence = fallback._submit_prompt(
        str(fake_surf),
        "123",
        "Complete prompt <<<GROK_DONE:TEST>>>",
    )

    assert evidence["submit_confirmed"] is True
    assert evidence["composer_cleared_after_submit"] is True
    assert state.read_text(encoding="utf-8") == ""


def test_grok_fallback_accepts_prosemirror_punctuation_normalization() -> None:
    fallback = load_grok_fallback()
    sentinel = "<<<GROK_DONE:TEST>>>"

    assert fallback._prompt_delivery_matches(
        f"Answer the user's request. {sentinel}",
        f"Answer the users request {sentinel}",
    )
    assert not fallback._prompt_delivery_matches(
        f"Answer the user's request. {sentinel}",
        "Answer the users request",
    )


def test_grok_fallback_detects_provider_capacity_without_waiting(tmp_path: Path) -> None:
    fake_surf = tmp_path / "surf"
    fake_surf.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '"High Demand: Grok is under heavy usage right now."'
""",
        encoding="utf-8",
    )
    fake_surf.chmod(0o755)
    fallback = load_grok_fallback()

    try:
        fallback._wait_for_sentinel(
            str(fake_surf),
            "123",
            "<<<GROK_DONE:TEST>>>",
            timeout_s=30,
            stable_polls=1,
        )
    except fallback.FallbackError as exc:
        assert "capacity busy" in str(exc)
        assert exc.evidence["provider_busy"] is True
    else:
        raise AssertionError("provider capacity should fail fast")


def test_grok_submit_cleans_terminal_sentinel_and_writes_meta(tmp_path: Path) -> None:
    fake_surf = tmp_path / "surf"
    write_fake_surf(fake_surf, tab_url="https://grok.com/", response="pong\n<<<GROK_DONE:TEST>>>")

    proc = run_grok_submit(
        tmp_path,
        fake_surf,
        "--tab-id",
        "123",
        "--url",
        "https://grok.com",
        "--no-activate",
    )

    assert proc.returncode == 0, proc.stderr
    response = tmp_path / "response.md"
    meta = json.loads((tmp_path / "response.md.meta.json").read_text(encoding="utf-8"))
    assert response.read_text(encoding="utf-8") == "pong\n"
    assert meta["status"] == "completed"
    assert meta["proof_status"] == "response_proven"
    assert meta["raw_contains_sentinel"] is True
    assert meta["clean_contains_sentinel"] is False
    assert meta["requested_tab_id"] == "123"
    assert meta["tab_identity_preflight"]["ok"] is True
    assert meta["no_activate"] is True


def test_grok_submit_rejects_wrong_tab_before_provider_submit(tmp_path: Path) -> None:
    fake_surf = tmp_path / "surf"
    write_fake_surf(fake_surf, tab_url="https://chatgpt.com/", response="should not run")

    proc = run_grok_submit(tmp_path, fake_surf, "--tab-id", "123", "--url", "https://grok.com")

    assert proc.returncode == 4
    meta = json.loads((tmp_path / "response.md.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "browser_tab_identity_mismatch"
    assert meta["proof_status"] == "wrong_tab"
    assert meta["tab_identity_preflight"]["provider_ok"] is False


def test_grok_submit_accepts_conversation_route_for_provider_root_url(tmp_path: Path) -> None:
    fake_surf = tmp_path / "surf"
    write_fake_surf(
        fake_surf,
        tab_url="https://grok.com/c/conversation-id",
        response="pong\n<<<GROK_DONE:TEST>>>",
    )

    proc = run_grok_submit(
        tmp_path,
        fake_surf,
        "--tab-id",
        "123",
        "--url",
        "https://grok.com/",
    )

    assert proc.returncode == 0, proc.stderr
    meta = json.loads((tmp_path / "response.md.meta.json").read_text(encoding="utf-8"))
    assert meta["tab_identity_preflight"]["provider_ok"] is True
    assert meta["tab_identity_preflight"]["url_ok"] is True


def test_grok_submit_classifies_unknown_message_type_as_tool_unsupported(tmp_path: Path) -> None:
    fake_surf = tmp_path / "surf"
    fake_surf.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    printf '%s\n' '[{"id":123,"title":"Grok","url":"https://grok.com/"}]'
    ;;
  focus.state)
    printf '%s\n' '{"activeTabId":999,"activeTabUrl":"https://example.test/"}'
    ;;
  grok)
    echo 'Error: Unknown message type: GROK_EVALUATE' >&2
    exit 1
    ;;
  *)
    echo "unexpected fake surf command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_surf.chmod(0o755)

    proc = run_grok_submit(tmp_path, fake_surf, "--tab-id", "123", "--url", "https://grok.com")

    assert proc.returncode == 1
    meta = json.loads((tmp_path / "response.md.meta.json").read_text(encoding="utf-8"))
    assert meta["failure"] == "grok_tool_unsupported"
    assert meta["blocker"] == "BLOCKED_GROK_TOOL_UNSUPPORTED"
    assert meta["proof_status"] == "provider_blocked"
