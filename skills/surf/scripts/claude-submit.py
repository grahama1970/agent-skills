#!/usr/bin/env python3
"""Submit a prompt to an existing Claude browser tab with sentinel proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RUN_SH = Path(os.environ.get("SURF_RUN_SH", str(SKILL_DIR / "run.sh")))
TAB_STATE_FILE = Path(os.environ.get("SURF_CLAUDE_TAB_STATE", "/tmp/surf-claude-controlled-tab-id"))


class SubmitFailure(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="surf claude.submit",
        description="Submit a prompt to a controlled Claude tab and require a terminal sentinel.",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--raw-output", default="")
    parser.add_argument("--meta-output", default="")
    parser.add_argument("--submitted-output", default="")
    parser.add_argument("--sentinel", default="auto")
    parser.add_argument("--stable-polls", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--tab-id", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument(
        "--attach-file",
        default="",
        help="Attach a file to the Claude message before submitting the prompt.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_path = Path(args.raw_output or f"{args.output}.raw.md")
    meta_path = Path(args.meta_output or f"{args.output}.meta.json")
    submitted_path = Path(args.submitted_output or f"{args.output}.submitted.md")
    for path in (output_path, raw_path, meta_path, submitted_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")
    attach_file = Path(args.attach_file).expanduser() if args.attach_file else None
    if attach_file and not attach_file.is_file():
        raise SystemExit(f"--attach-file: file not found: {attach_file}")
    if "SURF_RUN_SH" not in os.environ and not Path("/tmp/surf.sock").exists():
        raise SystemExit("surf claude.submit requires the surf browser extension socket at /tmp/surf.sock.")

    sentinel = args.sentinel
    if not sentinel or sentinel == "auto":
        sentinel = f"<<<CLAUDE_DONE:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}:{secrets.token_hex(4)}>>>"

    prompt = input_path.read_text(encoding="utf-8")
    submitted_prompt = "\n".join(
        [
            prompt.rstrip(),
            "",
            "---",
            "",
            "For transport verification, answer the request normally, then append a final",
            "line containing only this exact marker:",
            "",
            sentinel,
            "",
            "The marker must be the last line of your answer.",
            "",
        ]
    )
    submitted_path.write_text(submitted_prompt, encoding="utf-8")

    started_at = _now()
    focus_before = _focus_state()
    requested_tab_id = _resolve_tab(args.tab_id, args.url)
    content_script_recovery: list[dict[str, Any]] = []
    if args.no_activate and not requested_tab_id:
        _write_failed_meta(
            meta_path,
            args,
            input_path,
            output_path,
            raw_path,
            submitted_path,
            sentinel,
            started_at,
            _now(),
            "no_activate_requires_explicit_tab",
            requested_tab_id="",
        )
        raise SystemExit(2)
    if not requested_tab_id:
        remembered = _remembered_tab()
        requested_tab_id = remembered or ""

    try:
        if not requested_tab_id:
            raise SubmitFailure("No Claude tab id supplied, resolved, or remembered.")
        _ensure_claude_content_script_ready(requested_tab_id, content_script_recovery)
        _assert_claude_tab(requested_tab_id, args.url)
        attachment = _attach_file(requested_tab_id, attach_file) if attach_file else None
        _ensure_claude_content_script_ready(requested_tab_id, content_script_recovery)
        _submit_prompt(requested_tab_id, submitted_prompt)
        raw_text = _wait_for_sentinel(
            requested_tab_id,
            sentinel,
            timeout_seconds=args.timeout,
            stable_polls=max(1, args.stable_polls),
        )
        raw_path.write_text(raw_text, encoding="utf-8")
        clean_text = _clean_response(raw_text, sentinel)
        output_path.write_text(clean_text, encoding="utf-8")
        focus_after = _focus_state()
        meta = _success_meta(
            args=args,
            input_path=input_path,
            output_path=output_path,
            raw_path=raw_path,
            submitted_path=submitted_path,
            sentinel=sentinel,
            started_at=started_at,
            finished_at=_now(),
            requested_tab_id=requested_tab_id,
            focus_before=focus_before,
            focus_after=focus_after,
            clean_text=clean_text,
            raw_text=raw_text,
            attach_file=attach_file,
            attachment=attachment,
            content_script_recovery=content_script_recovery,
        )
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        TAB_STATE_FILE.write_text(str(requested_tab_id).strip() + "\n", encoding="utf-8")
        print(json.dumps(meta, indent=2, sort_keys=True))
        return 0 if meta["status"] == "completed" else 5
    except Exception as exc:
        finished = _now()
        raw_text = ""
        try:
            raw_text = _surf(["text", "--tab-id", requested_tab_id], timeout=30).stdout
            raw_path.write_text(raw_text, encoding="utf-8")
        except Exception:
            raw_path.write_text("", encoding="utf-8")
        _write_failed_meta(
            meta_path,
            args,
            input_path,
            output_path,
            raw_path,
            submitted_path,
            sentinel,
            started_at,
            finished,
            str(exc),
            requested_tab_id=requested_tab_id,
            raw_text=raw_text,
            content_script_recovery=content_script_recovery,
        )
        print(str(exc), file=sys.stderr)
        return 4


def _resolve_tab(tab_id: str, url: str) -> str:
    cleaned = re.sub(r"[^0-9]", "", tab_id or "")[:20]
    if cleaned:
        return cleaned
    if not url:
        return ""
    tabs = _tab_list()
    for tab in tabs:
        if _normalize_url(str(tab.get("url") or "")) == _normalize_url(url):
            return str(tab.get("id") or "")
    raise SubmitFailure(f"No open Chrome tab matched --url: {url}")


def _remembered_tab() -> str:
    if not TAB_STATE_FILE.is_file():
        return ""
    return re.sub(r"[^0-9]", "", TAB_STATE_FILE.read_text(encoding="utf-8"))[:20]


def _assert_claude_tab(tab_id: str, expect_url: str) -> None:
    try:
        page_text = _surf(["text", "--tab-id", tab_id], timeout=30).stdout
        if "claude.ai" not in page_text:
            raise SubmitFailure(f"tab {tab_id} is not a Claude tab")
        if expect_url and _normalize_url(expect_url) not in page_text:
            raise SubmitFailure(f"tab {tab_id} URL mismatch: expected {expect_url}")
        return
    except SubmitFailure:
        raise
    except Exception:
        pass
    for tab in _tab_list():
        if str(tab.get("id")) == str(tab_id):
            url = str(tab.get("url") or "")
            if "claude.ai" not in url:
                raise SubmitFailure(f"tab {tab_id} is not a Claude tab: {url}")
            if expect_url and _normalize_url(url) != _normalize_url(expect_url):
                raise SubmitFailure(f"tab {tab_id} URL mismatch: expected {expect_url}, saw {url}")
            return
    raise SubmitFailure(f"Claude tab {tab_id} not found in surf tab.list")


def _submit_prompt(tab_id: str, prompt: str) -> None:
    read = _surf(["read", "--tab-id", tab_id], timeout=60).stdout
    textbox_ref = _find_ref(read, r'textbox "Write your prompt to Claude" \[(e\d+)\]')
    if not textbox_ref:
        raise SubmitFailure("Claude prompt textbox not found")
    _surf(["click", textbox_ref, "--tab-id", tab_id], timeout=60)
    _surf(["type", prompt, "--ref", textbox_ref, "--tab-id", tab_id], timeout=60)
    read_after = _surf(["read", "--tab-id", tab_id], timeout=60).stdout
    send_ref = _find_ref(read_after, r'button "Send message" \[(e\d+)\]')
    if send_ref:
        _surf(["click", send_ref, "--tab-id", tab_id], timeout=60)
    else:
        _surf(["key", "Enter", "--tab-id", tab_id], timeout=60)


def _attach_file(tab_id: str, attach_file: Path) -> dict[str, Any]:
    expose_script = (
        "const input=document.querySelector('input[type=file][data-testid=file-upload],"
        "input[type=file][aria-label=\"Upload files\"]');"
        "if(!input) throw new Error('Claude file input not found');"
        "input.id='surf-claude-submit-upload-input';"
        "input.removeAttribute('aria-hidden');"
        "input.tabIndex=0;"
        "Object.assign(input.style,{position:'fixed',left:'20px',bottom:'20px',width:'240px',"
        "height:'44px',opacity:'1',zIndex:'2147483647',background:'white',color:'black'});"
        "return JSON.stringify({ok:true,id:input.id,type:input.type,multiple:input.multiple});"
    )
    _surf(["js", expose_script, "--tab-id", tab_id], timeout=60)
    read = _surf(["read", "--filter", "all", "--tab-id", tab_id], timeout=60).stdout
    upload_ref = _find_ref(read, r'button "Upload files" \[(e\d+)\] type="file"')
    if not upload_ref:
        raise SubmitFailure("Claude upload file input ref not found after expose step")
    attach_file_abs = attach_file.resolve()
    _surf(["upload", "--ref", upload_ref, "--files", str(attach_file_abs), "--tab-id", tab_id], timeout=60)
    visible = _wait_for_attachment(tab_id, attach_file_abs.name)
    return {
        "path": str(attach_file_abs),
        "filename": attach_file_abs.name,
        "upload_ref": upload_ref,
        "preview_visible": visible,
    }


def _wait_for_attachment(tab_id: str, filename: str) -> bool:
    deadline = time.time() + 60
    while time.time() < deadline:
        text = _surf(["text", "--tab-id", tab_id], timeout=60).stdout
        if filename in text:
            return True
        time.sleep(2)
    raise SubmitFailure(f"uploaded attachment {filename!r} did not appear in Claude page text")


def _wait_for_sentinel(tab_id: str, sentinel: str, *, timeout_seconds: int, stable_polls: int) -> str:
    deadline = time.time() + timeout_seconds
    previous_hash = ""
    stable = 0
    last_text = ""
    while time.time() < deadline:
        last_text = _surf(["text", "--tab-id", tab_id], timeout=60).stdout
        latest_response = _latest_claude_response(last_text)
        if sentinel in latest_response and "Claude is responding" not in last_text:
            digest = hashlib.sha256(last_text.encode("utf-8")).hexdigest()
            if digest == previous_hash:
                stable += 1
            else:
                stable = 0
                previous_hash = digest
            if stable >= stable_polls:
                return last_text
        time.sleep(2)
    raise SubmitFailure(f"timed out waiting for marker {sentinel!r}")


def _clean_response(raw_text: str, sentinel: str) -> str:
    response_text = _latest_claude_response(raw_text)
    idx = response_text.rfind(sentinel)
    if idx < 0:
        raise SubmitFailure("sentinel missing from latest Claude response")
    return response_text[:idx].rstrip() + "\n"


def _latest_claude_response(raw_text: str) -> str:
    marker = "Claude responded:"
    idx = raw_text.rfind(marker)
    if idx < 0:
        return raw_text
    return raw_text[idx + len(marker) :]


def _success_meta(
    *,
    args: argparse.Namespace,
    input_path: Path,
    output_path: Path,
    raw_path: Path,
    submitted_path: Path,
    sentinel: str,
    started_at: str,
    finished_at: str,
    requested_tab_id: str,
    focus_before: dict[str, Any],
    focus_after: dict[str, Any],
    clean_text: str,
    raw_text: str,
    attach_file: Path | None = None,
    attachment: dict[str, Any] | None = None,
    content_script_recovery: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    contamination = [
        needle
        for needle in [
            "Skip to content",
            "Chat history",
            "Write your prompt to Claude",
        ]
        if needle in clean_text
    ]
    focus_changed = (
        focus_before.get("focusedWindowId") != focus_after.get("focusedWindowId")
        or focus_before.get("activeTabId") != focus_after.get("activeTabId")
    )
    status = "completed" if not contamination and sentinel in raw_text and sentinel not in clean_text else "failed"
    return {
        "status": status,
        "failure": None if status == "completed" else "missing_sentinel_or_contaminated_clean_output",
        "input": str(input_path),
        "submitted_output": str(submitted_path),
        "output": str(output_path),
        "raw_output": str(raw_path),
        "sentinel": sentinel,
        "requested_tab_id": requested_tab_id,
        "requested_url": args.url or None,
        "attach_file": str(attach_file.resolve()) if attach_file else None,
        "attachment": attachment,
        "attachment_missing": bool(attach_file and not attachment),
        "attachment_preview_missing": bool(attachment and not attachment.get("preview_visible")),
        "stable_polls": int(args.stable_polls),
        "timeout_s": int(args.timeout),
        "raw_contains_sentinel": sentinel in raw_text,
        "clean_contains_sentinel": sentinel in clean_text,
        "clean_contamination_markers": contamination,
        "raw_chars": len(raw_text),
        "clean_chars": len(clean_text),
        "controlled_tab_id": requested_tab_id,
        "controlled_tab_id_mismatch": False,
        "no_activate": bool(args.no_activate),
        "activated": None,
        "activation_violation": False,
        "focused_window_before": focus_before.get("focusedWindowId"),
        "focused_window_after": focus_after.get("focusedWindowId"),
        "active_tab_before": focus_before.get("activeTabId"),
        "active_tab_after": focus_after.get("activeTabId"),
        "focus_changed": focus_changed,
        "content_script_recovery": content_script_recovery or [],
        "started_at": started_at,
        "finished_at": finished_at,
    }


def _write_failed_meta(
    meta_path: Path,
    args: argparse.Namespace,
    input_path: Path,
    output_path: Path,
    raw_path: Path,
    submitted_path: Path,
    sentinel: str,
    started_at: str,
    finished_at: str,
    failure: str,
    *,
    requested_tab_id: str,
    raw_text: str = "",
    content_script_recovery: list[dict[str, Any]] | None = None,
) -> None:
    meta = {
        "status": "failed",
        "failure": failure,
        "input": str(input_path),
        "submitted_output": str(submitted_path),
        "output": str(output_path),
        "raw_output": str(raw_path),
        "sentinel": sentinel,
        "requested_tab_id": requested_tab_id or None,
        "requested_url": args.url or None,
        "attach_file": str(Path(args.attach_file).expanduser()) if args.attach_file else None,
        "attachment": None,
        "raw_contains_sentinel": sentinel in raw_text,
        "clean_contains_sentinel": False,
        "raw_chars": len(raw_text),
        "clean_chars": 0,
        "controlled_tab_id": requested_tab_id or None,
        "no_activate": bool(args.no_activate),
        "content_script_recovery": content_script_recovery or [],
        "started_at": started_at,
        "finished_at": finished_at,
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tab_list() -> list[dict[str, Any]]:
    last_error = ""
    for _ in range(3):
        result = _surf(["tab.list", "--json"], timeout=60)
        try:
            payload = json.loads(result.stdout)
            break
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            time.sleep(0.5)
    else:
        raise SubmitFailure(f"surf tab.list returned invalid JSON after retries: {last_error}")
    if isinstance(payload, dict):
        payload = payload.get("tabs", [])
    if not isinstance(payload, list):
        raise SubmitFailure("surf tab.list did not return a list")
    return [item for item in payload if isinstance(item, dict)]


def _focus_state() -> dict[str, Any]:
    try:
        payload = json.loads(_surf(["focus.state", "--json"], timeout=15).stdout)
    except Exception:
        return {"focusedWindowId": None, "activeTabId": None, "activeTabUrl": None}
    return {
        "focusedWindowId": payload.get("focusedWindowId"),
        "activeTabId": payload.get("activeTabId"),
        "activeTabUrl": payload.get("activeTabUrl"),
    }


def _ensure_claude_content_script_ready(tab_id: str, recovery_events: list[dict[str, Any]]) -> None:
    probe = _run_surf(["read", "--tab-id", tab_id], timeout=60)
    if probe.returncode == 0 and not _is_content_script_missing(probe):
        return
    if not _is_content_script_missing(probe):
        _raise_surf_failure(["read", "--tab-id", tab_id], probe)

    event: dict[str, Any] = {
        "status": "content_script_missing",
        "tab_id": tab_id,
        "detected_at": _now(),
        "probe_stderr": probe.stderr.strip()[:1000],
        "probe_stdout": probe.stdout.strip()[:1000],
        "action": "tab.reload --hard",
    }
    recovery_events.append(event)

    reload_proc = _run_surf(["tab.reload", "--hard", "--tab-id", tab_id], timeout=60)
    event["reload_returncode"] = reload_proc.returncode
    event["reload_stdout"] = reload_proc.stdout.strip()[:1000]
    event["reload_stderr"] = reload_proc.stderr.strip()[:1000]
    if reload_proc.returncode != 0:
        event["status"] = "reload_failed"
        _raise_surf_failure(["tab.reload", "--hard", "--tab-id", tab_id], reload_proc)

    deadline = time.time() + int(os.environ.get("SURF_CLAUDE_CONTENT_SCRIPT_READY_TIMEOUT", "45"))
    attempt = 0
    last_probe = probe
    while time.time() < deadline:
        attempt += 1
        time.sleep(min(1 + attempt, 5))
        last_probe = _run_surf(["read", "--tab-id", tab_id], timeout=60)
        if last_probe.returncode == 0 and not _is_content_script_missing(last_probe):
            event["status"] = "recovered"
            event["ready_attempts"] = attempt
            event["recovered_at"] = _now()
            return

    event["status"] = "recovery_failed"
    event["ready_attempts"] = attempt
    event["last_probe_stdout"] = last_probe.stdout.strip()[:1000]
    event["last_probe_stderr"] = last_probe.stderr.strip()[:1000]
    raise SubmitFailure(
        "Claude content script was not loaded; reloaded the controlled tab but it did not become readable again"
    )


def _surf(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    proc = _run_surf(args, timeout=timeout)
    if proc.returncode != 0:
        _raise_surf_failure(args, proc)
    return proc


def _run_surf(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(RUN_SH), *args], capture_output=True, text=True, timeout=timeout)


def _raise_surf_failure(args: list[str], proc: subprocess.CompletedProcess[str]) -> None:
    raise SubmitFailure(proc.stderr.strip() or proc.stdout.strip() or f"surf {' '.join(args)} failed")


def _is_content_script_missing(proc: subprocess.CompletedProcess[str]) -> bool:
    haystack = f"{proc.stdout}\n{proc.stderr}".lower()
    return "content script not loaded" in haystack


def _find_ref(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
