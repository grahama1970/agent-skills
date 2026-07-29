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
    def __init__(self, message: str, *, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}


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
    parser.add_argument("--lock-timeout", type=int, default=0)
    parser.add_argument("--tab-id", default="")
    parser.add_argument("--url", default="")
    parser.add_argument(
        "--model",
        default="",
        help="Optional Claude browser model preference label, for example 'Opus 5 High'.",
    )
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument(
        "--attach-file",
        action="append",
        default=[],
        help="Attach a file to the Claude message before submitting the prompt.",
    )
    parser.add_argument(
        "--attach-files",
        default="",
        help="Comma-separated file paths to attach to the Claude message.",
    )
    args = parser.parse_args()
    if args.lock_timeout > 0:
        os.environ["SURF_LOCK_TIMEOUT_MS"] = str(args.lock_timeout * 1000)

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_path = Path(args.raw_output or f"{args.output}.raw.md")
    meta_path = Path(args.meta_output or f"{args.output}.meta.json")
    submitted_path = Path(args.submitted_output or f"{args.output}.submitted.md")
    for path in (output_path, raw_path, meta_path, submitted_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")
    attach_files = _normalize_attach_files(args.attach_file, args.attach_files)
    for attach_file in attach_files:
        if not attach_file.is_file():
            raise SystemExit(f"--attach-file: file not found: {attach_file}")
    if "SURF_RUN_SH" not in os.environ and not Path("/tmp/surf.sock").exists():
        raise SystemExit("surf claude.submit requires the surf browser extension socket at /tmp/surf.sock.")

    sentinel = args.sentinel
    if not sentinel or sentinel == "auto":
        sentinel = f"<<<CLAUDE_DONE:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}:{secrets.token_hex(4)}>>>"

    prompt = input_path.read_text(encoding="utf-8")
    model_instruction: list[str] = []
    if args.model:
        model_instruction = [
            f"Requested Claude model preference: {args.model}",
            (
                "If the current Claude UI is not using that model and you cannot switch models, "
                "say so under Blockers before answering."
            ),
            "",
        ]
    submitted_prompt = "\n".join(
        [
            prompt.rstrip(),
            "",
            *model_instruction,
            "---",
            "",
            "Automation-only instruction: answer the user's request normally. Do not mention,",
            "quote, summarize, or explain this automation instruction. After your complete",
            "answer, append a final line containing only this exact marker:",
            "",
            sentinel,
            "",
            "Do not print anything after that marker.",
            "",
        ]
    )
    submitted_path.write_text(submitted_prompt, encoding="utf-8")

    started_at = _now()
    focus_before = _focus_state()
    requested_tab_id = _resolve_tab(args.tab_id, args.url)
    tab_identity_preflight: dict[str, Any] = {}
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
        tab_identity_preflight = _assert_claude_tab(requested_tab_id, args.url)
        _ensure_claude_content_script_ready(requested_tab_id, content_script_recovery)
        attachments = _attach_files(requested_tab_id, attach_files) if attach_files else []
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
            attach_files=attach_files,
            attachments=attachments,
            content_script_recovery=content_script_recovery,
            tab_identity_preflight=tab_identity_preflight,
        )
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        TAB_STATE_FILE.write_text(str(requested_tab_id).strip() + "\n", encoding="utf-8")
        print(json.dumps(meta, indent=2, sort_keys=True))
        return 0 if meta["status"] == "completed" else 5
    except Exception as exc:
        finished = _now()
        raw_text = ""
        try:
            raw_text = _page_text(requested_tab_id, timeout=30)
            raw_path.write_text(raw_text, encoding="utf-8")
        except Exception:
            raw_path.write_text("", encoding="utf-8")
        if _raw_text_has_response_sentinel(raw_text, sentinel):
            try:
                clean_text = _clean_response(raw_text, sentinel)
                output_path.write_text(clean_text, encoding="utf-8")
                focus_after = _focus_state()
                recovered_attachments = _recovered_attachment_metadata(attach_files)
                meta = _success_meta(
                    args=args,
                    input_path=input_path,
                    output_path=output_path,
                    raw_path=raw_path,
                    submitted_path=submitted_path,
                    sentinel=sentinel,
                    started_at=started_at,
                    finished_at=finished,
                    requested_tab_id=requested_tab_id,
                    focus_before=focus_before,
                    focus_after=focus_after,
                    clean_text=clean_text,
                    raw_text=raw_text,
                    attach_files=attach_files,
                    attachments=recovered_attachments,
                    content_script_recovery=content_script_recovery,
                    tab_identity_preflight=tab_identity_preflight,
                )
                meta["recovered_after_failure"] = True
                meta["recovery_failure"] = str(exc)
                meta["response_source"] = "post_failure_text_capture"
                meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                TAB_STATE_FILE.write_text(str(requested_tab_id).strip() + "\n", encoding="utf-8")
                print(json.dumps(meta, indent=2, sort_keys=True))
                return 0 if meta["status"] == "completed" else 5
            except Exception:
                pass
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
            failure_metadata=getattr(exc, "metadata", {}),
            tab_identity_preflight=tab_identity_preflight,
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


