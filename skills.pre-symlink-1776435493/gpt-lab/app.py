"""Standard PySide6 launcher for the GPT Lab QML application.

Registers GptLabBridge as a context property and loads GptLabApp.qml.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger


def launch_app() -> None:
    """Launch the GPT Lab QML application."""
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from bridge import GptLabBridge
    from scale_helper import apply_auto_scale

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    bridge = GptLabBridge()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("gptBridge", bridge)

    # Add QML import path for EmbryStyle singleton
    qml_dir = Path(__file__).parent / "qml"
    engine.addImportPath(str(qml_dir))

    app_qml = qml_dir / "GptLabApp.qml"
    engine.load(QUrl.fromLocalFile(str(app_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load GptLabApp.qml")
        sys.exit(1)

    apply_auto_scale(engine)

    logger.info("GPT Lab app launched")

    app.exec()


if __name__ == "__main__":
    launch_app()
