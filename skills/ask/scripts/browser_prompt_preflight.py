#!/usr/bin/env python3
"""Fail-closed preflight for browser-handler prompts/bundles.

surf's webgpt submit refuses any prompt or attached bundle that references
unreadable local filesystem paths (schema surf.webgpt_prompt_preflight.v1,
reason web_review_bundle_unreadable) and path-like `~<digits>` tokens
(agent-skills#973). The lane then fails late with
`browser_submit_not_accepted`, after tab binding and wasted cycles.

Run this BEFORE any browser-handler submit (`tau-dag`/`compete` with a web*
handler, the `webgpt` shortcut) on your prompt and every --attach-file. It exits
non-zero and names the offending tokens so you fix them (describe paths as prose,
or attach the file's *content* — never reference a live local path/socket).

Usage:
    browser_prompt_preflight.py [--prompt "<text>"] [FILE ...]
    echo "<prompt>" | browser_prompt_preflight.py -           # prompt on stdin
Exit: 0 clean, 2 offending tokens found, 1 usage error.
"""
from __future__ import annotations

import re
import sys

# Absolute local roots surf rejects when the path exists on disk, plus ~ home
# refs and the `~<digits>` path-preflight trap.
_ABS = re.compile(r"(?<![\w])/(?:run|home|mnt|tmp|var|opt|usr|etc|root|dev|proc|sys)/[\w./+-]+")
_HOME = re.compile(r"(?<![\w])~/[\w./+-]+")
_TILDE_NUM = re.compile(r"~\d")
# Relative paths that resolve to a real file are rejected by surf too. This
# preflight exists to catch refusals BEFORE a lane is bound, and it missed a
# live one: `./run.sh` in a review bundle passed here and surf then refused the
# submit as web_review_bundle_unreadable, after tab binding and a wasted round.
_REL = re.compile(r"(?<![\w])\.{1,2}/[\w./+-]+")


def scan(label: str, text: str) -> list[tuple[str, str, str]]:
    hits: list[tuple[str, str, str]] = []
    for rx, kind in (
        (_ABS, "absolute_local_path"),
        (_HOME, "home_path"),
        (_TILDE_NUM, "tilde_digits"),
        (_REL, "relative_local_path"),
    ):
        for m in rx.finditer(text or ""):
            hits.append((label, kind, m.group(0)))
    return hits


#: Extensions whose content is data, not prose. An attachment the provider
#: uploads as a file is never read as prompt text.
_BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".ico",
    ".pdf", ".zip", ".gz", ".tar", ".mp4", ".mov", ".mp3", ".wav", ".woff", ".woff2",
}


def _is_binary(path: str) -> bool:
    """Whether this attachment is data rather than prose.

    Checked by suffix first, then by sniffing for a NUL byte, so an unlisted
    binary format is still skipped rather than mis-scanned as text.
    """
    import os

    if os.path.splitext(path)[1].lower() in _BINARY_SUFFIXES:
        return True
    try:
        with open(path, "rb") as handle:
            return b"\x00" in handle.read(4096)
    except OSError:
        return False


def main(argv: list[str]) -> int:
    args = argv[1:]
    prompt = ""
    files: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--prompt":
            i += 1
            prompt = args[i] if i < len(args) else ""
        elif a == "-":
            prompt = sys.stdin.read()
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            files.append(a)
        i += 1

    hits: list[tuple[str, str, str]] = []
    if prompt:
        hits += scan("<prompt>", prompt)
    for f in files:
        # Binary attachments carry no prose to reject. Scanning a JPEG's bytes
        # found "~4", "~5", "~2" and failed the submit as tilde_digits, which
        # blocked EVERY image attachment: a six-seat vision roundtable could not
        # dispatch at all (observed 2026-08-16 with a 308 KB lion photo).
        if _is_binary(f):
            continue
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                hits += scan(f, fh.read())
        except OSError as exc:
            print(f"ERROR: cannot read {f}: {exc}", file=sys.stderr)
            return 1

    if not hits:
        print("browser-prompt-preflight: OK (no local paths / ~<digits>)")
        return 0

    print("browser-prompt-preflight: FAIL — surf will reject this submit "
          "(browser_submit_not_accepted). Offending references:", file=sys.stderr)
    seen = set()
    for label, kind, tok in hits:
        key = (label, tok)
        if key in seen:
            continue
        seen.add(key)
        print(f"  [{kind}] {tok}   (in {label})", file=sys.stderr)
    print("\nFix: describe paths/sockets as prose (e.g. 'the daemon's Unix socket'), "
          "or attach the file's CONTENT — never reference a live local path. "
          "For '~<digits>' write 'about <n>'.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