def _assert_claude_tab(tab_id: str, expect_url: str) -> dict[str, Any]:
    for tab in _tab_list():
        if str(tab.get("id")) == str(tab_id):
            url = str(tab.get("url") or "")
            identity = {
                "ok": True,
                "expected_tab_id": str(tab_id),
                "expected_url": expect_url or None,
                "tab": tab,
                "accepted_url_transition": False,
            }
            if "claude.ai" not in url:
                identity.update({"ok": False, "error": "not_claude_tab", "live_url": url})
                raise SubmitFailure(
                    f"tab {tab_id} is not a Claude tab: {url}",
                    metadata={"tab_identity_preflight": identity},
                )
            if expect_url and _normalize_url(url) != _normalize_url(expect_url):
                if _is_claude_new_to_chat_transition(expect_url, url):
                    identity.update(
                        {
                            "accepted_url_transition": True,
                            "expected_url": expect_url,
                            "live_url": url,
                            "reason": "claude_new_tab_materialized_chat",
                        }
                    )
                    return identity
                identity.update(
                    {
                        "ok": False,
                        "error": "expected_url_mismatch",
                        "expected_url": expect_url,
                        "live_url": url,
                    }
                )
                raise SubmitFailure(
                    f"tab {tab_id} URL mismatch: expected {expect_url}, saw {url}",
                    metadata={"tab_identity_preflight": identity},
                )
            identity["live_url"] = url
            return identity
    try:
        page_text = _page_text(tab_id, timeout=30)
        if "claude.ai" not in page_text:
            raise SubmitFailure(
                f"tab {tab_id} is not a Claude tab",
                metadata={
                    "tab_identity_preflight": {
                        "ok": False,
                        "error": "not_claude_tab",
                        "expected_tab_id": str(tab_id),
                        "expected_url": expect_url or None,
                    }
                },
            )
        if expect_url and _normalize_url(expect_url) not in page_text:
            raise SubmitFailure(
                f"tab {tab_id} URL mismatch: expected {expect_url}",
                metadata={
                    "tab_identity_preflight": {
                        "ok": False,
                        "error": "expected_url_mismatch",
                        "expected_tab_id": str(tab_id),
                        "expected_url": expect_url,
                    }
                },
            )
        return {
            "ok": True,
            "expected_tab_id": str(tab_id),
            "expected_url": expect_url or None,
            "live_url": None,
            "accepted_url_transition": False,
            "source": "page_text_fallback",
        }
    except SubmitFailure:
        raise
    except Exception:
        pass
    raise SubmitFailure(
        f"Claude tab {tab_id} not found in surf tab.list",
        metadata={
            "tab_identity_preflight": {
                "ok": False,
                "error": "tab_not_found",
                "expected_tab_id": str(tab_id),
                "expected_url": expect_url or None,
            }
        },
    )


