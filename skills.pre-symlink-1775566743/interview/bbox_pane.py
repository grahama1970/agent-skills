"""Bounding-box annotation pane for the Interview skill.

Provides an interactive canvas where humans draw/edit/delete bounding boxes
on PDF page images. Used by pdf-lab for convergence feedback, and available
to any consuming skill via the pane registry.

HTML mode: full canvas with draw/select/delete, label toolbar, pre-annotations.
TUI mode:  fallback showing pre-annotations as a numbered list + hint to use HTML.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .images import load_image_for_html


def prepare_bbox_image(path: str | Path, max_width: int = 900) -> str:
    """Load an image at higher resolution for annotation overlay.

    Returns a data URI string, or empty string on failure.
    """
    return load_image_for_html(path, max_width=max_width)


def _default_labels() -> list[dict]:
    """Default label set when none provided."""
    return [
        {"name": "Table", "color": "#22c55e"},
        {"name": "Section", "color": "#3b82f6"},
        {"name": "Figure", "color": "#f59e0b"},
        {"name": "Delete", "color": "#ef4444"},
    ]


def generate_bbox_annotation_pane(
    question: dict,
    base_path: Path | None = None,
) -> str:
    """Generate HTML for a bbox annotation question pane.

    Args:
        question: Question dict with id, text, images, bbox_labels, pre_annotations, etc.
        base_path: Base path for resolving relative image paths.

    Returns:
        HTML string for the question pane.
    """
    qid = question["id"]
    text = question.get("text", "").replace("\n", "<br>")
    images = question.get("images", [])
    bbox_labels = question.get("bbox_labels") or _default_labels()
    pre_annotations = question.get("pre_annotations") or []
    render_dpi = question.get("render_dpi", 150)
    page_num = question.get("page_num", 0)

    # Resolve image path
    image_data_uri = ""
    if images:
        img_path = Path(images[0])
        if base_path and not img_path.is_absolute():
            img_path = base_path / img_path
        image_data_uri = prepare_bbox_image(img_path)

    # Build label toolbar buttons
    label_buttons_html = ""
    for i, lbl in enumerate(bbox_labels):
        name = lbl["name"]
        color = lbl["color"]
        active_class = "active" if i == 0 else ""
        shortcut = i + 1 if i < 9 else ""
        label_buttons_html += (
            f'<button class="bbox-label-btn {active_class}" '
            f'data-label="{name}" data-color="{color}" '
            f'onclick="setBboxLabel(\'{qid}\', \'{name}\', \'{color}\')" '
            f'style="--label-color: {color}">'
            f'<span class="bbox-label-key">{shortcut}</span> {name}'
            f'</button>\n'
        )

    # Pre-annotations JSON
    pre_ann_json = json.dumps(pre_annotations)
    labels_json = json.dumps(bbox_labels)

    # Annotation list (initial)
    ann_list_html = ""
    if pre_annotations:
        for i, ann in enumerate(pre_annotations):
            ann_type = ann.get("type", "?")
            bbox = ann.get("bbox", [0, 0, 0, 0])
            ann_list_html += (
                f'<div class="bbox-ann-item" data-idx="{i}">'
                f'<span class="bbox-ann-type">{ann_type}</span> '
                f'<span class="bbox-ann-coords">'
                f'[{bbox[0]:.0f}, {bbox[1]:.0f}, {bbox[2]:.0f}, {bbox[3]:.0f}]'
                f'</span>'
                f'<button class="bbox-ann-delete" onclick="deleteBboxAnnotation(\'{qid}\', {i})"'
                f' title="Delete">x</button>'
                f'</div>'
            )

    # Image or placeholder
    canvas_html = ""
    if image_data_uri:
        canvas_html = (
            f'<div class="bbox-canvas-container" id="bbox-container-{qid}">'
            f'<img src="{image_data_uri}" class="bbox-base-image" '
            f'id="bbox-img-{qid}" draggable="false">'
            f'<canvas class="bbox-overlay" id="bbox-canvas-{qid}"></canvas>'
            f'</div>'
        )
    else:
        canvas_html = (
            '<div class="bbox-no-image">'
            'No image available for annotation. '
            'Ensure PDF screenshots are generated first.'
            '</div>'
        )

    return f'''
    <div class="question-pane" id="pane-{qid}">
        <div class="max-w-4xl mx-auto">
            <div class="text-lg mb-4">{text}</div>

            <!-- Label toolbar -->
            <div class="bbox-toolbar" id="bbox-toolbar-{qid}">
                <span class="bbox-toolbar-label">Labels:</span>
                {label_buttons_html}
                <span class="bbox-toolbar-hint">
                    Draw: click+drag · Select: click box · Delete: <kbd>Del</kbd> · Undo: <kbd>Ctrl+Z</kbd>
                </span>
            </div>

            <!-- Canvas -->
            {canvas_html}

            <!-- Annotation list -->
            <div class="bbox-ann-list" id="bbox-ann-list-{qid}">
                <div class="bbox-ann-header">Annotations ({len(pre_annotations)})</div>
                {ann_list_html}
            </div>

            <!-- Hidden data for JS -->
            <script>
                (function() {{
                    if (!window._bboxData) window._bboxData = {{}};
                    window._bboxData['{qid}'] = {{
                        labels: {labels_json},
                        preAnnotations: {pre_ann_json},
                        renderDpi: {render_dpi},
                        pageNum: {page_num}
                    }};
                }})();
            </script>
        </div>
    </div>
    '''


def create_bbox_tui_pane(question: Any, base_path: Path | None = None) -> Any:
    """Create a TUI pane for bbox annotation (fallback mode).

    Args:
        question: Question object with bbox fields.
        base_path: Base path for resolving images.

    Returns:
        A BboxAnnotationPane TabPane instance.
    """
    from .tui_panes import BboxAnnotationPane
    return BboxAnnotationPane(question, base_path=base_path)
