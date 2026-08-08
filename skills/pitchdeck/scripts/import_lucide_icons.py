"""Import lucide line icons into the hash-pinned pitchdeck icon library.

The deck's illustration vocabulary was ten hand-authored glyphs, which is why
generated slides read as icon-poor next to the author's drawn scenes. Lucide is
an installed MIT-licensed line-icon set of 1,861 icons drawn on one consistent
24x24 grid with the same stroke weight — the same visual family, at scale.

Only icons whose primitives map to NATIVE PowerPoint objects are imported:
rect -> preset rect, circle -> preset ellipse, line/polyline/simple path ->
straight-segment freeform. Icons containing curve commands (C/S/Q/T/A) are
SKIPPED rather than approximated, because the library's contract is that a
resolved icon is natively editable — silently degrading a curve to a polygon
would be a lie about editability, and resolve_icon() would have no way to know.

Inputs: a JSON dump of lucide's icon data (node -e, see --dump-help).
Outputs: manifest entries with sanitized SVG, sha256, and native mapping.
Failure modes: a requested icon that is not natively mappable is reported and
skipped, never emitted with a raster or curve fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

CURVE_COMMANDS = re.compile(r"[CcSsQqTtAa]")
PATH_TOKENS = re.compile(r"([MmLlHhVvZz])|(-?\d*\.?\d+)")
GRID = 24.0  # lucide's canonical viewBox


def path_to_vertices(spec: str) -> list[tuple[float, float]] | None:
    """Parse a curve-free path into absolute vertices, or None if unsupported."""
    if CURVE_COMMANDS.search(spec):
        return None
    vertices: list[tuple[float, float]] = []
    cursor = [0.0, 0.0]
    command = None
    numbers: list[float] = []

    def flush() -> bool:
        nonlocal numbers
        if command in {"M", "L"}:
            for i in range(0, len(numbers) - 1, 2):
                cursor[0], cursor[1] = numbers[i], numbers[i + 1]
                vertices.append((cursor[0], cursor[1]))
        elif command in {"m", "l"}:
            for i in range(0, len(numbers) - 1, 2):
                cursor[0] += numbers[i]
                cursor[1] += numbers[i + 1]
                vertices.append((cursor[0], cursor[1]))
        elif command in {"H", "h", "V", "v"}:
            for value in numbers:
                if command == "H":
                    cursor[0] = value
                elif command == "h":
                    cursor[0] += value
                elif command == "V":
                    cursor[1] = value
                else:
                    cursor[1] += value
                vertices.append((cursor[0], cursor[1]))
        elif command in {"Z", "z"}:
            if vertices:
                vertices.append(vertices[0])
        elif command is not None:
            return False
        numbers = []
        return True

    for match in PATH_TOKENS.finditer(spec):
        letter, number = match.groups()
        if letter:
            if not flush():
                return None
            command = letter
        else:
            numbers.append(float(number))
    if not flush():
        return None
    return vertices if len(vertices) >= 2 else None


def build_mapping(parts: list) -> dict | None:
    """Native PPTX mapping, or None when any primitive needs a curve."""
    mapped: list[dict] = []
    for kind, attrs in parts:
        if kind == "rect":
            x, y = float(attrs.get("x", 0)), float(attrs.get("y", 0))
            w, h = float(attrs["width"]), float(attrs["height"])
            preset = "rounded_rect" if float(attrs.get("rx", 0)) > 0 else "rect"
            mapped.append({"kind": "preset", "preset": preset,
                           "bbox": [x / GRID, y / GRID, w / GRID, h / GRID]})
        elif kind in {"circle", "ellipse"}:
            cx, cy = float(attrs["cx"]), float(attrs["cy"])
            rx = float(attrs.get("r") or attrs["rx"])
            ry = float(attrs.get("r") or attrs["ry"])
            mapped.append({"kind": "preset", "preset": "ellipse",
                           "bbox": [(cx - rx) / GRID, (cy - ry) / GRID, 2 * rx / GRID, 2 * ry / GRID]})
        elif kind == "line":
            pts = [(float(attrs["x1"]), float(attrs["y1"])), (float(attrs["x2"]), float(attrs["y2"]))]
            mapped.append({"kind": "freeform", "closed": False,
                           "vertices": [[x / GRID, y / GRID] for x, y in pts]})
        elif kind in {"polyline", "polygon"}:
            raw = [float(v) for v in re.findall(r"-?\d*\.?\d+", attrs.get("points", ""))]
            pts = list(zip(raw[0::2], raw[1::2]))
            if len(pts) < 2:
                return None
            mapped.append({"kind": "freeform", "closed": kind == "polygon",
                           "vertices": [[x / GRID, y / GRID] for x, y in pts]})
        elif kind == "path":
            vertices = path_to_vertices(attrs.get("d", ""))
            if vertices is None:
                return None
            mapped.append({"kind": "freeform", "closed": attrs.get("d", "").strip()[-1] in "Zz",
                           "vertices": [[x / GRID, y / GRID] for x, y in vertices]})
        else:
            return None
    return {"parts": mapped} if mapped else None


def to_svg(parts: list) -> str:
    """Reconstruct the icon as a standalone stroked SVG (web rendering)."""
    body = []
    for kind, attrs in parts:
        rendered = " ".join(f'{k}="{v}"' for k, v in attrs.items())
        body.append(f"<{kind} {rendered}/>")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="#000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        + "".join(body)
        + "</svg>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, required=True, help="JSON dump of lucide icon data")
    parser.add_argument("--manifest", type=Path, required=True, help="pitchdeck icon manifest to extend")
    parser.add_argument("--icons", nargs="*", help="Specific icon names; default imports every mappable icon")
    args = parser.parse_args()

    data = json.loads(args.dump.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != "pitchdeck.icon_library.v1":
        raise SystemExit("manifest schema mismatch — refusing to write")
    library_dir = args.manifest.parent
    existing = {entry["id"] for entry in manifest["icons"]}
    wanted = args.icons or sorted(data)
    imported, skipped = [], []
    for name in wanted:
        parts = data.get(name)
        if parts is None:
            skipped.append(f"{name}: not in lucide")
            continue
        mapping = build_mapping(parts)
        if mapping is None:
            skipped.append(f"{name}: contains curves — not natively editable")
            continue
        icon_id = re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()
        if icon_id in existing:
            # Hash-pinned ids are bound by golden documents; imports are
            # ADDITIVE only or golden revalidation breaks (the #1271 compat law).
            skipped.append(f"{icon_id}: already pinned — additive import only")
            continue
        svg = to_svg(parts)
        svg_file = f"{icon_id}.svg"
        (library_dir / svg_file).write_text(svg, encoding="utf-8")
        manifest["icons"].append({
            "id": icon_id,
            "svg_file": svg_file,
            "svg_sha256": hashlib.sha256(svg.encode()).hexdigest(),
            # Field name matters: resolve_icon() dispatches on native_mapping
            # and fails closed when it is absent.
            "native_mapping": {"kind": "group", **mapping},
            "png_fallback": None,
            "license": "lucide (ISC), 24x24 grid",
        })
        existing.add(icon_id)
        imported.append(icon_id)
    manifest["icons"].sort(key=lambda e: e["id"])
    args.manifest.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"imported": len(imported), "skipped": len(skipped),
                      "library_total": len(manifest["icons"]), "examples": imported[:10]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
