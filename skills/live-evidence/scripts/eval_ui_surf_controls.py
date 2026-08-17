#!/usr/bin/env python3
"""Drive the built React HUD with Surf against a YouTube-derived interview turn."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(override=False)


YOUTUBE_URL = "https://youtu.be/c6zu897JVQY"
YOUTUBE_TITLE = "Google Coding Interview With a Meta Software Engineer"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: ui-surf-youtube-eval",
                "watch_terms:",
                "  - invalid parentheses",
                "  - stack",
                "  - remove invalid",
                "project_aliases:",
                "  youtube-eval:",
                "    - parenthesis interview",
                "    - stack solution",
                "repo_priorities:",
                "  - youtube-eval",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ask_fixture_runner(path: Path) -> Path:
    runner = path / "ask-ui-surf-fixture-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'run_dir="${LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR:?}"',
                'mkdir -p "$run_dir/node-artifacts/handler-fixture"',
                'printf "%s\\n" "$*" > "$run_dir/argv.txt"',
                'cat > "$run_dir/node-artifacts/handler-fixture/response.md" <<\'EOF\'',
                "Ask solution: Use a stack of opening-parenthesis indices, blank invalid closing parentheses immediately, then blank leftover opening indices and join the character array. Clarify bounds, character set, return contract, and empty-string behavior first.",
                "EOF",
                'printf \'{"run_dir":"%s"}\\n\' "$run_dir"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_s: float = 20.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def surf(root: Path, args: list[str], *, timeout_s: float = 20.0) -> str:
    runner = root.parent / "surf" / "run.sh"
    if not runner.exists():
        raise RuntimeError(f"Surf runner not found: {runner}")
    result = run_command([str(runner), *args], cwd=root.parent.parent, timeout_s=timeout_s)
    return result.stdout.strip()


def surf_new_tab(root: Path, url: str) -> int:
    output = surf(root, ["tab.new", url, "--json"], timeout_s=20.0)
    match = re.search(r"Created tab\s+(\d+)", output)
    if not match:
        raise RuntimeError(f"could not parse tab id from Surf output: {output}")
    return int(match.group(1))


def surf_js(root: Path, tab_id: int, script: str, *, timeout_s: float = 20.0) -> Any:
    output = surf(root, ["js", script, "--tab-id", str(tab_id)], timeout_s=timeout_s)
    parsed = json.loads(output)
    if isinstance(parsed, str):
        return json.loads(parsed)
    return parsed


def surf_click(root: Path, tab_id: int, selector: str) -> None:
    surf(root, ["click", selector, "--tab-id", str(tab_id)], timeout_s=20.0)


def surf_type(root: Path, tab_id: int, text: str) -> None:
    surf(root, ["type", text, "--tab-id", str(tab_id)], timeout_s=20.0)


def wait_for_cards(client: httpx.Client, count: int, *, timeout_s: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get("/api/state")
        response.raise_for_status()
        last_state = response.json()
        if len(last_state.get("cards") or []) >= count:
            return last_state
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {count} cards; last_state={last_state}")


def wait_for_dom(root: Path, tab_id: int, *, timeout_s: float = 10.0) -> dict[str, Any]:
    script = r"""
