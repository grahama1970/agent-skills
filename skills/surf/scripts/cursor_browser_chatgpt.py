#!/usr/bin/env python3
"""Submit a prompt to ChatGPT in Cursor's embedded browser via cursor-browser-bridge."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from cursor_browser_client import (
    CursorBrowserBridgeError,
    call_tool,
    extract_chatgpt_response,
    extract_snapshot_refs,
    make_sentinel,
    strip_sentinel,
    wait_for_bridge,
)


def _snapshot_text(view_id: str) -> str:
    return call_tool(
        "browser_snapshot",
        {"viewId": view_id, "interactive": True},
        timeout=60,
    ).text


def _page_text_via_eval(view_id: str) -> str:
    script = "document.body ? document.body.innerText : ''"
    result = call_tool("browser_evaluate", {"viewId": view_id, "script": script}, timeout=60)
    text = result.text
    try:
        parsed = json.loads(text)
        if isinstance(parsed, str):
            return parsed
    except json.JSONDecodeError:
        pass
    return text


def submit_chatgpt(
    prompt: str,
    *,
    view_id: str,
    sentinel: str,
    timeout: float = 900.0,
    stable_polls: int = 3,
    poll_interval: float = 2.5,
) -> dict:
    wait_for_bridge()
    call_tool("browser_lock", {"viewId": view_id}, timeout=30)
    try:
        snap = _snapshot_text(view_id)
        refs = extract_snapshot_refs(snap)
        if "textbox" not in refs:
            raise CursorBrowserBridgeError(
                "Could not find ChatGPT compose textbox in browser_snapshot. "
                "Open an authenticated chatgpt.com conversation in Cursor Browser first."
            )
        textbox = refs["textbox"]
        call_tool(
            "browser_click",
            {"viewId": view_id, "ref": textbox, "element": "Chat with ChatGPT"},
            timeout=30,
        )
        time.sleep(0.3)
        call_tool(
            "browser_fill",
            {"viewId": view_id, "ref": textbox, "value": prompt},
            timeout=60,
        )
        time.sleep(0.3)
        if "send" in refs:
            call_tool(
                "browser_click",
                {"viewId": view_id, "ref": refs["send"], "element": "Send prompt"},
                timeout=30,
            )
        else:
            call_tool("browser_press_key", {"viewId": view_id, "key": "Enter"}, timeout=30)

        deadline = time.monotonic() + timeout
        last_text = ""
        stable = 0
        last_change = time.monotonic()
        raw_text = ""
        while time.monotonic() < deadline:
            time.sleep(poll_interval)
            raw_text = _page_text_via_eval(view_id)
            has_sentinel = sentinel in raw_text
            if raw_text != last_text:
                last_text = raw_text
                stable = 0
                last_change = time.monotonic()
            else:
                stable += 1
            if has_sentinel and stable >= stable_polls and (time.monotonic() - last_change) >= 3.0:
                break
        response = extract_chatgpt_response(raw_text, sentinel) or strip_sentinel(raw_text, sentinel)
        return {
            "raw_text": raw_text,
            "response": response,
            "has_sentinel": sentinel in raw_text,
            "textbox_ref": textbox,
            "send_ref": refs.get("send"),
        }
    finally:
        try:
            call_tool("browser_unlock", {"viewId": view_id}, timeout=15)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit prompt to ChatGPT in Cursor Browser")
    parser.add_argument("--input", required=True, help="Prompt file path")
    parser.add_argument("--output", required=True, help="Clean response path")
    parser.add_argument("--raw-output", default="", help="Raw response path")
    parser.add_argument("--meta-output", default="", help="Meta JSON path")
    parser.add_argument("--submitted-output", default="", help="Submitted prompt path")
    parser.add_argument("--view-id", required=True, help="Cursor browser viewId")
    parser.add_argument("--sentinel", default="auto")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--stable-polls", type=int, default=3)
    args = parser.parse_args()

    prompt = Path(args.input).read_text()
    sentinel = args.sentinel
    if sentinel in {"", "auto"}:
        sentinel = make_sentinel("WEBGPT_DONE")
    submitted = (
        prompt.rstrip()
        + "\n\n---\n\nCompletion contract for browser automation:\n\n"
        + "At the very end of your final answer, print exactly:\n\n"
        + sentinel
        + "\n\nDo not print anything after that marker.\n"
    )
    if args.submitted_output:
        Path(args.submitted_output).write_text(submitted)

    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    status = "failed"
    failure = None
    payload: dict = {}
    try:
        payload = submit_chatgpt(
            submitted,
            view_id=args.view_id,
            sentinel=sentinel,
            timeout=args.timeout,
            stable_polls=args.stable_polls,
        )
        raw_text = payload.get("raw_text", "")
        clean = payload.get("response", "")
        Path(args.output).write_text(clean)
        raw_path = args.raw_output or f"{args.output}.raw.md"
        Path(raw_path).write_text(raw_text)
        if sentinel in raw_text and sentinel not in clean:
            status = "completed"
        else:
            failure = "missing_sentinel_or_contaminated_clean_output"
    except CursorBrowserBridgeError as exc:
        failure = str(exc)
        Path(args.output).write_text("")
        if args.raw_output:
            Path(args.raw_output).write_text("")
    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta = {
        "status": status,
        "failure": failure,
        "backend": "cursor-browser",
        "requested_view_id": args.view_id,
        "controlled_view_id": args.view_id,
        "sentinel": sentinel,
        "stable_polls": args.stable_polls,
        "timeout_s": args.timeout,
        "raw_contains_sentinel": bool(payload.get("has_sentinel")),
        "clean_contains_sentinel": False,
        "started_at": started,
        "finished_at": finished,
        "textbox_ref": payload.get("textbox_ref"),
        "send_ref": payload.get("send_ref"),
    }
    if args.meta_output:
        Path(args.meta_output).write_text(json.dumps(meta, indent=2) + "\n")
        print(json.dumps(meta, indent=2))
    return 0 if status == "completed" else 5


if __name__ == "__main__":
    raise SystemExit(main())
