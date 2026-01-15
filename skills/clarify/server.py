from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.serving import make_server

from .types import ClarifyQuestion

CLARIFY_DIR = Path(__file__).resolve().parent
DIST_DIR = CLARIFY_DIR / "ui" / "dist"


class ClarifyServer:
    def __init__(self, step_name: str, attempt: int, questions: List[ClarifyQuestion]):
        if not DIST_DIR.exists():
            raise RuntimeError(
                f"Clarify UI build not found at {DIST_DIR}. Run `npm --prefix {CLARIFY_DIR}/ui run build` first."
            )
        self.step_name = step_name
        self.attempt = attempt
        self.questions = questions
        self._event = threading.Event()
        self.responses: List[Dict[str, Any]] | None = None
        self.payload: Dict[str, Any] | None = None
        self._server = None
        self._thread: threading.Thread | None = None

    def _session_payload(self) -> Dict[str, Any]:
        return {
            "step": self.step_name,
            "attempt": self.attempt,
            "questions": [asdict(q) for q in self.questions],
        }

    def _create_app(self) -> Flask:
        app = Flask(__name__, static_folder=str(DIST_DIR), static_url_path="/")
        session_payload = self._session_payload()
        event = self._event
        server = self

        @app.route("/api/questions", methods=["GET"])
        def api_questions():
            return jsonify(session_payload)

        @app.route("/api/responses", methods=["POST"])
        def api_responses():
            data = request.get_json(silent=True) or {}
            responses = data.get("responses")
            if not isinstance(responses, list):
                return jsonify({"ok": False, "error": "responses must be a list"}), 400
            server.responses = responses
            server.payload = data
            event.set()
            return jsonify({"ok": True})

        @app.route("/favicon.ico")
        def favicon():
            return ("", 204)

        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_frontend(path: str):
            target = DIST_DIR / path
            if path and target.exists() and target.is_file():
                return send_from_directory(DIST_DIR, path)
            return send_from_directory(DIST_DIR, "index.html")

        return app

    def start(self) -> int:
        app = self._create_app()
        server = make_server("127.0.0.1", 0, app)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        return port

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=1)
