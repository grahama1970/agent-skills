#!/usr/bin/env python3
"""
HTTP Server for Interview HTML Form.

Serves wizard-style form with tabbed navigation matching Claude Code's UX.
"""
from __future__ import annotations

import json
import os
import sys
import webbrowser
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

if TYPE_CHECKING:
    from .interview import Session

SCRIPT_DIR = Path(__file__).parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"


def generate_question_pane(question: dict, base_path: Path | None = None) -> str:
    """Generate HTML for a question pane (wizard-style).

    Args:
        question: Question dict with id, text, header, options, images, multi_select
        base_path: Base path for resolving relative image paths
    """
    from .images import render_images_for_html, render_comparison_images_for_html
    from .registry import get_html_renderer

    qid = question["id"]
    text = question["text"].replace("\n", "<br>")
    options = question.get("options", [])
    images = question.get("images", [])
    multi_select = question.get("multi_select", False)
    question_type = question.get("type", "yes_no_refine")
    comparison_images = question.get("comparison_images", [])
    allow_custom_image = question.get("allow_custom_image", False)

    # Check registry for custom pane renderer
    renderer = get_html_renderer(question_type)
    if renderer:
        return renderer(question, base_path)

    # Handle image_compare type specially
    if question_type == "image_compare" and comparison_images:
        return generate_image_compare_pane(question, base_path)

    # Code block HTML
    code_block = question.get("code_block")
    code_lang = question.get("code_lang", "")
    code_html = ""
    if code_block:
        import html as html_mod
        escaped_code = html_mod.escape(code_block)
        lang_class = f' class="language-{code_lang}"' if code_lang else ""
        code_html = f'''
        <pre style="background:#1e293b;color:#e2e8f0;padding:1rem;border-radius:0.5rem;
                    overflow-x:auto;font-size:0.875rem;margin:1rem 0;border:1px solid #334155;">
            <code{lang_class}>{escaped_code}</code>
        </pre>
        '''

    # Images HTML (actual images for HTML mode)
    images_html = ""
    if images:
        image_data = render_images_for_html(images, base_path)
        for img in image_data:
            if img["valid"]:
                images_html += f'''
                <img src="{img['data_uri']}" alt="{img['alt']}" class="question-image">
                '''
            else:
                images_html += f'''
                <div class="image-placeholder">{img['alt']}</div>
                '''

    # Multi-select hint
    multi_hint = ""
    if multi_select:
        multi_hint = '<div class="multi-hint">(Select multiple with Space, Enter to confirm)</div>'

    # Options HTML - numbered list with descriptions
    options_html = ""
    for i, opt in enumerate(options, 1):
        # Handle both dict (new format) and string (old format)
        if isinstance(opt, dict):
            label = opt.get("label", "")
            description = opt.get("description", "")
        else:
            label = str(opt)
            description = ""

        desc_html = f'<div class="option-description">{description}</div>' if description else ""
        options_html += f'''
        <div class="option-item" data-label="{label}" onclick="selectOption('{qid}', {i})">
            <div class="option-number">{i}.</div>
            <div class="option-content">
                <div class="option-label">{label}</div>
                {desc_html}
            </div>
        </div>
        '''

    # Add "Other" option with image paste support
    other_index = len(options) + 1
    paste_zone_html = ""
    if allow_custom_image or question_type in ("select", "yes_no_refine"):
        # Always show paste zone for enhanced collaboration
        paste_zone_html = f'''
            <div class="image-paste-zone">
                <div class="paste-hint">
                    <kbd>Ctrl+V</kbd> to paste image or drag & drop
                </div>
            </div>
        '''

    options_html += f'''
    <div class="option-item other-option" onclick="selectOption('{qid}', {other_index}, true)">
        <div class="option-number">{other_index}.</div>
        <div class="option-content">
            <input type="text" class="other-input" placeholder="Other (type your response or paste image)"
                   onclick="event.stopPropagation()"
                   onchange="updateResponse('{qid}'); updateTabCompletion('{qid}')">
            {paste_zone_html}
        </div>
    </div>
    '''

    # Conviction/weight controls (shown after option selection)
    conviction_html = f'''
    <div class="conviction-controls" id="conviction-{qid}" style="display:none;margin-top:1rem;
         padding:0.75rem;background:#f8fafc;border-radius:0.5rem;border:1px solid #e2e8f0;">
        <div style="display:flex;gap:1.5rem;align-items:center;flex-wrap:wrap;">
            <div>
                <span style="font-size:0.75rem;font-weight:600;color:#64748b;text-transform:uppercase;">Conviction</span>
                <div style="display:flex;gap:0.25rem;margin-top:0.25rem;">
                    <button class="conv-btn" data-qid="{qid}" data-field="conviction" data-val="strong"
                        style="padding:0.25rem 0.5rem;border-radius:0.25rem;font-size:0.75rem;cursor:pointer;
                        border:1px solid #cbd5e1;background:white;">Strong</button>
                    <button class="conv-btn" data-qid="{qid}" data-field="conviction" data-val="neutral"
                        style="padding:0.25rem 0.5rem;border-radius:0.25rem;font-size:0.75rem;cursor:pointer;
                        border:1px solid #cbd5e1;background:#e2e8f0;">Neutral</button>
                    <button class="conv-btn" data-qid="{qid}" data-field="conviction" data-val="slight"
                        style="padding:0.25rem 0.5rem;border-radius:0.25rem;font-size:0.75rem;cursor:pointer;
                        border:1px solid #cbd5e1;background:white;">Slight</button>
                </div>
            </div>
            <div>
                <span style="font-size:0.75rem;font-weight:600;color:#64748b;text-transform:uppercase;">Weight</span>
                <div style="display:flex;gap:0.25rem;margin-top:0.25rem;">
                    <button class="conv-btn" data-qid="{qid}" data-field="weight" data-val="critical"
                        style="padding:0.25rem 0.5rem;border-radius:0.25rem;font-size:0.75rem;cursor:pointer;
                        border:1px solid #cbd5e1;background:white;">Critical</button>
                    <button class="conv-btn" data-qid="{qid}" data-field="weight" data-val="important"
                        style="padding:0.25rem 0.5rem;border-radius:0.25rem;font-size:0.75rem;cursor:pointer;
                        border:1px solid #cbd5e1;background:#e2e8f0;">Important</button>
                    <button class="conv-btn" data-qid="{qid}" data-field="weight" data-val="minor"
                        style="padding:0.25rem 0.5rem;border-radius:0.25rem;font-size:0.75rem;cursor:pointer;
                        border:1px solid #cbd5e1;background:white;">Minor</button>
                </div>
            </div>
        </div>
    </div>
    '''

    return f'''
    <div class="question-pane" id="pane-{qid}">
        <div class="max-w-2xl mx-auto">
            <div class="text-lg mb-4">{text}</div>
            {code_html}
            {images_html}
            {multi_hint}
            <div class="options-container">
                {options_html}
            </div>
            {conviction_html}
        </div>
    </div>
    '''


