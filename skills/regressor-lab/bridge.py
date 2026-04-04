"""RegressorLabBridge -- QObject bridge between QML UI and regressor-lab CLI.

Exposes properties and slots for data loading, benchmarking, tuning,
deployment, and rollback. All heavy work delegates to ./run.sh subprocess
via daemon threads to keep the UI responsive.
"""
from __future__ import annotations
import os

import json
import subprocess
import threading
from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import Property, QMetaObject, QObject, Qt, Signal, Slot

SKILL_DIR = Path(__file__).parent
RUN_SH = SKILL_DIR / "run.sh"
REGISTRY_PATH = SKILL_DIR / "qml" / "tab-registry.json"


def _run_cmd(*args: str, timeout: int = 120) -> Optional[str]:
    """Run a ./run.sh command and return stdout, or None on error."""
    try:
        result = subprocess.run(
            [str(RUN_SH), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(SKILL_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.warning(f"run.sh {args} failed: {result.stderr.strip()}")
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"run.sh {args} timed out ({timeout}s)")
        return None
    except Exception as e:
        logger.error(f"run.sh {args} error: {e}")
        return None


class RegressorLabBridge(QObject):
    """Bridge between RegressorLabApp.qml and the regressor-lab skill CLI."""

    # -- path validation ---------------------------------------------------

    @staticmethod
    def _validate_path(path: str) -> Path:
        """Validate and resolve a user-provided file path."""
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")
        return p

    # -- Signals --
    dataInfoJsonChanged = Signal()
    benchmarkResultJsonChanged = Signal()
    tuneResultJsonChanged = Signal()
    deployHistoryJsonChanged = Signal()
    trainingStatusChanged = Signal()
    tabRegistryJsonChanged = Signal()
    errorOccurred = Signal(str)

    def _emit_later(self, signal_name: str):
        """Thread-safe signal emission via queued connection."""
        QMetaObject.invokeMethod(self, signal_name, Qt.QueuedConnection)

    def _set_error(self, msg: str):
        """Emit error to UI (thread-safe)."""
        self.errorOccurred.emit(msg)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._data_info_json = "{}"
        self._benchmark_result_json = "{}"
        self._tune_result_json = "{}"
        self._deploy_history_json = "[]"
        self._training_status = "idle"
        self._tab_registry_json = self._load_tab_registry()

    # -- Properties --

    @Property(str, notify=dataInfoJsonChanged)
    def dataInfoJson(self) -> str:
        return self._data_info_json

    @Property(str, notify=benchmarkResultJsonChanged)
    def benchmarkResultJson(self) -> str:
        return self._benchmark_result_json

    @Property(str, notify=tuneResultJsonChanged)
    def tuneResultJson(self) -> str:
        return self._tune_result_json

    @Property(str, notify=deployHistoryJsonChanged)
    def deployHistoryJson(self) -> str:
        return self._deploy_history_json

    @Property(str, notify=trainingStatusChanged)
    def trainingStatus(self) -> str:
        return self._training_status

    @Property(str, notify=tabRegistryJsonChanged)
    def tabRegistryJson(self) -> str:
        return self._tab_registry_json

    # -- Slots --

    @Slot()
    def refresh(self) -> None:
        """Reload all state from disk/CLI."""
        logger.info("Refreshing regressor-lab state")
        self._load_deploy_history()

    @Slot(str, str)
    def loadData(self, path: str, target_col: str) -> None:
        """Load JSONL data file and extract column metadata (daemon thread)."""
        try:
            validated = self._validate_path(path)
        except FileNotFoundError as exc:
            logger.warning(f"Invalid path: {exc}")
            return
        def _worker() -> None:
            logger.info(f"Loading data: {validated} target={target_col}")
            self._set_status("loading")

            output = _run_cmd("collect", "--source", str(validated), "--info-json")
            if output:
                try:
                    info = json.loads(output)
                    info["path"] = str(validated)
                    info["target"] = target_col
                    self._data_info_json = json.dumps(info)
                    self._emit_later("dataInfoJsonChanged")
                except json.JSONDecodeError as exc:
                    logger.warning(f"Invalid JSON from collect: {output[:200]}")
                    self._set_error(f"Failed to parse data info: {exc}")
                    self._build_data_info_fallback(str(validated), target_col)
            else:
                self._build_data_info_fallback(str(validated), target_col)

            self._set_status("idle")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @Slot(str)
    def runBenchmark(self, architectures_json: str) -> None:
        """Run multi-architecture benchmark comparison (daemon thread)."""
        archs = json.loads(architectures_json)
        arch_str = ",".join(archs) if archs else "auto"

        data_info = json.loads(self._data_info_json)
        data_path = data_info.get("path", "")
        target = data_info.get("target", "")

        if not data_path or not target:
            logger.warning("No data loaded -- cannot benchmark")
            return

        def _worker() -> None:
            logger.info(f"Running benchmark: architectures={arch_str}")
            self._set_status("training")

            output = _run_cmd(
                "benchmark", data_path,
                "--target", target,
                "--models", arch_str,
                "--json",
                timeout=300,
            )
            if output:
                try:
                    result = json.loads(output)
                    self._benchmark_result_json = json.dumps(result)
                    self._emit_later("benchmarkResultJsonChanged")
                except json.JSONDecodeError as exc:
                    logger.warning(f"Invalid benchmark JSON: {output[:200]}")
                    self._set_error(f"Failed to parse benchmark result: {exc}")

            self._set_status("complete")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @Slot(str, str, str, int)
    def runTune(
        self,
        model_type: str,
        params_json: str,
        strategy: str,
        max_trials: int,
    ) -> None:
        """Run hyperparameter tuning for a given model type (daemon thread)."""
        data_info = json.loads(self._data_info_json)
        data_path = data_info.get("path", "")
        target = data_info.get("target", "")

        if not data_path:
            logger.warning("No data loaded -- cannot tune")
            return

        def _worker() -> None:
            logger.info(f"Tuning {model_type} strategy={strategy} trials={max_trials}")
            self._set_status("training")

            args = [
                "tune", data_path,
                "--target", target,
                "--model", model_type,
                "--strategy", strategy,
                "--trials", str(max_trials),
                "--json",
            ]

            output = _run_cmd(*args, timeout=600)
            if output:
                try:
                    result = json.loads(output)
                    self._tune_result_json = json.dumps(result)
                    self._emit_later("tuneResultJsonChanged")
                except json.JSONDecodeError as exc:
                    logger.warning(f"Invalid tune JSON: {output[:200]}")
                    self._set_error(f"Failed to parse tune result: {exc}")

            self._set_status("complete")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @Slot(str, str)
    def deploy(self, model_path: str, task: str) -> None:
        """Deploy a trained model to discovery.py (daemon thread)."""
        try:
            validated_model = self._validate_path(model_path)
        except FileNotFoundError as exc:
            logger.warning(f"Invalid model path: {exc}")
            return
        def _worker() -> None:
            logger.info(f"Deploying {validated_model} as task={task}")
            self._set_status("deploying")

            output = _run_cmd(
                "deploy", str(validated_model),
                "--task", task,
                "--json",
            )
            if output:
                logger.info(f"Deploy output: {output[:200]}")

            self._load_deploy_history()
            self._set_status("idle")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @Slot(str)
    def rollback(self, task: str) -> None:
        """Rollback a deployed model for the given task (daemon thread)."""
        def _worker() -> None:
            logger.info(f"Rolling back task={task}")

            output = _run_cmd("deploy", "--rollback", task, "--json")
            if output:
                logger.info(f"Rollback output: {output[:200]}")

            self._load_deploy_history()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    # -- Private helpers --

    def _set_status(self, status: str) -> None:
        if self._training_status != status:
            self._training_status = status
            self._emit_later("trainingStatusChanged")

    def _load_tab_registry(self) -> str:
        try:
            return REGISTRY_PATH.read_text()
        except FileNotFoundError:
            logger.warning("tab-registry.json not found")
            return '{"groups": []}'

    def _load_deploy_history(self) -> None:
        history_file = SKILL_DIR / "models" / "deploy_history.json"
        try:
            if history_file.exists():
                data = json.loads(history_file.read_text())
                self._deploy_history_json = json.dumps(data)
            else:
                self._deploy_history_json = "[]"
        except Exception as e:
            logger.warning(f"Failed to load deploy history: {e}")
            self._set_error(f"Failed to load deploy history: {e}")
            self._deploy_history_json = "[]"
        self._emit_later("deployHistoryJsonChanged")

    def _build_data_info_fallback(self, path: str, target_col: str) -> None:
        """Build minimal data info by reading the JSONL file directly."""
        try:
            lines = Path(path).read_text().strip().split("\n")
            rows = [json.loads(line) for line in lines if line.strip()]
            if not rows:
                return
            columns = list(rows[0].keys())
            features = [c for c in columns if c != target_col]
            target_vals = [r.get(target_col, 0) for r in rows if target_col in r]

            info = {
                "path": path,
                "target": target_col,
                "columns": columns,
                "features": features,
                "sample_count": len(rows),
                "feature_count": len(features),
                "target_min": min(target_vals) if target_vals else 0,
                "target_max": max(target_vals) if target_vals else 0,
                "preview": rows[:10],
            }
            self._data_info_json = json.dumps(info)
            self._emit_later("dataInfoJsonChanged")
        except Exception as e:
            logger.warning(f"Fallback data info failed: {e}")
            self._set_error(f"Failed to load data info: {e}")
