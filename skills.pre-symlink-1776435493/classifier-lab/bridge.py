"""PySide6 QObject bridge for classifier-lab GUI.

Exposes training, benchmarking, evaluation, ensemble, and export
operations to QML. All heavy work runs in background threads and
delegates to ./run.sh subcommands with --json output.
"""
from __future__ import annotations
import os

import json
import subprocess
import threading
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QMetaObject, QObject, Property, Qt, Signal, Slot

SKILL_DIR = Path(__file__).parent
RUN_SH = str(SKILL_DIR / "run.sh")


def _run_cmd(args: list[str], timeout: int = 600) -> dict | list | str:
    """Run a run.sh subcommand, return parsed JSON or raw stdout."""
    try:
        result = subprocess.run(
            [RUN_SH] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(SKILL_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        out = result.stdout.strip()
        if not out:
            return result.stderr.strip() or ""
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return out
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except Exception as e:
        return {"error": str(e)}


class ClassifierLabBridge(QObject):
    """Bridge between QML and classifier-lab CLI."""

    # -- path validation ---------------------------------------------------

    @staticmethod
    def _validate_path(path: str) -> Path:
        """Validate and resolve a user-provided file path."""
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")
        return p

    # Signals
    benchmarkResultJsonChanged = Signal()
    trainStateJsonChanged = Signal()
    evaluateResultJsonChanged = Signal()
    ensembleResultJsonChanged = Signal()
    exportListJsonChanged = Signal()
    trainingStatusChanged = Signal()
    trainLogTextChanged = Signal()
    tabRegistryJsonChanged = Signal()
    errorOccurred = Signal(str)

    def _emit_later(self, signal_name: str):
        """Thread-safe signal emission via queued connection."""
        QMetaObject.invokeMethod(self, signal_name, Qt.QueuedConnection)

    def _set_error(self, msg: str):
        """Emit error to UI (thread-safe)."""
        self.errorOccurred.emit(msg)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._benchmark_result_json = "[]"
        self._train_state_json = "{}"
        self._evaluate_result_json = "{}"
        self._ensemble_result_json = "{}"
        self._export_list_json = "[]"
        self._training_status = "idle"
        self._train_log_text = ""

        # Load tab registry
        self._tab_registry_json = ""
        try:
            registry_path = SKILL_DIR / "qml" / "tab-registry.json"
            if registry_path.exists():
                self._tab_registry_json = registry_path.read_text()
        except Exception as e:
            logger.warning(f"Failed to load tab-registry.json: {e}")
            self._set_error(f"Failed to load tab-registry.json: {e}")

        # Scan for existing exported models
        self._scan_exports()

    # -- Properties --------------------------------------------------------

    @Property(str, notify=benchmarkResultJsonChanged)
    def benchmarkResultJson(self):
        return self._benchmark_result_json

    @Property(str, notify=trainStateJsonChanged)
    def trainStateJson(self):
        return self._train_state_json

    @Property(str, notify=evaluateResultJsonChanged)
    def evaluateResultJson(self):
        return self._evaluate_result_json

    @Property(str, notify=ensembleResultJsonChanged)
    def ensembleResultJson(self):
        return self._ensemble_result_json

    @Property(str, notify=exportListJsonChanged)
    def exportListJson(self):
        return self._export_list_json

    @Property(str, notify=trainingStatusChanged)
    def trainingStatus(self):
        return self._training_status

    @Property(str, notify=trainLogTextChanged)
    def trainLogText(self):
        return self._train_log_text

    @Property(str, constant=True)
    def tabRegistryJson(self):
        return self._tab_registry_json

    # -- Helpers -----------------------------------------------------------

    def _set_status(self, status: str):
        self._training_status = status
        self._emit_later("trainingStatusChanged")

    def _append_log(self, text: str):
        self._train_log_text += text + "\n"
        self._emit_later("trainLogTextChanged")

    def _scan_exports(self):
        """Scan models/ directory for exported files."""
        models_dir = SKILL_DIR / "models"
        if not models_dir.exists():
            return
        exports = []
        for ext in ("*.onnx", "*.pt", "*.torchscript", "*.joblib"):
            for p in models_dir.glob(ext):
                fmt = p.suffix.lstrip(".").upper()
                if fmt == "PT":
                    fmt = "TorchScript"
                elif fmt == "TORCHSCRIPT":
                    fmt = "TorchScript"
                size_mb = p.stat().st_size / (1024 * 1024)
                exports.append({
                    "path": str(p),
                    "format": fmt,
                    "size_mb": round(size_mb, 2),
                    "timestamp": "",
                })
        self._export_list_json = json.dumps(exports)
        self._emit_later("exportListJsonChanged")

    # -- Slots -------------------------------------------------------------

    @Slot()
    def refresh(self):
        """Reload exported models list."""
        self._scan_exports()
        logger.info("Classifier Lab bridge refreshed")

    @Slot(str, str, int, int, float)
    def runTrain(self, data_path: str, backbone: str, epochs: int,
                 batch_size: int, lr: float):
        """Launch a training run in a background thread."""
        if self._training_status == "training":
            return
        try:
            validated_data = self._validate_path(data_path)
        except FileNotFoundError as exc:
            self._append_log(f"Invalid path: {exc}")
            return
        self._set_status("training")
        self._train_log_text = ""
        self.trainLogTextChanged.emit()
        self._append_log(f"Starting training: {backbone} on {validated_data}")
        self._append_log(f"  epochs={epochs}  batch={batch_size}  lr={lr}")

        def _worker():
            try:
                args = [
                    "train",
                    "--data-dir", str(validated_data),
                    "--backbone", backbone,
                    "--epochs", str(epochs),
                    "--batch-size", str(batch_size),
                    "--lr", str(lr),
                    "--json",
                ]
                proc = subprocess.Popen(
                    [RUN_SH] + args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(SKILL_DIR),
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                for line in iter(proc.stdout.readline, ""):
                    self._append_log(line.rstrip())
                proc.wait()

                if proc.returncode == 0:
                    self._set_status("complete")
                    self._append_log("Training complete.")
                else:
                    self._set_status("error")
                    self._append_log(f"Training failed (exit {proc.returncode})")

                # Try to parse final JSON from log
                try:
                    lines = self._train_log_text.strip().split("\n")
                    for line in reversed(lines):
                        line = line.strip()
                        if line.startswith("{"):
                            self._train_state_json = line
                            self._emit_later("trainStateJsonChanged")
                            break
                except Exception:
                    pass

            except Exception as e:
                self._set_status("error")
                self._append_log(f"Error: {e}")
                self._set_error(f"Training failed: {e}")

        threading.Thread(target=_worker, daemon=True, name="train-worker").start()

    @Slot(str)
    def runBenchmark(self, backbones_json: str):
        """Run benchmark across selected backbones."""
        if self._training_status in ("training", "benchmarking"):
            return
        self._set_status("benchmarking")
        self._append_log("Starting benchmark...")

        def _worker():
            try:
                backbones = json.loads(backbones_json)
                backbone_str = ",".join(backbones)
                result = _run_cmd([
                    "benchmark",
                    "--backbones", backbone_str,
                    "--json",
                ])
                if isinstance(result, list):
                    self._benchmark_result_json = json.dumps(result)
                elif isinstance(result, dict) and "results" in result:
                    self._benchmark_result_json = json.dumps(result["results"])
                elif isinstance(result, str):
                    # Try to extract JSON array from output
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, list):
                            self._benchmark_result_json = json.dumps(parsed)
                    except Exception:
                        self._append_log(result)
                self._emit_later("benchmarkResultJsonChanged")
                self._set_status("idle")
                self._append_log("Benchmark complete.")
            except Exception as e:
                self._set_status("error")
                self._append_log(f"Benchmark error: {e}")
                self._set_error(f"Benchmark failed: {e}")

        threading.Thread(target=_worker, daemon=True, name="bench-worker").start()

    @Slot(str, str)
    def evaluate(self, model_path: str, test_path: str):
        """Evaluate a model on test data."""
        try:
            validated_model = self._validate_path(model_path)
            validated_test = self._validate_path(test_path)
        except FileNotFoundError as exc:
            self._append_log(f"Invalid path: {exc}")
            return
        self._append_log(f"Evaluating {validated_model} on {validated_test}...")

        def _worker():
            try:
                result = _run_cmd([
                    "evaluate",
                    "--model", str(validated_model),
                    "--test-dir", str(validated_test),
                    "--json",
                ])
                if isinstance(result, dict):
                    self._evaluate_result_json = json.dumps(result)
                elif isinstance(result, str):
                    try:
                        self._evaluate_result_json = json.dumps(json.loads(result))
                    except Exception:
                        self._evaluate_result_json = json.dumps({"error": result})
                self._emit_later("evaluateResultJsonChanged")
                self._append_log("Evaluation complete.")
            except Exception as e:
                self._append_log(f"Evaluate error: {e}")
                self._set_error(f"Evaluate failed: {e}")

        threading.Thread(target=_worker, daemon=True, name="eval-worker").start()

    @Slot(str, str)
    def runEnsemble(self, models_json: str, strategy: str):
        """Create and test an ensemble."""
        self._append_log(f"Running ensemble ({strategy})...")

        def _worker():
            try:
                models = json.loads(models_json)
                model_paths = [m["path"] for m in models]
                weights = [str(m["weight"]) for m in models]
                result = _run_cmd([
                    "ensemble",
                    "--models", ",".join(model_paths),
                    "--weights", ",".join(weights),
                    "--strategy", strategy,
                    "--json",
                ])
                if isinstance(result, dict):
                    self._ensemble_result_json = json.dumps(result)
                elif isinstance(result, str):
                    try:
                        self._ensemble_result_json = json.dumps(json.loads(result))
                    except Exception:
                        self._ensemble_result_json = json.dumps({"error": result})
                self._emit_later("ensembleResultJsonChanged")
                self._append_log("Ensemble complete.")
            except Exception as e:
                self._append_log(f"Ensemble error: {e}")
                self._set_error(f"Ensemble failed: {e}")

        threading.Thread(target=_worker, daemon=True, name="ensemble-worker").start()

    @Slot(str, str, str)
    def exportModel(self, model_path: str, fmt: str, output_path: str):
        """Export a model to the specified format."""
        try:
            validated_model = self._validate_path(model_path)
        except FileNotFoundError as exc:
            self._append_log(f"Invalid model path: {exc}")
            return
        resolved_output = Path(output_path).resolve()
        if not resolved_output.parent.exists():
            self._append_log(f"Invalid output path: parent directory does not exist: {resolved_output.parent}")
            return
        self._append_log(f"Exporting {validated_model} as {fmt}...")

        def _worker():
            try:
                result = _run_cmd([
                    "export",
                    "--model", str(validated_model),
                    "--format", fmt.lower(),
                    "--output", str(resolved_output),
                    "--json",
                ])
                self._append_log(f"Export result: {result}")
                # Refresh exports list
                self._scan_exports()
            except Exception as e:
                self._append_log(f"Export error: {e}")
                self._set_error(f"Export failed: {e}")

        threading.Thread(target=_worker, daemon=True, name="export-worker").start()
