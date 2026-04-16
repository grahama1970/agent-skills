#!/usr/bin/env python3
"""Evidence Case Viewer — KDE/QML app with EmbryStyle.

Launch modes:
  app.py                    — Open viewer, tail events from pipeline
  app.py --question "..."   — Open viewer AND run pipeline immediately
  app.py --tail-only        — Just tail existing log (no pipeline)
  app.py --emit-only "..."  — Run pipeline headless (no GUI), write NDJSON
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer

# Ensure our skill directory is on path for events.py import
SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))


def main(
    question: str = typer.Option("", "--question", "-q", help="Question to evaluate immediately on launch"),
    tail_only: bool = typer.Option(False, "--tail-only", help="Only tail the event log (don't run pipeline)"),
    emit_only: str = typer.Option("", "--emit-only", help="Run pipeline headless (no GUI), write NDJSON to stdout"),
    log: str = typer.Option("/tmp/evidence-case-events.jsonl", "--log", help="NDJSON event log path"),
    subagent_url: str = typer.Option("http://localhost:8620", "--subagent-url", help="URL of /create-subagent container for chat well"),
) -> None:
    # Headless mode: just run pipeline and print events
    if emit_only:
        from events import run_evidence_pipeline, EventEmitter
        emitter = EventEmitter(log)
        result = run_evidence_pipeline(emit_only, emitter)
        import json
        print(json.dumps(result, indent=2, default=str))
        return

    # GUI mode
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtCore import QUrl, QTimer

    from bridge import EvidenceBridge

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Evidence Case Viewer")
    app.setOrganizationName("EmbryOS")

    engine = QQmlApplicationEngine()

    # Create bridge and register as context property
    bridge = EvidenceBridge(log_path=log, subagent_url=subagent_url)
    engine.rootContext().setContextProperty("evidenceBridge", bridge)

    # Load QML
    qml_file = SKILL_DIR / "qml" / "EvidenceCaseViewer.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        print("ERROR: Failed to load QML", file=sys.stderr)
        sys.exit(1)

    # Start tailing the event log
    bridge.startTailing()

    # Check if /create-subagent is running
    bridge.checkAgentHealth()

    # If question provided, run pipeline after UI is up
    if question and not tail_only:
        QTimer.singleShot(200, lambda: bridge.runPipeline(question))

    sys.exit(app.exec())


if __name__ == "__main__":
    typer.run(main)
