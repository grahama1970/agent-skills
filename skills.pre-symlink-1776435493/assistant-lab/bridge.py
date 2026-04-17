"""PySide6 QObject bridge for Assistant Lab QML app.

Wraps assistant-lab run.sh CLI via subprocess — never imports internals.
"""
from __future__ import annotations
import os

import json
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, Property, Qt, Signal, Slot

_SKILL_DIR = Path(__file__).resolve().parent
_RUN_SH = str(_SKILL_DIR / "run.sh")
_SHADOW_FILE = Path.home() / ".pi" / "assistant" / "shadow.jsonl"
_METRICS_FILE = Path.home() / ".pi" / "assistant" / "lab_metrics.jsonl"
_REGISTRY_FILE = _SKILL_DIR.parent / "assistant" / "model_registry.json"
_TRAINING_DATA = Path.home() / ".pi" / "assistant" / "training_data"


class AssistantLabBridge(QObject):
    # -- signals -----------------------------------------------------------
    registryChanged = Signal()
    shadowStatusChanged = Signal()
    trainStateChanged = Signal()
    diagnoseResultChanged = Signal()
    metricsLogChanged = Signal()
    synthesisResultChanged = Signal()
    cascadeStatusChanged = Signal()
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
        self._registry = "{}"
        self._shadow_status = "[]"
        self._train_state = "{}"
        self._diagnose_result = "{}"
        self._metrics_log = "[]"
        self._synthesis_result = "{}"
        self._cascade_status = "idle"
        self._tab_registry = self._load_tab_registry()

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _load_tab_registry() -> str:
        p = _SKILL_DIR / "qml" / "tab-registry.json"
        if p.exists():
            return p.read_text()
        return '{"groups":[]}'

    def _run_cli(self, *args: str, parse_json: bool = True):
        """Run run.sh with args, return parsed JSON or raw stdout."""
        cmd = [_RUN_SH, *args]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
                cwd=str(_SKILL_DIR),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if parse_json and result.stdout.strip():
                return json.loads(result.stdout.strip())
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
            self._set_error(f"CLI error: {exc}")
            return {} if parse_json else ""

    def _bg(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    def _read_jsonl(self, path: Path, limit: int = 100) -> list:
        """Read last N lines of a JSONL file."""
        if not path.exists():
            return []
        entries = []
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            return []
        return entries[-limit:]

    # -- properties --------------------------------------------------------

    @Property(str, notify=registryChanged)
    def registryJson(self):
        return self._registry

    @Property(str, notify=shadowStatusChanged)
    def shadowStatusJson(self):
        return self._shadow_status

    @Property(str, notify=trainStateChanged)
    def trainStateJson(self):
        return self._train_state

    @Property(str, notify=diagnoseResultChanged)
    def diagnoseResultJson(self):
        return self._diagnose_result

    @Property(str, notify=metricsLogChanged)
    def metricsLogJson(self):
        return self._metrics_log

    @Property(str, notify=synthesisResultChanged)
    def synthesisResultJson(self):
        return self._synthesis_result

    @Property(str, notify=cascadeStatusChanged)
    def cascadeStatus(self):
        return self._cascade_status

    @Property(str, notify=tabRegistryChanged)
    def tabRegistryJson(self):
        return self._tab_registry

    # -- slots: refresh ----------------------------------------------------

    @Slot()
    def refresh(self):
        self._bg(self._do_refresh)

    def _do_refresh(self):
        self._load_registry()
        self._load_shadow_status()
        self._load_train_state()
        self._load_metrics_log()

    def _load_registry(self):
        if _REGISTRY_FILE.exists():
            try:
                data = json.loads(_REGISTRY_FILE.read_text())
                self._registry = json.dumps(data)
                self._emit_later("registryChanged")
                # Determine cascade health
                v = len(data.get("validators", {}))
                c = len(data.get("classifiers", {}))
                self._cascade_status = "healthy" if (v + c) > 0 else "idle"
                self._emit_later("cascadeStatusChanged")
            except (json.JSONDecodeError, OSError) as exc:
                self._set_error(f"Failed to load registry: {exc}")

    def _load_shadow_status(self):
        """Aggregate shadow.jsonl into per-task status."""
        entries = self._read_jsonl(_SHADOW_FILE, limit=5000)
        tasks = {}
        for e in entries:
            task = e.get("task", "")
            if not task:
                continue
            if task not in tasks:
                tasks[task] = {"task": task, "agree": 0, "total": 0, "model_type": ""}
            tasks[task]["total"] += 1
            if e.get("agreed"):
                tasks[task]["agree"] += 1
            tasks[task]["model_type"] = e.get("local_source", "")

        result = []
        for t in sorted(tasks.values(), key=lambda x: x["task"]):
            total = t["total"]
            result.append({
                "task": t["task"],
                "agreement_rate": t["agree"] / max(1, total),
                "sample_count": total,
                "model_type": t["model_type"],
            })
        self._shadow_status = json.dumps(result)
        self._emit_later("shadowStatusChanged")

    def _load_train_state(self):
        """Scan training data directory for datasets."""
        datasets = []
        if _TRAINING_DATA.exists():
            for task_dir in sorted(_TRAINING_DATA.iterdir()):
                if task_dir.is_dir():
                    label_files = list(task_dir.glob("labels_*.jsonl"))
                    total_labels = 0
                    last_harvest = ""
                    for lf in label_files:
                        total_labels += sum(1 for _ in open(lf) if _.strip())
                        mtime = lf.stat().st_mtime
                        ts = str(lf.stem).replace("labels_", "")
                        if ts > last_harvest:
                            last_harvest = ts
                    datasets.append({
                        "task": task_dir.name,
                        "label_count": total_labels,
                        "last_harvest": last_harvest[:19] if last_harvest else "-",
                        "path": str(task_dir),
                    })
        self._train_state = json.dumps({"datasets": datasets, "recent_trains": []})
        self._emit_later("trainStateChanged")

    def _load_metrics_log(self):
        entries = self._read_jsonl(_METRICS_FILE, limit=50)
        entries.reverse()
        self._metrics_log = json.dumps(entries)
        self._emit_later("metricsLogChanged")

    # -- slots: train ------------------------------------------------------

    @Slot(str, str)
    def train(self, task: str, model_type: str):
        if not task:
            return
        self.progressChanged.emit(f"Training {model_type} for {task}...")
        self._cascade_status = "training"
        self.cascadeStatusChanged.emit()
        self._bg(lambda: self._do_train(task, model_type))

    def _do_train(self, task: str, model_type: str):
        data = self._run_cli("train", "--task", task, "--type", model_type)
        # Append to recent trains
        state = json.loads(self._train_state)
        if isinstance(data, dict):
            state.setdefault("recent_trains", []).insert(0, data)
        self._train_state = json.dumps(state)
        self._emit_later("trainStateChanged")
        self._cascade_status = "idle"
        self._emit_later("cascadeStatusChanged")
        self.progressChanged.emit(f"Training complete: {task} {model_type}")

    @Slot(str)
    def harvest(self, task: str):
        if not task:
            return
        self.progressChanged.emit(f"Harvesting labels for {task}...")
        self._bg(lambda: self._do_harvest(task))

    def _do_harvest(self, task: str):
        self._run_cli("harvest", "--task", task)
        self._load_train_state()
        self.progressChanged.emit(f"Harvest complete: {task}")

    # -- slots: diagnose / auto-improve ------------------------------------

    @Slot(str)
    def diagnose(self, task: str):
        if not task:
            return
        self._bg(lambda: self._do_diagnose(task))

    def _do_diagnose(self, task: str):
        data = self._run_cli("diagnose", "--task", task)
        if isinstance(data, dict):
            self._diagnose_result = json.dumps(data)
            self._emit_later("diagnoseResultChanged")

    @Slot(str)
    def autoImprove(self, task: str):
        if not task:
            return
        self.progressChanged.emit(f"Auto-improving {task}...")
        self._cascade_status = "training"
        self.cascadeStatusChanged.emit()
        self._bg(lambda: self._do_auto_improve(task))

    def _do_auto_improve(self, task: str):
        self._run_cli("auto-improve", "--task", task, parse_json=False)
        self._do_refresh()
        self._cascade_status = "idle"
        self._emit_later("cascadeStatusChanged")
        self.progressChanged.emit(f"Auto-improve complete: {task}")

    @Slot()
    def autoImproveAll(self):
        self.progressChanged.emit("Auto-improving all tasks...")
        self._cascade_status = "training"
        self.cascadeStatusChanged.emit()
        self._bg(self._do_auto_improve_all)

    def _do_auto_improve_all(self):
        self._run_cli("auto-improve", "--all", parse_json=False)
        self._do_refresh()
        self._cascade_status = "idle"
        self._emit_later("cascadeStatusChanged")
        self.progressChanged.emit("Auto-improve all complete")

    # -- slots: synthesis --------------------------------------------------

    @Slot(str, int)
    def runSynthesisEval(self, task: str, count: int):
        if not task:
            return
        self.progressChanged.emit(f"Running synthesis eval for {task} ({count} conversations)...")
        self._bg(lambda: self._do_synthesis(task, count))

    def _do_synthesis(self, task: str, count: int):
        cmd = ["uv", "run", "python", str(_SKILL_DIR / "synthesis_eval.py"),
               "--task", task, "--count", str(count)]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
                cwd=str(_SKILL_DIR),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.stdout.strip():
                data = json.loads(result.stdout.strip())
                self._synthesis_result = json.dumps(data)
                self._emit_later("synthesisResultChanged")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
            self._set_error(f"Synthesis error: {exc}")
        self.progressChanged.emit(f"Synthesis eval complete: {task}")
