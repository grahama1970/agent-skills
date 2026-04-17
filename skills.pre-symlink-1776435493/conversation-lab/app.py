"""Unified PySide6 launcher for Conversation Lab QML app.

Usage:
    python app.py [--session FILE] [--tab ID]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from bridge import ConversationLabBridge
from scale_helper import apply_auto_scale

QML_DIR = Path(__file__).resolve().parent / "qml"


def launch_app(
    session_file: str | None = None,
    start_tab: str = "diagnose",
) -> int:
    """Launch the Conversation Lab QML application."""
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Conversation Lab")
    app.setOrganizationName("Embry")

    engine = QQmlApplicationEngine()

    # Create bridge
    conv_bridge = ConversationLabBridge(session_file=session_file)

    # Register bridge as context property
    engine.rootContext().setContextProperty("convBridge", conv_bridge)

    # Add QML import path for EmbryStyle singleton
    engine.addImportPath(str(QML_DIR))

    # Load QML
    qml_file = QML_DIR / "ConversationLabApp.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        print("ERROR: Failed to load QML", file=sys.stderr)
        return 1

    apply_auto_scale(engine)

    # Set initial tab
    tab_map = {"diagnose": 0, "sessions": 1, "converge": 2, "promote": 3}
    root = engine.rootObjects()[0]
    if start_tab in tab_map:
        root.setProperty("activeTab", tab_map[start_tab])

    return app.exec()


def main(
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Session JSONL file path"),
    tab: str = typer.Option("diagnose", "--tab", "-t", help="Initial tab to display"),
) -> None:
    valid_tabs = ["diagnose", "sessions", "converge", "promote"]
    if tab not in valid_tabs:
        raise typer.BadParameter(f"Invalid tab: {tab}. Choose from {valid_tabs}")
    sys.exit(launch_app(session_file=session, start_tab=tab))


if __name__ == "__main__":
    typer.run(main)
