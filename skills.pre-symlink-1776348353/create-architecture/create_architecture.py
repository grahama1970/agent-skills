"""Create and update architecture diagrams in UX Lab's Excalidraw canvas."""

import json
import random
import sys
from pathlib import Path
from typing import List, Optional

import httpx
import typer
import yaml
from rich.console import Console

app = typer.Typer(help="Architecture diagram generator for UX Lab Excalidraw canvas")
console = Console()

UX_LAB_URL = "http://localhost:3001"

COLORS = {
    "purple": "#7c3aed",
    "green": "#00ff88",
    "blue": "#4a9eff",
    "amber": "#ffaa00",
    "red": "#ff4444",
    "dim": "#64748b",
}


def _nonce() -> int:
    return random.randint(1, 2_000_000_000)


def _build_elements(components: list[dict], connections: list[dict], name: str = "") -> list[dict]:
    """Generate Excalidraw elements from component + connection definitions."""
    elements: list[dict] = []
    comp_map: dict[str, dict] = {}

    # --- Canvas-aware layout (see CHART_DESIGN.md) ---
    CANVAS_W = 1300  # usable width (full screen minus margins)
    CANVAS_H = 700   # usable height (minus toolbar + bottom bar)
    MARGIN = 40

    # Scan grid extents from component data
    max_row = max((comp.get("row", idx) for idx, comp in enumerate(components)), default=0)
    max_col = max((comp.get("col", 0) for comp in components), default=0)
    n_rows = max_row + 1
    n_cols = max_col + 1

    # Compute cell sizes to fit canvas
    title_h = 30 if name else 0
    usable_h = CANVAS_H - title_h - MARGIN
    usable_w = CANVAS_W - MARGIN * 2

    row_h = usable_h / n_rows
    col_w = usable_w / n_cols if n_cols > 1 else usable_w

    # Box fills ~70% of cell width, ~55% of cell height
    box_w = int(min(col_w * 0.70, 350))  # cap at 350px
    if n_cols == 1:
        box_w = int(min(usable_w * 0.35, 350))  # single column: 35% width

    # Font scales with cell
    font_size = max(10, min(14, int(row_h * 0.15)))

    # Center the grid in canvas
    grid_w = n_cols * col_w
    x_offset = MARGIN + (usable_w - grid_w) / 2
    y_cursor = MARGIN

    # Title element at top of diagram
    if name:
        elements.append({
            "type": "text",
            "id": "title",
            "x": MARGIN,
            "y": y_cursor,
            "width": usable_w,
            "height": title_h,
            "text": name,
            "originalText": name,
            "fontSize": 20,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "top",
            "strokeColor": "#ffffff",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "isDeleted": False,
            "groupIds": [],
            "roundness": None,
            "boundElements": None,
            "link": None,
            "locked": False,
            "containerId": None,
            "lineHeight": 1.2,
            "version": 2,
            "versionNonce": _nonce(),
            "seed": _nonce(),
            "updated": 1774450000000,
        })
        y_cursor += title_h + 10

    for comp in components:
        comp_id = comp["id"]
        color = COLORS.get(comp.get("color", "blue"), comp.get("color", COLORS["blue"]))
        label = comp.get("label", comp_id)
        tech = comp.get("tech", "")
        latency = comp.get("latency", "")
        subtitle_raw = f"{tech} · {latency}".strip(" ·") if tech or latency else ""
        # Only show subtitle if box is tall enough for 2 lines (needs ~30px min)
        min_two_line_h = font_size * 1.2 * 2 + 12  # 2 lines + padding
        h = int(row_h * 0.55)  # box fills 55% of row height
        subtitle = subtitle_raw if h >= min_two_line_h else ""
        # Detect diamond shape for decision nodes (◇ prefix)
        is_diamond = label.startswith("◇")
        shape_type = "diamond" if is_diamond else "rectangle"
        rect_id = f"rect_{comp_id}"
        label_id = f"label_{comp_id}"

        # Diamonds: equal width and height for a proper square-rotated-45 shape
        w = box_w
        if is_diamond:
            side = int(row_h * 0.75)  # 75% of row height, square
            w = side
            h = side

        # Grid layout: use row/col if specified, else stack vertically
        row = comp.get("row")
        col = comp.get("col", 0)
        if row is not None:
            # Center box within its grid cell
            cell_x = x_offset + col * col_w
            comp_x = cell_x + (col_w - w) / 2
            comp_y = y_cursor + row * row_h + (row_h - h) / 2
        else:
            comp_x = x_offset + (col_w - w) / 2
            comp_y = y_cursor
            y_cursor += h + 8

        # Track position for arrow generation
        comp_map[comp_id] = {"rect_id": rect_id, "y": comp_y, "h": h, "x": comp_x, "w": w}

        # Build bound elements list (arrows added later; text bound only for rectangles)
        bound = [] if is_diamond else [{"id": label_id, "type": "text"}]

        elements.append({
            "type": shape_type,
            "id": rect_id,
            "x": comp_x,
            "y": comp_y,
            "width": w,
            "height": h,
            "strokeColor": color,
            "backgroundColor": f"{color}99",  # higher opacity for readability
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "isDeleted": False,
            "groupIds": [],
            "roundness": {"type": 3},
            "boundElements": bound,
            "link": None,
            "locked": False,
            "version": 2,
            "versionNonce": _nonce(),
            "seed": _nonce(),
            "updated": 1774450000000,
            "customData": {"label": label, "tech": tech, "latency": latency, "description": comp.get("description", "")},
        })

        # For diamonds: label BELOW the shape (unbound, not inside)
        # For rectangles: label inside the shape (bound via containerId)
        if is_diamond:
            # Strip ◇ prefix for cleaner label below diamond
            clean_label = label.lstrip("◇ ").strip()
            # Center text below diamond — width must fit the full label
            label_w = max(len(clean_label) * 8, 150)  # ~8px per char, min 150
            text_x = comp_x + w / 2 - label_w / 2  # center below diamond
            text_y = comp_y + h + 6  # below the diamond
            elements.append({
                "type": "text",
                "id": label_id,
                "x": text_x,
                "y": text_y,
                "width": label_w,
                "height": font_size + 8,
                "text": clean_label,
                "originalText": clean_label,
                "autoResize": True,
                "fontSize": font_size + 2,  # slightly larger for below-diamond labels
                "fontFamily": 3,  # monospace for crisp readability
                "textAlign": "center",
                "verticalAlign": "top",
                "strokeColor": "#ffffff",  # white text on dark canvas
                "backgroundColor": "transparent",
                "fillStyle": "solid",
                "strokeWidth": 1,
                "roughness": 0,
                "opacity": 100,
                "angle": 0,
                "isDeleted": False,
                "groupIds": [],
                "roundness": None,
                "boundElements": None,
                "link": None,
                "locked": False,
                "containerId": None,  # NOT bound to diamond
                "lineHeight": 1.2,
                "version": 2,
                "versionNonce": _nonce(),
                "seed": _nonce(),
                "updated": 1774450000000,
            })
        else:
            full_text = f"{label}\n{subtitle}" if subtitle else label
            elements.append({
                "type": "text",
                "id": label_id,
                "x": comp_x + 10,
                "y": comp_y + 10,
                "width": w - 20,
                "height": h - 20,
                "text": full_text,
                "originalText": full_text,
                "autoResize": True,
                "fontSize": font_size,
                "fontFamily": 3,  # monospace for crisp readability
                "textAlign": "center",
                "verticalAlign": "middle",
                "strokeColor": "#ffffff",
                "backgroundColor": "transparent",
                "fillStyle": "solid",
                "strokeWidth": 1,
                "roughness": 0,
                "opacity": 100,
                "angle": 0,
                "isDeleted": False,
                "groupIds": [],
                "roundness": None,
                "boundElements": None,
                "link": None,
                "locked": False,
                "containerId": rect_id,
                "lineHeight": 1.2,
                "version": 2,
                "versionNonce": _nonce(),
                "seed": _nonce(),
                "updated": 1774450000000,
            })

        y_cursor += h + 8

    # Build connections (default: sequential if none specified)
    if not connections and len(components) > 1:
        connections = [
            {"from": components[i]["id"], "to": components[i + 1]["id"]}
            for i in range(len(components) - 1)
        ]

    for conn in connections:
        src = comp_map.get(conn["from"])
        dst = comp_map.get(conn["to"])
        if not src or not dst:
            console.print(f"[yellow]WARN: skipping connection {conn['from']} → {conn['to']} (unknown component)[/yellow]")
            continue

        arrow_id = f"arrow_{conn['from']}_{conn['to']}"

        # Compute orthogonal (right-angle) waypoints manually
        src_cx = src["x"] + src["w"] / 2
        src_cy = src["y"] + src["h"] / 2
        dst_cx = dst["x"] + dst["w"] / 2
        dst_cy = dst["y"] + dst["h"] / 2

        same_col = abs(src_cx - dst_cx) < 10  # same column within tolerance

        if same_col:
            # Same column: straight vertical, exit bottom → enter top
            if dst_cy > src_cy:
                start_x = src_cx
                start_y = src["y"] + src["h"]
                end_x = dst_cx
                end_y = dst["y"]
            else:
                start_x = src_cx
                start_y = src["y"]
                end_x = dst_cx
                end_y = dst["y"] + dst["h"]
            dx = end_x - start_x
            dy = end_y - start_y
            waypoints = [[0, 0], [dx, dy]]
        else:
            # Different columns: orthogonal L-shaped or Z-shaped routing
            # Exit from the side facing the destination
            if dst_cx > src_cx:
                # Destination is to the right: exit right side
                start_x = src["x"] + src["w"]
                start_y = src_cy
                end_x = dst["x"]
                end_y = dst_cy
            else:
                # Destination is to the left: exit left side
                start_x = src["x"]
                start_y = src_cy
                end_x = dst["x"] + dst["w"]
                end_y = dst_cy

            dx = end_x - start_x
            dy = end_y - start_y

            if abs(dy) < 10:
                # Same row: straight horizontal
                waypoints = [[0, 0], [dx, dy]]
            else:
                # L-shape: go horizontal halfway, then vertical, then horizontal
                mid_x = dx / 2
                waypoints = [[0, 0], [mid_x, 0], [mid_x, dy], [dx, dy]]

        # Add arrow binding to source and destination rectangles
        for el in elements:
            if el["id"] == src["rect_id"] and el["type"] == "rectangle":
                el["boundElements"].append({"id": arrow_id, "type": "arrow"})
            if el["id"] == dst["rect_id"] and el["type"] == "rectangle":
                el["boundElements"].append({"id": arrow_id, "type": "arrow"})

        elements.append({
            "type": "arrow",
            "id": arrow_id,
            "x": start_x,
            "y": start_y,
            "width": abs(dx),
            "height": abs(dy),
            "strokeColor": COLORS["dim"],
            "strokeWidth": 2,
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "fillStyle": "solid",
            "isDeleted": False,
            "groupIds": [],
            "roundness": {"type": 2},
            "boundElements": None,
            "link": None,
            "locked": False,
            "elbowed": True,
            "fixedSegments": [],
            "startIsSpecial": False,
            "endIsSpecial": False,
            "startBinding": {"elementId": src["rect_id"], "focus": 0, "gap": 4, "fixedPoint": None},
            "endBinding": {"elementId": dst["rect_id"], "focus": 0, "gap": 4, "fixedPoint": None},
            "startArrowhead": None,
            "endArrowhead": "arrow",
            "points": waypoints,
            "lastCommittedPoint": None,
            "version": 2,
            "versionNonce": _nonce(),
            "seed": _nonce(),
            "updated": 1774450000000,
        })

    # Z-order: shapes first, then arrows, then text on top (last = renders on top)
    shapes = [e for e in elements if e["type"] in ("rectangle", "diamond", "ellipse")]
    arrows = [e for e in elements if e["type"] == "arrow"]
    texts = [e for e in elements if e["type"] == "text"]
    return shapes + arrows + texts


