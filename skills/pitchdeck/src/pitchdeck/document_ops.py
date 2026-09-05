"""Structural edits on a canonical deck.document.json: elements, slides,
images, crops, and agent-generated figures.

Every op loads the document, mutates a copy, re-validates the WHOLE model, and
only then writes the document and re-projects deck.data.json (+ assets/).
A rejected op changes nothing on disk. Inputs are paths/ids/fractions; there
is no free-form command execution — figures come from the create-figure and
create-svg skills' own CLIs with fixed argument shapes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .asset_ops import _IMAGE_SUFFIXES, _verify_asset_content
from .document import Bbox, DeckDocument, DocElement, DocElementKind, DocSlide, DocTextStyle
from .document_ui import project_document_to_ui
from .models import AssetKind, AssetSpec, AssetStatus, Visibility

SKILLS = Path(__file__).resolve().parents[3]


def _load(document: Path) -> DeckDocument:
    return DeckDocument.model_validate(json.loads(document.read_text(encoding="utf-8")))


def _slide(doc: DeckDocument, slide_id: str) -> DocSlide:
    slide = next((s for s in doc.slides if s.id == slide_id), None)
    if slide is None:
        raise ValueError(f"unknown slide '{slide_id}'")
    return slide


def _unique(existing: set[str], stem: str) -> str:
    stem = re.sub(r"[^a-z0-9-]+", "-", stem.lower()).strip("-") or "item"
    candidate, n = stem, 2
    while candidate in existing:
        candidate, n = f"{stem}-{n}", n + 1
    return candidate


def _commit(document: Path, doc: DeckDocument, output_dir: Path, asset_base: Path) -> dict:
    """Full-model revalidation, then write document + projection together."""
    revalidated = DeckDocument.model_validate(json.loads(doc.model_dump_json(by_alias=True)))
    payload = project_document_to_ui(revalidated)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for asset in revalidated.assets:
        raw = os.path.expandvars(str(asset.local_path or ""))
        if not raw:
            continue
        source = Path(raw) if Path(raw).is_absolute() else asset_base / raw
        if not source.is_file():
            raise ValueError(f"asset '{asset.id}' not found at {source}")
        target = assets_dir / source.name
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copy(source, target)
        index.append({"id": asset.id, "kind": asset.kind.value, "alt_text": asset.alt_text, "file": f"assets/{source.name}"})
    existing_path = output_dir / "deck.data.json"
    revision = int(json.loads(existing_path.read_text()).get("revision", 0)) + 1 if existing_path.exists() else 1
    payload["revision"] = revision
    payload["assets_index"] = index
    document.write_text(revalidated.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
    existing_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return {"status": "PASS", "revision": revision}


def register_image(doc: DeckDocument, document_dir: Path, file: Path, alt: str, *, kind: AssetKind = AssetKind.ILLUSTRATION,
                   generation_brief: str | None = None) -> AssetSpec:
    """Copy a file into the bundle's assets/ (magic-bytes checked) and register it."""
    suffix = file.suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        raise ValueError(f"unsupported image type '{suffix}'; allowed: {sorted(_IMAGE_SUFFIXES)}")
    if not alt.strip():
        raise ValueError("alt text is required")
    _verify_asset_content(file, suffix)
    # New assets live beside the DOCUMENT (absolute path), never inside the
    # shared example bundle that asset_base may point at.
    assets_dir = document_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    asset_id = _unique({a.id for a in doc.assets}, file.stem)
    target = assets_dir / f"{asset_id}{suffix}"
    shutil.copy(file, target)
    spec = AssetSpec(id=asset_id, kind=kind, visibility=Visibility.PUBLIC, local_path=str(target.resolve()),
                     alt_text=alt.strip(), status=AssetStatus.PRESENT, generation_brief=generation_brief)
    doc.assets.append(spec)
    return spec


def add_element(doc: DeckDocument, slide_id: str, *, kind: str, text: str | None = None, asset_id: str | None = None,
                bbox: Bbox | None = None) -> DocElement:
    slide = _slide(doc, slide_id)
    ids = {e.id for e in slide.elements}
    z = max((e.z for e in slide.elements), default=0) + 1
    bbox = bbox or Bbox(x=0.3, y=0.35, w=0.4, h=0.3)
    if kind == "text":
        el = DocElement(id=_unique(ids, "text"), kind=DocElementKind.TEXT, bbox=bbox, z=z, role="callout",
                        text=text or "New text", style=DocTextStyle())
    elif kind == "image":
        if not any(a.id == asset_id for a in doc.assets):
            raise ValueError(f"asset '{asset_id}' is not registered")
        el = DocElement(id=_unique(ids, f"img-{asset_id}"), kind=DocElementKind.IMAGE, bbox=bbox, z=z, role="visual", asset_id=asset_id)
    else:
        raise ValueError("kind must be text or image")
    slide.elements.append(el)
    return el


def delete_element(doc: DeckDocument, slide_id: str, element_id: str) -> None:
    slide = _slide(doc, slide_id)
    if not any(e.id == element_id for e in slide.elements):
        raise ValueError(f"unknown element '{element_id}'")
    if len(slide.elements) == 1:
        raise ValueError("a slide must keep at least one element; delete the slide instead")
    slide.elements = [e for e in slide.elements if e.id != element_id]
    slide.bindings = [b for b in slide.bindings if not b.path.startswith(f"element:{element_id}")]


