"""StreamDeckLabBridge -- QObject bridge between QML UI and streamdeck-lab CLI.

All backend operations delegate to ``./run.sh <command> --json`` via subprocess,
keeping the bridge thin and the CLI the single source of truth.
Heavy operations run in daemon threads to avoid blocking the UI.
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


SCRIPT_DIR = Path(__file__).parent
RUN_SH = SCRIPT_DIR / "run.sh"


def _run_cmd(*args: str, timeout: int = 30) -> str:
    """Run a run.sh sub-command and return stdout."""
    cmd = ["bash", str(RUN_SH), *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(SCRIPT_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.warning(f"run.sh {args} failed: {result.stderr.strip()}")
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"run.sh {args} timed out after {timeout}s")
        return ""
    except Exception as exc:
        logger.error(f"run.sh {args} error: {exc}")
        return ""


def _build_event_catalog_json() -> str:
    """Build event catalog JSON via a subprocess that reads EVENT_CATALOG.

    The 'events' CLI command outputs human-readable text, so we use a
    small Python snippet to extract the catalog as JSON.
    """
    code = (
        "import json, sys; sys.path.insert(0, '.'); "
        "from streamdeck_lab import EVENT_CATALOG; "
        "events = [{"
        "'name': k, 'context': v.get('context',''), "
        "'action': v.get('action',''), "
        "'position': v.get('position', -1), "
        "'alert_tier': v.get('alert_tier',''), "
        "'flash': v.get('flash', False), "
        "'requires_ack': v.get('requires_ack', False), "
        "'description': v.get('description','')"
        "} for k, v in EVENT_CATALOG.items()]; "
        "print(json.dumps(events))"
    )
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(SCRIPT_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as exc:
        logger.warning(f"Event catalog subprocess failed: {exc}")
    return "[]"


class StreamDeckLabBridge(QObject):
    """Bridge between QML and the streamdeck-lab CLI.

    All slots that do I/O run in daemon threads to keep the UI responsive.
    """

    # -- Signals --
    templatesJsonChanged = Signal()
    groundTruthJsonChanged = Signal()
    evaluateResultJsonChanged = Signal()
    generatedPageJsonChanged = Signal()
    eventCatalogJsonChanged = Signal()
    evalStatusChanged = Signal()
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
        self._templates_json = "[]"
        self._ground_truth_json = "[]"
        self._evaluate_result_json = "null"
        self._generated_page_json = "null"
        self._event_catalog_json = "[]"
        self._eval_status = "idle"
        self._tab_registry_json = ""
        self._load_tab_registry()

    # ── Helpers ────────────────────────────────────────────────────

    def _bg(self, fn: object) -> None:
        """Run fn in a daemon thread."""
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    def _set_eval_status(self, status: str) -> None:
        if self._eval_status != status:
            self._eval_status = status
            self._emit_later("evalStatusChanged")

    # -- Tab registry --

    def _load_tab_registry(self) -> None:
        reg_path = SCRIPT_DIR / "qml" / "tab-registry.json"
        if reg_path.exists():
            self._tab_registry_json = reg_path.read_text()
        else:
            self._tab_registry_json = "[]"

    def _get_tab_registry_json(self) -> str:
        return self._tab_registry_json

    tabRegistryJson = Property(str, _get_tab_registry_json, notify=tabRegistryJsonChanged)

    # -- Templates --

    def _get_templates_json(self) -> str:
        return self._templates_json

    templatesJson = Property(str, _get_templates_json, notify=templatesJsonChanged)

    # -- Ground truth --

    def _get_ground_truth_json(self) -> str:
        return self._ground_truth_json

    groundTruthJson = Property(str, _get_ground_truth_json, notify=groundTruthJsonChanged)

    # -- Evaluate result --

    def _get_evaluate_result_json(self) -> str:
        return self._evaluate_result_json

    evaluateResultJson = Property(str, _get_evaluate_result_json, notify=evaluateResultJsonChanged)

    # -- Generated page --

    def _get_generated_page_json(self) -> str:
        return self._generated_page_json

    generatedPageJson = Property(str, _get_generated_page_json, notify=generatedPageJsonChanged)

    # -- Event catalog --

    def _get_event_catalog_json(self) -> str:
        return self._event_catalog_json

    eventCatalogJson = Property(str, _get_event_catalog_json, notify=eventCatalogJsonChanged)

    # -- Eval status --

    def _get_eval_status(self) -> str:
        return self._eval_status

    evalStatus = Property(str, _get_eval_status, notify=evalStatusChanged)

    # ── Slots ──────────────────────────────────────────────────────

    @Slot()
    def refresh(self) -> None:
        """Reload all data from the CLI in background."""
        self._bg(self._do_refresh)

    def _do_refresh(self) -> None:
        logger.info("StreamDeckLabBridge.refresh()")
        self._do_load_templates()
        self._do_load_event_catalog()
        self._do_load_ground_truth()

    @Slot()
    def loadTemplates(self) -> None:
        """Load template list from CLI."""
        self._bg(self._do_load_templates)

    def _do_load_templates(self) -> None:
        raw = _run_cmd("list-templates", "--json")
        if raw:
            self._templates_json = raw
            self._emit_later("templatesJsonChanged")
            return

        # Fallback: read ground_truth/contexts.json for template names
        gt_path = SCRIPT_DIR / "ground_truth" / "contexts.json"
        if gt_path.exists():
            try:
                gt = json.loads(gt_path.read_text())
                templates = []
                for entry in gt:
                    templates.append({
                        "name": entry.get("template", ""),
                        "context": entry.get("context", ""),
                        "button_count": 0,
                        "status": "unverified",
                    })
                self._templates_json = json.dumps(templates)
                self._emit_later("templatesJsonChanged")
            except Exception as exc:
                logger.warning(f"Failed to parse ground truth: {exc}")
                self._set_error(f"Failed to parse ground truth: {exc}")

    def _do_load_event_catalog(self) -> None:
        """Load event catalog via subprocess."""
        raw = _run_cmd("events", "--json")
        if raw:
            # Check if it looks like JSON
            try:
                json.loads(raw)
                self._event_catalog_json = raw
                self._emit_later("eventCatalogJsonChanged")
                return
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: extract EVENT_CATALOG via subprocess
        catalog_json = _build_event_catalog_json()
        self._event_catalog_json = catalog_json
        self._emit_later("eventCatalogJsonChanged")

    def _do_load_ground_truth(self) -> None:
        """Load ground truth definitions from file."""
        gt_path = SCRIPT_DIR / "ground_truth" / "contexts.json"
        if gt_path.exists():
            try:
                self._ground_truth_json = gt_path.read_text()
                self._emit_later("groundTruthJsonChanged")
            except Exception as exc:
                logger.warning(f"Failed to load ground truth: {exc}")
                self._set_error(f"Failed to load ground truth: {exc}")

    @Slot(str)
    def evaluate(self, template_name: str) -> None:
        """Evaluate a single template in background."""
        self._set_eval_status("running")
        self._bg(lambda: self._do_evaluate(template_name))

    def _do_evaluate(self, template_name: str) -> None:
        raw = _run_cmd("evaluate", "--template", template_name, "--json")
        if raw:
            self._evaluate_result_json = raw
            try:
                result = json.loads(raw)
                self._set_eval_status("pass" if result.get("pass") else "fail")
            except Exception:
                self._set_eval_status("fail")
        else:
            self._evaluate_result_json = "null"
            self._set_eval_status("fail")
        self._emit_later("evaluateResultJsonChanged")

    @Slot()
    def evaluateAll(self) -> None:
        """Evaluate all templates in background."""
        self._set_eval_status("running")
        self._bg(self._do_evaluate_all)

    def _do_evaluate_all(self) -> None:
        raw = _run_cmd("evaluate-all", "--json")
        if raw:
            self._evaluate_result_json = raw
            try:
                results = json.loads(raw)
                all_pass = all(r.get("pass") for r in results) if results else False
                self._set_eval_status("pass" if all_pass else "fail")
            except Exception:
                self._set_eval_status("fail")
        else:
            self._evaluate_result_json = "null"
            self._set_eval_status("fail")
        self._emit_later("evaluateResultJsonChanged")

    @Slot(str, str)
    def generate(self, context: str, events_json: str) -> None:
        """Generate a dynamic page layout in background."""
        self._bg(lambda: self._do_generate(context, events_json))

    def _do_generate(self, context: str, events_json: str) -> None:
        try:
            events = json.loads(events_json) if events_json else []
        except Exception:
            events = []

        events_csv = ",".join(events)
        args = ["generate", "--context", context, "--json"]
        if events_csv:
            args.extend(["--events", events_csv])

        raw = _run_cmd(*args)
        if raw:
            self._generated_page_json = raw
        else:
            self._generated_page_json = json.dumps({"error": "generate failed"})
        self._emit_later("generatedPageJsonChanged")

    @Slot(str, str)
    def mutate(self, context: str, event: str) -> None:
        """Apply a single event mutation in background."""
        self._bg(lambda: self._do_mutate(context, event))

    def _do_mutate(self, context: str, event: str) -> None:
        raw = _run_cmd("mutate", "--template", context, "--event", event, "--json")
        if raw:
            self._generated_page_json = raw
        else:
            self._generated_page_json = json.dumps({"error": "mutate failed"})
        self._emit_later("generatedPageJsonChanged")

    @Slot()
    def pushToHardware(self) -> None:
        """Push the current generated page to Stream Deck hardware in background."""
        self._bg(self._do_push_to_hardware)

    def _do_push_to_hardware(self) -> None:
        try:
            page_data = json.loads(self._generated_page_json)
        except Exception:
            logger.warning("No generated page to push")
            return

        context = page_data.get("context", "")
        events = [
            m.get("event", "")
            for m in page_data.get("mutations", [])
            if m.get("event")
        ]
        events_csv = ",".join(events)

        args = ["push", "--context", context]
        if events_csv:
            args.extend(["--events", events_csv])

        raw = _run_cmd(*args)
        if raw:
            logger.info(f"Pushed to hardware: {raw[:100]}")
        else:
            logger.warning("Push to hardware returned no output")

    @Slot(str, str)
    def saveGroundTruth(self, context: str, data_json: str) -> None:
        """Save ground truth for a context in background."""
        self._bg(lambda: self._do_save_ground_truth(context, data_json))

    def _do_save_ground_truth(self, context: str, data_json: str) -> None:
        gt_dir = SCRIPT_DIR / "ground_truth"
        gt_dir.mkdir(parents=True, exist_ok=True)
        gt_path = gt_dir / "contexts.json"

        try:
            new_entry = json.loads(data_json)
        except Exception as exc:
            logger.error(f"Invalid ground truth JSON: {exc}")
            self._set_error(f"Invalid ground truth JSON: {exc}")
            return

        # Load existing, replace or append
        existing: list[dict] = []
        if gt_path.exists():
            try:
                existing = json.loads(gt_path.read_text())
            except Exception:
                pass

        replaced = False
        for i, entry in enumerate(existing):
            if entry.get("context") == context:
                existing[i] = new_entry
                replaced = True
                break
        if not replaced:
            existing.append(new_entry)

        gt_path.write_text(json.dumps(existing, indent=2))
        logger.info(f"Saved ground truth for context: {context}")

        self._ground_truth_json = json.dumps(existing)
        self._emit_later("groundTruthJsonChanged")

    @Slot(str)
    def loadGroundTruth(self, context: str) -> None:
        """Reload ground truth from file in background."""
        self._bg(self._do_load_ground_truth)

    @Slot()
    def loadEvents(self) -> None:
        """Load the event catalog in background."""
        self._bg(self._do_load_event_catalog)

    @Slot()
    def clearEvents(self) -> None:
        """Clear event catalog (reset to empty)."""
        self._event_catalog_json = "[]"
        self.eventCatalogJsonChanged.emit()
