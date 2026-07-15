#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


@dataclass
class Cluster:
    x1: int
    y1: int
    x2: int
    y2: int
    area: int

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2


def run(
    cmd: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
    )


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def clipboard_text() -> str:
    proc = run(["xclip", "-selection", "clipboard", "-o"], check=False, timeout=3)
    return proc.stdout if proc.returncode == 0 else ""


def set_clipboard_text(text: str) -> None:
    proc = subprocess.Popen(
        ["xclip", "-selection", "clipboard", "-i"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    assert proc.stdin is not None
    proc.stdin.write(text)
    proc.stdin.close()
    # xclip commonly stays alive as the X selection owner. Do not wait for it
    # to exit; just give X11 a moment to publish the new clipboard contents.
    time.sleep(0.2)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if clipboard_text() == text:
            return
        time.sleep(0.1)
    raise SystemExit("Clipboard did not publish the intended prompt text")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def normalize_ocr_text(text: str) -> str:
    text = text.upper()
    replacements = {
        "|": "I",
        "$": "S",
        "_": " ",
        "\u2014": " ",
        "\u2013": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_expected_text(raw_text: str, expected: str) -> bool:
    return normalize_ocr_text(expected) in normalize_ocr_text(raw_text)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def mouse_position() -> tuple[int, int]:
    proc = run(["xdotool", "getmouselocation", "--shell"], timeout=3)
    values: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key in {"X", "Y"}:
            values[key] = int(value)
    return values["X"], values["Y"]


def wait_for_pointer_idle(idle_seconds: float, timeout: float) -> None:
    if idle_seconds <= 0:
        return
    start = time.time()
    last_pos = mouse_position()
    stable_since = time.time()
    while time.time() - start <= timeout:
        time.sleep(0.1)
        current = mouse_position()
        now = time.time()
        if current == last_pos:
            if now - stable_since >= idle_seconds:
                return
        else:
            last_pos = current
            stable_since = now
    raise SystemExit(f"Pointer was not idle for {idle_seconds:.1f}s within {timeout:.1f}s")


def window_geometry(window_id: str) -> dict[str, int]:
    proc = run(["xdotool", "getwindowgeometry", "--shell", window_id], timeout=5)
    values: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key in {"X", "Y", "WIDTH", "HEIGHT"}:
            values[key] = int(value)
    for required in ("X", "Y", "WIDTH", "HEIGHT"):
        if required not in values:
            raise SystemExit(f"Could not read window geometry field {required} for {window_id}")
    return values


def wmctrl_window_info(window_id: str) -> dict[str, object]:
    decimal_id = int(window_id, 0)
    hex_id = f"0x{decimal_id:08x}"
    proc = run(["wmctrl", "-lxG"], check=False, timeout=5)
    for line in proc.stdout.splitlines():
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        wid = parts[0]
        if wid.lower() != hex_id.lower():
            continue
        return {
            "id": wid,
            "desktop": int(parts[1]),
            "x": int(parts[2]),
            "y": int(parts[3]),
            "width": int(parts[4]),
            "height": int(parts[5]),
            "wm_class": parts[6],
            "title": parts[7],
            "is_chrome": "chrome" in parts[6].lower(),
        }
    raise SystemExit(f"Window id {window_id} was not found by wmctrl")


def xdotool_mouse(args: argparse.Namespace, window_id: str, x: int, y: int, *extra: str) -> dict[str, object]:
    wait_for_pointer_idle(args.pointer_idle_seconds, args.pointer_idle_timeout)
    restore_pos = mouse_position()
    geometry = window_geometry(window_id)
    abs_x = geometry["X"] + x
    abs_y = geometry["Y"] + y
    run(["xdotool", "mousemove", "--sync", str(abs_x), str(abs_y), *extra], timeout=5)
    if extra:
        run(["xdotool", "mousemove", "--sync", str(restore_pos[0]), str(restore_pos[1])], timeout=5)
    final_pos = mouse_position()
    return {
        "window_id": window_id,
        "window_geometry": geometry,
        "local": {"x": x, "y": y},
        "absolute": {"x": abs_x, "y": abs_y},
        "pointer_restore_before": {"x": restore_pos[0], "y": restore_pos[1]},
        "pointer_after": {"x": final_pos[0], "y": final_pos[1]},
        "pointer_restored": final_pos == restore_pos if extra else None,
        "extra": list(extra),
        "pointer_idle_seconds": args.pointer_idle_seconds,
    }


def xdotool_scroll(
    args: argparse.Namespace,
    window_id: str,
    x: int,
    y: int,
    *,
    button: str = "5",
    clicks: int = 1,
) -> dict[str, object]:
    wait_for_pointer_idle(args.pointer_idle_seconds, args.pointer_idle_timeout)
    restore_pos = mouse_position()
    geometry = window_geometry(window_id)
    abs_x = geometry["X"] + x
    abs_y = geometry["Y"] + y
    run(["xdotool", "mousemove", "--sync", str(abs_x), str(abs_y)], timeout=5)
    for _idx in range(max(0, clicks)):
        run(["xdotool", "click", button], timeout=5)
        time.sleep(0.03)
    run(["xdotool", "mousemove", "--sync", str(restore_pos[0]), str(restore_pos[1])], timeout=5)
    final_pos = mouse_position()
    return {
        "window_id": window_id,
        "window_geometry": geometry,
        "local": {"x": x, "y": y},
        "absolute": {"x": abs_x, "y": abs_y},
        "button": button,
        "clicks": max(0, clicks),
        "pointer_restore_before": {"x": restore_pos[0], "y": restore_pos[1]},
        "pointer_after": {"x": final_pos[0], "y": final_pos[1]},
        "pointer_restored": final_pos == restore_pos,
        "pointer_idle_seconds": args.pointer_idle_seconds,
    }


def xdotool_key(args: argparse.Namespace, *keys: str) -> dict[str, object]:
    wait_for_pointer_idle(args.pointer_idle_seconds, args.pointer_idle_timeout)
    before = mouse_position()
    run(["xdotool", "key", "--clearmodifiers", *keys], timeout=5)
    after = mouse_position()
    return {
        "keys": list(keys),
        "pointer_before": {"x": before[0], "y": before[1]},
        "pointer_after": {"x": after[0], "y": after[1]},
        "pointer_unchanged": before == after,
        "pointer_idle_seconds": args.pointer_idle_seconds,
    }


def scroll_sidepanel_to_bottom(args: argparse.Namespace, window_id: str, width: int, height: int) -> dict[str, object] | None:
    if args.scroll_bottom_clicks <= 0:
        return None
    # Place the wheel over the Gemini side-panel conversation area, above the
    # composer, so wheel events affect the chat history rather than page content.
    scroll_x = width - 250
    scroll_y = int(height * 0.62)
    return xdotool_scroll(args, window_id, scroll_x, scroll_y, button="5", clicks=args.scroll_bottom_clicks)


def validate_chrome_window(window_id: str, title_regex: str) -> dict[str, object]:
    info = wmctrl_window_info(window_id)
    if not info.get("is_chrome"):
        raise SystemExit(f"Target window is not Chrome: {info}")
    if title_regex and not re.search(title_regex, str(info.get("title", "")), re.I):
        raise SystemExit(f"Target Chrome title did not match {title_regex!r}: {info.get('title')}")
    return info


def find_window(title_regex: str) -> str:
    proc = run(["wmctrl", "-lxG"])
    pattern = re.compile(title_regex, re.I)
    matches: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        wid, title = parts[0], parts[7]
        wm_class = parts[6]
        if "chrome" not in wm_class.lower():
            continue
        if pattern.search(title):
            matches.append((wid, title))
    if not matches:
        raise SystemExit(f"No visible Chrome window matched title regex: {title_regex}")
    if len(matches) > 1:
        details = "\n".join(f"  {wid} {title}" for wid, title in matches)
        raise SystemExit(f"Multiple Chrome windows matched title regex; pass --window-id:\n{details}")
    return matches[0][0]


def capture_window(window_id: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(["import", "-window", window_id, str(output)], timeout=8)


def icon_clusters(image_path: Path) -> tuple[list[Cluster], dict[str, int]]:
    image = np.array(Image.open(image_path).convert("RGB"))
    height, width = image.shape[:2]
    # Chrome's built-in Gemini panel is docked at the right edge. Keep this
    # constrained so text in the page content does not become an icon candidate.
    x_min = int(width * 0.80)
    y_min = int(height * 0.05)
    y_max = int(height * 0.88)
    crop = image[y_min:y_max, x_min:width]

    mx = crop.max(axis=2)
    mn = crop.min(axis=2)
    # Gemini action icons are neutral light gray on a dark panel. This excludes
    # the blue send button and most colored page content.
    mask = ((mx > 120) & ((mx - mn) < 70)).astype("uint8") * 255
    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    clusters: list[Cluster] = []
    for idx in range(1, count):
        x, y, w, h, area = [int(v) for v in stats[idx]]
        if not (5 <= w <= 42 and 5 <= h <= 34 and 25 <= area <= 450):
            continue
        clusters.append(Cluster(x + x_min, y + y_min, x + x_min + w, y + y_min + h, area))
    return clusters, {"width": width, "height": height, "x_min": x_min, "y_min": y_min, "y_max": y_max}


def group_action_rows(clusters: list[Cluster]) -> list[list[Cluster]]:
    rows: list[list[Cluster]] = []
    for cluster in sorted(clusters, key=lambda c: c.cy):
        for row in rows:
            if abs(cluster.cy - np.mean([c.cy for c in row])) <= 14:
                row.append(cluster)
                break
        else:
            rows.append([cluster])

    grouped: list[list[Cluster]] = []
    for row in rows:
        row = sorted(row, key=lambda c: c.cx)
        merged: list[Cluster] = []
        for item in row:
            if merged and item.x1 - merged[-1].x2 <= 16:
                prev = merged[-1]
                merged[-1] = Cluster(
                    min(prev.x1, item.x1),
                    min(prev.y1, item.y1),
                    max(prev.x2, item.x2),
                    max(prev.y2, item.y2),
                    prev.area + item.area,
                )
            else:
                merged.append(item)
        if len(merged) >= 4:
            grouped.append(merged)
    return grouped


def locate_copy_icon(image_path: Path, *, min_y: int = 0) -> tuple[Cluster, dict[str, object]]:
    clusters, crop_meta = icon_clusters(image_path)
    rows = group_action_rows(clusters)
    candidates: list[list[Cluster]] = []
    for row in rows:
        span = row[-1].x2 - row[0].x1
        mean_height = float(np.mean([c.y2 - c.y1 for c in row]))
        row_y = float(np.mean([c.cy for c in row]))
        if row_y >= min_y and 4 <= len(row) <= 7 and 80 <= span <= 280 and 10 <= mean_height <= 30:
            candidates.append(row)
    if not candidates:
        raise SystemExit("Could not detect a Gemini action row with at least four icon clusters")

    # Prefer the lowest compact action row above the prompt composer. Text rows
    # are wider and contain many more glyph clusters than Gemini's icon row.
    row = sorted(candidates, key=lambda r: np.mean([c.cy for c in r]))[-1]
    row = sorted(row, key=lambda c: c.cx)
    if len(row) < 4:
        raise SystemExit("Detected action row has fewer than four controls")
    target = row[3]
    return target, {
        "crop": crop_meta,
        "cluster_count": len(clusters),
        "candidate_rows": [[c.__dict__ for c in r] for r in candidates],
        "selected_index": 3,
        "selected": target.__dict__,
    }


def annotate(image_path: Path, target: Cluster, output: Path) -> None:
    image = cv2.imread(str(image_path))
    if image is None:
        return
    cv2.rectangle(image, (target.x1 - 8, target.y1 - 8), (target.x2 + 8, target.y2 + 8), (0, 255, 0), 3)
    cv2.circle(image, (int(target.cx), int(target.cy)), 8, (0, 255, 0), 2)
    cv2.imwrite(str(output), image)


def ocr_sidepanel_response(image_path: Path, output_dir: Path) -> tuple[str, dict[str, str]]:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    crop_box = (int(width * 0.82), int(height * 0.12), width - 20, int(height * 0.78))
    crop = image.crop(crop_box)
    crop_path = output_dir / "response-ocr-crop.png"
    scaled_path = output_dir / "response-ocr-crop-scaled.png"
    text_path = output_dir / "response.ocr.txt"
    crop.save(crop_path)
    gray = crop.convert("L").resize((crop.width * 3, crop.height * 3))
    gray.save(scaled_path)
    proc = run(["tesseract", str(scaled_path), "stdout", "--psm", "6"], check=False, timeout=15)
    text = proc.stdout.strip()
    text_path.write_text(text + ("\n" if text else ""))
    return text, {
        "crop": str(crop_path),
        "scaled_crop": str(scaled_path),
        "text": str(text_path),
        "stderr": proc.stderr,
    }


def ocr_answer_near_action_row(image_path: Path, target: Cluster, output_dir: Path) -> tuple[str, dict[str, str]]:
    image = Image.open(image_path).convert("RGB")
    width, _height = image.size
    crop_box = (
        int(width * 0.82),
        max(0, target.y1 - 180),
        width - 20,
        max(1, target.y1 - 18),
    )
    crop = image.crop(crop_box)
    crop_path = output_dir / "answer-ocr-crop.png"
    scaled_path = output_dir / "answer-ocr-crop-scaled.png"
    text_path = output_dir / "answer.ocr.txt"
    crop.save(crop_path)
    gray = crop.convert("L").resize((crop.width * 4, crop.height * 4))
    gray.save(scaled_path)
    proc = run(["tesseract", str(scaled_path), "stdout", "--psm", "6"], check=False, timeout=15)
    text = proc.stdout.strip()
    text_path.write_text(text + ("\n" if text else ""))
    return text, {
        "crop": str(crop_path),
        "scaled_crop": str(scaled_path),
        "text": str(text_path),
        "stderr": proc.stderr,
    }


def ocr_composer_region(image_path: Path, output_dir: Path, expected_response: str | None = None) -> dict[str, object]:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    crop_box = (int(width * 0.82), int(height * 0.78), width - 20, height - 20)
    result = run_tesseract_crop(image, crop_box, output_dir, "after-paste.composer")
    result["expected_response"] = expected_response
    result["expected_match"] = bool(expected_response and contains_expected_text(str(result["raw_text"]), expected_response))
    return result


def run_tesseract_crop(image: Image.Image, crop_box: tuple[int, int, int, int], output_dir: Path, stem: str) -> dict[str, object]:
    crop = image.crop(crop_box)
    crop_path = output_dir / f"{stem}.png"
    scaled_path = output_dir / f"{stem}.scaled.png"
    text_path = output_dir / f"{stem}.ocr.txt"
    normalized_path = output_dir / f"{stem}.normalized.txt"
    crop.save(crop_path)
    scaled = crop.convert("L").resize((max(1, crop.width * 3), max(1, crop.height * 3)))
    scaled.save(scaled_path)
    proc = run(["tesseract", str(scaled_path), "stdout", "--psm", "6"], check=False, timeout=15)
    raw_text = proc.stdout.strip()
    normalized = normalize_ocr_text(raw_text)
    text_path.write_text(raw_text + ("\n" if raw_text else ""))
    normalized_path.write_text(normalized + ("\n" if normalized else ""))
    return {
        "stem": stem,
        "crop_box": list(crop_box),
        "crop": str(crop_path),
        "scaled_crop": str(scaled_path),
        "text": str(text_path),
        "normalized_text": str(normalized_path),
        "raw_text": raw_text,
        "normalized": normalized,
        "stderr": proc.stderr,
    }


def assistant_response_boxes(
    width: int,
    height: int,
    min_y: int,
    target: Cluster | None,
) -> list[tuple[str, tuple[int, int, int, int], bool]]:
    side_x1 = int(width * 0.82)
    side_x2 = width - 20
    boxes: list[tuple[str, tuple[int, int, int, int], bool]] = [
        # Diagnostic only. This crop can include the user's prompt bubble, so it
        # must not be used as expected-response proof.
        ("right-panel", (side_x1, int(height * 0.10), side_x2, int(height * 0.88)), False),
        ("assistant-band", (side_x1, min_y, side_x2, int(height * 0.48)), True),
        ("new-response", (side_x1, max(0, min_y - 40), side_x2, int(height * 0.66)), True),
    ]
    if target is not None:
        boxes.extend(
            [
                (
                    "near-action-row",
                    (side_x1, max(0, target.y1 - 220), side_x2, max(1, target.y1 - 18)),
                    True,
                ),
                (
                    "answer-line",
                    (side_x1, max(0, target.y1 - 96), side_x2, max(1, target.y1 - 38)),
                    True,
                ),
            ]
        )
    return boxes


def extract_response_ocr(
    image_path: Path,
    output_dir: Path,
    attempt: int,
    *,
    min_y: int,
    expected_response: str | None = None,
    target: Cluster | None = None,
) -> dict[str, object]:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    candidate_boxes = assistant_response_boxes(width, height, min_y, target)

    candidates = [
        {
            **run_tesseract_crop(image, box, output_dir, f"poll-{attempt:03d}.{name}"),
            "eligible_for_expected_match": eligible,
        }
        for name, box, eligible in candidate_boxes
    ]
    expected_match = False
    accepted = None
    if expected_response:
        for candidate in candidates:
            if candidate.get("eligible_for_expected_match") and contains_expected_text(str(candidate["raw_text"]), expected_response):
                expected_match = True
                accepted = candidate
                break
    else:
        accepted = max(candidates, key=lambda c: len(str(c["normalized"])), default=None)

    return {
        "source": "ocr_primary",
        "image": str(image_path),
        "expected_response": expected_response,
        "expected_normalized": normalize_ocr_text(expected_response or ""),
        "expected_match": expected_match,
        "accepted": accepted,
        "candidates": candidates,
    }


def annotate_crop(image_path: Path, crop_box: list[int], output: Path) -> None:
    image = cv2.imread(str(image_path))
    if image is None:
        return
    x1, y1, x2, y2 = [int(v) for v in crop_box]
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 3)
    cv2.imwrite(str(output), image)


def click_copy(args: argparse.Namespace) -> int:
    window_id = args.window_id or find_window(args.title_regex)
    window_info = validate_chrome_window(window_id, args.title_regex)
    out_dir = Path(args.output_dir or f"/tmp/surf-gemini-sidepanel-{utc_stamp()}")
    out_dir.mkdir(parents=True, exist_ok=True)

    before_shot = out_dir / "before.png"
    pre_scroll_shot = out_dir / "pre-scroll.png"
    annotated = out_dir / "before.annotated.png"
    after_shot = out_dir / "after.png"
    response_path = Path(args.response_output) if args.response_output else out_dir / "clipboard.txt"
    meta_path = Path(args.meta_output) if args.meta_output else out_dir / "meta.json"

    clip_before = clipboard_text()
    capture_window(window_id, pre_scroll_shot)
    width, height = window_size(pre_scroll_shot)
    run(["xdotool", "windowactivate", "--sync", window_id], timeout=5)
    scroll_event = scroll_sidepanel_to_bottom(args, window_id, width, height)
    if scroll_event:
        time.sleep(0.2)
    capture_window(window_id, before_shot)
    target, detection = locate_copy_icon(before_shot)
    annotate(before_shot, target, annotated)

    if not args.dry_run:
        click_event = xdotool_mouse(args, window_id, int(target.cx), int(target.cy), "click", "1")
        time.sleep(args.wait)
    else:
        click_event = None

    clip_after = clipboard_text()
    capture_window(window_id, after_shot)
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(clip_after)
    changed = sha256_text(clip_before) != sha256_text(clip_after)
    ocr_text = ""
    ocr_meta = None
    if args.ocr_fallback:
        ocr_text, ocr_meta = ocr_answer_near_action_row(after_shot, target, out_dir)
        if not changed and ocr_text:
            response_path.write_text(ocr_text + "\n")

    meta = {
        "status": "dry_run" if args.dry_run else (
            "completed" if changed and clip_after else (
                "ocr_fallback_completed" if args.ocr_fallback and ocr_text else "clipboard_unchanged"
            )
        ),
        "mocked": False,
        "live": True,
        "window_id": window_id,
        "window_info": window_info,
        "title_regex": args.title_regex,
        "clicked": None if args.dry_run else {"x": int(target.cx), "y": int(target.cy)},
        "scroll_to_bottom_event": scroll_event,
        "click_event": click_event,
        "clipboard_before_chars": len(clip_before),
        "clipboard_after_chars": len(clip_after),
        "clipboard_before_sha256": sha256_text(clip_before),
        "clipboard_after_sha256": sha256_text(clip_after),
        "clipboard_changed": changed,
        "ocr_fallback_used": bool(args.ocr_fallback and not changed and ocr_text),
        "pre_scroll_screenshot": str(pre_scroll_shot),
        "before_screenshot": str(before_shot),
        "annotated_screenshot": str(annotated),
        "after_screenshot": str(after_shot),
        "response_output": str(response_path),
        "ocr": ocr_meta,
        "detection": detection,
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    return 0 if args.dry_run or (changed and clip_after) or (args.ocr_fallback and ocr_text) else 1


def window_size(image_path: Path) -> tuple[int, int]:
    image = Image.open(image_path)
    return image.size


def submit_and_copy(args: argparse.Namespace) -> int:
    window_id = args.window_id or find_window(args.title_regex)
    window_info = validate_chrome_window(window_id, args.title_regex)
    out_dir = Path(args.output_dir or f"/tmp/surf-gemini-sidepanel-submit-{utc_stamp()}")
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = out_dir / "prompt.txt"
    prompt_path.write_text(args.prompt)
    pre_scroll_shot = out_dir / "submit.pre-scroll.png"
    initial_shot = out_dir / "submit.before.png"
    after_paste_shot = out_dir / "submit.after-paste.png"
    capture_window(window_id, pre_scroll_shot)
    width, height = window_size(pre_scroll_shot)

    # These coordinates are intentionally window-relative and derived from the
    # captured Chrome window dimensions. The sidebar itself is outside DOM/CDP.
    composer_x = width - 430
    composer_y = height - 116
    send_x = width - 55
    send_y = height - 69
    min_new_response_y = int(height * 0.18)

    set_clipboard_text(args.prompt)
    run(["xdotool", "windowactivate", "--sync", window_id], timeout=5)
    scroll_event = scroll_sidepanel_to_bottom(args, window_id, width, height)
    if scroll_event:
        time.sleep(0.2)
    capture_window(window_id, initial_shot)
    composer_event = xdotool_mouse(args, window_id, composer_x, composer_y, "click", "1")
    time.sleep(0.2)
    select_event = xdotool_key(args, "ctrl+a")
    time.sleep(0.1)
    clear_event = xdotool_key(args, "BackSpace")
    time.sleep(0.1)
    paste_event = xdotool_key(args, "ctrl+v")
    time.sleep(0.5)
    capture_window(window_id, after_paste_shot)
    paste_ocr = ocr_composer_region(after_paste_shot, out_dir, args.expected_response)
    if args.expected_response and not paste_ocr.get("expected_match"):
        meta_path = Path(args.meta_output) if args.meta_output else out_dir / "meta.json"
        meta = {
            "status": "paste_not_proven",
            "mocked": False,
            "live": True,
            "window_id": window_id,
            "window_info": window_info,
            "title_regex": args.title_regex,
            "prompt": str(prompt_path),
            "pre_scroll_screenshot": str(pre_scroll_shot),
            "submit_before_screenshot": str(initial_shot),
            "after_paste_screenshot": str(after_paste_shot),
            "scroll_to_bottom_event": scroll_event,
            "composer_click": {"x": composer_x, "y": composer_y},
            "composer_click_event": composer_event,
            "select_event": select_event,
            "clear_event": clear_event,
            "paste_event": paste_event,
            "expected_response": args.expected_response,
            "paste_ocr": paste_ocr,
            "claims": {
                "proves": "The script did not send the prompt because the after-paste screenshot/OCR did not show the expected response token in the visible Gemini composer region.",
                "does_not_prove": "No Gemini response or copy action was attempted for this failed turn.",
            },
        }
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
        print(json.dumps(meta, indent=2))
        return 1
    send_event = xdotool_mouse(args, window_id, send_x, send_y, "click", "1")

    copy_meta = None
    last_error = ""
    last_ocr = None
    stable_seen = 0
    previous_normalized = ""
    deadline = time.time() + args.timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        time.sleep(args.poll_interval)
        poll_shot = out_dir / f"poll-{attempt:03d}.png"
        capture_window(window_id, poll_shot)
        target = None
        try:
            target, _detection = locate_copy_icon(poll_shot, min_y=min_new_response_y)
        except SystemExit as exc:
            last_error = str(exc)
        annotated = out_dir / f"poll-{attempt:03d}.annotated.png"
        if target is not None:
            annotate(poll_shot, target, annotated)

        if args.ocr_primary:
            last_ocr = extract_response_ocr(
                poll_shot,
                out_dir,
                attempt,
                min_y=min_new_response_y,
                expected_response=args.expected_response,
                target=target,
            )
            accepted = last_ocr.get("accepted") if isinstance(last_ocr, dict) else None
            normalized = str(accepted.get("normalized", "")) if isinstance(accepted, dict) else ""
            if normalized and normalized == previous_normalized:
                stable_seen += 1
            elif normalized:
                stable_seen = 1
                previous_normalized = normalized
            else:
                stable_seen = 0
                previous_normalized = ""

            expected_match = bool(last_ocr.get("expected_match")) if isinstance(last_ocr, dict) else False
            stable_ok = bool(normalized and stable_seen >= args.stable_polls and not args.expected_response)
            if expected_match or stable_ok:
                response_path = Path(args.response_output) if args.response_output else out_dir / "response.md"
                normalized_path = out_dir / "response.normalized.txt"
                response_path.parent.mkdir(parents=True, exist_ok=True)
                raw_text = str(accepted.get("raw_text", "")) if isinstance(accepted, dict) else ""
                response_path.write_text(raw_text + ("\n" if raw_text else ""))
                normalized_path.write_text(normalized + ("\n" if normalized else ""))
                accepted_annotated = out_dir / "accepted-response.annotated.png"
                crop_box = accepted.get("crop_box") if isinstance(accepted, dict) else None
                if isinstance(crop_box, list):
                    annotate_crop(poll_shot, crop_box, accepted_annotated)
                copy_meta = {
                    "attempt": attempt,
                    "source": "ocr_primary",
                    "ocr_primary_used": True,
                    "expected_match": expected_match,
                    "stable_polls_required": args.stable_polls,
                    "stable_polls_observed": stable_seen,
                    "copy_screenshot": str(poll_shot),
                    "copy_annotated_screenshot": str(annotated) if target is not None else None,
                    "accepted_response_annotated": str(accepted_annotated) if accepted_annotated.exists() else None,
                    "response_output": str(response_path),
                    "normalized_response_output": str(normalized_path),
                    "ocr": last_ocr,
                }
                break
            continue

        if target is None:
            continue
        before = clipboard_text()
        copy_event = xdotool_mouse(args, window_id, int(target.cx), int(target.cy), "click", "1")
        time.sleep(args.wait)
        after = clipboard_text()
        clipboard_expected_match = bool(args.expected_response and contains_expected_text(after, args.expected_response))
        if after and sha256_text(after) != sha256_text(before) and (not args.expected_response or clipboard_expected_match):
            response_path = Path(args.response_output) if args.response_output else out_dir / "response.md"
            response_path.parent.mkdir(parents=True, exist_ok=True)
            response_path.write_text(after)
            copy_meta = {
                "attempt": attempt,
                "clicked": {"x": int(target.cx), "y": int(target.cy)},
                "click_event": copy_event,
                "clipboard_before_chars": len(before),
                "clipboard_after_chars": len(after),
                "clipboard_before_sha256": sha256_text(before),
                "clipboard_after_sha256": sha256_text(after),
                "clipboard_changed": True,
                "expected_response": args.expected_response,
                "expected_match": clipboard_expected_match,
                "copy_screenshot": str(poll_shot),
                "copy_annotated_screenshot": str(annotated),
                "response_output": str(response_path),
                "source": "clipboard",
            }
            break
        if args.ocr_fallback:
            ocr_text, ocr_meta = ocr_answer_near_action_row(poll_shot, target, out_dir)
            if ocr_text:
                response_path = Path(args.response_output) if args.response_output else out_dir / "response.md"
                response_path.parent.mkdir(parents=True, exist_ok=True)
                response_path.write_text(ocr_text + "\n")
                copy_meta = {
                    "attempt": attempt,
                    "clicked": {"x": int(target.cx), "y": int(target.cy)},
                    "click_event": copy_event,
                    "clipboard_before_chars": len(before),
                    "clipboard_after_chars": len(after),
                    "clipboard_before_sha256": sha256_text(before),
                    "clipboard_after_sha256": sha256_text(after),
                    "clipboard_changed": False,
                    "ocr_fallback_used": True,
                    "copy_screenshot": str(poll_shot),
                    "copy_annotated_screenshot": str(annotated),
                    "response_output": str(response_path),
                    "source": "ocr",
                    "ocr": ocr_meta,
                }
                break

    meta_path = Path(args.meta_output) if args.meta_output else out_dir / "meta.json"
    meta = {
        "status": "completed" if copy_meta else "response_not_proven",
        "mocked": False,
        "live": True,
        "window_id": window_id,
        "window_info": window_info,
        "title_regex": args.title_regex,
        "prompt": str(prompt_path),
        "pre_scroll_screenshot": str(pre_scroll_shot),
        "submit_before_screenshot": str(initial_shot),
        "after_paste_screenshot": str(after_paste_shot),
        "scroll_to_bottom_event": scroll_event,
        "composer_click": {"x": composer_x, "y": composer_y},
        "send_click": {"x": send_x, "y": send_y},
        "composer_click_event": composer_event,
        "select_event": select_event,
        "clear_event": clear_event,
        "paste_event": paste_event,
        "send_click_event": send_event,
        "paste_ocr": paste_ocr,
        "timeout": args.timeout,
        "last_error": last_error,
        "expected_response": args.expected_response,
        "expected_response_normalized": normalize_ocr_text(args.expected_response or ""),
        "ocr_primary": args.ocr_primary,
        "last_ocr": last_ocr,
        "copy": copy_meta,
        "claims": {
            "proves": "When status=completed with source=clipboard and expected_match=true, foreground OS automation submitted a prompt, dynamically located the visible Gemini side-panel copy button, clicked it, and copied the expected response text to the desktop clipboard. When source=ocr_primary, success is based on matching visible screenshot OCR instead.",
            "does_not_prove": "This is foreground desktop automation; it does not prove background/no-hijack operation or DOM/CDP access to Chrome's built-in Gemini side panel.",
        },
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    return 0 if copy_meta else 1


def paste_and_send(args: argparse.Namespace) -> int:
    window_id = args.window_id or find_window(args.title_regex)
    window_info = validate_chrome_window(window_id, args.title_regex)
    out_dir = Path(args.output_dir or f"/tmp/surf-gemini-sidepanel-send-{utc_stamp()}")
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = out_dir / "prompt.txt"
    prompt_path.write_text(args.prompt)
    pre_scroll_shot = out_dir / "pre-scroll.png"
    before_shot = out_dir / "before.png"
    after_paste_shot = out_dir / "after-paste.png"
    after_send_shot = out_dir / "after-send.png"
    meta_path = Path(args.meta_output) if args.meta_output else out_dir / "meta.json"

    capture_window(window_id, pre_scroll_shot)
    width, height = window_size(pre_scroll_shot)
    composer_x = args.composer_x if args.composer_x is not None else width - 430
    composer_y = args.composer_y if args.composer_y is not None else height - 116
    send_x = args.send_x if args.send_x is not None else width - 55
    send_y = args.send_y if args.send_y is not None else height - 69

    set_clipboard_text(args.prompt)
    run(["xdotool", "windowactivate", "--sync", window_id], timeout=5)
    scroll_event = scroll_sidepanel_to_bottom(args, window_id, width, height)
    if scroll_event:
        time.sleep(0.2)
    capture_window(window_id, before_shot)
    composer_event = xdotool_mouse(args, window_id, composer_x, composer_y, "click", "1")
    time.sleep(0.25)
    select_event = xdotool_key(args, "ctrl+a")
    paste_event = xdotool_key(args, "ctrl+v")
    time.sleep(args.after_paste_wait)
    capture_window(window_id, after_paste_shot)

    if args.no_send:
        status = "pasted_not_sent"
        send_event = None
    else:
        send_event = xdotool_mouse(args, window_id, send_x, send_y, "click", "1")
        time.sleep(args.after_send_wait)
        capture_window(window_id, after_send_shot)
        status = "sent"

    meta = {
        "status": status,
        "mocked": False,
        "live": True,
        "window_id": window_id,
        "window_info": window_info,
        "title_regex": args.title_regex,
        "prompt": str(prompt_path),
        "pre_scroll_screenshot": str(pre_scroll_shot),
        "before_screenshot": str(before_shot),
        "after_paste_screenshot": str(after_paste_shot),
        "after_send_screenshot": str(after_send_shot) if not args.no_send else None,
        "composer_click": {"x": composer_x, "y": composer_y},
        "send_click": None if args.no_send else {"x": send_x, "y": send_y},
        "scroll_to_bottom_event": scroll_event,
        "composer_click_event": composer_event,
        "select_event": select_event,
        "paste_event": paste_event,
        "send_click_event": send_event,
        "claims": {
            "proves": "Foreground OS automation pasted text into the visible Chrome Gemini side-panel composer and clicked the send button.",
            "does_not_prove": "It does not prove Gemini produced a response or that the response can be copied.",
        },
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    return 0


def submit_loop(args: argparse.Namespace) -> int:
    window_id = args.window_id or find_window(args.title_regex)
    window_info = validate_chrome_window(window_id, args.title_regex)
    out_dir = Path(args.output_dir or f"/tmp/surf-gemini-sidepanel-loop-{utc_stamp()}")
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = out_dir / "transcript.jsonl"
    summary_path = Path(args.meta_output) if args.meta_output else out_dir / "summary.json"
    run_id = args.run_id or utc_stamp()

    turns: list[dict[str, object]] = []
    transcript_path.write_text("")
    overall_status = "completed"
    failure_reason = ""

    for turn in range(1, args.turns + 1):
        expected = args.expected_template.format(turn=turn, run_id=run_id)
        prompt = args.prompt_template.format(turn=turn, run_id=run_id, expected=expected)
        turn_dir = out_dir / f"turn-{turn:02d}"
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "submit",
            "--window-id",
            window_id,
            "--title-regex",
            args.title_regex,
            "--prompt",
            prompt,
            "--expected-response",
            expected,
            "--output-dir",
            str(turn_dir),
            "--timeout",
            str(args.timeout_per_turn),
            "--poll-interval",
            str(args.poll_interval),
            "--wait",
            str(args.wait),
            "--pointer-idle-seconds",
            str(args.pointer_idle_seconds),
            "--pointer-idle-timeout",
            str(args.pointer_idle_timeout),
            "--scroll-bottom-clicks",
            str(args.scroll_bottom_clicks),
        ]
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout_per_turn + args.pointer_idle_timeout + 30,
        )
        meta_path = turn_dir / "meta.json"
        turn_meta = load_json(meta_path) if meta_path.exists() else {}
        response_path = Path(str(turn_meta.get("copy", {}).get("response_output", turn_dir / "response.md"))) if isinstance(turn_meta.get("copy"), dict) else turn_dir / "response.md"
        response_text = response_path.read_text() if response_path.exists() else ""
        copy_meta = turn_meta.get("copy") if isinstance(turn_meta.get("copy"), dict) else {}
        pointer_events = [
            turn_meta.get("scroll_to_bottom_event"),
            turn_meta.get("composer_click_event"),
            turn_meta.get("send_click_event"),
            copy_meta.get("click_event") if isinstance(copy_meta, dict) else None,
        ]
        pointer_restored = all(
            isinstance(event, dict) and event.get("pointer_restored") is True
            for event in pointer_events
        )
        keyboard_events = [
            turn_meta.get("select_event"),
            turn_meta.get("clear_event"),
            turn_meta.get("paste_event"),
        ]
        keyboard_idle_recorded = all(
            isinstance(event, dict) and event.get("pointer_unchanged") is True
            for event in keyboard_events
        )
        expected_match = bool(isinstance(copy_meta, dict) and copy_meta.get("expected_match") is True)
        paste_ocr = turn_meta.get("paste_ocr") if isinstance(turn_meta.get("paste_ocr"), dict) else {}
        paste_expected_match = bool(paste_ocr.get("expected_match") is True)
        status_ok = (
            proc.returncode == 0
            and turn_meta.get("status") == "completed"
            and expected_match
            and pointer_restored
            and keyboard_idle_recorded
            and paste_expected_match
        )
        turn_record = {
            "turn": turn,
            "status": "completed" if status_ok else "failed",
            "mocked": False,
            "live": True,
            "window_id": window_id,
            "expected": expected,
            "prompt": prompt,
            "command": cmd,
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
            "turn_dir": str(turn_dir),
            "meta": str(meta_path),
            "response_output": str(response_path),
            "response_sha256": sha256_text(response_text),
            "response_chars": len(response_text),
            "expected_match": expected_match,
            "pointer_restored": pointer_restored,
            "keyboard_idle_recorded": keyboard_idle_recorded,
            "paste_expected_match": paste_expected_match,
            "copy_source": copy_meta.get("source") if isinstance(copy_meta, dict) else None,
            "copy_screenshot": copy_meta.get("copy_screenshot") if isinstance(copy_meta, dict) else None,
            "copy_annotated_screenshot": copy_meta.get("copy_annotated_screenshot") if isinstance(copy_meta, dict) else None,
        }
        turns.append(turn_record)
        with transcript_path.open("a") as fh:
            fh.write(json.dumps(turn_record) + "\n")
        if not status_ok:
            overall_status = "failed"
            failure_reason = (
                f"turn {turn} failed: returncode={proc.returncode}, "
                f"meta_status={turn_meta.get('status')!r}, expected_match={expected_match}, "
                f"pointer_restored={pointer_restored}, keyboard_idle_recorded={keyboard_idle_recorded}, "
                f"paste_expected_match={paste_expected_match}"
            )
            break
        if args.between_turn_wait > 0 and turn < args.turns:
            time.sleep(args.between_turn_wait)

    summary = {
        "status": overall_status,
        "mocked": False,
        "live": True,
        "run_id": run_id,
        "turns_requested": args.turns,
        "turns_completed": sum(1 for turn in turns if turn["status"] == "completed"),
        "window_id": window_id,
        "window_info": window_info,
        "transcript": str(transcript_path),
        "turns": turns,
        "failure_reason": failure_reason,
        "claims": {
            "proves": "When status=completed and turns_completed equals turns_requested, the foreground Gemini side-panel transport completed repeated fresh prompt/send/copy turns, rejected stale clipboard responses by expected text, waited for idle before mouse and keyboard actions, restored the pointer after every mouse click, and proved the expected text was visible in the composer before send.",
            "does_not_prove": "This does not prove background/no-focus operation or that Gemini's side panel is DOM/CDP-accessible.",
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if overall_status == "completed" and summary["turns_completed"] == args.turns else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Foreground desktop automation for Chrome Gemini side panel.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    copy = sub.add_parser("copy", help="Find and click the visible Gemini side-panel copy button.")
    copy.add_argument("--window-id", help="X11 window id. Prefer this for fail-closed targeting.")
    copy.add_argument("--title-regex", default=r"UX Lab|Embry|Gemini|Google Chrome", help="Chrome window title regex when --window-id is omitted.")
    copy.add_argument("--output-dir", help="Artifact directory. Default: /tmp/surf-gemini-sidepanel-<timestamp>.")
    copy.add_argument("--response-output", help="Where to write copied clipboard text.")
    copy.add_argument("--meta-output", help="Where to write metadata JSON.")
    copy.add_argument("--wait", type=float, default=0.6, help="Seconds to wait after clicking copy.")
    copy.add_argument("--pointer-idle-seconds", type=float, default=1.5, help="Require the mouse pointer to be still this many seconds before scripted mouse movement. Use 0 to disable.")
    copy.add_argument("--pointer-idle-timeout", type=float, default=10.0, help="Maximum seconds to wait for pointer idle before failing closed.")
    copy.add_argument("--scroll-bottom-clicks", type=int, default=8, help="Mouse-wheel down clicks over the Gemini side panel before locating controls. Use 0 to disable.")
    copy.add_argument("--ocr-fallback", action="store_true", help="If copy does not change the clipboard, OCR the visible side panel into the response output and mark the metadata as fallback.")
    copy.add_argument("--dry-run", action="store_true", help="Detect and annotate only; do not click.")
    copy.set_defaults(func=click_copy)

    submit = sub.add_parser("submit", help="Paste a prompt into the visible Gemini side-panel composer, send, and copy the response.")
    submit.add_argument("--prompt", required=True, help="Prompt text to paste into the side-panel composer.")
    submit.add_argument("--window-id", help="X11 window id. Prefer this for fail-closed targeting.")
    submit.add_argument("--title-regex", default=r"UX Lab|Embry|Gemini|Google Chrome", help="Chrome window title regex when --window-id is omitted.")
    submit.add_argument("--output-dir", help="Artifact directory. Default: /tmp/surf-gemini-sidepanel-submit-<timestamp>.")
    submit.add_argument("--response-output", help="Where to write copied response text.")
    submit.add_argument("--meta-output", help="Where to write metadata JSON.")
    submit.add_argument("--timeout", type=float, default=90.0, help="Seconds to wait for a copyable response.")
    submit.add_argument("--poll-interval", type=float, default=3.0, help="Seconds between screenshot polls.")
    submit.add_argument("--wait", type=float, default=0.6, help="Seconds to wait after clicking copy.")
    submit.add_argument("--pointer-idle-seconds", type=float, default=1.5, help="Require the mouse pointer to be still this many seconds before scripted mouse movement. Use 0 to disable.")
    submit.add_argument("--pointer-idle-timeout", type=float, default=10.0, help="Maximum seconds to wait for pointer idle before failing closed.")
    submit.add_argument("--scroll-bottom-clicks", type=int, default=8, help="Mouse-wheel down clicks over the Gemini side panel before pasting or locating controls. Use 0 to disable.")
    submit.add_argument("--expected-response", help="Expected response text for OCR-primary validation.")
    submit.add_argument("--ocr-primary", action="store_true", help="Use OCR validation as the primary response success path instead of requiring clipboard copy.")
    submit.add_argument("--stable-polls", type=int, default=2, help="Stable non-empty OCR polls required when no --expected-response is supplied.")
    submit.add_argument("--ocr-fallback", action="store_true", help="If copy does not change the clipboard, OCR the visible answer near the detected action row and mark the metadata as fallback.")
    submit.set_defaults(func=submit_and_copy)

    send = sub.add_parser("send", help="Paste text into the visible Gemini side-panel composer and click send.")
    send.add_argument("--prompt", required=True, help="Prompt text to paste into the side-panel composer.")
    send.add_argument("--window-id", help="X11 window id. Prefer this for fail-closed targeting.")
    send.add_argument("--title-regex", default=r"UX Lab|Embry|Gemini|Google Chrome", help="Chrome window title regex when --window-id is omitted.")
    send.add_argument("--output-dir", help="Artifact directory. Default: /tmp/surf-gemini-sidepanel-send-<timestamp>.")
    send.add_argument("--meta-output", help="Where to write metadata JSON.")
    send.add_argument("--composer-x", type=int, help="Override window-relative composer X coordinate.")
    send.add_argument("--composer-y", type=int, help="Override window-relative composer Y coordinate.")
    send.add_argument("--send-x", type=int, help="Override window-relative send-button X coordinate.")
    send.add_argument("--send-y", type=int, help="Override window-relative send-button Y coordinate.")
    send.add_argument("--after-paste-wait", type=float, default=0.5, help="Seconds to wait before after-paste screenshot.")
    send.add_argument("--after-send-wait", type=float, default=1.0, help="Seconds to wait before after-send screenshot.")
    send.add_argument("--pointer-idle-seconds", type=float, default=1.5, help="Require the mouse pointer to be still this many seconds before scripted mouse movement. Use 0 to disable.")
    send.add_argument("--pointer-idle-timeout", type=float, default=10.0, help="Maximum seconds to wait for pointer idle before failing closed.")
    send.add_argument("--scroll-bottom-clicks", type=int, default=8, help="Mouse-wheel down clicks over the Gemini side panel before pasting. Use 0 to disable.")
    send.add_argument("--no-send", action="store_true", help="Paste and screenshot only; do not click send.")
    send.set_defaults(func=paste_and_send)

    loop = sub.add_parser("loop", help="Run repeated fresh Gemini side-panel prompt/send/copy turns with a JSONL transcript.")
    loop.add_argument("--window-id", help="X11 window id. Prefer this for fail-closed targeting.")
    loop.add_argument("--title-regex", default=r"UX Lab|Embry|Gemini|Google Chrome", help="Chrome window title regex when --window-id is omitted.")
    loop.add_argument("--output-dir", help="Artifact directory. Default: /tmp/surf-gemini-sidepanel-loop-<timestamp>.")
    loop.add_argument("--meta-output", help="Where to write summary JSON.")
    loop.add_argument("--turns", type=int, default=2, help="Number of fresh prompt/send/copy turns to run.")
    loop.add_argument("--run-id", help="Stable id included in generated expected responses. Default: UTC timestamp.")
    loop.add_argument("--expected-template", default="LOOP {run_id} TURN {turn} OK", help="Python format string with {run_id} and {turn}.")
    loop.add_argument("--prompt-template", default="Ignore the shared tab. Reply with exactly: {expected}", help="Python format string with {run_id}, {turn}, and {expected}.")
    loop.add_argument("--timeout-per-turn", type=float, default=90.0, help="Seconds to wait for each fresh copied response.")
    loop.add_argument("--poll-interval", type=float, default=3.0, help="Seconds between screenshot polls.")
    loop.add_argument("--wait", type=float, default=0.6, help="Seconds to wait after clicking copy.")
    loop.add_argument("--between-turn-wait", type=float, default=0.5, help="Seconds to wait between successful turns.")
    loop.add_argument("--pointer-idle-seconds", type=float, default=1.5, help="Require the mouse pointer to be still this many seconds before scripted mouse movement. Use 0 to disable.")
    loop.add_argument("--pointer-idle-timeout", type=float, default=10.0, help="Maximum seconds to wait for pointer idle before failing closed.")
    loop.add_argument("--scroll-bottom-clicks", type=int, default=8, help="Mouse-wheel down clicks over the Gemini side panel before each turn. Use 0 to disable.")
    loop.set_defaults(func=submit_loop)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
