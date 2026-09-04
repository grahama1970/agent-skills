#!/usr/bin/env python3
"""Compile Excalidraw whiteboard animation tokens into create-svg scenes."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Literal

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

app = typer.Typer(help="Compile Excalidraw animation tokens into create-svg input.")

SKILL_DIR = Path(__file__).resolve().parents[1]

PRESETS = {
    "reveal": "fade-slide-y",
    "line-draw": "draw-stroke",
    "glow-pulse": "halo-pulse",
    "highlight": "color-pin",
    "pulse": "pulse",
}
ACCENTS = {"green", "cyan", "amber", "orange", "red", "white"}  # must stay a subset of create-svg accents


class OpsNode(BaseModel):
    """Metadata carried by a visual Excalidraw element."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["node"]
    role: Literal["source", "target"]
    title: str = Field(min_length=1)
    subtitle: str | None = None
    detail: str | None = None
    accent: str = "cyan"
    number: int | None = None

    @model_validator(mode="after")
    def accent_known(self) -> "OpsNode":
        if self.accent not in ACCENTS:
            raise ValueError(f"unknown accent {self.accent!r}")
        return self


class OpsAnimation(BaseModel):
    """Metadata carried by a movable animation token."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["animation"]
    preset: Literal["reveal", "line-draw", "glow-pulse", "highlight", "pulse"]
    targetId: str | None = None
    startMs: int = Field(default=0, ge=0)
    durationMs: int = Field(default=700, gt=0)
    easing: str = "easeOut"
    repeat: Literal["once", "loop"] = "once"


class ExcalidrawElement(BaseModel):
    """Small validated slice of an Excalidraw element; unknown drawing fields pass through."""

    model_config = ConfigDict(extra="allow")
    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    isDeleted: bool = False
    groupIds: list[str] = Field(default_factory=list)
    customData: dict[str, Any] | None = None
    text: str | None = None

    def ops(self) -> OpsNode | OpsAnimation | None:
        raw = (self.customData or {}).get("opsExcalidraw")
        if not isinstance(raw, dict):
            return None
        if raw.get("kind") == "node":
            return OpsNode.model_validate(raw)
        if raw.get("kind") == "animation":
            return OpsAnimation.model_validate(raw)
        raise ValueError(f"element {self.id}: unknown opsExcalidraw.kind")

    def overlaps(self, other: "ExcalidrawElement") -> bool:
        return not (
            self.x + self.width < other.x
            or other.x + other.width < self.x
            or self.y + self.height < other.y
            or other.y + other.height < self.y
        )


class ExcalidrawScene(BaseModel):
    """Plain Excalidraw scene JSON."""

    model_config = ConfigDict(extra="allow")
    type: Literal["excalidraw"]
    version: int
    source: str | None = None
    elements: list[ExcalidrawElement]
    appState: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, Any] = Field(default_factory=dict)


class LibraryItem(BaseModel):
    """Excalidraw library item."""

    model_config = ConfigDict(extra="allow")
    id: str
    status: str = "published"
    elements: list[ExcalidrawElement]


class ExcalidrawLibrary(BaseModel):
    """Excalidraw .excalidrawlib JSON."""

    model_config = ConfigDict(extra="allow")
    type: Literal["excalidrawlib"]
    version: int = 2
    source: str | None = None
    libraryItems: list[LibraryItem]

    @model_validator(mode="before")
    @classmethod
    def normalize_v1(cls, data: Any) -> Any:
        """Upstream directory libraries use v1 `library: [[elements]]` format."""
        if isinstance(data, dict) and "libraryItems" not in data and isinstance(data.get("library"), list):
            data = dict(data)
            data["libraryItems"] = [
                {"id": f"v1-item-{idx}", "status": "published", "elements": group}
                for idx, group in enumerate(data.pop("library"))
                if isinstance(group, list)
            ]
        return data


class CompileResult(BaseModel):
    """Validated compiler result."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["ops_excalidraw.compile.v1"] = Field("ops_excalidraw.compile.v1", alias="schema")
    source: str
    output: str
    nodes: int
    animation_tokens: int
    target_count: int
    timeline_events: int


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_scene(path: Path) -> ExcalidrawScene:
    return ExcalidrawScene.model_validate(load_json(path))


def load_library(path: Path) -> ExcalidrawLibrary:
    return ExcalidrawLibrary.model_validate(load_json(path))