def _build_attachments(components: list[dict]) -> dict[str, list[str]]:
    """Extract file attachments keyed by rect element ID."""
    attachments: dict[str, list[str]] = {}
    for comp in components:
        files = comp.get("files", [])
        if files:
            attachments[f"rect_{comp['id']}"] = files
    return attachments


def _save(project_id: str, name: str, elements: list[dict], attachments: dict) -> dict:
    """Save architecture to UX Lab Express API."""
    payload = {"name": name, "elements": elements, "attachments": attachments}
    r = httpx.put(f"{UX_LAB_URL}/api/architecture/{project_id}", json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


@app.command()
def create(
    input: Optional[Path] = typer.Option(None, "--input", "-i", help="YAML pipeline definition file"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Architecture name (overrides YAML)"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID (slug, default: derived from name)"),
    json_input: Optional[str] = typer.Option(None, "--json", help="Inline JSON array of components"),
) -> None:
    """Create an architecture diagram from a pipeline definition."""
    if input and input.exists():
        with open(input) as f:
            spec = yaml.safe_load(f)
        components = spec.get("components", [])
        connections = spec.get("connections", [])
        arch_name = name or spec.get("name", input.stem)
    elif json_input:
        components = json.loads(json_input)
        connections = []
        arch_name = name or "Untitled Architecture"
    else:
        console.print("[red]ERROR: provide --input pipeline.yaml or --json '[...]'[/red]")
        raise typer.Exit(1)

    pid = project_id or arch_name.lower().replace(" ", "-").replace("/", "-")

    elements = _build_elements(components, connections, name=arch_name)
    attachments = _build_attachments(components)
    result = _save(pid, arch_name, elements, attachments)

    n_boxes = sum(1 for e in elements if e["type"] == "rectangle")
    n_arrows = sum(1 for e in elements if e["type"] == "arrow")
    console.print(f"[green]Saved:[/green] {arch_name} → {pid}")
    console.print(f"  {n_boxes} components, {n_arrows} connections, {len(attachments)} with file attachments")
    console.print(f"  View: http://localhost:3002/#architecture (select {pid})")

    if "--json" in sys.argv or any(a.startswith("--json") for a in sys.argv):
        print(json.dumps(result))


@app.command()
def list() -> None:
    """List saved architecture projects."""
    r = httpx.get(f"{UX_LAB_URL}/api/architecture", timeout=10)
    r.raise_for_status()
    data = r.json()
    archs = data.get("architectures", [])
    if not archs:
        console.print("[dim]No architectures saved yet[/dim]")
        return
    for a in archs:
        console.print(f"  [cyan]{a.get('id', '?'):30s}[/cyan] {a.get('name', '')}")


@app.command()
def add_component(
    project: str = typer.Option(..., "--project", "-p", help="Existing project ID"),
    label: str = typer.Option(..., "--label", "-l", help="Component label"),
    tech: str = typer.Option("", "--tech", help="Technology description"),
    latency: str = typer.Option("", "--latency", help="Latency budget"),
    color: str = typer.Option("blue", "--color", help="Color: purple|green|blue|amber|red"),
    after: Optional[str] = typer.Option(None, "--after", help="Insert after this component ID"),
    files: Optional[List[str]] = typer.Option(None, "--file", "-f", help="Attached file paths"),
) -> None:
    """Add a component to an existing architecture."""
    r = httpx.get(f"{UX_LAB_URL}/api/architecture/{project}", timeout=10)
    if r.status_code == 404:
        console.print(f"[red]Architecture '{project}' not found[/red]")
        raise typer.Exit(1)
    r.raise_for_status()
    data = r.json()

    existing_elements = data.get("excalidraw", data).get("elements", [])
    existing_attachments = data.get("excalidraw", data).get("attachments", data.get("attachments", {}))

    # Extract existing components from rectangles
    rects = [e for e in existing_elements if e.get("type") == "rectangle"]
    comp_ids = [e["id"].replace("rect_", "") for e in rects]

    new_id = label.lower().replace(" ", "_").replace("/", "_")
    new_comp = {"id": new_id, "label": label, "tech": tech, "latency": latency, "color": color, "files": files or []}

    # Rebuild component list with new component inserted
    components = []
    for cid in comp_ids:
        rect = next(e for e in rects if e["id"] == f"rect_{cid}")
        cd = rect.get("customData", {})
        components.append({
            "id": cid,
            "label": cd.get("label", cid),
            "tech": cd.get("tech", ""),
            "latency": cd.get("latency", ""),
            "color": next((k for k, v in COLORS.items() if v == rect.get("strokeColor")), "blue"),
            "files": existing_attachments.get(f"rect_{cid}", []),
        })

    if after and after in comp_ids:
        idx = comp_ids.index(after) + 1
        components.insert(idx, new_comp)
    else:
        components.append(new_comp)

    elements = _build_elements(components, [])
    attachments = _build_attachments(components)
    arch_name = data.get("title", data.get("excalidraw", {}).get("name", project))
    result = _save(project, arch_name, elements, attachments)

    console.print(f"[green]Added:[/green] {label} → {project}")
    console.print(f"  Now {len(components)} components total")


if __name__ == "__main__":
    app()