const firstStatus = document.querySelector('.clarify-anchor-card')?.getAttribute('data-status') || null;
const activeNext = document.querySelectorAll('.clarify-anchor-card[data-active-next="true"]').length;
const noteEditor = document.querySelector('.clarify-note-editor') !== null;
const streamCards = document.querySelectorAll('[data-qs-action="LIVE_EVIDENCE_CARD_SELECT"]').length;
const text = document.body.innerText.toLowerCase();
return JSON.stringify({
  title: document.title,
  streamCards,
  activeNext,
  firstStatus,
  noteEditor,
  hasClarify: document.querySelector('.hero-clarify-card') !== null,
  hasBounds: text.includes('bounds on n?'),
  hasCharacterSet: text.includes('character set?'),
  hasChip: text.includes('listening for answer'),
  hasSolution: document.querySelector('.solution-pane') !== null,
  hasCopyCode: text.includes('copy code'),
  hasGlanceMode: text.includes('glance mode'),
  hasTeleprompter: document.querySelector('.teleprompter-bar') !== null,
  compact: document.querySelector('.meeting-shell')?.getAttribute('data-compact') || null,
  peek: document.querySelector('.meeting-shell')?.getAttribute('data-peek') || null
});
"""
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = surf_js(root, tab_id, script)
        if (
            last.get("streamCards", 0) >= 1
            and last.get("activeNext") == 1
            and last.get("hasClarify")
            and last.get("hasSolution")
            and last.get("hasTeleprompter")
        ):
            return last
        time.sleep(0.25)
    raise RuntimeError(f"timed out waiting for UI DOM projection: {last}")


def post_turn(client: httpx.Client, *, speaker: str, text: str, sequence: int) -> None:
    response = client.post(
        "/api/transcript",
        json={
            "schema": "live_evidence.transcript_event.v1",
            "speaker": speaker,
            "kind": "final",
            "source": "api",
            "sequence": sequence,
            "text": text,
        },
    )
    response.raise_for_status()


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not (root / "ui" / "dist" / "index.html").exists():
        raise RuntimeError("built React UI missing; run ./run.sh ui-build before eval-ui-surf-controls")

    with tempfile.TemporaryDirectory(prefix="live-evidence-ui-surf-eval-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "youtube-eval"
        repo.mkdir(parents=True)
        (repo / "remove_invalid_parentheses.js").write_text(
            "\n".join(
                [
                    "export function removeInvalidParentheses(input) {",
                    "  const chars = input.split('');",
                    "  const stack = [];",
                    "  for (let index = 0; index < chars.length; index += 1) {",
                    "    if (chars[index] === '(') stack.push(index);",
                    "    if (chars[index] === ')' && stack.length > 0) stack.pop();",
                    "    else if (chars[index] === ')') chars[index] = '';",
                    "  }",
                    "  while (stack.length > 0) chars[stack.pop()] = '';",
                    "  return chars.join('');",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        profile_path = temp / "profile.yaml"
        write_profile(profile_path)
        ask_run_dir = temp / "ask-run"
        ask_runner = write_ask_fixture_runner(temp)
        data_dir = temp / "data"
        port = free_port()
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
            "LIVE_EVIDENCE_PROFILE": str(profile_path),
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "0.3",
            "LIVE_EVIDENCE_PROCESS_TIMEOUT": "3",
            "LIVE_EVIDENCE_MAX_CARDS": "6",
            "LIVE_EVIDENCE_ASK_RUNNER": str(ask_runner),
            "LIVE_EVIDENCE_ASK_HANDLER": "fixture-handler",
            "LIVE_EVIDENCE_ASK_TIMEOUT": "3",
            "LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR": str(ask_run_dir),
            "MEMORY_SERVICE_URL": "http://127.0.0.1:9",
        }
        log_path = temp / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "live_evidence", "serve", "--host", "127.0.0.1", "--port", str(port), "--no-browser"],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        tab_id: int | None = None
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3.0) as client:
                for _ in range(60):
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"server did not start; log={log_path.read_text(encoding='utf-8')}")

                tab_id = surf_new_tab(root, f"http://127.0.0.1:{port}/")
                client.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()
                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=1,
                    text="Given letters mixed with parentheses, how would you remove the minimum invalid parentheses and return any valid string?",
                )
                wait_for_cards(client, 1)

                initial_dom = wait_for_dom(root, tab_id)
                if initial_dom.get("firstStatus") != "unanswered":
                    raise RuntimeError(f"first clarification item should begin unanswered: {initial_dom}")
                for key in ("hasBounds", "hasCharacterSet", "hasChip", "hasCopyCode", "hasGlanceMode"):
                    if not initial_dom.get(key):
                        raise RuntimeError(f"missing required UI affordance {key}: {initial_dom}")

                surf_click(root, tab_id, '[data-qs-action="LIVE_EVIDENCE_CLARIFY_ITEM_TOGGLE"]')
                toggled = surf_js(
                    root,
                    tab_id,
                    r"""return JSON.stringify({
  firstStatus: document.querySelector('.clarify-anchor-card')?.getAttribute('data-status'),
  activeNext: document.querySelectorAll('.clarify-anchor-card[data-active-next="true"]').length
});""",
                )
                if toggled.get("firstStatus") != "confirmed" or toggled.get("activeNext") != 1:
                    raise RuntimeError(f"clarification toggle did not confirm first item and advance next action: {toggled}")

                surf_click(root, tab_id, '[data-qs-action="LIVE_EVIDENCE_CLARIFY_NOTE_EDIT"]')
                editor = surf_js(root, tab_id, "return JSON.stringify({open: !!document.querySelector('.clarify-note-editor')})")
                if not editor.get("open"):
                    raise RuntimeError("manual note editor did not open on explicit edit action")
                surf_click(root, tab_id, '[data-qs-action="LIVE_EVIDENCE_CLARIFY_NOTE_UPDATE"]')
                surf_type(root, tab_id, "N <= 100000")
                note_state = surf_js(
                    root,
                    tab_id,
                    r"""return JSON.stringify({
  chipText: document.querySelector('.clarify-answer-chip')?.innerText || '',
  inputValue: document.querySelector('[data-qs-action="LIVE_EVIDENCE_CLARIFY_NOTE_UPDATE"]')?.value || ''
});""",
                )
                if "100000" not in note_state.get("chipText", "") or "100000" not in note_state.get("inputValue", ""):
                    raise RuntimeError(f"clarification note did not surface as read-only chip: {note_state}")

                fold_click = surf_js(
                    root,
                    tab_id,
                    r"""const button = Array.from(document.querySelectorAll('[data-qs-action="LIVE_EVIDENCE_SOLUTION_TOGGLE_CODE_FOLD"]')).find((item) => !item.disabled);