def live_elements(scene: ExcalidrawScene) -> list[ExcalidrawElement]:
    return [element for element in scene.elements if not element.isDeleted]


def classify(scene: ExcalidrawScene) -> tuple[list[tuple[ExcalidrawElement, OpsNode]], list[tuple[ExcalidrawElement, OpsAnimation]]]:
    nodes: list[tuple[ExcalidrawElement, OpsNode]] = []
    animations: list[tuple[ExcalidrawElement, OpsAnimation]] = []
    for element in live_elements(scene):
        ops = element.ops()
        if isinstance(ops, OpsNode):
            nodes.append((element, ops))
        elif isinstance(ops, OpsAnimation):
            animations.append((element, ops))
    return nodes, animations


def resolve_target(
    token_el: ExcalidrawElement,
    token: OpsAnimation,
    nodes: list[tuple[ExcalidrawElement, OpsNode]],
) -> ExcalidrawElement:
    by_id = {element.id: element for element, _node in nodes}
    if token.targetId:
        if target := by_id.get(token.targetId):
            return target
        role_matches = [element for element, node in nodes if node.role == token.targetId]
        if len(role_matches) == 1:
            return role_matches[0]
        if len(role_matches) > 1:
            raise ValueError(f"animation token {token_el.id}: role alias {token.targetId!r} matched multiple targets")
        raise ValueError(f"animation token {token_el.id}: targetId {token.targetId!r} not found")

    grouped = [element for element, _node in nodes if set(element.groupIds) & set(token_el.groupIds)]
    if len(grouped) == 1:
        return grouped[0]
    if len(grouped) > 1:
        raise ValueError(f"animation token {token_el.id}: group binding matched multiple targets")

    overlapping = [element for element, _node in nodes if token_el.overlaps(element)]
    if len(overlapping) == 1:
        return overlapping[0]
    if len(overlapping) > 1:
        raise ValueError(f"animation token {token_el.id}: overlap binding matched multiple targets")
    raise ValueError(f"animation token {token_el.id}: unbound animation token")


def create_svg_target(target: ExcalidrawElement, target_map: dict[str, str], preset: str) -> str:
    mapped = target_map[target.id]
    if preset == "line-draw" and mapped.startswith("target-card-"):
        return "connector-" + mapped.rsplit("-", 1)[1]
    if preset == "line-draw" and mapped == "source-node":
        return "connector-0"
    if preset == "glow-pulse" and mapped == "source-node":
        return "source-glow"
    return mapped


def compile_scene(input_path: Path, output_path: Path) -> CompileResult:
    scene = load_scene(input_path)
    nodes, animations = classify(scene)
    sources = [(element, node) for element, node in nodes if node.role == "source"]
    targets = sorted(
        [(element, node) for element, node in nodes if node.role == "target"],
        key=lambda item: (item[0].y, item[0].x, item[0].id),
    )
    if len(sources) != 1:
        raise ValueError(f"expected exactly one source node, found {len(sources)}")
    if not targets:
        raise ValueError("expected at least one target node")

    source_el, source_node = sources[0]
    target_map = {source_el.id: "source-node"}
    target_map.update({element.id: f"target-card-{idx}" for idx, (element, _node) in enumerate(targets)})

    events: list[dict[str, Any]] = []
    for token_el, token in sorted(animations, key=lambda item: (item[1].startMs, item[0].id)):
        target = resolve_target(token_el, token, nodes)
        event: dict[str, Any] = {
            "target": create_svg_target(target, target_map, token.preset),
            "recipe": PRESETS[token.preset],
            "start_ms": token.startMs,
            "end_ms": token.startMs + token.durationMs,
        }
        if token.preset == "reveal":
            event["from_y"] = -18
        if token.preset == "glow-pulse":
            event["peak_opacity"] = 0.35
        if token.preset == "highlight":
            event["from_color"] = "#10213b"
            event["to_color"] = "#14394d"
        events.append(event)

    doc = {
        "schema_version": 1,
        "theme": "fixing-opus-neon-v1",
        "template": "fanout-anatomy",
        "metadata": {
            "title": scene.appState.get("name") or "Interview whiteboard",
            "description": "Compiled from ops-excalidraw animation tokens into create-svg scene and timeline input.",
        },
        "source": {
            "title": source_node.title,
            "subtitle": source_node.subtitle or source_node.detail or "whiteboard source",
        },
        "targets": [
            {
                "number": node.number or idx + 1,
                "heading": node.title,
                "detail": node.detail or node.subtitle or "strategy step",
                "accent": node.accent,
            }
            for idx, (_element, node) in enumerate(targets)
        ],
        "caption": "EXCALIDRAW WHITEBOARD · CREATE-SVG RENDER",
        "timeline": {"cycle_ms": max([event["end_ms"] for event in events] + [2400]) + 1200, "events": events},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(doc, indent=2) + "\n")
    return CompileResult(
        source=str(input_path),
        output=str(output_path),
        nodes=len(nodes),
        animation_tokens=len(animations),
        target_count=len(targets),
        timeline_events=len(events),
    )


