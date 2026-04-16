"""PySide6 QObject bridge for Conversation Lab QML app.

Exposes diagnosis, sessions, convergence state, and promote pipeline
data as QML-readable properties. Runs CLI commands via subprocess
to avoid importing heavy dependencies into the GUI process.
"""
from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Property, QMetaObject, QObject, Qt, Signal, Slot

SKILL_DIR = Path(__file__).resolve().parent
TAB_REGISTRY = SKILL_DIR / "qml" / "tab-registry.json"
STATE_DIR = Path.home() / ".pi" / "conversation-lab"
STATE_FILE = STATE_DIR / "convergence_state.json"


class ConversationLabBridge(QObject):
    """Bridge between conversation-lab CLI and QML UI."""

    # ── Signals ──────────────────────────────────────────────
    diagnosisChanged = Signal()
    sessionsChanged = Signal()
    convergenceStateChanged = Signal()
    promoteStateChanged = Signal()
    convergenceStatusChanged = Signal()
    progressChanged = Signal(float, str)  # (0-1, message)
    errorOccurred = Signal(str)

    def _emit_later(self, signal_name: str):
        """Thread-safe signal emission via queued connection."""
        QMetaObject.invokeMethod(self, signal_name, Qt.QueuedConnection)

    def _set_error(self, msg: str):
        """Emit error to UI (thread-safe)."""
        self.errorOccurred.emit(msg)

    def __init__(self, session_file: Optional[str] = None, parent: QObject | None = None):
        super().__init__(parent)
        self._session_file = session_file
        self._diagnosis_json = "{}"
        self._sessions_json = "[]"
        self._convergence_state_json = "{}"
        self._promote_state_json = "{}"
        self._convergence_status = "idle"
        self._tab_registry_json = "{}"

        # Load tab registry
        if TAB_REGISTRY.exists():
            self._tab_registry_json = TAB_REGISTRY.read_text()

        # Initial load
        self._load_convergence_state()
        self._run_diagnosis()

    # ── Properties ───────────────────────────────────────────
    @Property(str, notify=diagnosisChanged)
    def diagnosisJson(self) -> str:
        return self._diagnosis_json

    @Property(str, notify=sessionsChanged)
    def sessionsJson(self) -> str:
        return self._sessions_json

    @Property(str, notify=convergenceStateChanged)
    def convergenceStateJson(self) -> str:
        return self._convergence_state_json

    @Property(str, notify=promoteStateChanged)
    def promoteStateJson(self) -> str:
        return self._promote_state_json

    @Property(str, notify=convergenceStatusChanged)
    def convergenceStatus(self) -> str:
        return self._convergence_status

    @Property(str, constant=True)
    def tabRegistryJson(self) -> str:
        return self._tab_registry_json

    # ── Slots ────────────────────────────────────────────────
    @Slot()
    def refresh(self):
        """Re-run diagnosis and reload convergence state."""
        threading.Thread(target=self._run_diagnosis, daemon=True).start()
        self._load_convergence_state()

    @Slot()
    def startConvergence(self):
        """Start convergence loop in background."""
        threading.Thread(target=self._run_converge, args=(False,), daemon=True).start()

    @Slot()
    def startConvergenceDryRun(self):
        """Start dry-run convergence."""
        threading.Thread(target=self._run_converge, args=(True,), daemon=True).start()

    @Slot(bool)
    def runPromoteNightly(self, dry_run: bool):
        """Run QRA promotion pipeline."""
        threading.Thread(target=self._run_promote, args=(dry_run,), daemon=True).start()

    # ── Internal Methods ─────────────────────────────────────
    def _run_cli(self, args: list[str], timeout: int = 300) -> Optional[str]:
        """Run conversation_lab.py CLI command and return stdout."""
        cmd = ["uv", "run", "--project", str(SKILL_DIR), "python",
               str(SKILL_DIR / "conversation_lab.py"), *args]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                cwd=str(SKILL_DIR),
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as exc:
            self._set_error(f"Failed to run CLI: {exc}")
            return None

    def _run_diagnosis(self):
        """Run diagnose command and parse output."""
        args = ["diagnose", "--format", "json"]
        if self._session_file:
            args.insert(1, self._session_file)

        output = self._run_cli(args)
        if output:
            try:
                diagnosis = json.loads(output)
                self._diagnosis_json = output

                # Extract flattened session list for SessionsPage
                sessions = diagnosis.get("sessions", [])
                self._sessions_json = json.dumps(sessions)

                self._emit_later("diagnosisChanged")
                self._emit_later("sessionsChanged")
            except json.JSONDecodeError as exc:
                self._set_error(f"Failed to parse diagnosis: {exc}")

    def _load_convergence_state(self):
        """Load convergence state from disk."""
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text())
                self._convergence_state_json = json.dumps(state)
                self._convergence_status = state.get("status", "idle")
                self._emit_later("convergenceStateChanged")
                self._emit_later("convergenceStatusChanged")
            except (json.JSONDecodeError, OSError) as exc:
                self._set_error(f"Failed to load convergence state: {exc}")

    def _run_converge(self, dry_run: bool):
        """Run convergence loop."""
        self._convergence_status = "running"
        self._emit_later("convergenceStatusChanged")

        args = ["converge", "--max-cycles", "5", "--json-stream"]
        if dry_run:
            args.append("--dry-run")
        if self._session_file:
            args.insert(1, self._session_file)

        output = self._run_cli(args, timeout=3600)
        if output:
            try:
                # Parse final output (last complete JSON object)
                for line in reversed(output.splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        data = json.loads(line)
                        if "convergence" in data:
                            self._convergence_state_json = json.dumps(data["convergence"])
                            self._convergence_status = data["convergence"].get("status", "completed")
                            break
            except json.JSONDecodeError as exc:
                self._set_error(f"Failed to parse convergence output: {exc}")

        # Reload from disk as fallback
        self._load_convergence_state()
        self._run_diagnosis()

    def _run_promote(self, dry_run: bool):
        """Run nightly promotion pipeline."""
        args = ["promote-nightly"]
        if dry_run:
            args.append("--dry-run")
        if self._session_file:
            args.insert(1, self._session_file)

        output = self._run_cli(args, timeout=600)
        if output:
            try:
                # Try to parse JSON from output
                for line in output.splitlines():
                    line = line.strip()
                    if line.startswith("{"):
                        state = json.loads(line)
                        state["last_run"] = datetime.now().isoformat()
                        self._promote_state_json = json.dumps(state)
                        self._emit_later("promoteStateChanged")
                        break
            except json.JSONDecodeError as exc:
                self._set_error(f"Failed to parse promote output: {exc}")
