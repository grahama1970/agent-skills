"""PySide6 QObject bridge for PDF Lab QML app.

Wraps pdf_lab.py CLI via subprocess — never imports internals directly.
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, Property, Qt, Signal, Slot

_SKILL_DIR = Path(__file__).resolve().parent
_CLI = str(_SKILL_DIR / "pdf_lab.py")
_QUESTION_BOOK = Path.home() / ".pi" / "pdf-lab" / "question_book.jsonl"


class PdfLabBridge(QObject):
    # -- path validation ---------------------------------------------------

    @staticmethod
    def _validate_path(path: str) -> Path:
        """Validate and resolve a user-provided file path."""
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")
        return p

    # -- signals -----------------------------------------------------------
    tuneResultChanged = Signal()
    questionsChanged = Signal()
    historyChanged = Signal()
    screenshotsChanged = Signal()
    bboxesChanged = Signal()
    tuneStatusChanged = Signal()
    currentPdfNameChanged = Signal()
    tabRegistryChanged = Signal()
    progressChanged = Signal(str)
    errorOccurred = Signal(str)

    def _emit_later(self, signal_name: str):
        """Thread-safe signal emission via queued connection."""
        QMetaObject.invokeMethod(self, signal_name, Qt.QueuedConnection)

    def _set_error(self, msg: str):
        """Emit error to UI (thread-safe)."""
        self.errorOccurred.emit(msg)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tune_result = "{}"
        self._questions = "[]"
        self._history = "[]"
        self._screenshots = "[]"
        self._bboxes = "[]"
        self._tune_status = "idle"
        self._current_pdf = "No PDF loaded"
        self._tab_registry = self._load_tab_registry()

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _load_tab_registry() -> str:
        p = _SKILL_DIR / "qml" / "tab-registry.json"
        if p.exists():
            return p.read_text()
        return '{"groups":[]}'

    def _run_cli(self, *args: str, parse_json: bool = True):
        """Run pdf_lab.py with args, return parsed JSON or raw stdout."""
        cmd = ["uv", "run", "python", _CLI, *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(_SKILL_DIR),
            )
            if parse_json and result.stdout.strip():
                return json.loads(result.stdout.strip())
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
            self._set_error(f"CLI error: {exc}")
            return {} if parse_json else ""

    def _bg(self, fn):
        """Run fn in a daemon thread."""
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    # -- properties --------------------------------------------------------

    @Property(str, notify=tuneResultChanged)
    def tuneResultJson(self):
        return self._tune_result

    @Property(str, notify=questionsChanged)
    def questionsJson(self):
        return self._questions

    @Property(str, notify=historyChanged)
    def historyJson(self):
        return self._history

    @Property(str, notify=screenshotsChanged)
    def screenshotsJson(self):
        return self._screenshots

    @Property(str, notify=bboxesChanged)
    def bboxesJson(self):
        return self._bboxes

    @Property(str, notify=tuneStatusChanged)
    def tuneStatus(self):
        return self._tune_status

    @Property(str, notify=currentPdfNameChanged)
    def currentPdfName(self):
        return self._current_pdf

    @Property(str, notify=tabRegistryChanged)
    def tabRegistryJson(self):
        return self._tab_registry

    # -- slots: tune -------------------------------------------------------

    @Slot()
    def refresh(self):
        """Reload all data from CLI."""
        self._bg(self._do_refresh)

    def _do_refresh(self):
        self._load_status()
        self._load_questions()
        self._load_history()

    def _load_status(self):
        data = self._run_cli("status", "--json")
        if isinstance(data, dict):
            self._tune_result = json.dumps(data)
            self._emit_later("tuneResultChanged")
            self._tune_status = data.get("status", "idle")
            self._emit_later("tuneStatusChanged")

    @Slot(bool, bool)
    def runTune(self, dry_run: bool, write_back: bool):
        """Run convergence tune."""
        self._tune_status = "running"
        self.tuneStatusChanged.emit()  # main thread: slot called from QML
        self._bg(lambda: self._do_tune(dry_run, write_back))

    def _do_tune(self, dry_run: bool, write_back: bool):
        args = ["tune", "--converge", "--json"]
        if dry_run:
            args.append("--dry-run")
        if write_back:
            args.append("--write-back")
        data = self._run_cli(*args)
        if isinstance(data, dict):
            self._tune_result = json.dumps(data)
            self._emit_later("tuneResultChanged")
            self._tune_status = data.get("status", "idle")
            self._emit_later("tuneStatusChanged")

    # -- slots: questions --------------------------------------------------

    def _load_questions(self):
        data = self._run_cli("book", "--json")
        if isinstance(data, list):
            self._questions = json.dumps(data)
        elif isinstance(data, dict) and "questions" in data:
            self._questions = json.dumps(data["questions"])
        self._emit_later("questionsChanged")

    @Slot()
    def reviewQuestions(self):
        """Launch interactive question review."""
        self._bg(lambda: self._run_cli("answer", "--mode", "tui", parse_json=False))

    # -- slots: history ----------------------------------------------------

    def _load_history(self):
        data = self._run_cli("status", "--json")
        if isinstance(data, dict) and "history" in data:
            self._history = json.dumps(data["history"])
            self._emit_later("historyChanged")

    @Slot(str)
    def rollback(self, sha: str):
        """Rollback a specific write-back commit."""
        self._bg(lambda: self._do_rollback(sha))

    def _do_rollback(self, sha: str):
        self.progressChanged.emit(f"Rolling back {sha[:7]}...")
        self._run_cli("rollback", "--sha", sha, parse_json=False)
        self._load_history()
        self.progressChanged.emit(f"Rolled back {sha[:7]}")

    # -- slots: annotate ---------------------------------------------------

    @Slot(str)
    def loadPdf(self, path: str):
        """Load a PDF for annotation (capture screenshots)."""
        try:
            validated = self._validate_path(path)
        except FileNotFoundError as exc:
            self.progressChanged.emit(f"Invalid path: {exc}")
            return
        self._current_pdf = validated.name
        self.currentPdfNameChanged.emit()
        self._bg(lambda: self._do_load_pdf(str(validated)))

    def _do_load_pdf(self, path: str):
        self.progressChanged.emit("Capturing page screenshots...")
        data = self._run_cli("diagnose", path, "--json")
        if isinstance(data, dict):
            screenshots = data.get("screenshots", [])
            self._screenshots = json.dumps(screenshots)
            self._emit_later("screenshotsChanged")
            self._tune_result = json.dumps(data)
            self._emit_later("tuneResultChanged")
        self.progressChanged.emit("PDF loaded")

    @Slot(int, float, float, float, float, str)
    def addBbox(self, page: int, x: float, y: float, w: float, h: float, bbox_type: str):
        """Add a bounding box annotation."""
        current = json.loads(self._bboxes)
        current.append({
            "page": page, "x": x, "y": y, "w": w, "h": h,
            "type": bbox_type, "source": "manual", "action": "add",
        })
        self._bboxes = json.dumps(current)
        self.bboxesChanged.emit()

    @Slot(int)
    def deleteBbox(self, index: int):
        """Delete a bounding box by index."""
        current = json.loads(self._bboxes)
        if 0 <= index < len(current):
            current.pop(index)
            self._bboxes = json.dumps(current)
            self.bboxesChanged.emit()

    @Slot()
    def saveAnnotations(self):
        """Save bbox annotations to disk."""
        data_dir = Path.home() / ".pi" / "pdf-lab"
        data_dir.mkdir(parents=True, exist_ok=True)
        out = data_dir / "annotations.json"
        out.write_text(self._bboxes)
        self.progressChanged.emit(f"Saved {len(json.loads(self._bboxes))} annotations")
