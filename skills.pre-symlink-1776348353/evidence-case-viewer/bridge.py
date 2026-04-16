"""PySide6 bridge that tails NDJSON events and exposes them to QML.

Watches /tmp/evidence-case-events.jsonl for new lines and emits Qt signals
that the QML app binds to. Each event type maps to a specific signal.

Chat well connects to /create-subagent (FastAPI container) via SSE streaming
so the human can talk to the evidence-building agent in real time.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot, Property

DEFAULT_LOG = "/tmp/evidence-case-events.jsonl"
DEFAULT_SUBAGENT_URL = "http://localhost:8620"

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    """Load a validated prompt from /prompt-lab/prompts/{name}.txt."""
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


class EvidenceBridge(QObject):
    """Tails NDJSON event log and exposes pipeline state to QML."""

    # Signals for QML binding
    questionReceived = Signal(str)
    gateStarted = Signal(str, str)          # gate_id, label
    gateResult = Signal(str, bool, str)     # gate_id, passed, reason
    sentenceMarkup = Signal(list)           # [{term, level, label}, ...]
    qraRecall = Signal(int, list)           # count, top_qras
    plausibilityDetail = Signal(str, bool, str, list)  # backend, answerable, reason, clarifying_qs
    clarifySuggestions = Signal(list, str)   # questions, reason
    techniqueGroups = Signal(dict, int)      # groups, total_tagged
    verdictReceived = Signal(str, str, str)  # verdict, grade, reason
    pipelineReset = Signal()
    errorOccurred = Signal(str)

    # Chat well signals
    chatMessageReceived = Signal(str, str)  # role ("user"|"agent"), text
    chatStreamChunk = Signal(str)           # partial text from SSE stream
    chatStreamDone = Signal(str)            # final complete response
    agentConnectedChanged = Signal()

    # Property change signals
    _questionChanged = Signal()
    _verdictChanged = Signal()
    _gradeChanged = Signal()
    _reasonChanged = Signal()
    _gatesChanged = Signal()
    _annotationsChanged = Signal()
    _qrasChanged = Signal()
    _runningChanged = Signal()
    _chatHistoryChanged = Signal()

    def __init__(self, log_path: str = DEFAULT_LOG,
                 subagent_url: str = DEFAULT_SUBAGENT_URL):
        super().__init__()
        self._log_path = Path(log_path)
        self._subagent_url = subagent_url
        self._question = ""
        self._verdict = ""
        self._grade = ""
        self._reason = ""
        self._gates = []       # [{id, label, passed, reason, ts}]
        self._annotations = [] # [{term, level, label}]
        self._qras = []        # [{control_id, question, score}]
        self._running = False
        self._tail_thread = None
        self._stop_event = threading.Event()
        self._chat_history = []  # [{role, text, ts}]
        self._agent_connected = False
        self._chat_streaming = False

    # ── Properties for QML ──────────────────────────────────

    @Property(str, notify=_questionChanged)
    def question(self):
        return self._question

    @Property(str, notify=_verdictChanged)
    def verdict(self):
        return self._verdict

    @Property(str, notify=_gradeChanged)
    def grade(self):
        return self._grade

    @Property(str, notify=_reasonChanged)
    def reason(self):
        return self._reason

    @Property(list, notify=_gatesChanged)
    def gates(self):
        return self._gates

    @Property(list, notify=_annotationsChanged)
    def annotations(self):
        return self._annotations

    @Property(list, notify=_qrasChanged)
    def qras(self):
        return self._qras

    @Property(bool, notify=_runningChanged)
    def running(self):
        return self._running

    @Property(list, notify=_chatHistoryChanged)
    def chatHistory(self):
        return self._chat_history

    @Property(bool, notify=agentConnectedChanged)
    def agentConnected(self):
        return self._agent_connected

    # ── Slots for QML ───────────────────────────────────────

    @Slot(str)
    def runPipeline(self, question: str):
        """Run evidence pipeline in background thread."""
        if self._running:
            return
        self._reset()
        self._running = True
        self._runningChanged.emit()

        def _run():
            try:
                from events import run_evidence_pipeline, EventEmitter
                emitter = EventEmitter(str(self._log_path))
                run_evidence_pipeline(question, emitter)
            except Exception as e:
                self.errorOccurred.emit(str(e))
            finally:
                self._running = False
                self._runningChanged.emit()

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    @Slot(str)
    def sendChat(self, message: str):
        """Send a message to the /create-subagent and stream the response."""
        if not message.strip() or self._chat_streaming:
            return

        # Add user message to history
        self._chat_history.append({
            "role": "user", "text": message,
            "ts": time.time(),
        })
        self._chatHistoryChanged.emit()
        self.chatMessageReceived.emit("user", message)

        # Build context from current pipeline state
        context = self._build_agent_context()
        full_prompt = f"{context}\n\nHuman says: {message}"

        def _stream():
            self._chat_streaming = True
            response_text = ""
            try:
                body = json.dumps({
                    "prompt": full_prompt,
                    "system_prompt": _load_prompt("evidence_case_chat"),
                    "max_turns": 1,
                    "idle_timeout": 60,
                }).encode()

                req = urllib.request.Request(
                    f"{self._subagent_url}/chat/stream",
                    data=body,
                    headers={"Content-Type": "application/json",
                             "Accept": "text/event-stream"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=90) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data: "):
                            data = line[6:]
                            try:
                                evt = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            etype = evt.get("type", "")
                            if etype == "text":
                                chunk = evt.get("text", "")
                                response_text += chunk
                                self.chatStreamChunk.emit(chunk)
                            elif etype == "result":
                                result = evt.get("result", "")
                                if result and not response_text:
                                    response_text = result
                            elif etype == "done":
                                break

            except (urllib.error.URLError, OSError) as e:
                response_text = f"[Agent unavailable: {e}]"
                self._agent_connected = False
                self.agentConnectedChanged.emit()
            finally:
                self._chat_streaming = False
                if response_text:
                    self._chat_history.append({
                        "role": "agent", "text": response_text,
                        "ts": time.time(),
                    })
                    self._chatHistoryChanged.emit()
                    self.chatStreamDone.emit(response_text)
                    self.chatMessageReceived.emit("agent", response_text)

        t = threading.Thread(target=_stream, daemon=True)
        t.start()

    @Slot()
    def checkAgentHealth(self):
        """Check if /create-subagent container is reachable."""
        def _check():
            try:
                req = urllib.request.Request(
                    f"{self._subagent_url}/health", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    self._agent_connected = data.get("status") == "ok"
            except (urllib.error.URLError, OSError):
                self._agent_connected = False
            self.agentConnectedChanged.emit()
        threading.Thread(target=_check, daemon=True).start()

    def _build_agent_context(self) -> str:
        """Build a context string from current pipeline state for the agent."""
        parts = []
        if self._question:
            parts.append(f"Question under evaluation: {self._question}")
        if self._annotations:
            markup = ", ".join(
                f"{a['term']}({a.get('level','?')})" for a in self._annotations
            )
            parts.append(f"Entity markup: {markup}")
        if self._gates:
            gate_str = ", ".join(
                f"{g['id']}:{g['status']}" for g in self._gates
            )
            parts.append(f"Gates: {gate_str}")
        if self._qras:
            qra_str = ", ".join(
                f"{q.get('control_id','?')}({q.get('score',0):.2f})"
                for q in self._qras[:5]
            )
            parts.append(f"Top QRAs: {qra_str}")
        if self._verdict:
            parts.append(f"Current verdict: {self._verdict} ({self._grade})")
        return "\n".join(parts) if parts else "Pipeline not yet started."

    @Slot()
    def startTailing(self):
        """Start tailing the NDJSON log file."""
        if self._tail_thread and self._tail_thread.is_alive():
            return
        self._stop_event.clear()
        self._tail_thread = threading.Thread(target=self._tail_loop, daemon=True)
        self._tail_thread.start()

    @Slot()
    def stopTailing(self):
        """Stop tailing."""
        self._stop_event.set()

    # ── Internal ────────────────────────────────────────────

    def _reset(self):
        """Clear all state for a new pipeline run."""
        self._question = ""
        self._verdict = ""
        self._grade = ""
        self._reason = ""
        self._gates = []
        self._annotations = []
        self._qras = []
        self._questionChanged.emit()
        self._verdictChanged.emit()
        self._gradeChanged.emit()
        self._reasonChanged.emit()
        self._gatesChanged.emit()
        self._annotationsChanged.emit()
        self._qrasChanged.emit()
        self.pipelineReset.emit()

    def _tail_loop(self):
        """Tail the NDJSON log, emitting signals for each event."""
        pos = 0
        # Start from beginning to replay existing events (tail-only mode
        # needs to show the current pipeline state, not just new events)

        while not self._stop_event.is_set():
            if not self._log_path.exists():
                time.sleep(0.1)
                continue

            size = self._log_path.stat().st_size
            if size < pos:
                # File was truncated (new pipeline run)
                pos = 0
                self._reset()

            if size > pos:
                with open(self._log_path, "r") as f:
                    f.seek(pos)
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                self._handle_event(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                    pos = f.tell()

            time.sleep(0.05)  # 50ms poll — responsive but light

    def _handle_event(self, event: dict[str, Any]):
        """Route an event to the appropriate signal."""
        etype = event.get("type", "")

        if etype == "question_received":
            self._question = event.get("question", "")
            self._questionChanged.emit()
            self.questionReceived.emit(self._question)

        elif etype == "gate_start":
            gate_id = event.get("gate", "")
            label = event.get("label", gate_id)
            self._gates.append({
                "id": gate_id, "label": label,
                "status": "running", "passed": None, "reason": "",
                "ts": event.get("ts", 0),
            })
            self._gatesChanged.emit()
            self.gateStarted.emit(gate_id, label)

        elif etype == "gate_result":
            gate_id = event.get("gate", "")
            passed = event.get("passed", True)
            reason = event.get("reason", "")
            # Update existing gate entry
            for g in self._gates:
                if g["id"] == gate_id and g["status"] == "running":
                    g["status"] = "passed" if passed else "failed"
                    g["passed"] = passed
                    g["reason"] = reason
                    break
            self._gatesChanged.emit()
            self.gateResult.emit(gate_id, passed, reason)

        elif etype == "sentence_markup":
            self._annotations = event.get("annotations", [])
            self._annotationsChanged.emit()
            self.sentenceMarkup.emit(self._annotations)

        elif etype == "qra_recall":
            count = event.get("count", 0)
            top = event.get("top_qras", [])
            self._qras = top
            self._qrasChanged.emit()
            self.qraRecall.emit(count, top)

        elif etype == "plausibility_detail":
            self.plausibilityDetail.emit(
                event.get("backend", ""),
                event.get("answerable", True),
                event.get("reason", ""),
                event.get("clarifying_questions", []),
            )

        elif etype == "clarify_suggestions":
            self.clarifySuggestions.emit(
                event.get("questions", []),
                event.get("reason", ""),
            )

        elif etype == "technique_groups":
            self.techniqueGroups.emit(
                event.get("groups", {}),
                event.get("total_tagged", 0),
            )

        elif etype == "verdict":
            self._verdict = event.get("verdict", "")
            self._grade = event.get("grade", "")
            self._reason = event.get("reason", "")
            self._verdictChanged.emit()
            self._gradeChanged.emit()
            self._reasonChanged.emit()
            self.verdictReceived.emit(self._verdict, self._grade, self._reason)
