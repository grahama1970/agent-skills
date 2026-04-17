"""GptLabBridge -- QObject bridge between QML UI and gpt-lab CLI.

Exposes model registry, benchmark results, profiler data, and report
generation to the QML front-end.  All heavy work delegates to run.sh
via subprocess.
"""
from __future__ import annotations
import os

import json
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import Property, QMetaObject, QObject, Qt, Signal, Slot


SKILL_DIR = Path(__file__).resolve().parent
MODELS_JSON = SKILL_DIR / "models.json"
RUN_SH = SKILL_DIR / "run.sh"


def _run_cmd(args: list[str], timeout: int = 120) -> Optional[str]:
    """Run a run.sh sub-command and return stdout or None on failure."""
    try:
        result = subprocess.run(
            [str(RUN_SH)] + args,
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
        logger.error(f"run.sh {args} timed out after {timeout}s")
        return None
    except Exception as exc:
        logger.error(f"run.sh {args} error: {exc}")
        return None


class GptLabBridge(QObject):
    """Bridge for gpt-lab QML application."""

    # Signals
    registryJsonChanged = Signal()
    benchmarkResultJsonChanged = Signal()
    profileResultJsonChanged = Signal()
    reportListJsonChanged = Signal()
    benchmarkStatusChanged = Signal()
    tabRegistryJsonChanged = Signal()
    errorOccurred = Signal(str)

    def _emit_later(self, signal_name: str):
        """Thread-safe signal emission via queued connection."""
        QMetaObject.invokeMethod(self, signal_name, Qt.QueuedConnection)

    def _set_error(self, msg: str):
        """Emit error to UI (thread-safe)."""
        self.errorOccurred.emit(msg)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._registry_json = "{}"
        self._benchmark_result_json = "[]"
        self._profile_result_json = "{}"
        self._report_list_json = "[]"
        self._benchmark_status = "idle"
        self._tab_registry_json = "{}"
        self._load_tab_registry()

    # ── Properties ────────────────────────────────────────────

    def _get_registry_json(self) -> str:
        return self._registry_json

    registryJson = Property(str, _get_registry_json, notify=registryJsonChanged)

    def _get_benchmark_result_json(self) -> str:
        return self._benchmark_result_json

    benchmarkResultJson = Property(
        str, _get_benchmark_result_json, notify=benchmarkResultJsonChanged
    )

    def _get_profile_result_json(self) -> str:
        return self._profile_result_json

    profileResultJson = Property(
        str, _get_profile_result_json, notify=profileResultJsonChanged
    )

    def _get_report_list_json(self) -> str:
        return self._report_list_json

    reportListJson = Property(
        str, _get_report_list_json, notify=reportListJsonChanged
    )

    def _get_benchmark_status(self) -> str:
        return self._benchmark_status

    benchmarkStatus = Property(
        str, _get_benchmark_status, notify=benchmarkStatusChanged
    )

    def _get_tab_registry_json(self) -> str:
        return self._tab_registry_json

    tabRegistryJson = Property(
        str, _get_tab_registry_json, notify=tabRegistryJsonChanged
    )

    # ── Internal helpers ──────────────────────────────────────

    def _load_tab_registry(self) -> None:
        """Load tab-registry.json for the QML side."""
        reg_path = SKILL_DIR / "qml" / "tab-registry.json"
        if reg_path.exists():
            self._tab_registry_json = reg_path.read_text()
            self.tabRegistryJsonChanged.emit()

    def _set_status(self, status: str) -> None:
        if self._benchmark_status != status:
            self._benchmark_status = status
            self.benchmarkStatusChanged.emit()

    # ── Slots ─────────────────────────────────────────────────

    @Slot()
    def refresh(self) -> None:
        """Reload all data from disk."""
        self.loadRegistry()
        logger.info("GptLabBridge: refreshed")

    @Slot()
    def loadRegistry(self) -> None:
        """Load models.json into registryJson property."""
        try:
            if MODELS_JSON.exists():
                data = MODELS_JSON.read_text()
                # Validate it parses
                json.loads(data)
                self._registry_json = data
            else:
                self._registry_json = json.dumps(
                    {"candidate_models": [], "api_models": []}
                )
            self.registryJsonChanged.emit()
        except Exception as exc:
            logger.error(f"Failed to load registry: {exc}")
            self._set_error(f"Failed to load registry: {exc}")

    @Slot(str, str, str, str)
    def addModel(
        self, name: str, params: str, model_type: str, provider: str
    ) -> None:
        """Add a candidate model to models.json."""
        try:
            registry = json.loads(self._registry_json)
            params_b = float(params) if params else 0.0
            new_model = {
                "name": name,
                "params_b": params_b,
                "type": model_type,
                "provider": provider,
            }
            if "candidate_models" not in registry:
                registry["candidate_models"] = []
            registry["candidate_models"].append(new_model)
            MODELS_JSON.write_text(json.dumps(registry, indent=2) + "\n")
            self._registry_json = json.dumps(registry)
            self.registryJsonChanged.emit()
            logger.info(f"Added model: {name}")
        except Exception as exc:
            logger.error(f"Failed to add model: {exc}")
            self._set_error(f"Failed to add model: {exc}")

    @Slot(str)
    def removeModel(self, name: str) -> None:
        """Remove a candidate model by name from models.json."""
        try:
            registry = json.loads(self._registry_json)
            candidates = registry.get("candidate_models", [])
            registry["candidate_models"] = [
                m for m in candidates if m.get("name") != name
            ]
            MODELS_JSON.write_text(json.dumps(registry, indent=2) + "\n")
            self._registry_json = json.dumps(registry)
            self.registryJsonChanged.emit()
            logger.info(f"Removed model: {name}")
        except Exception as exc:
            logger.error(f"Failed to remove model: {exc}")
            self._set_error(f"Failed to remove model: {exc}")

    @Slot(str, str, int)
    def runBenchmark(self, task: str, models_json: str, sample_count: int) -> None:
        """Run benchmark for given task and models."""
        self._set_status("running")
        try:
            models = json.loads(models_json)
            models_str = ",".join(models)
            output = _run_cmd(
                ["benchmark", "--task", task, "--models", models_str],
                timeout=300,
            )
            if output:
                # Try to parse JSON from output (last line or full)
                for line in reversed(output.splitlines()):
                    line = line.strip()
                    if line.startswith("[") or line.startswith("{"):
                        try:
                            json.loads(line)
                            self._benchmark_result_json = line
                            self.benchmarkResultJsonChanged.emit()
                            break
                        except json.JSONDecodeError:
                            continue
            self._set_status("done")
        except Exception as exc:
            logger.error(f"Benchmark failed: {exc}")
            self._set_error(f"Benchmark failed: {exc}")
            self._set_status("error")

    @Slot(str, str, str)
    def runCompare(self, task: str, model1: str, model2: str) -> None:
        """Compare two models head-to-head."""
        self._set_status("running")
        try:
            output = _run_cmd(
                [
                    "compare",
                    "--task", task,
                    "--finetuned", model1,
                    "--prompted", model2,
                ],
                timeout=300,
            )
            if output:
                for line in reversed(output.splitlines()):
                    line = line.strip()
                    if line.startswith("[") or line.startswith("{"):
                        try:
                            json.loads(line)
                            self._benchmark_result_json = line
                            self.benchmarkResultJsonChanged.emit()
                            break
                        except json.JSONDecodeError:
                            continue
            self._set_status("done")
        except Exception as exc:
            logger.error(f"Compare failed: {exc}")
            self._set_error(f"Compare failed: {exc}")
            self._set_status("error")

    @Slot(str, float)
    def findMinimum(self, task: str, threshold: float) -> None:
        """Find the smallest model meeting a threshold."""
        self._set_status("running")
        try:
            output = _run_cmd(
                [
                    "find-minimum",
                    "--task", task,
                    "--threshold", str(threshold),
                ],
                timeout=300,
            )
            if output:
                for line in reversed(output.splitlines()):
                    line = line.strip()
                    if line.startswith("[") or line.startswith("{"):
                        try:
                            json.loads(line)
                            self._benchmark_result_json = line
                            self.benchmarkResultJsonChanged.emit()
                            break
                        except json.JSONDecodeError:
                            continue
            self._set_status("done")
        except Exception as exc:
            logger.error(f"Find minimum failed: {exc}")
            self._set_error(f"Find minimum failed: {exc}")
            self._set_status("error")

    @Slot(str)
    def runProfile(self, model: str) -> None:
        """Profile a single model for latency and memory."""
        self._set_status("running")
        try:
            output = _run_cmd(
                ["profile", "--model", model, "--samples", "50"],
                timeout=300,
            )
            if output:
                for line in reversed(output.splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            json.loads(line)
                            self._profile_result_json = line
                            self.profileResultJsonChanged.emit()
                            break
                        except json.JSONDecodeError:
                            continue
            self._set_status("done")
        except Exception as exc:
            logger.error(f"Profile failed: {exc}")
            self._set_error(f"Profile failed: {exc}")
            self._set_status("error")

    @Slot(str)
    def generateReport(self, task: str) -> None:
        """Generate a report for the given task."""
        try:
            output = _run_cmd(
                ["report", "--task", task, "--format", "json"],
                timeout=120,
            )
            if output:
                for line in reversed(output.splitlines()):
                    line = line.strip()
                    if line.startswith("[") or line.startswith("{"):
                        try:
                            json.loads(line)
                            self._report_list_json = line
                            self.reportListJsonChanged.emit()
                            break
                        except json.JSONDecodeError:
                            continue
            # Also try loading history
            history_output = _run_cmd(["history", "--task", task], timeout=60)
            if history_output:
                for line in reversed(history_output.splitlines()):
                    line = line.strip()
                    if line.startswith("["):
                        try:
                            json.loads(line)
                            self._report_list_json = line
                            self.reportListJsonChanged.emit()
                            break
                        except json.JSONDecodeError:
                            continue
            logger.info(f"Report generated for task: {task}")
        except Exception as exc:
            logger.error(f"Report generation failed: {exc}")
            self._set_error(f"Report generation failed: {exc}")
