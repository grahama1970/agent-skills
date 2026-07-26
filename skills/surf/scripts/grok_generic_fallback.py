#!/usr/bin/env python3
"""Fallback Grok submit path using generic Surf tab controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class FallbackError(RuntimeError):
    def __init__(self, message: str, *, evidence: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.evidence = evidence or {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surf-run", required=True)
    parser.add_argument("--tab-id", required=True)
    parser.add_argument("--submitted-prompt-path", required=True)
    parser.add_argument("--raw-output", required=True)
    parser.add_argument("--sentinel", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--stable-polls", type=int, default=2)
    parser.add_argument("--attach-file", action="append", default=[])
    args = parser.parse_args()

    evidence: dict[str, Any] = {
        "transport_fallback": "generic_surf_js_type_submit",
        "tab_id": args.tab_id,
        "attachments": [],
    }

    try:
        prompt = Path(args.submitted_prompt_path).read_text(encoding="utf-8")
        attachments = [Path(value).expanduser().resolve() for value in args.attach_file]
        for attachment in attachments:
            if not attachment.is_file():
                raise FallbackError(f"attachment file not found: {attachment}")
        if attachments:
            evidence["attachments"] = _upload_attachments(args.surf_run, args.tab_id, attachments)

        focus = _focus_composer(args.surf_run, args.tab_id)
        evidence["composer_focus"] = focus
        if not focus.get("ok"):
            raise FallbackError("Grok composer was not focusable", evidence=evidence)

        _surf(
            args.surf_run,
            ["type", prompt, "--clear", "--submit", "--tab-id", args.tab_id],
            timeout=90,
        )
        evidence["submitted_by"] = "surf_type_clear_submit"

        raw_text, poll_evidence = _wait_for_sentinel(
            args.surf_run,
            args.tab_id,
            args.sentinel,
            timeout_s=args.timeout,
            stable_polls=max(1, args.stable_polls),
        )
        evidence.update(poll_evidence)
        Path(args.raw_output).write_text(raw_text, encoding="utf-8")
        print(json.dumps({"ok": True, **evidence}, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        if isinstance(exc, FallbackError):
            evidence.update(exc.evidence)
        evidence.update({"ok": False, "error": str(exc)})
        payload = json.dumps(evidence, indent=2, sort_keys=True)
        print(payload)
        print(payload, file=sys.stderr)
        return 1


def _surf(surf_run: str, args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [surf_run, *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=True,
    )


def _surf_jsonish(surf_run: str, args: list[str], *, timeout: int = 60) -> Any:
    proc = _surf(surf_run, args, timeout=timeout)
    return _decode_surf_stdout(proc.stdout)


def _decode_surf_stdout(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _focus_composer(surf_run: str, tab_id: str) -> dict[str, Any]:
    js = r"""
(() => {
  const visible = (el) => {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
      style.opacity !== '0' && rect.width > 0 && rect.height > 0;
  };
  const selectors = [
    'textarea',
    '[contenteditable="true"][role="textbox"]',
    '[data-testid="grokComposerInput"]',
    '[role="textbox"]'
  ];
  const seen = new Set();
  const candidates = [];
  for (const selector of selectors) {
    for (const el of document.querySelectorAll(selector)) {
      if (!seen.has(el) && visible(el)) {
        seen.add(el);
        candidates.push(el);
      }
    }
  }
  const el = candidates[candidates.length - 1];
  if (!el) {
    return {ok:false, reason:'composer_not_found', url:location.href, title:document.title};
  }
  el.focus();
  const rect = el.getBoundingClientRect();
  return {
    ok: document.activeElement === el || el.contains(document.activeElement),
    tag: el.tagName,
    role: el.getAttribute('role'),
    ariaLabel: el.getAttribute('aria-label'),
    dataTestId: el.getAttribute('data-testid'),
    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
    url: location.href,
    title: document.title
  };
})()
"""
    value = _surf_jsonish(surf_run, ["js", js, "--tab-id", tab_id], timeout=60)
    return value if isinstance(value, dict) else {"ok": False, "raw": value}


def _upload_attachments(surf_run: str, tab_id: str, attachments: list[Path]) -> list[dict[str, Any]]:
    expose_js = r"""
