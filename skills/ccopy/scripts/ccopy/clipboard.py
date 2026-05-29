"""Platform clipboard helpers."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import List, Tuple

from ccopy.errors import CursorCopyError

def copy_to_clipboard(text: str) -> str:
    commands: List[Tuple[List[str], bytes]] = []
    system = platform.system()
    encoded = text.encode("utf-8")
    if system == "Darwin":
        commands.append((["pbcopy"], encoded))
    elif system == "Windows":
        commands.append((["clip"], encoded))
    else:
        if os.environ.get("WSL_DISTRO_NAME") or "microsoft" in platform.release().lower():
            commands.append((["clip.exe"], encoded))
        if os.environ.get("WAYLAND_DISPLAY"):
            commands.append((["wl-copy"], encoded))
        if os.environ.get("DISPLAY"):
            commands.append((["xclip", "-selection", "clipboard"], encoded))
            commands.append((["xsel", "--clipboard", "--input"], encoded))
        # Try common tools even if DISPLAY/WAYLAND was not exported into this shell.
        commands.append((["wl-copy"], encoded))
        commands.append((["xclip", "-selection", "clipboard"], encoded))
        commands.append((["xsel", "--clipboard", "--input"], encoded))

    failures: List[str] = []
    tried: set[str] = set()
    for cmd, payload in commands:
        name = cmd[0]
        if name in tried:
            continue
        tried.add(name)
        if shutil.which(name) is None:
            continue
        try:
            subprocess.run(cmd, input=payload, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return name
        except Exception as exc:
            failures.append(f"{name}: {exc}")
    detail = "; ".join(failures) if failures else "no clipboard command found"
    raise CursorCopyError(
        "could not copy to clipboard (" + detail + "). Re-run with --print or install pbcopy/wl-copy/xclip/xsel/clip."
    )
