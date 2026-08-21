"""OS-level pointer replay for Surf pointer plans.

This module deliberately only replays an already-authorized pointer plan. It
does not detect, solve, or classify CAPTCHA challenges.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


SUPPORTED_EVENTS = {"mouseMoved", "mousePressed", "mouseReleased"}
SUPPORTED_BACKENDS = {"auto", "uinput", "xdotool"}


class PointerDispatchError(ValueError):
    """Raised when an OS pointer replay request is invalid or unavailable."""


@dataclass(frozen=True)
class WindowContext:
    """Screen mapping context for viewport CSS coordinates."""

    origin_x: int
    origin_y: int
    device_pixel_ratio: float
    source: str
    window_id: str | None = None
    width: int | None = None
    height: int | None = None


Runner = Callable[[list[str], int], subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]


def default_runner(args: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str]:
    """Run one OS input command with a short timeout."""

    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise PointerDispatchError(f"OS pointer command timed out: {' '.join(args)}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise PointerDispatchError(f"OS pointer command failed: {' '.join(args)}{detail}") from exc


def load_plan(path: Path) -> dict[str, Any]:
    """Load a pointer plan JSON object."""

    with path.expanduser().resolve().open("r", encoding="utf-8") as handle:
        plan = json.load(handle)
    if not isinstance(plan, dict):
        raise PointerDispatchError("pointer plan must be a JSON object")
    if not isinstance(plan.get("samples"), list):
        raise PointerDispatchError("pointer plan must contain a samples array")
    return plan


def plan_sha256(path: str | None) -> str | None:
    """Return the plan file sha256 when a source path exists."""

    if not path:
        return None
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def select_backend(backend: str, *, dry_run: bool) -> str:
    """Select an OS pointer backend.

    uinput is preferred only when it is importable and writable. xdotool is the
    fallback and is also used for dry-run receipts so CI can prove coordinate
    mapping without moving the local pointer.
    """

    if backend not in SUPPORTED_BACKENDS:
        raise PointerDispatchError(
            f"unsupported pointer dispatch backend: {backend}; expected auto, uinput, or xdotool"
        )
    if backend == "uinput":
        if dry_run or _uinput_available():
            return "uinput"
        raise PointerDispatchError("uinput backend is unavailable or /dev/uinput is not writable")
    if backend == "xdotool":
        if dry_run or shutil.which("xdotool"):
            return "xdotool"
        raise PointerDispatchError("xdotool backend is unavailable on PATH")
    if _uinput_available():
        return "uinput"
    if dry_run or shutil.which("xdotool"):
        return "xdotool"
    raise PointerDispatchError("no OS pointer backend available; install xdotool or configure uinput")


def _uinput_available() -> bool:
    try:
        import uinput  # noqa: F401
    except ImportError:
        return False
    return os.access("/dev/uinput", os.W_OK)


def resolve_window_context(
    plan: dict[str, Any],
    *,
    backend: str,
    dry_run: bool,
    window_id: str | None = None,
    window_origin_x: int | None = None,
    window_origin_y: int | None = None,
    device_pixel_ratio: float | None = None,
    runner: Runner = default_runner,
) -> WindowContext:
    """Resolve viewport CSS to screen-pixel mapping context."""

    dpr = _resolve_dpr(plan, device_pixel_ratio)
    if window_origin_x is not None or window_origin_y is not None:
        if window_origin_x is None or window_origin_y is None:
            raise PointerDispatchError("window origin override requires both x and y")
        return WindowContext(
            origin_x=int(window_origin_x),
            origin_y=int(window_origin_y),
            device_pixel_ratio=dpr,
            source="explicit",
            window_id=window_id,
        )

    if dry_run:
        raise PointerDispatchError("dry-run OS dispatch requires explicit --window-origin-x and --window-origin-y")
    if backend != "xdotool":
        raise PointerDispatchError("automatic window geometry currently requires the xdotool backend")

    resolved_window_id = window_id or _active_window_id(runner)
    geometry = _xdotool_window_geometry(resolved_window_id, runner)
    return WindowContext(
        origin_x=geometry["X"],
        origin_y=geometry["Y"],
        device_pixel_ratio=dpr,
        source="xdotool.getwindowgeometry",
        window_id=resolved_window_id,
        width=geometry.get("WIDTH"),
        height=geometry.get("HEIGHT"),
    )


def _resolve_dpr(plan: dict[str, Any], device_pixel_ratio: float | None) -> float:
    value = device_pixel_ratio
    if value is None:
        value = plan.get("device_pixel_ratio") or plan.get("deviceScaleFactor") or 1.0
    try:
        dpr = float(value)
    except (TypeError, ValueError) as exc:
        raise PointerDispatchError(f"invalid device pixel ratio: {value}") from exc
    if dpr <= 0:
        raise PointerDispatchError("device pixel ratio must be positive")
    return dpr


def _active_window_id(runner: Runner) -> str:
    proc = runner(["xdotool", "getactivewindow"], 5)
    window_id = proc.stdout.strip()
    if not window_id:
        raise PointerDispatchError("xdotool did not return an active window id")
    return window_id


def _xdotool_window_geometry(window_id: str, runner: Runner) -> dict[str, int]:
    proc = runner(["xdotool", "getwindowgeometry", "--shell", window_id], 5)
    values: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        if key in {"X", "Y", "WIDTH", "HEIGHT"}:
            values[key] = int(raw)
    if "X" not in values or "Y" not in values:
        raise PointerDispatchError("xdotool geometry output did not include X and Y")
    return values


def map_samples_to_screen(samples: list[dict[str, Any]], context: WindowContext) -> list[dict[str, Any]]:
    """Validate and map viewport CSS samples to screen-pixel samples."""

    if not samples:
        raise PointerDispatchError("pointer dispatch requires at least one sample")

    mapped = []
    previous_time = 0
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise PointerDispatchError(f"pointer sample at index {index} must be an object")
        event = sample.get("event")
        if event not in SUPPORTED_EVENTS:
            raise PointerDispatchError(f"unsupported pointer event at index {index}: {event}")
        x_css = _sample_coordinate(sample, "x_css", "x")
        y_css = _sample_coordinate(sample, "y_css", "y")
        current_time = int(sample.get("time_ms", previous_time))
        delay_ms = max(0, current_time - previous_time)
        previous_time = current_time
        mapped.append(
            {
                "index": index,
                "event": event,
                "time_ms": current_time,
                "delay_ms": delay_ms,
                "x_css": x_css,
                "y_css": y_css,
                "screen_x": context.origin_x + round(x_css * context.device_pixel_ratio),
                "screen_y": context.origin_y + round(y_css * context.device_pixel_ratio),
            }
        )
    return mapped


def _sample_coordinate(sample: dict[str, Any], primary: str, fallback: str) -> float:
    value = sample.get(primary, sample.get(fallback))
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PointerDispatchError(f"pointer sample missing numeric {primary}") from exc


def dispatch_os_pointer_plan(
    plan: dict[str, Any],
    *,
    source_path: str | None = None,
    backend: str = "auto",
    dry_run: bool = False,
    window_id: str | None = None,
    window_origin_x: int | None = None,
    window_origin_y: int | None = None,
    device_pixel_ratio: float | None = None,
    runner: Runner = default_runner,
    sleeper: Sleeper = time.sleep,
) -> dict[str, Any]:
    """Replay a pointer plan through an OS-level input backend."""

    selected_backend = select_backend(backend, dry_run=dry_run)
    context = resolve_window_context(
        plan,
        backend=selected_backend,
        dry_run=dry_run,
        window_id=window_id,
        window_origin_x=window_origin_x,
        window_origin_y=window_origin_y,
        device_pixel_ratio=device_pixel_ratio,
        runner=runner,
    )
    events = map_samples_to_screen(plan["samples"], context)

    if not dry_run:
        if selected_backend == "xdotool":
            _dispatch_xdotool(events, runner=runner, sleeper=sleeper)
        else:
            _dispatch_uinput(events, sleeper=sleeper)

    return {
        "schema_version": "surf.pointer_dispatch_receipt.v1",
        "success": True,
        "transport_selected": "os",
        "backend": selected_backend,
        "dry_run": dry_run,
        "source_path": source_path,
        "source_sha256": plan_sha256(source_path),
        "sample_count": len(events),
        "coordinate_mapping": {
            "input": "viewport_css_px",
            "output": "screen_px",
            "window_origin_screen_px": {"x": context.origin_x, "y": context.origin_y},
            "device_pixel_ratio": context.device_pixel_ratio,
            "source": context.source,
            "window_id": context.window_id,
            "window_size_screen_px": (
                {"width": context.width, "height": context.height}
                if context.width is not None and context.height is not None
                else None
            ),
        },
        "events": events,
        "proof_boundary": {
            "dispatch_only": True,
            "post_observation_required": True,
            "does_not_prove_challenge_solved": True,
            "does_not_choose_target_coordinates": True,
        },
    }


def _dispatch_xdotool(events: list[dict[str, Any]], *, runner: Runner, sleeper: Sleeper) -> None:
    for event in events:
        if event["delay_ms"]:
            sleeper(event["delay_ms"] / 1000.0)
        runner(["xdotool", "mousemove", str(event["screen_x"]), str(event["screen_y"])], 5)
        if event["event"] == "mousePressed":
            runner(["xdotool", "mousedown", "1"], 5)
        elif event["event"] == "mouseReleased":
            runner(["xdotool", "mouseup", "1"], 5)


def _dispatch_uinput(events: list[dict[str, Any]], *, sleeper: Sleeper) -> None:
    import uinput

    max_x = max(event["screen_x"] for event in events) + 1
    max_y = max(event["screen_y"] for event in events) + 1
    device = uinput.Device(
        [
            uinput.ABS_X + (0, max_x, 0, 0),
            uinput.ABS_Y + (0, max_y, 0, 0),
            uinput.BTN_LEFT,
        ]
    )
    for event in events:
        if event["delay_ms"]:
            sleeper(event["delay_ms"] / 1000.0)
        device.emit(uinput.ABS_X, event["screen_x"], syn=False)
        device.emit(uinput.ABS_Y, event["screen_y"])
        if event["event"] == "mousePressed":
            device.emit(uinput.BTN_LEFT, 1)
        elif event["event"] == "mouseReleased":
            device.emit(uinput.BTN_LEFT, 0)
