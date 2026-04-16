"""PySide6 QML launcher for the Classifier Lab GUI.

Registers ClassifierLabBridge as a context property and loads
ClassifierLabApp.qml with the EmbryStyle singleton.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger


def launch_app() -> None:
    """Launch the Classifier Lab tabbed application."""
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from bridge import ClassifierLabBridge
    from scale_helper import apply_auto_scale

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    bridge = ClassifierLabBridge()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("classifierBridge", bridge)

    # Add QML import path for EmbryStyle singleton
    qml_dir = Path(__file__).parent / "qml"
    engine.addImportPath(str(qml_dir))

    app_qml = qml_dir / "ClassifierLabApp.qml"
    engine.load(QUrl.fromLocalFile(str(app_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load ClassifierLabApp.qml")
        sys.exit(1)

    apply_auto_scale(engine)

    logger.info("Classifier Lab launched")

    app.aboutToQuit.connect(bridge.refresh)
    app.exec()


if __name__ == "__main__":
    launch_app()