def validate_path(path: Path) -> dict[str, Any]:
    raw = load_json(path)
    if raw.get("type") == "excalidrawlib":
        lib = load_library(path)
        token_count = 0
        node_count = 0
        for item in lib.libraryItems:
            for element in item.elements:
                ops = element.ops()
                token_count += isinstance(ops, OpsAnimation)
                node_count += isinstance(ops, OpsNode)
        return {
            "schema": "ops_excalidraw.validate.v1",
            "status": "PASS",
            "kind": "library",
            "items": len(lib.libraryItems),
            "nodes": node_count,
            "animation_tokens": token_count,
        }
    scene = ExcalidrawScene.model_validate(raw)
    nodes, animations = classify(scene)
    for token_el, token in animations:
        resolve_target(token_el, token, nodes)
    return {
        "schema": "ops_excalidraw.validate.v1",
        "status": "PASS",
        "kind": "scene",
        "elements": len(live_elements(scene)),
        "nodes": len(nodes),
        "animation_tokens": len(animations),
    }


def base_element(element_id: str, kind: str, x: int, y: int, width: int, height: int, custom: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": element_id,
        "type": kind,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": "#1e88e5",
        "backgroundColor": "transparent",
        "fillStyle": "hachure",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [element_id + "-group"],
        "frameId": None,
        "roundness": {"type": 3},
        "seed": int(hashlib.sha256(element_id.encode()).hexdigest()[:8], 16) % 999999,
        "version": 1,
        "versionNonce": int(hashlib.sha256((element_id + "nonce").encode()).hexdigest()[:8], 16) % 999999,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "customData": {"opsExcalidraw": custom},
    }


def text_element(element_id: str, x: int, y: int, text: str, group: str) -> dict[str, Any]:
    element = base_element(element_id, "text", x, y, max(80, len(text) * 10), 28, {})
    element.update(
        {
            "text": text,
            "fontSize": 20,
            "fontFamily": 5,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": None,
            "originalText": text,
            "lineHeight": 1.25,
            "groupIds": [group],
            "customData": None,
        }
    )
    return element


