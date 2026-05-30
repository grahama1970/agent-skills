"""Platform clipboard helpers."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Dict, Iterator, List, Tuple

from ccopy.errors import CursorCopyError

_CLIPBOARD_TIMEOUT_S = 2.0


def _linux_env_candidates() -> Iterator[Dict[str, str]]:
    """Yield env overlays for clipboard tools when the shell lacks session vars."""
    seen: set[tuple[tuple[str, str], ...]] = set()

    def emit(env: Dict[str, str]) -> Iterator[Dict[str, str]]:
        key = tuple(sorted(env.items()))
        if key in seen:
            return
        seen.add(key)
        yield dict(env)

    yield from emit(dict(os.environ))

    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return

    uid = os.getuid()
    for candidate in (":0", ":1"):
        env = dict(os.environ)
        env["DISPLAY"] = candidate
        yield from emit(env)

    wayland_path = f"/run/user/{uid}/wayland-0"
    if os.path.exists(wayland_path):
        env = dict(os.environ)
        env["WAYLAND_DISPLAY"] = "wayland-0"
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        yield from emit(env)


def _command_specs() -> List[Tuple[str, List[str]]]:
    system = platform.system()
    specs: List[Tuple[str, List[str]]] = []
    if system == "Darwin":
        specs.append(("pbcopy", ["pbcopy"]))
    elif system == "Windows":
        specs.append(("clip", ["clip"]))
    else:
        if os.environ.get("WSL_DISTRO_NAME") or "microsoft" in platform.release().lower():
            specs.append(("clip.exe", ["clip.exe"]))
        prefer_x11 = os.environ.get("XDG_SESSION_TYPE") == "x11" or bool(os.environ.get("DISPLAY"))
        prefer_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
        x11_cmds = [
            ("xclip", ["xclip", "-selection", "clipboard"]),
            ("xsel", ["xsel", "--clipboard", "--input"]),
        ]
        wayland_cmds = [("wl-copy", ["wl-copy"])]
        if prefer_wayland and not prefer_x11:
            specs.extend(wayland_cmds + x11_cmds)
        else:
            specs.extend(x11_cmds + wayland_cmds)
    return specs


def _display_hint(env: Dict[str, str]) -> str:
    parts = []
    if env.get("DISPLAY"):
        parts.append(f"DISPLAY={env['DISPLAY']}")
    if env.get("WAYLAND_DISPLAY"):
        parts.append(f"WAYLAND_DISPLAY={env['WAYLAND_DISPLAY']}")
    return f" ({', '.join(parts)})" if parts else " (no session display)"


def _run_clipboard(cmd: List[str], payload: bytes, env: Dict[str, str]) -> None:
    proc = subprocess.run(
        cmd,
        input=payload,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
        timeout=_CLIPBOARD_TIMEOUT_S,
    )
    if proc.returncode == 0:
        return
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    hint = err or f"exit status {proc.returncode}"
    raise RuntimeError(hint)


def copy_to_clipboard(text: str) -> str:
    encoded = text.encode("utf-8")
    system = platform.system()
    failures: List[str] = []
    env_iter: Iterator[Dict[str, str]]
    if system in ("Darwin", "Windows"):
        env_iter = iter([dict(os.environ)])
    else:
        env_iter = _linux_env_candidates()

    for env in env_iter:
        for name, cmd in _command_specs():
            if shutil.which(cmd[0]) is None:
                continue
            hint = _display_hint(env) if system not in ("Darwin", "Windows") else ""
            try:
                _run_clipboard(cmd, encoded, env)
                return f"{name}{hint}".strip()
            except Exception as exc:
                failures.append(f"{name}{hint}: {exc}")

    detail = "; ".join(failures) if failures else "no clipboard command found"
    raise CursorCopyError(
        "could not copy to clipboard ("
        + detail
        + "). Agent/headless shells often lack DISPLAY; use --print, run from a "
        + "terminal on your desktop session, or set DISPLAY=:0. "
        + "Install pbcopy/wl-copy/xclip/xsel/clip if missing."
    )