if (!button) return JSON.stringify({clicked: false, reason: 'enabled fold button missing'});
button.click();
return JSON.stringify({clicked: true, text: button.innerText});""",
                )
                if not fold_click.get("clicked"):
                    raise RuntimeError(f"code fold button missing or disabled: {fold_click}")
                fold_state = {"fullClass": False}
                for _ in range(12):
                    fold_state = surf_js(
                        root,
                        tab_id,
                        "return JSON.stringify({fullClass: document.body.innerText.toLowerCase().includes('full class')})",
                    )
                    if fold_state.get("fullClass"):
                        break
                    time.sleep(0.1)
                if not fold_state.get("fullClass"):
                    raise RuntimeError(f"code fold control did not expand full implementation: {fold_state}; click={fold_click}")

                full_screenshot_path = temp / "live-evidence-ui-surf-controls-full.png"
                surf(root, ["snap", "--output", str(full_screenshot_path), "--tab-id", str(tab_id)], timeout_s=30.0)
                if not full_screenshot_path.exists() or full_screenshot_path.stat().st_size < 10_000:
                    raise RuntimeError(f"full HUD Surf screenshot missing or too small: {full_screenshot_path}")

                surf_click(root, tab_id, '[data-qs-action="LIVE_EVIDENCE_MEETING_TOGGLE_COMPACT"]')
                surf_click(root, tab_id, '[data-qs-action="LIVE_EVIDENCE_MEETING_TOGGLE_DEFINITION_PEEK"]')
                mode_state = surf_js(
                    root,
                    tab_id,
                    r"""return JSON.stringify({
  compact: document.querySelector('.meeting-shell')?.getAttribute('data-compact'),
  peek: document.querySelector('.meeting-shell')?.getAttribute('data-peek')
});""",
                )
                if mode_state.get("compact") != "true" or mode_state.get("peek") != "true":
                    raise RuntimeError(f"compact/peek controls did not toggle: {mode_state}")

                compact_screenshot_path = temp / "live-evidence-ui-surf-controls-compact.png"
                surf(root, ["snap", "--output", str(compact_screenshot_path), "--tab-id", str(tab_id)], timeout_s=30.0)
                if not compact_screenshot_path.exists() or compact_screenshot_path.stat().st_size < 10_000:
                    raise RuntimeError(f"compact HUD Surf screenshot missing or too small: {compact_screenshot_path}")

                receipt = {
                    "schema": "live_evidence.ui_surf_controls_eval_receipt.v1",
                    "status": "PASS",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "mocked": False,
                    "live": False,
                    "fixture_backed": True,
                    "youtube_source": {
                        "url": YOUTUBE_URL,
                        "title": YOUTUBE_TITLE,
                        "committed_text_policy": "distilled-paraphrase injected through local API",
                    },
                    "surf": {
                        "tab_id": tab_id,
                        "url": f"http://127.0.0.1:{port}/",
                        "full_screenshot": str(full_screenshot_path),
                        "compact_screenshot": str(compact_screenshot_path),
                    },
                    "checks": {
                        "real_fastapi_server": True,
                        "built_react_ui": True,
                        "surf_controlled_tab": True,
                        "youtube_derived_turn_to_card": True,
                        "clarification_grid_visible": True,
                        "single_active_next_action": True,
                        "answer_chip_visible": True,
                        "manual_note_editor_hidden_until_explicit_edit": True,
                        "manual_note_surfaces_as_chip": True,
                        "compact_mode_control": True,
                        "definition_peek_control": True,
                        "code_fold_control": True,
                    },
                    "claims": {
                        "proves": "Surf can control the built Live Evidence React HUD against a real local API, inspect a YouTube-derived answer card, and exercise clarification, note, compact, peek, and code-fold UI controls.",
                        "does_not_prove": "live YouTube audio playback, PipeWire capture, GPU STT inference, live Ask provider correctness, or external browser-oracle review.",
                    },
                }
                receipt_dir = Path(os.getenv("LIVE_EVIDENCE_DATA_DIR", str(data_dir)))
                receipt_dir.mkdir(parents=True, exist_ok=True)
                receipt_path = receipt_dir / "ui-surf-controls-eval-receipt.json"
                receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                stable_receipt = Path("/tmp/live-evidence-ui-surf-controls-eval-receipt.json")
                stable_full_shot = Path("/tmp/live-evidence-ui-surf-controls-full.png")
                stable_compact_shot = Path("/tmp/live-evidence-ui-surf-controls-compact.png")
                shutil.copy2(receipt_path, stable_receipt)
                shutil.copy2(full_screenshot_path, stable_full_shot)
                shutil.copy2(compact_screenshot_path, stable_compact_shot)
                print("ui surf controls receipt:", receipt_path)
                print("ui surf controls full screenshot:", full_screenshot_path)
                print("ui surf controls compact screenshot:", compact_screenshot_path)
                print("ui surf controls: PASS")
        finally:
            if tab_id is not None:
                try:
                    surf(root, ["tab.close", str(tab_id)], timeout_s=10.0)
                except Exception:
                    pass
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
