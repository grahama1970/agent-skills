#!/usr/bin/env python3
from __future__ import annotations
"""Apply the PersonaPlex P11 ChatWell speech_final wiring to ChatTab.tsx.

The uploaded creation bundle did not include the full ChatTab.tsx body. This
script therefore performs the smallest deterministic in-place edit against the
known seam from the brief: `piChat.send(query, type)`.

Exit codes:
  0: patch applied or already present
  2: expected ChatTab seam was not found
"""

import argparse
import re
import sys
from pathlib import Path

CHAT_TAB_REL = Path('pi-mono/packages/ux-lab/src/components/sparta/explorer/ChatTab.tsx')
IMPORT_LINE = "import { sendPersonaPlexSpeechFinalBestEffort } from './personaplexSpeechFinalClient'"
SEND_MARKER = 'sendPersonaPlexSpeechFinalBestEffort(query'


def _insert_import(source: str) -> str:
    if "./personaplexSpeechFinalClient" in source:
        return source

    persona_panel_import = re.compile(
        r"^(import\s+\{\s*PersonaPlexVoiceTracePanel\s*\}\s+from\s+['\"]\.\/PersonaPlexVoiceTracePanel['\"]\s*)$",
        re.MULTILINE,
    )
    match = persona_panel_import.search(source)
    if match:
        return source[: match.end()] + "\n" + IMPORT_LINE + source[match.end():]

    # Fallback: append after the final top-level import block.
    import_lines = list(re.finditer(r"^import\s+.*$", source, flags=re.MULTILINE))
    if not import_lines:
        raise RuntimeError('no import block found in ChatTab.tsx')
    last = import_lines[-1]
    return source[: last.end()] + "\n" + IMPORT_LINE + source[last.end():]


def _insert_send(source: str) -> str:
    if SEND_MARKER in source:
        return source

    pattern = re.compile(r"^(?P<indent>\s*)piChat\.send\(query,\s*type\)\s*$", re.MULTILINE)
    match = pattern.search(source)
    if not match:
        raise RuntimeError('expected line `piChat.send(query, type)` not found')

    indent = match.group('indent')
    injected = (
        f"{indent}piChat.send(query, type)\n"
        f"{indent}void sendPersonaPlexSpeechFinalBestEffort(query, {{\n"
        f"{indent}  wsUrl: 'ws://127.0.0.1:8788/ws',\n"
        f"{indent}  personaId: 'embry',\n"
        f"{indent}}})"
    )
    return source[: match.start()] + injected + source[match.end():]


def patch_source(source: str) -> str:
    return _insert_send(_insert_import(source))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', default='.', help='repository root containing pi-mono/')
    parser.add_argument('--chat-tab', default=None, help='optional explicit ChatTab.tsx path')
    parser.add_argument('--check', action='store_true', help='do not write; fail if a change would be made')
    args = parser.parse_args(argv)

    chat_tab = Path(args.chat_tab) if args.chat_tab else Path(args.repo_root) / CHAT_TAB_REL
    chat_tab = chat_tab.resolve()
    if not chat_tab.exists():
        print(f'ERROR: ChatTab.tsx not found: {chat_tab}', file=sys.stderr)
        return 2

    source = chat_tab.read_text(encoding='utf-8')
    try:
        patched = patch_source(source)
    except RuntimeError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    if patched == source:
        print(f'OK: P11 ChatWell PersonaPlex speech_final wiring already present in {chat_tab}')
        return 0

    if args.check:
        print(f'NEEDS_PATCH: {chat_tab}')
        return 2

    chat_tab.write_text(patched, encoding='utf-8')
    print(f'OK: patched {chat_tab}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
