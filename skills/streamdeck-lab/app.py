"""Stream Deck Lab -- PySide6/QML application launcher.

Opens StreamDeckLabApp.qml with the deckBridge context property
for all backend communication.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

TAB_MAP = {
    "templates": 0,
    "ground-truth": 1,
    "evaluate": 2,
    "generator": 3,
    "events": 4,
}


def launch_app(start_tab: str = "templates") -> None:
    """Launch the Stream Deck Lab QML application.

    Args:
        start_tab: Tab to show on launch (templates, ground-truth, evaluate,
                   generator, events).
    """
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from bridge import StreamDeckLabBridge
    from scale_helper import apply_auto_scale

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    bridge = StreamDeckLabBridge()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("deckBridge", bridge)
    engine.rootContext().setContextProperty("streamdeckBridge", bridge)
    engine.rootContext().setContextProperty("startTab", TAB_MAP.get(start_tab, 0))

    # Add QML import path for EmbryStyle singleton
    qml_dir = Path(__file__).parent / "qml"
    engine.addImportPath(str(qml_dir))

    app_qml = qml_dir / "StreamDeckLabApp.qml"
    engine.load(QUrl.fromLocalFile(str(app_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load StreamDeckLabApp.qml")
        sys.exit(1)

    apply_auto_scale(engine)

    logger.info(f"Stream Deck Lab launched (tab: {start_tab})")

    app.exec()


if __name__ == "__main__":
    tab = sys.argv[1] if len(sys.argv) > 1 else "templates"
    launch_app(start_tab=tab)
