#!/usr/bin/env python3
"""
HTTP Server for Interview HTML Form.

Serves Tailwind-styled form and collects responses.
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


def generate_question_html(question: dict) -> str:
    """Generate HTML for a single question card."""
    qid = question["id"]
    qtype = question.get("type", "yes_no_refine")
    text = question["text"].replace("\n", "<br>")
    recommendation = question.get("recommendation", "")
    reason = question.get("reason", "")
    options = question.get("options", [])

    # Recommendation badge
    rec_html = ""
    if recommendation:
        rec_class = "recommendation-keep" if recommendation.lower() in ("keep", "yes") else "recommendation-drop"
        rec_html = f'''
        <div class="border-l-4 p-3 mb-4 {rec_class}">
            <div class="font-semibold">Agent Recommendation: {recommendation.upper()}</div>
            {f'<div class="text-sm mt-1">{reason}</div>' if reason else ''}
        </div>
        '''

    # Options HTML based on type
    options_html = ""

    if qtype in ("yes_no", "yes_no_refine"):
        options_html = f'''
        <div class="space-y-2">
            {'<label class="flex items-center p-2 rounded hover:bg-gray-50 cursor-pointer"><input type="radio" name="' + qid + '" value="accept" class="mr-3 h-4 w-4 text-blue-600"> <span class="font-medium text-blue-600">Accept recommendation</span></label>' if recommendation else ''}
            <label class="flex items-center p-2 rounded hover:bg-gray-50 cursor-pointer">
                <input type="radio" name="{qid}" value="keep" class="mr-3 h-4 w-4 text-green-600">
                <span>Yes / Keep</span>
            </label>
            <label class="flex items-center p-2 rounded hover:bg-gray-50 cursor-pointer">
                <input type="radio" name="{qid}" value="drop" class="mr-3 h-4 w-4 text-red-600">
                <span>No / Drop</span>
            </label>
        </div>
        '''

        if qtype == "yes_no_refine":
            options_html += f'''
            <div class="mt-3">
                <input type="text" id="refine_{qid}" placeholder="Refinement notes (optional)"
                       class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
            </div>
            '''

    elif qtype == "select":
        opts = ""
        if recommendation:
            opts += f'''
            <label class="flex items-center p-2 rounded hover:bg-gray-50 cursor-pointer">
                <input type="radio" name="{qid}" value="accept" class="mr-3 h-4 w-4 text-blue-600">
                <span class="font-medium text-blue-600">Accept: {recommendation}</span>
            </label>
            '''
        for opt in options:
            opts += f'''
            <label class="flex items-center p-2 rounded hover:bg-gray-50 cursor-pointer">
                <input type="radio" name="{qid}" value="{opt}" class="mr-3 h-4 w-4">
                <span>{opt}</span>
            </label>
            '''
        options_html = f'<div class="space-y-2">{opts}</div>'

    elif qtype == "multi":
        opts = ""
        for opt in options:
            checked = "checked" if recommendation and opt in recommendation else ""
            opts += f'''
            <label class="flex items-center p-2 rounded hover:bg-gray-50 cursor-pointer">
                <input type="checkbox" name="{qid}" value="{opt}" {checked} class="mr-3 h-4 w-4 text-blue-600 rounded">
                <span>{opt}</span>
            </label>
            '''
        options_html = f'<div class="space-y-2">{opts}</div>'

    elif qtype == "text":
        default = recommendation or ""
        options_html = f'''
        <textarea name="{qid}" rows="3" placeholder="Your response"
                  class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500">{default}</textarea>
        '''

    elif qtype == "confirm":
        options_html = f'''
        <div class="flex space-x-4">
            <label class="flex items-center p-3 border rounded-lg hover:bg-green-50 cursor-pointer flex-1 justify-center">
                <input type="radio" name="{qid}" value="confirm" class="mr-2 h-4 w-4 text-green-600">
                <span class="font-medium text-green-600">Confirm</span>
            </label>
            <label class="flex items-center p-3 border rounded-lg hover:bg-red-50 cursor-pointer flex-1 justify-center">
                <input type="radio" name="{qid}" value="cancel" class="mr-2 h-4 w-4 text-red-600">
                <span class="font-medium text-red-600">Cancel</span>
            </label>
        </div>
        '''

    return f'''
    <div class="question-card bg-white rounded-lg shadow-md p-6"
         data-qid="{qid}" data-qtype="{qtype}" data-recommendation="{recommendation}">
        <div class="prose max-w-none mb-4">
            <div class="text-gray-800 whitespace-pre-wrap">{text}</div>
        </div>
        {rec_html}
        {options_html}
    </div>
    '''


def render_form(session: "Session") -> str:
    """Render the full HTML form."""
    template_path = TEMPLATES_DIR / "form.html"
    template = template_path.read_text()

    # Generate questions HTML
    questions_html = ""
    for i, q in enumerate(session.questions, 1):
        questions_html += f'<div class="text-sm text-gray-500 mb-2">Question {i} of {len(session.questions)}</div>'
        questions_html += generate_question_html(q.to_dict())

    # Replace placeholders
    html = template.replace("{{TITLE}}", session.title)
    html = html.replace("{{CONTEXT}}", session.context or "")
    html = html.replace("{{SESSION_ID}}", session.id)
    html = html.replace("{{TOTAL}}", str(len(session.questions)))
    html = html.replace("{{QUESTIONS_HTML}}", questions_html)

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
