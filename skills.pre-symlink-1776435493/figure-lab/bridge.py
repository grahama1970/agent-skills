"""PySide6 QObject bridge for figure-lab GUI.

Exposes gallery data, evaluation results, promote lists, and catalog status
to QML. All skill operations delegate to figure_lab.py via subprocess.

Convention: bridge wraps CLI via subprocess, NEVER imports internals.
Heavy ops run in daemon threads to keep QML responsive.
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import QMetaObject, QObject, Property, Qt, Signal, Slot

SKILL_DIR = Path(__file__).resolve().parent
GALLERY_DIR = SKILL_DIR / "gallery"
PROMOTE_THRESHOLD = 0.75


def _run_cli(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run figure_lab.py CLI command via uv."""
    cmd = ["uv", "run", "--project", str(SKILL_DIR),
           "python", "figure_lab.py", *args]
    logger.debug("bridge cmd: {}", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(SKILL_DIR),
    )


def _load_gallery_meta() -> list[dict[str, Any]]:
    """Load all gallery metadata JSONs directly (no CLI --json needed)."""
    items: list[dict[str, Any]] = []
    if not GALLERY_DIR.exists():
        return items
    for jf in sorted(GALLERY_DIR.glob("*.json")):
        try:
            data = json.loads(jf.read_text())
            items.append(data)
        except Exception as exc:
            logger.debug("Skipping {}: {}", jf.name, exc)
    return items