def _is_claude_new_to_chat_transition(expected_url: str, live_url: str) -> bool:
    expected = _parse_url(expected_url)
    live = _parse_url(live_url)
    if expected.netloc not in {"claude.ai", "www.claude.ai"}:
        return False
    if live.netloc not in {"claude.ai", "www.claude.ai"}:
        return False
    expected_path = expected.path.rstrip("/")
    live_path = live.path.rstrip("/")
    return expected_path in {"", "/new"} and live_path.startswith("/chat/")


def _submit_prompt(tab_id: str, prompt: str) -> None:
    read = _surf(["read", "--tab-id", tab_id], timeout=60).stdout
    textbox_ref = _find_ref(read, r'textbox "Write your prompt to Claude" \[(e\d+)\]')
    if not textbox_ref:
        raise SubmitFailure("Claude prompt textbox not found")
    _surf(["click", textbox_ref, "--tab-id", tab_id], timeout=60)
    _surf(["type", prompt, "--ref", textbox_ref, "--tab-id", tab_id], timeout=60)
    if not _wait_for_claude_prompt_text(tab_id, prompt, timeout_seconds=10):
        raise SubmitFailure("Claude prompt composer did not receive inserted text")
    read_after = _surf(["read", "--tab-id", tab_id], timeout=60).stdout
    send_ref = _find_ref(read_after, r'button "Send message" \[(e\d+)\]')
    if send_ref:
        _surf(["click", send_ref, "--tab-id", tab_id], timeout=60)
    else:
        _surf(["key", "Enter", "--tab-id", tab_id], timeout=60)
    if not _wait_for_claude_submission_acceptance(tab_id, prompt, timeout_seconds=10):
        raise SubmitFailure("Claude prompt was staged but not submitted")


def _wait_for_claude_prompt_text(tab_id: str, prompt: str, *, timeout_seconds: int) -> bool:
    start = _normalize_visible_text(prompt[:80])
    end = _normalize_visible_text(prompt[-80:])
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        text = _normalize_visible_text(_page_text(tab_id, timeout=30))
        if start in text and end in text:
            return True
        time.sleep(0.5)
    return False


def _wait_for_claude_submission_acceptance(tab_id: str, prompt: str, *, timeout_seconds: int) -> bool:
    start = _normalize_visible_text(prompt[:80])
    end = _normalize_visible_text(prompt[-80:])
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        text = _normalize_visible_text(_page_text(tab_id, timeout=30))
        prompt_still_staged = start in text and end in text
        responding = "Claude is responding" in text or "Stop response" in text
        if responding or not prompt_still_staged:
            return True
        time.sleep(0.5)
    return False


def _normalize_visible_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _raw_text_has_response_sentinel(raw_text: str, sentinel: str) -> bool:
    return "Claude responded:" in raw_text and sentinel in _latest_claude_response(raw_text)


def _normalize_attach_files(values: list[str], comma_separated: str) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        if value:
            paths.append(Path(value).expanduser())
    if comma_separated:
        for part in comma_separated.split(","):
            part = part.strip()
            if part:
                paths.append(Path(part).expanduser())
    return paths


def _attach_files(tab_id: str, attach_files: list[Path]) -> list[dict[str, Any]]:
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
    resolved = [attach_file.resolve() for attach_file in attach_files]
    _surf(["upload", "--ref", upload_ref, "--files", ",".join(str(path) for path in resolved), "--tab-id", tab_id], timeout=120)
    attachments: list[dict[str, Any]] = []
    for attach_file_abs in resolved:
        visible = _wait_for_attachment(tab_id, attach_file_abs.name)
        attachments.append(
            {
                "path": str(attach_file_abs),
                "filename": attach_file_abs.name,
                "upload_ref": upload_ref,
                "preview_visible": visible,
            }
        )
    return attachments