(() => {
  const input = document.querySelector('input[type="file"]');
  if (!input) return {ok:false, reason:'file_input_not_found'};
  input.id = 'surf-grok-submit-upload-input';
  input.removeAttribute('aria-hidden');
  input.tabIndex = 0;
  Object.assign(input.style, {
    position:'fixed',
    left:'20px',
    bottom:'20px',
    width:'260px',
    height:'44px',
    opacity:'1',
    zIndex:'2147483647',
    background:'white',
    color:'black'
  });
  return {ok:true, id:input.id, type:input.type, multiple:input.multiple};
})()
"""
    exposed = _surf_jsonish(surf_run, ["js", expose_js, "--tab-id", tab_id], timeout=60)
    if not isinstance(exposed, dict) or not exposed.get("ok"):
        raise FallbackError("Grok file input not found", evidence={"attachment_expose": exposed})

    read = _surf(surf_run, ["read", "--filter", "all", "--tab-id", tab_id], timeout=60).stdout
    upload_ref = _find_upload_ref(read)
    if not upload_ref:
        raise FallbackError(
            "Grok upload input ref not found after expose step",
            evidence={"attachment_expose": exposed, "attachment_read_chars": len(read)},
        )

    files_arg = ",".join(str(path) for path in attachments)
    _surf(surf_run, ["upload", "--ref", upload_ref, "--files", files_arg, "--tab-id", tab_id], timeout=120)

    uploaded: list[dict[str, Any]] = []
    deadline = time.time() + 90
    names = [path.name for path in attachments]
    while time.time() < deadline:
        text = _page_text(surf_run, tab_id)
        if all(name in text for name in names):
            for path in attachments:
                uploaded.append({"path": str(path), "filename": path.name, "upload_ref": upload_ref, "preview_visible": True})
            return uploaded
        time.sleep(2)
    raise FallbackError(
        "Grok attachment preview did not appear",
        evidence={"attachment_expose": exposed, "upload_ref": upload_ref, "filenames": names},
    )


def _find_upload_ref(read_text: str) -> str:
    for line in read_text.splitlines():
        if "surf-grok-submit-upload-input" in line or 'type="file"' in line:
            for part in line.split():
                if part.startswith("[e") and part.endswith("]"):
                    return part.strip("[]")
    return ""


def _wait_for_sentinel(
    surf_run: str,
    tab_id: str,
    sentinel: str,
    *,
    timeout_s: int,
    stable_polls: int,
) -> tuple[str, dict[str, Any]]:
    deadline = time.time() + timeout_s
    previous_hash = ""
    stable = 0
    poll_count = 0
    last_text = ""
    sentinel_seen_at: int | None = None
    while time.time() < deadline:
        poll_count += 1
        last_text = _latest_sentinel_text(surf_run, tab_id, sentinel)
        if sentinel in last_text:
            sentinel_seen_at = sentinel_seen_at or poll_count
            digest = hashlib.sha256(last_text.encode("utf-8")).hexdigest()
            if digest == previous_hash:
                stable += 1
            else:
                previous_hash = digest
                stable = 0
            if stable >= stable_polls:
                return last_text, {
                    "sentinel_seen_at_poll": sentinel_seen_at,
                    "poll_count": poll_count,
                    "stable_polls_observed": stable,
                    "response_source": "grok_dom_candidate_with_sentinel",
                }
        time.sleep(2)
    raise FallbackError(
        f"timed out waiting for Grok sentinel {sentinel!r}",
        evidence={"poll_count": poll_count, "last_text_chars": len(last_text), "sentinel_seen_at_poll": sentinel_seen_at},
    )


def _latest_sentinel_text(surf_run: str, tab_id: str, sentinel: str) -> str:
    js = f"""
(() => {{
  const sentinel = {json.dumps(sentinel)};
  const selector = [
    'article',
    '[data-testid*="message"]',
    '[class*="message"]',
    '[class*="prose"]',
    '[class*="markdown"]',
    'main div'
  ].join(',');
  const texts = Array.from(document.querySelectorAll(selector))
    .map((el) => (el.innerText || '').trim())
    .filter((text) => text.includes(sentinel));
  texts.sort((a, b) => a.length - b.length);
  return texts[0] || document.body.innerText || '';
}})()
"""
    value = _surf_jsonish(surf_run, ["js", js, "--tab-id", tab_id], timeout=60)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return json.dumps(value, indent=2, sort_keys=True)
    return str(value or "")


def _page_text(surf_run: str, tab_id: str) -> str:
    value = _surf_jsonish(surf_run, ["js", "return document.body.innerText || ''", "--tab-id", tab_id], timeout=60)
    return value if isinstance(value, str) else str(value or "")


if __name__ == "__main__":
    raise SystemExit(main())