# Comprehensive node palette for live strategy whiteboarding. Grounded in
# system-design interview component libraries (queue/LB/cache/DB/vector store/
# LLM blocks) plus this workstation's real projects: memory (graph+vector
# recall), tau (DAG creator/reviewer gates), sparta (controls/QRA evidence).
NODE_SPECS: list[tuple[str, str, dict[str, Any]]] = [
    # generic strategy blocks
    ("target-card", "Target", {"title": "Strategy step", "detail": "evidence-backed", "accent": "green"}),
    ("node-decision", "Decision", {"title": "Decision", "detail": "choose + why", "accent": "amber"}),
    ("node-risk", "Risk", {"title": "Risk", "detail": "blast radius", "accent": "red"}),
    ("node-question", "Question", {"title": "Open question", "detail": "needs answer", "accent": "orange"}),
    ("node-milestone", "Milestone", {"title": "Milestone", "detail": "done when...", "accent": "white"}),
    ("node-actor", "Actor", {"title": "Actor", "detail": "human/system user", "accent": "cyan"}),
    ("node-evidence", "Evidence", {"title": "Evidence", "detail": "receipt-backed", "accent": "green"}),
    # system-design blocks
    ("node-service", "Service", {"title": "Service", "detail": "deployable unit", "accent": "cyan"}),
    ("node-api-gateway", "API GW", {"title": "API gateway", "detail": "routing/auth", "accent": "cyan"}),
    ("node-database", "Database", {"title": "Database", "detail": "relational store", "accent": "cyan"}),
    ("node-queue", "Queue", {"title": "Message queue", "detail": "async decouple", "accent": "amber"}),
    ("node-cache", "Cache", {"title": "Cache", "detail": "hot path", "accent": "orange"}),
    ("node-load-balancer", "LB", {"title": "Load balancer", "detail": "fan-out traffic", "accent": "cyan"}),
    ("node-llm", "LLM", {"title": "LLM", "detail": "model call", "accent": "white"}),
    # memory project (graph memory stack)
    ("node-graph-db", "Graph DB", {"title": "Graph DB", "detail": "ArangoDB collections/edges", "accent": "cyan"}),
    ("node-vector-store", "Vectors", {"title": "Vector store", "detail": "Qdrant semantic sync", "accent": "white"}),
    ("node-embedder", "Embedder", {"title": "Embedder", "detail": "text/multimodal vectors", "accent": "white"}),
    ("node-recall", "Recall", {"title": "Memory recall", "detail": "BM25+dense+graph hop", "accent": "green"}),
    # tau project (DAG orchestration)
    ("node-dag", "DAG", {"title": "Tau DAG", "detail": "immutable goal contract", "accent": "cyan"}),
    ("node-creator", "Creator", {"title": "Creator", "detail": "implements the change", "accent": "green"}),
    ("node-reviewer", "Reviewer", {"title": "Reviewer", "detail": "VERDICT: PASS/FAIL", "accent": "amber"}),
    ("node-gate", "Gate", {"title": "Gate", "detail": "deterministic check", "accent": "red"}),
    ("node-receipt", "Receipt", {"title": "Receipt", "detail": "durable proof artifact", "accent": "green"}),
    # sparta project (compliance pipeline)
    ("node-control", "Control", {"title": "Control", "detail": "framework control ref", "accent": "cyan"}),
    ("node-qra", "QRA", {"title": "QRA", "detail": "question/reasoning/answer", "accent": "cyan"}),
    ("node-crosswalk", "Crosswalk", {"title": "Crosswalk", "detail": "framework mapping edge", "accent": "orange"}),
    ("node-pipeline-stage", "Stage", {"title": "Pipeline stage", "detail": "ingest -> QRA -> validate", "accent": "amber"}),
]


def toolkit(output: Path) -> None:
    items = []
    specs = [
        ("source-node", "Source", base_element("source", "rectangle", 0, 0, 220, 110, {"kind": "node", "role": "source", "title": "Client context", "subtitle": "interview source"})),
    ]
    for node_id, label, meta in NODE_SPECS:
        custom = {"kind": "node", "role": "target", **meta}
        specs.append((node_id, label, base_element(node_id, "rectangle", 0, 0, 220, 110, custom)))
    specs += [
        ("anim-reveal", "Reveal", base_element("anim-reveal", "diamond", 0, 0, 72, 72, {"kind": "animation", "preset": "reveal", "startMs": 0, "durationMs": 600})),
        ("anim-line-draw", "Line draw", base_element("anim-line-draw", "diamond", 0, 0, 72, 72, {"kind": "animation", "preset": "line-draw", "startMs": 600, "durationMs": 700})),
        ("anim-glow-pulse", "Glow", base_element("anim-glow-pulse", "ellipse", 0, 0, 72, 72, {"kind": "animation", "preset": "glow-pulse", "targetId": "source", "startMs": 1200, "durationMs": 900})),
        ("anim-highlight", "Highlight", base_element("anim-highlight", "ellipse", 0, 0, 72, 72, {"kind": "animation", "preset": "highlight", "startMs": 1600, "durationMs": 700})),
        ("anim-pulse", "Pulse", base_element("anim-pulse", "ellipse", 0, 0, 72, 72, {"kind": "animation", "preset": "pulse", "startMs": 2000, "durationMs": 700})),
    ]
    for item_id, label, element in specs:
        group = element["groupIds"][0]
        items.append({"id": item_id, "status": "published", "elements": [element, text_element(item_id + "-label", 0, 86, label, group)]})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"type": "excalidrawlib", "version": 2, "source": "ops-excalidraw", "libraryItems": items}, indent=2) + "\n")


def fail(exc: Exception) -> None:
    """Print a typed failure and exit non-zero."""

    print(json.dumps({"schema": "ops_excalidraw.error.v1", "status": "FAIL", "error": str(exc)}), file=sys.stderr)
    raise typer.Exit(1)