def _wait_for_attachment(tab_id: str, filename: str) -> bool:
    deadline = time.time() + 60
    while time.time() < deadline:
        text = _page_text(tab_id, timeout=60)
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
        last_text = _page_text(tab_id, timeout=60)
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
    attach_files: list[Path] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    content_script_recovery: list[dict[str, Any]] | None = None,
    tab_identity_preflight: dict[str, Any] | None = None,
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
    attach_files = attach_files or []
    attachments = attachments or []
    attachment_missing = bool(attach_files) and len(attachments) != len(attach_files)
    attachment_preview_missing = any(item.get("preview_visible") is False for item in attachments)
    status = (
        "completed"
        if not contamination
        and sentinel in raw_text
        and sentinel not in clean_text
        and not attachment_missing
        and not attachment_preview_missing
        else "failed"
    )
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
        "current_url": _live_url_from_identity(tab_identity_preflight),
        "tab_identity_preflight": tab_identity_preflight or None,
        "requested_model": args.model or None,
        "model_preference": args.model or None,
        "model_selection_proven": False,
        "model_selection_note": (
            "Claude submit records the requested browser model preference; it does not prove the web UI selected that model."
            if args.model
            else None
        ),
        "attach_file": str(attach_files[0].resolve()) if len(attach_files) == 1 else None,
        "attach_files": [str(path.resolve()) for path in attach_files],
        "attachment": attachments[0] if len(attachments) == 1 else None,
        "attachments": attachments,
        "attachment_missing": attachment_missing,
        "attachment_preview_missing": attachment_preview_missing,
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


def _recovered_attachment_metadata(attach_files: list[Path]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for attach_file in attach_files:
        attachments.append(
            {
                "attached": True,
                "path": str(attach_file.resolve()),
                "name": attach_file.name,
                "preview_visible": None,
                "source": "post_failure_sentinel_recovery_attach_file",
            }
        )
    return attachments


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
    failure_metadata: dict[str, Any] | None = None,
    tab_identity_preflight: dict[str, Any] | None = None,
) -> None:
    failure_metadata = failure_metadata or {}
    tab_identity = failure_metadata.get("tab_identity_preflight") or tab_identity_preflight
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
        "current_url": _live_url_from_identity(tab_identity),
        "tab_identity_preflight": tab_identity or None,
        "requested_model": args.model or None,
        "model_preference": args.model or None,
        "model_selection_proven": False,
        "model_selection_note": (
            "Claude submit records the requested browser model preference; it does not prove the web UI selected that model."
            if args.model
            else None
        ),
        "attach_file": str(Path(args.attach_file[-1]).expanduser()) if args.attach_file else None,
        "attach_files": [str(path) for path in _normalize_attach_files(args.attach_file, getattr(args, "attach_files", ""))],
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


def _live_url_from_identity(identity: dict[str, Any] | None) -> str | None:
    if not isinstance(identity, dict):
        return None
    live_url = str(identity.get("live_url") or "").strip()
    if live_url:
        return live_url
    tab = identity.get("tab")
    if isinstance(tab, dict):
        live_url = str(tab.get("url") or "").strip()
        if live_url:
            return live_url
    return None


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


def _page_text(tab_id: str, *, timeout: int) -> str:
    return _surf(["page.text", "--tab-id", tab_id], timeout=timeout).stdout


def _run_surf(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        lock_wait_seconds = max(
            0,
            (int(os.environ.get("SURF_LOCK_TIMEOUT_MS", "60000")) + 999) // 1000,
        )
    except ValueError:
        lock_wait_seconds = 60
    return subprocess.run(
        [str(RUN_SH), *args],
        capture_output=True,
        text=True,
        timeout=timeout + lock_wait_seconds,
    )


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


def _parse_url(url: str) -> Any:
    import urllib.parse

    return urllib.parse.urlparse(url.strip())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
