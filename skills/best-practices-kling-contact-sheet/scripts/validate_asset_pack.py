#!/usr/bin/env python3
"""Validate a Kling-style asset pack folder.

Checks:
- manifest.json exists and parses
- 2-4 references are listed
- reference files exist
- extensions are .jpg, .jpeg, or .png
- files are <=10 MB
- image dimensions are at least 300x300 px

"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Optional, Tuple

import typer

app = typer.Typer(add_completion=False, help="Validate a Kling-style asset pack folder.")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_BYTES = 10 * 1024 * 1024
MIN_DIMENSION = 300

class ValidationMessage:
    def __init__(self, level: str, message: str) -> None:
        self.level = level
        self.message = message

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"

def png_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    with path.open("rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height

def jpeg_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    with path.open("rb") as f:
        data = f.read(2)
        if data != b"\xff\xd8":
            return None
        while True:
            marker_prefix = f.read(1)
            if not marker_prefix:
                return None
            if marker_prefix != b"\xff":
                continue
            marker = f.read(1)
            while marker == b"\xff":
                marker = f.read(1)
            if marker in [b"\xd8", b"\xd9"]:
                continue
            length_bytes = f.read(2)
            if len(length_bytes) != 2:
                return None
            length = struct.unpack(">H", length_bytes)[0]
            if length < 2:
                return None
            sof_markers = {b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf"}
            if marker in sof_markers:
                segment = f.read(length - 2)
                if len(segment) < 5:
                    return None
                height, width = struct.unpack(">HH", segment[1:5])
                return width, height
            f.seek(length - 2, os.SEEK_CUR)

def image_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".png":
            return png_dimensions(path)
        if suffix in {".jpg", ".jpeg"}:
            return jpeg_dimensions(path)
    except OSError:
        return None
    return None

def validate_pack(pack: Path) -> list[ValidationMessage]:
    messages: list[ValidationMessage] = []
    manifest_path = pack / "manifest.json"
    if not manifest_path.exists():
        return [ValidationMessage("ERROR", "manifest.json is missing.")]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [ValidationMessage("ERROR", f"manifest.json is not valid JSON: {exc}")]

    refs = manifest.get("references")
    if not isinstance(refs, list):
        messages.append(ValidationMessage("ERROR", "manifest.references must be a list."))
        refs = []

    if len(refs) < 2 or len(refs) > 4:
        messages.append(ValidationMessage("ERROR", f"Kling Element reference count should be 2-4; found {len(refs)}."))
    else:
        messages.append(ValidationMessage("OK", f"Reference count is {len(refs)}."))

    for i, ref in enumerate(refs, start=1):
        if not isinstance(ref, dict):
            messages.append(ValidationMessage("ERROR", f"Reference {i} is not an object."))
            continue
        rel = ref.get("file")
        if not rel:
            messages.append(ValidationMessage("ERROR", f"Reference {i} has no file path."))
            continue
        path = pack / rel
        if not path.exists():
            messages.append(ValidationMessage("ERROR", f"Missing reference file: {rel}"))
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            messages.append(ValidationMessage("ERROR", f"Unsupported extension for {rel}: {path.suffix}"))
        else:
            messages.append(ValidationMessage("OK", f"Extension ok: {rel}"))
        size = path.stat().st_size
        if size > MAX_BYTES:
            messages.append(ValidationMessage("ERROR", f"File too large: {rel} is {size / 1024 / 1024:.2f} MB; max is 10 MB."))
        elif size == 0:
            messages.append(ValidationMessage("WARN", f"File is empty placeholder: {rel}"))
        else:
            messages.append(ValidationMessage("OK", f"File size ok: {rel} ({size / 1024 / 1024:.2f} MB)"))

        dims = image_dimensions(path)
        if dims is None:
            if size == 0:
                continue
            messages.append(ValidationMessage("WARN", f"Could not read image dimensions: {rel}"))
        else:
            width, height = dims
            if width < MIN_DIMENSION or height < MIN_DIMENSION:
                messages.append(ValidationMessage("ERROR", f"Image too small: {rel} is {width}x{height}; minimum is 300x300."))
            else:
                messages.append(ValidationMessage("OK", f"Dimensions ok: {rel} ({width}x{height})"))

    desc = manifest.get("description", {})
    if isinstance(desc, dict):
        for field in ["core_identity", "visual_details"]:
            if not str(desc.get(field, "")).strip():
                messages.append(ValidationMessage("WARN", f"Description field is empty: {field}"))
        for field in ["do_not_change", "ignore"]:
            value = desc.get(field, [])
            if not isinstance(value, list) or not value:
                messages.append(ValidationMessage("WARN", f"Description list is empty: {field}"))
    else:
        messages.append(ValidationMessage("WARN", "manifest.description should be an object."))

    return messages

@app.command()
def main(pack: Path = typer.Argument(..., help="Path to asset pack folder containing manifest.json")) -> None:
    pack = pack.expanduser().resolve()
    messages = validate_pack(pack)
    for msg in messages:
        typer.echo(str(msg))
    has_error = any(msg.level == "ERROR" for msg in messages)
    if has_error:
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