class FigureLabBridge(QObject):
    """Bridge between QML and figure-lab skill CLI."""

    # -- path validation ---------------------------------------------------

    @staticmethod
    def _validate_path(path: str) -> Path:
        """Validate and resolve a user-provided file path."""
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")
        return p

    # Signals for property changes
    galleryJsonChanged = Signal()
    evaluateResultJsonChanged = Signal()
    promoteListJsonChanged = Signal()
    catalogStatusJsonChanged = Signal()
    composeStatusChanged = Signal()
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
        self._gallery_json = "[]"
        self._evaluate_result_json = "{}"
        self._promote_list_json = '{"pending":[],"promoted":[],"stats":{}}'
        self._catalog_status_json = "{}"
        self._compose_status = "{}"
        self._tab_registry_json = self._load_tab_registry()

    # -- Tab registry --------------------------------------------------------

    @staticmethod
    def _load_tab_registry() -> str:
        path = SKILL_DIR / "qml" / "tab-registry.json"
        try:
            return path.read_text()
        except Exception:
            return "{}"

    def _get_tab_registry_json(self) -> str:
        return self._tab_registry_json

    tabRegistryJson = Property(str, _get_tab_registry_json,
                               notify=tabRegistryJsonChanged)

    # -- Gallery -------------------------------------------------------------

    def _get_gallery_json(self) -> str:
        return self._gallery_json

    galleryJson = Property(str, _get_gallery_json, notify=galleryJsonChanged)

    # -- Evaluate result -----------------------------------------------------

    def _get_evaluate_result_json(self) -> str:
        return self._evaluate_result_json

    evaluateResultJson = Property(str, _get_evaluate_result_json,
                                  notify=evaluateResultJsonChanged)

    # -- Promote list --------------------------------------------------------

    def _get_promote_list_json(self) -> str:
        return self._promote_list_json

    promoteListJson = Property(str, _get_promote_list_json,
                               notify=promoteListJsonChanged)

    # -- Catalog status ------------------------------------------------------

    def _get_catalog_status_json(self) -> str:
        return self._catalog_status_json

    catalogStatusJson = Property(str, _get_catalog_status_json,
                                 notify=catalogStatusJsonChanged)

    # -- Compose status ------------------------------------------------------

    def _get_compose_status(self) -> str:
        return self._compose_status

    composeStatus = Property(str, _get_compose_status,
                             notify=composeStatusChanged)

    # -- Slots ---------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        """Reload gallery, promote list, and catalog status."""
        def _work():
            self._load_gallery_internal("", 0.0, False)
            self._load_promote_list()
            self._load_catalog_status()
        threading.Thread(target=_work, daemon=True).start()

    @Slot(str, str, str, str, str)
    def compose(self, viz_type: str, data_path: str, title: str,
                description: str, output_path: str) -> None:
        """Compose a new visualization in a background thread."""
        validated_data: Path | None = None
        if data_path:
            try:
                validated_data = self._validate_path(data_path)
            except FileNotFoundError as exc:
                logger.warning(f"Invalid data path: {exc}")
                return
        resolved_output: Path | None = None
        if output_path:
            resolved_output = Path(output_path).resolve()
            if not resolved_output.parent.exists():
                logger.warning(f"Invalid output path: parent directory does not exist: {resolved_output.parent}")
                return
        def _work():
            args = ["compose", "--type", viz_type]
            if validated_data:
                args += ["--data", str(validated_data)]
            # CLI uses --description (no --title); combine both
            desc = f"{title}: {description}" if title and description else (title or description)
            if desc:
                args += ["--description", desc]
            if resolved_output:
                args += ["--output", str(resolved_output)]
            try:
                result = _run_cli(*args)
                if result.returncode == 0:
                    status = {"status": "ok"}
                    # Try to find the output path from the gallery
                    items = _load_gallery_meta()
                    if items:
                        latest = max(items, key=lambda x: x.get("created_at", ""))
                        status["output_path"] = latest.get("output_path", "")
                else:
                    status = {"status": "error", "error": result.stderr[:300]}
            except subprocess.TimeoutExpired:
                status = {"status": "error", "error": "timeout"}
                self._set_error("Compose timed out")
            except Exception as exc:
                status = {"status": "error", "error": str(exc)}
                self._set_error(f"Compose failed: {exc}")
            self._compose_status = json.dumps(status)
            self._emit_later("composeStatusChanged")
            # Refresh gallery after compose
            self._load_gallery_internal("", 0.0, False)
        threading.Thread(target=_work, daemon=True).start()

    @Slot(str)
    def evaluate(self, composition_path: str) -> None:
        """Evaluate a single composition in a background thread."""
        try:
            validated = self._validate_path(composition_path)
        except FileNotFoundError as exc:
            logger.warning(f"Invalid composition path: {exc}")
            return
        def _work():
            try:
                result = _run_cli("evaluate", "--input", str(validated))
                if result.returncode == 0:
                    # Re-read the metadata JSON for the evaluated file
                    p = validated
                    meta_path = p.with_suffix(".json")
                    if meta_path.exists():
                        data = json.loads(meta_path.read_text())
                    else:
                        data = {"status": "ok", "raw": result.stdout[:500]}
                else:
                    data = {"status": "error", "error": result.stderr[:300]}
            except Exception as exc:
                data = {"status": "error", "error": str(exc)}
                self._set_error(f"Evaluate failed: {exc}")
            self._evaluate_result_json = json.dumps(data)
            self._emit_later("evaluateResultJsonChanged")
        threading.Thread(target=_work, daemon=True).start()

    @Slot()
    def evaluateAll(self) -> None:
        """Evaluate all compositions in the gallery."""
        def _work():
            items = _load_gallery_meta()
            last_result: dict[str, Any] = {}
            for item in items:
                path = item.get("output_path", "")
                if path and Path(path).exists():
                    try:
                        _run_cli("evaluate", "--input", path)
                    except Exception as exc:
                        logger.warning("evaluate {} failed: {}", path, exc)
            # Reload after evaluating all
            items = _load_gallery_meta()
            if items:
                last_result = items[-1]
            else:
                last_result = {"status": "ok"}
            self._evaluate_result_json = json.dumps(last_result)
            self._emit_later("evaluateResultJsonChanged")
            self._load_gallery_internal("", 0.0, False)
            self._load_promote_list()
        threading.Thread(target=_work, daemon=True).start()

    @Slot(str)
    def promote(self, name: str) -> None:
        """Promote a composition by name in a background thread."""
        def _work():
            # Find the HTML file in gallery by name
            html_path = GALLERY_DIR / f"{name}.html"
            if html_path.exists():
                try:
                    _run_cli("promote", "--input", str(html_path))
                except Exception as exc:
                    logger.error("promote {} failed: {}", name, exc)
                    self._set_error(f"Failed to promote {name}: {exc}")
            else:
                logger.warning("No HTML found for '{}' at {}", name, html_path)
            self._load_gallery_internal("", 0.0, False)
            self._load_promote_list()
        threading.Thread(target=_work, daemon=True).start()

    @Slot(str)
    def demote(self, name: str) -> None:
        """Demote a composition by name (reset promoted flag)."""
        def _work():
            meta_path = GALLERY_DIR / f"{name}.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text())
                    data["promoted"] = False
                    data["promoted_at"] = None
                    meta_path.write_text(json.dumps(data, indent=2))
                    logger.info("Demoted '{}'", name)
                except Exception as exc:
                    logger.error("demote {} failed: {}", name, exc)
                    self._set_error(f"Failed to demote {name}: {exc}")
            else:
                logger.warning("No metadata found for '{}' at {}", name, meta_path)
            self._load_gallery_internal("", 0.0, False)
            self._load_promote_list()
        threading.Thread(target=_work, daemon=True).start()

    @Slot(str, float, bool)
    def loadGallery(self, filter_type: str, min_score: float,
                    promoted_only: bool) -> None:
        """Load gallery with filters (called from QML)."""
        def _work():
            self._load_gallery_internal(filter_type, min_score, promoted_only)
        threading.Thread(target=_work, daemon=True).start()

    @Slot()
    def loadPromoteCandidates(self) -> None:
        """Load promotion candidates list."""
        def _work():
            self._load_promote_list()
        threading.Thread(target=_work, daemon=True).start()

    @Slot()
    def catalogStatus(self) -> None:
        """Refresh catalog status."""
        def _work():
            self._load_catalog_status()
        threading.Thread(target=_work, daemon=True).start()

    # -- Internal helpers ----------------------------------------------------

    def _load_gallery_internal(self, filter_type: str, min_score: float,
                               promoted_only: bool) -> None:
        """Load gallery metadata, apply filters, update property."""
        items = _load_gallery_meta()
        # Apply filters
        if filter_type:
            items = [i for i in items if i.get("viz_type") == filter_type]
        if min_score > 0:
            items = [i for i in items
                     if (i.get("overall_score") or 0) >= min_score]
        if promoted_only:
            items = [i for i in items if i.get("promoted")]
        self._gallery_json = json.dumps(items)
        self._emit_later("galleryJsonChanged")

    def _load_promote_list(self) -> None:
        """Build promote list from gallery metadata."""
        items = _load_gallery_meta()
        pending = [i for i in items
                   if not i.get("promoted")
                   and (i.get("overall_score") or 0) >= PROMOTE_THRESHOLD]
        promoted = [i for i in items if i.get("promoted")]
        failing = [i for i in items
                   if not i.get("promoted")
                   and (i.get("overall_score") or 0) < PROMOTE_THRESHOLD]
        result = {
            "pending": pending,
            "promoted": promoted,
            "stats": {
                "total": len(items),
                "promoted": len(promoted),
                "pending": len(pending),
                "failing": len(failing),
            },
        }
        self._promote_list_json = json.dumps(result)
        self._emit_later("promoteListJsonChanged")

    def _load_catalog_status(self) -> None:
        """Load catalog status via CLI."""
        try:
            result = _run_cli("catalog-status")
            # Parse the Rich table output for total/pending counts
            stdout = result.stdout
            total = 0
            pending = 0
            for line in stdout.splitlines():
                if "implemented" in line.lower() and "pending" in line.lower():
                    import re
                    nums = re.findall(r"(\d+)", line)
                    if len(nums) >= 2:
                        total = int(nums[0])
                        pending = int(nums[1])
            data = {"total": total, "pending": pending}
        except Exception as exc:
            logger.warning("catalog-status failed: {}", exc)
            self._set_error(f"Failed to load catalog status: {exc}")
            data = {"total": 0, "pending": 0}
        self._catalog_status_json = json.dumps(data)
        self._emit_later("catalogStatusJsonChanged")