def set_crop(doc: DeckDocument, slide_id: str, element_id: str, crop: Bbox | None) -> None:
    el = next((e for e in _slide(doc, slide_id).elements if e.id == element_id), None)
    if el is None or el.kind is not DocElementKind.IMAGE:
        raise ValueError("crop applies to an existing image element")
    el.crop = crop


def _renumber(doc: DeckDocument) -> None:
    for i, s in enumerate(doc.slides, 1):
        s.order = i


def slide_op(doc: DeckDocument, op: str, slide_id: str) -> str:
    slide = _slide(doc, slide_id)
    i = doc.slides.index(slide)
    if op == "delete":
        if len(doc.slides) == 1:
            raise ValueError("cannot delete the only slide")
        doc.slides.pop(i)
    elif op in {"duplicate", "add_after"}:
        new_id = _unique({s.id for s in doc.slides}, f"{slide.id}-copy" if op == "duplicate" else "new-slide")
        copy = slide.model_copy(deep=True) if op == "duplicate" else DocSlide(
            id=new_id, order=1, layout_origin=slide.layout_origin, transition=slide.transition, reveal=slide.reveal,
            elements=[DocElement(id="title", kind=DocElementKind.TEXT, bbox=Bbox(x=0.06, y=0.07, w=0.88, h=0.12), role="title",
                                 text="New slide", style=DocTextStyle(size_pt=28, bold=True))])
        copy.id = new_id
        if op == "duplicate":
            copy.claim_ids, copy.bindings = [], []  # provenance is per occurrence; a copy is not approved
        doc.slides.insert(i + 1, copy)
        slide_id = new_id
    elif op in {"move_left", "move_right"}:
        j = i - 1 if op == "move_left" else i + 1
        if not 0 <= j < len(doc.slides):
            raise ValueError("slide is already at the edge")
        doc.slides[i], doc.slides[j] = doc.slides[j], doc.slides[i]
    elif op in {"hide", "show"}:
        slide.hidden = op == "hide"
    else:
        raise ValueError(f"unknown slide op '{op}'")
    _renumber(doc)
    return slide_id


def render_figure(kind: str, spec: Path, *, chart_type: str = "bar", title: str = "Figure", workdir: Path) -> Path:
    """Generate an image through the owning skill CLI. kind=chart uses
    create-figure metrics (JSON metrics -> SVG); kind=diagram uses create-svg
    render (scene YAML -> deterministic SVG)."""
    if kind == "chart":
        if chart_type not in {"bar", "hbar", "pie", "line"}:
            raise ValueError("chart_type must be bar, hbar, pie or line")
        out = workdir / "chart.svg"
        cmd = [str(SKILLS / "create-figure/run.sh"), "metrics", "--input", str(spec), "--output", str(out), "--type", chart_type, "--title", title]
    elif kind == "diagram":
        out = workdir / "diagram.svg"
        cmd = [str(SKILLS / "create-svg/run.sh"), "render", str(spec), str(out)]
    else:
        raise ValueError("kind must be chart or diagram")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode or not out.is_file():
        raise ValueError(f"{cmd[0]} failed: {(proc.stderr or proc.stdout).strip()[-600:]}")
    return out


def apply(document: Path, output_dir: Path, asset_base: Path, op: str, **kw) -> dict:
    doc = _load(document)
    result: dict = {"op": op}
    if op == "add-text":
        result["element"] = add_element(doc, kw["slide_id"], kind="text", text=kw.get("text")).id
    elif op == "add-image":
        spec = register_image(doc, document.parent, Path(kw["file"]), kw["alt"], generation_brief=kw.get("generation_brief"))
        result["asset"] = spec.id
        result["element"] = add_element(doc, kw["slide_id"], kind="image", asset_id=spec.id, bbox=kw.get("bbox")).id
    elif op in {"add-chart", "add-diagram"}:
        with tempfile.TemporaryDirectory(prefix="pitchdeck-figure-") as tmp:
            image = render_figure(op.split("-")[1], Path(kw["spec"]), chart_type=kw.get("chart_type", "bar"),
                                  title=kw.get("title", "Figure"), workdir=Path(tmp))
            brief = f"{op} from {Path(kw['spec']).name} via {'create-figure' if op == 'add-chart' else 'create-svg'}"
            spec = register_image(doc, document.parent, image, kw["alt"], kind=AssetKind.DIAGRAM, generation_brief=brief)
        result["asset"] = spec.id
        result["element"] = add_element(doc, kw["slide_id"], kind="image", asset_id=spec.id, bbox=kw.get("bbox")).id
    elif op == "delete-element":
        delete_element(doc, kw["slide_id"], kw["element_id"])
    elif op == "crop":
        set_crop(doc, kw["slide_id"], kw["element_id"], kw.get("bbox"))
    elif op.startswith("slide-"):
        result["slide"] = slide_op(doc, op[len("slide-"):], kw["slide_id"])
    else:
        raise ValueError(f"unknown op '{op}'")
    result.update(_commit(document, doc, output_dir, asset_base))
    return result
