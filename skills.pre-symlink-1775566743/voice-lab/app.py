"""Unified launcher for voice-lab tabbed app.

Opens VoiceLabApp.qml with both editorBridge and guiBridge registered.
Replaces the separate editor.py and gui.py launchers.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def _to_embed_url(url: str) -> str:
    """Convert any YouTube URL to embed format for WebEngineView."""
    import re
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
        r"youtu\.be/([a-zA-Z0-9_-]+)",
        r"youtube\.com/embed/([a-zA-Z0-9_-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            vid = m.group(1)
            start = ""
            sm = re.search(r"[?&](?:start|t)=(\d+)", url)
            if sm:
                start = f"&start={sm.group(1)}"
            return f"https://www.youtube.com/embed/{vid}?enablejsapi=1&origin=null{start}"
    return url


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from any URL format."""
    import re
    for pat in [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
        r"youtu\.be/([a-zA-Z0-9_-]+)",
        r"youtube\.com/embed/([a-zA-Z0-9_-]+)",
    ]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def launch_app(
    ref_audio: Optional[Path] = None,
    srt_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    youtube_url: str = "",
    persona: str = "graham",
    start_tab: str = "dashboard",
) -> None:
    """Launch the unified voice-lab tabbed app.

    Args:
        ref_audio: Path to reference audio (optional, for Record tab).
        srt_path: Path to SRT file (optional, for Record tab).
        output_dir: Output directory for recordings.
        youtube_url: YouTube URL for editor preview.
        persona: Persona name.
        start_tab: Tab to show on launch (record, tts-compare, dashboard, rvc-sweep).
    """
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")
    # Chromium flags for WebEngine YouTube playback
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
        "--autoplay-policy=no-user-gesture-required "
        "--disable-features=UseChromeOSDirectVideoDecoder "
        "--enable-gpu-rasterization"
    )

    # Compute persistent takes directory when YouTube URL is provided
    if youtube_url and ref_audio:
        video_id = _extract_video_id(youtube_url)
        if video_id:
            voice_storage = Path(os.environ.get(
                "VOICE_STORAGE", "/mnt/storage12tb/media/personas"
            ))
            if not voice_storage.exists():
                voice_storage = Path.home() / "personas"
            takes_dir = voice_storage / persona / "voice-lab-takes" / video_id
            takes_dir.mkdir(parents=True, exist_ok=True)
            if output_dir is None:
                output_dir = takes_dir

    # WebEngine must be initialized before QGuiApplication
    from PySide6.QtWebEngineQuick import QtWebEngineQuick
    QtWebEngineQuick.initialize()

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType

    from content_provider import ContentProvider
    from editor_bridge import VoiceLabBridge
    from gui_bridge import VoiceLabGuiBridge
    from scale_helper import apply_auto_scale
    from waveform_painter import WaveformPainter

    # Register custom QML types
    qmlRegisterType(WaveformPainter, "VoiceLab", 1, 0, "WaveformPainter")

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    # Create both bridges
    gui_bridge = VoiceLabGuiBridge()
    editor_bridge = VoiceLabBridge()

    # Share mic: editor reads from gui_bridge's single pw-record
    editor_bridge.set_mic_source(gui_bridge)

    # Load editor session if ref_audio provided
    if ref_audio and srt_path:
        if output_dir is None:
            output_dir = ref_audio.parent
        editor_bridge.loadSession(str(ref_audio), str(srt_path), str(output_dir))
        if youtube_url:
            embed_url = _to_embed_url(youtube_url)
            editor_bridge.setVideoSource(embed_url, "youtube", "YouTube")
        start_tab = "record"

    # Content provider for the editor's content browser
    content_provider = ContentProvider()

    # Create QML engine with both bridges
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("editorBridge", editor_bridge)
    engine.rootContext().setContextProperty("guiBridge", gui_bridge)
    engine.rootContext().setContextProperty("contentProvider", content_provider)
    engine.rootContext().setContextProperty("startTab", start_tab)

    # Add QML import path for style singletons
    qml_dir = Path(__file__).parent / "qml"
    engine.addImportPath(str(qml_dir))

    # Load unified app QML
    app_qml = qml_dir / "VoiceLabApp.qml"
    engine.load(QUrl.fromLocalFile(str(app_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load VoiceLabApp.qml")
        sys.exit(1)

    apply_auto_scale(engine)

    logger.info(f"Voice Lab App launched (tab: {start_tab})")

    app.aboutToQuit.connect(gui_bridge.shutdown)
    app.exec()
