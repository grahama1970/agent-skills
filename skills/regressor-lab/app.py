"""Launcher for Regressor Lab PySide6/QML app.

Opens RegressorLabApp.qml with regressorBridge registered as context property.
Supports --tab flag to open a specific tab on launch.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from loguru import logger

TAB_MAP = {"data": 0, "benchmark": 1, "results": 2, "tune": 3, "deploy": 4}


def launch_app(start_tab: str = "data") -> None:
    """Launch the Regressor Lab tabbed app."""
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from bridge import RegressorLabBridge
    from scale_helper import apply_auto_scale

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    bridge = RegressorLabBridge()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("regressorBridge", bridge)

    # Pass starting tab index to QML
    tab_index = TAB_MAP.get(start_tab, 0)
    engine.rootContext().setContextProperty("startTabIndex", tab_index)

    # Add QML import path for EmbryStyle singleton
    qml_dir = Path(__file__).parent / "qml"
    engine.addImportPath(str(qml_dir))

    app_qml = qml_dir / "RegressorLabApp.qml"
    engine.load(QUrl.fromLocalFile(str(app_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load RegressorLabApp.qml")
        sys.exit(1)

    apply_auto_scale(engine)

    logger.info(f"Regressor Lab app launched (tab: {start_tab})")
    app.exec()


def main(
    tab: str = typer.Option("data", "--tab", help="Tab to open on launch (default: data)"),
) -> None:
    if tab not in TAB_MAP:
        raise typer.BadParameter(f"Invalid tab: {tab}. Choose from {list(TAB_MAP.keys())}")
    launch_app(start_tab=tab)


if __name__ == "__main__":
    typer.run(main)