def generate_image_compare_pane(question: dict, base_path: Path | None = None) -> str:
    """Generate HTML for an image comparison question.

    Args:
        question: Question dict with comparison_images
        base_path: Base path for resolving relative image paths
    """
    from .images import render_comparison_images_for_html

    qid = question["id"]
    text = question["text"].replace("\n", "<br>")
    comparison_images = question.get("comparison_images", [])
    allow_custom_image = question.get("allow_custom_image", True)  # Default true for image_compare

    # Render comparison images
    image_data = render_comparison_images_for_html(comparison_images, base_path)

    # Generate image option cards
    image_cards_html = ""
    for i, img in enumerate(image_data):
        img_html = ""
        if img["valid"]:
            img_html = f'<img src="{img["data_uri"]}" alt="{img["label"]}">'
        else:
            img_html = f'<div class="image-placeholder">{img["label"]} (not found)</div>'

        image_cards_html += f'''
        <div class="image-option-card" data-label="{img['label']}" onclick="selectImageOption('{qid}', {i}, '{img['label']}')">
            <div class="image-option-number">{i + 1}</div>
            {img_html}
            <div class="image-option-label">{img['label']}</div>
        </div>
        '''

    # Add custom image option
    if allow_custom_image:
        custom_index = len(image_data)
        image_cards_html += f'''
        <div class="image-option-card custom-image-option" data-label="custom" onclick="selectImageOption('{qid}', {custom_index}, 'custom')">
            <div class="image-option-number">{custom_index + 1}</div>
            <div class="image-paste-zone">
                <div class="paste-hint">
                    <kbd>Ctrl+V</kbd> to paste<br>
                    or drag & drop<br>
                    your own image
                </div>
            </div>
            <input type="text" class="custom-image-reason" placeholder="Why this image? (optional)"
                   onclick="event.stopPropagation()"
                   onchange="updateResponse('{qid}')">
        </div>
        '''

    return f'''
    <div class="question-pane" id="pane-{qid}">
        <div class="max-w-3xl mx-auto">
            <div class="text-lg mb-4">{text}</div>
            <div class="image-compare-grid">
                {image_cards_html}
            </div>
        </div>
    </div>
    '''


