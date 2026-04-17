"""PySide6 launcher for figure-lab tabbed app.

Opens FigureLabApp.qml with figureBridge registered as context property.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

# Tab name -> StackLayout index (matches tab-registry.json)
TAB_MAP = {"composer": 0, "gallery": 1, "evaluate": 2, "promote": 3}


def launch_app(start_tab: str = "composer") -> None:
    """Launch the figure-lab GUI.

    Args:
        start_tab: Tab to show on launch (composer, gallery, evaluate, promote).
    """
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from bridge import FigureLabBridge
    from scale_helper import apply_auto_scale

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    bridge = FigureLabBridge()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("figureBridge", bridge)
    engine.rootContext().setContextProperty("startTab",
                                           TAB_MAP.get(start_tab, 0))

    # Add QML import path for EmbryStyle singleton
    qml_dir = Path(__file__).parent / "qml"
    engine.addImportPath(str(qml_dir))

    app_qml = qml_dir / "FigureLabApp.qml"
    engine.load(QUrl.fromLocalFile(str(app_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load FigureLabApp.qml")
        sys.exit(1)

    apply_auto_scale(engine)

    logger.info("Figure Lab App launched (tab: {})", start_tab)

    app.exec()


if __name__ == "__main__":
    tab = sys.argv[1] if len(sys.argv) > 1 else "composer"
    launch_app(start_tab=tab)