@app.command(name="toolkit")
def toolkit_command(output: Path = typer.Option(..., "--output", help="Destination .excalidrawlib file.")) -> None:
    """Write the reusable interview animation toolkit."""

    try:
        toolkit(output)
        print(json.dumps(validate_path(output)))
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        fail(exc)


@app.command(name="validate")
def validate_command(path: Path) -> None:
    """Validate a .excalidraw board or .excalidrawlib toolkit."""

    try:
        print(json.dumps(validate_path(path)))
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        fail(exc)


@app.command(name="compile")
def compile_command(input_path: Path, output_path: Path) -> None:
    """Compile a board into create-svg scene/timeline JSON."""

    try:
        print(compile_scene(input_path, output_path).model_dump_json(by_alias=True))
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        fail(exc)


@app.command(name="quickstart")
def quickstart_command(port: int = typer.Option(7683, "--port", help="Local port.")) -> None:
    """One-command setup: regenerate the toolkit, then serve the whiteboard page."""

    toolkit_path = SKILL_DIR / "assets/toolkits/interview-animation-toolkit.excalidrawlib"
    toolkit(toolkit_path)
    print(json.dumps({"schema": "ops_excalidraw.quickstart.v1", "toolkit": str(toolkit_path), "next": f"open http://127.0.0.1:{port}/ — tick libraries in the side panel, drag blocks, press Render SVG"}), flush=True)
    whiteboard_command(port)


@app.command(name="push-board")
def push_board_command(
    board: Path,
    port: int = typer.Option(7683, "--port", help="Whiteboard server port."),
    replace: bool = typer.Option(False, "--replace", help="Unsafe: replace the live canvas directly instead of proposing."),
) -> None:
    """Propose a board to the whiteboard (human Accepts/Rejects); --replace applies it directly."""

    import urllib.request

    try:
        load_scene(board)  # fail closed before pushing
        endpoint = "board" if replace else "proposal"
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/{endpoint}", data=board.read_bytes(), method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(json.dumps({"schema": "ops_excalidraw.push_board.v1", "status": "PASS", "mode": endpoint, **json.loads(resp.read())}))
    except Exception as exc:  # noqa: BLE001 - single CLI boundary
        fail(exc)


@app.command(name="render-board")
def render_board_command(
    board: Path,
    output: Path = typer.Option(..., "--output", help="Destination .svg file."),
    show: bool = typer.Option(False, "--show", help="Open the rendered SVG in the default viewer."),
) -> None:
    """Compile a board and render it to an SVG file (no browser needed)."""

    import subprocess
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp) / "scene.yml"
            compile_scene(board, scene)
            render = subprocess.run(
                [str(SKILL_DIR / "../create-svg/run.sh"), "render", str(scene), str(output)],
                capture_output=True, text=True, timeout=120,
            )
            if render.returncode != 0 or not output.exists():
                raise ValueError(render.stderr[-2000:] or "create-svg render failed")
        if show:
            subprocess.Popen(["xdg-open", str(output)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(json.dumps({"schema": "ops_excalidraw.render_board.v1", "status": "PASS", "output": str(output), "bytes": output.stat().st_size}))
    except (OSError, ValueError, ValidationError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        fail(exc)


@app.command(name="push-library")
def push_library_command(
    library: Path,
    port: int = typer.Option(7683, "--port", help="Whiteboard server port."),
) -> None:
    """Persist custom library items to the running whiteboard's personal library."""

    import urllib.request

    try:
        lib = load_library(library)  # fail closed before pushing
        items = json.dumps([item.model_dump(by_alias=True) for item in lib.libraryItems]).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/personal-library", data=items, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(json.dumps({"schema": "ops_excalidraw.push_library.v1", "status": "PASS", **json.loads(resp.read())}))
    except Exception as exc:  # noqa: BLE001 - single CLI boundary
        fail(exc)


@app.command(name="whiteboard")
def whiteboard_command(port: int = typer.Option(7683, "--port", help="Local port.")) -> None:
    """Serve the embedded Excalidraw whiteboard with render button and library toggles."""

    import runpy
    import sys as _sys

    _sys.argv = ["whiteboard_server.py", str(port)]
    runpy.run_path(str(Path(__file__).with_name("whiteboard_server.py")), run_name="__main__")


if __name__ == "__main__":
    app()