def generate_tab_chip(question: dict) -> str:
    """Generate a tab chip for a question."""
    qid = question["id"]
    # Use header if available (max 12 chars), otherwise truncate text
    header = question.get("header") or question["text"][:12]
    return f'<div class="tab-chip" data-tab="{qid}">{header}</div>'


def render_form(session: "Session") -> str:
    """Render the wizard-style HTML form."""
    template_path = TEMPLATES_DIR / "form.html"
    template = template_path.read_text()

    # Get base path for image resolution
    base_path = Path(session.context).parent if session.context else None

    # Generate tabs HTML
    tabs_html = ""
    for q in session.questions:
        tabs_html += generate_tab_chip(q.to_dict())

    # Generate panes HTML
    panes_html = ""
    for q in session.questions:
        panes_html += generate_question_pane(q.to_dict(), base_path)

    # Generate context HTML
    context_html = ""
    if session.context:
        context_html = f'''
        <div class="bg-slate-800 text-slate-300 px-4 py-2 text-sm">
            {session.context}
        </div>
        '''

    # Generate questions JSON for JavaScript
    questions_json = json.dumps([
        {
            "id": q.id,
            "text": q.text,
            "header": q.header,
            "type": q.type,
            "multi_select": q.multi_select,
            "allow_custom_image": q.allow_custom_image,
            "options": [
                {"label": opt.label, "description": opt.description}
                if hasattr(opt, "label") else {"label": str(opt), "description": ""}
                for opt in (q.options or [])
            ],
            **({"bbox_labels": q.bbox_labels} if q.bbox_labels else {}),
            **({"pre_annotations": q.pre_annotations} if q.pre_annotations else {}),
            **({"render_dpi": q.render_dpi} if q.render_dpi != 150 else {}),
            **({"page_num": q.page_num} if q.page_num is not None else {}),
        }
        for q in session.questions
    ])

    # Inject bbox_canvas.js if any bbox_annotation questions exist
    bbox_js = ""
    has_bbox = any(q.type == "bbox_annotation" for q in session.questions)
    if has_bbox:
        bbox_js_path = TEMPLATES_DIR / "bbox_canvas.js"
        if bbox_js_path.exists():
            bbox_js = f"<script>\n{bbox_js_path.read_text()}\n</script>"

    # Replace placeholders
    html = template.replace("{{TITLE}}", session.title)
    html = html.replace("{{CONTEXT_HTML}}", context_html)
    html = html.replace("{{SESSION_ID}}", session.id)
    html = html.replace("{{TABS_HTML}}", tabs_html)
    html = html.replace("{{PANES_HTML}}", panes_html)
    html = html.replace("{{QUESTIONS_JSON}}", questions_json)
    html = html.replace("{{BBOX_CANVAS_JS}}", bbox_js)

    return html


class InterviewHandler(BaseHTTPRequestHandler):
    """HTTP request handler for interview form."""

    session: "Session" = None
    responses: dict = {}
    completed: threading.Event = None

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Serve the form."""
        if self.path == "/" or self.path == "/form":
            html = render_form(self.session)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle form submission."""
        if self.path == "/submit":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()

            try:
                data = json.loads(body)
                InterviewHandler.responses = data.get("responses", {})
                InterviewHandler.completed.set()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self.end_headers()


def run_html_interview(session: "Session", timeout: int) -> dict[str, dict]:
    """
    Run HTML interview in browser.

    Args:
        session: Interview session
        timeout: Timeout in seconds

    Returns:
        Dict mapping question IDs to response dicts
    """
    port = int(os.environ.get("INTERVIEW_PORT", 8765))

    # Find available port
    import socket
    for p in range(port, port + 100):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", p))
            sock.close()
            port = p
            break
        except OSError:
            continue

    # Set up handler
    InterviewHandler.session = session
    InterviewHandler.responses = {}
    InterviewHandler.completed = threading.Event()

    # Start server
    server = HTTPServer(("127.0.0.1", port), InterviewHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"
    print(f"Opening interview form at {url}")

    # Open browser
    webbrowser.open(url)

    # Wait for completion or timeout
    completed = InterviewHandler.completed.wait(timeout=timeout)

    if not completed:
        print(f"\nTimeout after {timeout}s - saving partial responses")

    # Shutdown server
    server.shutdown()

    return InterviewHandler.responses
