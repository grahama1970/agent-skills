#!/usr/bin/env python3
"""Gemini tab oracle controller.

Uses surf extension commands to control an authenticated Gemini tab,
inject a sentinel prompt, wait for completion, and extract the response.

Modeled on the surf-cli chatgpt command contract, but adapted for
Gemini's DOM structure.

Contract:
  - controlled_tab_id == requested_tab_id
  - sentinel present in raw response
  - clean response strips sentinel and page chrome
  - focus_changed recorded for proof
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from typing import Any


def surf_command(surf_run: str, *args: str, tab_id: str | None = None) -> str:
    """Run a surf command and return stdout."""
    cmd = [surf_run]
    cmd.extend(args)
    if tab_id:
        cmd.extend(["--tab-id", tab_id])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"surf {' '.join(args)} failed: {proc.stderr[:500]}")
    return proc.stdout


def find_gemini_elements(surf_run: str, tab_id: str) -> dict[str, str]:
    """Find Gemini input textbox and submit button refs."""
    stdout = surf_command(surf_run, "read", tab_id=tab_id)
    elements = {}
    # Look for textbox with Gemini prompt label
    for line in stdout.splitlines():
        # textbox "Enter a prompt for Gemini" [e38]
        m = re.search(r'textbox\s+"([^"]*(?:prompt|Gemini)[^"]*)"\s+\[(e\d+)\]', line, re.IGNORECASE)
        if m:
            elements["textbox"] = m.group(2)
            continue
        # submit button (often inside generic, look for Send message or just button near textbox)
        m = re.search(r'button\s+"([^"]*(?:Send|Submit)[^"]*)"\s+\[(e\d+)\]', line, re.IGNORECASE)
        if m:
            elements["submit"] = m.group(2)
    # Fallback: if no explicit submit, try button right after textbox in output order
    if "submit" not in elements and "textbox" in elements:
        # Heuristic: find any button after the textbox line
        lines = stdout.splitlines()
        found_textbox = False
        for line in lines:
            if elements["textbox"] in line:
                found_textbox = True
                continue
            if found_textbox:
                m = re.search(r'button\s+"([^"]*)"\s+\[(e\d+)\]', line)
                if m and "Stop" not in m.group(1) and "Settings" not in m.group(1):
                    elements["submit"] = m.group(2)
                    break
    return elements


def type_prompt(surf_run: str, tab_id: str, textbox_ref: str, prompt: str) -> None:
    """Type the prompt into the Gemini textbox."""
    # Click to focus first
    surf_command(surf_run, "click", textbox_ref, tab_id=tab_id)
    time.sleep(0.3)
    surf_command(surf_run, "type", prompt, "--ref", textbox_ref, tab_id=tab_id)
    time.sleep(0.3)


def click_submit(surf_run: str, tab_id: str, submit_ref: str) -> None:
    surf_command(surf_run, "click", submit_ref, tab_id=tab_id)
    time.sleep(0.5)


def is_generating(surf_run: str, tab_id: str) -> bool:
    """Check if Gemini is still generating (Stop response button present)."""
    try:
        stdout = surf_command(surf_run, "read", tab_id=tab_id)
    except RuntimeError:
        return False
    return "Stop response" in stdout


def get_page_text(surf_run: str, tab_id: str) -> str:
    """Get raw page text from Gemini tab."""
    stdout = surf_command(surf_run, "text", tab_id=tab_id)
    return stdout


def extract_latest_gemini_response(page_text: str, sentinel: str) -> str | None:
    """Extract the latest Gemini response from page text.

    Gemini page text format:
      ... You said <prompt> Gemini said <response> You said <prompt2> Gemini said <response2> ...

    We want the last response before the sentinel.
    """
    # Find the sentinel
    sentinel_idx = page_text.rfind(sentinel)
    if sentinel_idx == -1:
        return None

    # Get text before sentinel
    before = page_text[:sentinel_idx]

    # Find the last "Gemini said" before the sentinel
    marker = "Gemini said"
    last_idx = before.rfind(marker)
    if last_idx == -1:
        # Fallback: just return everything before sentinel
        return before.strip()

    response = before[last_idx + len(marker):].strip()

    # Clean up common artifacts
    # Remove "Show code" buttons that appear as text
    response = re.sub(r'Show\s*code\s*', '', response, flags=re.IGNORECASE)
    # Remove "Thinking" badge text if present
    response = re.sub(r'\bThinking\b', '', response)
    # Remove trailing button-like text
    response = re.sub(r'\n+.*$', '\n', response, flags=re.DOTALL)
    return response.strip()


def wait_for_response(
    surf_run: str,
    tab_id: str,
    sentinel: str,
    timeout: float = 300.0,
    stable_polls: int = 3,
    poll_interval: float = 2.5,
) -> dict[str, Any]:
    """Poll Gemini tab until response completes.

    Completion criteria:
      1. Sentinel appears in page text
      2. "Stop response" button is gone (not generating)
      3. Page text remains stable for N polls
    """
    deadline = time.monotonic() + timeout
    last_text = ""
    stable_count = 0
    last_change_time = time.monotonic()
    min_stable_seconds = 3.0

    while time.monotonic() < deadline:
        time.sleep(poll_interval)

        try:
            page_text = get_page_text(surf_run, tab_id)
        except RuntimeError:
            continue

        has_sentinel = sentinel in page_text
        generating = is_generating(surf_run, tab_id)

        # Track stability
        if page_text != last_text:
            last_text = page_text
            stable_count = 0
            last_change_time = time.monotonic()
        else:
            stable_count += 1

        stable_seconds = time.monotonic() - last_change_time

        # Determine if done
        is_done = (
            has_sentinel
            and not generating
            and stable_count >= stable_polls
            and stable_seconds >= min_stable_seconds
        )

        if is_done:
            response = extract_latest_gemini_response(page_text, sentinel)
            return {
                "done": True,
                "raw_text": page_text,
                "response": response or "",
                "has_sentinel": has_sentinel,
                "generating": generating,
                "stable_count": stable_count,
                "stable_seconds": stable_seconds,
            }

    # Timeout
    return {
        "done": False,
        "raw_text": last_text,
        "response": extract_latest_gemini_response(last_text, sentinel) or "",
        "has_sentinel": sentinel in last_text,
        "generating": is_generating(surf_run, tab_id),
        "stable_count": stable_count,
        "error": "timeout",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini tab oracle controller")
    parser.add_argument("--input", required=True, help="Prompt file path")
    parser.add_argument("--output", required=True, help="Clean response output path")
    parser.add_argument("--raw-output", required=True, help="Raw response output path")
    parser.add_argument("--meta-output", required=True, help="Metadata JSON output path")
    parser.add_argument("--sentinel", default="auto", help="Completion sentinel")
    parser.add_argument("--tab-id", required=True, help="Controlled Gemini tab id")
    parser.add_argument("--surf-run", default="", help="Path to surf run.sh")
    parser.add_argument("--timeout", type=float, default=300.0, help="Timeout in seconds")
    parser.add_argument("--stable-polls", type=int, default=3, help="Required stable polls")
    parser.add_argument("--no-activate", action="store_true", help="Background mode")
    args = parser.parse_args()

    surf_run = args.surf_run or (pathlib.Path(__file__).parent.parent / "run.sh").__str__()
    prompt = pathlib.Path(args.input).read_text()
    tab_id = args.tab_id

    if args.sentinel == "auto" or not args.sentinel:
        import random
        rand = "".join(f"{random.randint(0, 255):02x}" for _ in range(4))
        sentinel = f"<<<GEMINI_DONE:{time.strftime('%Y%m%dT%H%M%SZ')}:{rand}>>>"
    else:
        sentinel = args.sentinel

    submitted_prompt = (
        f"{prompt}\n\n---\n\n"
        f"Completion contract for browser automation:\n\n"
        f"At the very end of your final answer, print exactly:\n\n"
        f"{sentinel}\n\n"
        f"Do not print anything after that marker."
    )

    submitted_path = pathlib.Path(args.output).parent / (pathlib.Path(args.output).stem + ".submitted.md")
    submitted_path.write_text(submitted_prompt)

    # Pre-run focus state
    focus_before = ""
    try:
        focus_before = subprocess.run(
            [surf_run, "focus.state", "--json"],
            capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        pass

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    try:
        elements = find_gemini_elements(surf_run, tab_id)
        if "textbox" not in elements:
            raise RuntimeError("Could not find Gemini input textbox")

        type_prompt(surf_run, tab_id, elements["textbox"], submitted_prompt)

        if "submit" in elements:
            click_submit(surf_run, tab_id, elements["submit"])
        else:
            # Fallback: press Enter via surf key
            subprocess.run([surf_run, "key", "Enter", "--tab-id", tab_id], capture_output=True, timeout=10)

        result = wait_for_response(
            surf_run, tab_id, sentinel,
            timeout=args.timeout,
            stable_polls=args.stable_polls,
        )
    except Exception as exc:
        finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        meta = {
            "status": "failed",
            "error": str(exc),
            "requested_tab_id": tab_id,
            "controlled_tab_id": tab_id,
            "sentinel": sentinel,
            "started_at": started_at,
            "finished_at": finished_at,
        }
        pathlib.Path(args.meta_output).write_text(json.dumps(meta, indent=2) + "\n")
        pathlib.Path(args.raw_output).write_text("")
        pathlib.Path(args.output).write_text("")
        print(f"Gemini control failed: {exc}", file=sys.stderr)
        return 1

    finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Post-run focus state
    focus_after = ""
    try:
        focus_after = subprocess.run(
            [surf_run, "focus.state", "--json"],
            capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        pass

    raw_text = result.get("raw_text", "")
    response_text = result.get("response", "")

    # Clean extraction: remove sentinel if somehow left in
    if sentinel in response_text:
        response_text = response_text[:response_text.rfind(sentinel)].rstrip()

    pathlib.Path(args.raw_output).write_text(raw_text)
    pathlib.Path(args.output).write_text(response_text + "\n" if response_text and not response_text.endswith("\n") else response_text)

    # Parse focus change
    focus_changed = False
    try:
        before = json.loads(focus_before) if focus_before else {}
        after = json.loads(focus_after) if focus_after else {}
        focus_changed = (
            before.get("focusedWindowId") != after.get("focusedWindowId")
            or before.get("activeTabId") != after.get("activeTabId")
        )
    except Exception:
        pass

    # Contamination check
    contamination = []
    for needle in [
        "Completion contract for browser automation",
        "At the very end of your final answer",
        "Do not print anything after that marker",
    ]:
        if needle in response_text:
            contamination.append(needle)

    meta = {
        "status": "completed" if result.get("done") else "timeout",
        "requested_tab_id": tab_id,
        "controlled_tab_id": tab_id,
        "sentinel": sentinel,
        "raw_contains_sentinel": sentinel in raw_text,
        "clean_contains_sentinel": sentinel in response_text,
        "clean_contamination_markers": contamination,
        "raw_chars": len(raw_text),
        "clean_chars": len(response_text),
        "no_activate": args.no_activate,
        "focus_changed": focus_changed,
        "started_at": started_at,
        "finished_at": finished_at,
        "generating_at_end": result.get("generating", False),
        "stable_count": result.get("stable_count", 0),
    }
    pathlib.Path(args.meta_output).write_text(json.dumps(meta, indent=2) + "\n")

    if not result.get("done"):
        print("Gemini response did not complete within timeout", file=sys.stderr)
        return 4
    if not response_text.strip():
        print("Gemini response was empty after extraction", file=sys.stderr)
        return 5

    return 0


if __name__ == "__main__":
    sys.exit(main())
