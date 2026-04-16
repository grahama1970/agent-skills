"""Launch function for voice-lab GUI testing utility.

Opens a PySide6 QML window with Embry particle animation,
TTS A/B comparison, mic level meter, and persona switching.
Matches the Embry design system from the Tauri app.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger


def launch_gui() -> None:
    """Launch the voice-lab GUI window."""
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType

    from gui_bridge import VoiceLabGuiBridge
    from waveform_painter import WaveformPainter

    # Register custom QML types
    qmlRegisterType(WaveformPainter, "VoiceLab", 1, 0, "WaveformPainter")

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    bridge = VoiceLabGuiBridge()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)

    # Add QML import path for EmbryStyle + HorusStyle singletons
    qml_dir = Path(__file__).parent / "qml"
    engine.addImportPath(str(qml_dir))

    # Load main QML
    main_qml = qml_dir / "VoiceLabMain.qml"
    engine.load(QUrl.fromLocalFile(str(main_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load VoiceLabMain.qml")
        sys.exit(1)

    logger.info("Voice Lab GUI launched")

    # Clean up on exit
    app.aboutToQuit.connect(bridge.shutdown)
    app.exec()
