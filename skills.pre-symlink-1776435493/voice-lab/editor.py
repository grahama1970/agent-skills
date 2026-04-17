"""Launch function for voice-lab QML segment editor.

Opens a PySide6 QML window with dual waveform display (reference + recording),
video preview (YouTube + local via Jellyfin), content browser,
transport controls, and PipeWire recording integration.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from loguru import logger


def _to_embed_url(url: str) -> str:
    """Convert any YouTube URL to embed format for WebEngineView."""
    import re
    # Extract video ID from watch, share, or embed URLs
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
        r"youtu\.be/([a-zA-Z0-9_-]+)",
        r"youtube\.com/embed/([a-zA-Z0-9_-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            vid = m.group(1)
            # Preserve start time if present
            start = ""
            sm = re.search(r"[?&](?:start|t)=(\d+)", url)
            if sm:
                start = f"&start={sm.group(1)}"
            return f"https://www.youtube.com/embed/{vid}?enablejsapi=1&origin=null{start}"
    # Already an embed URL or unknown format — return as-is
    return url


def _extract_video_id(url: str) -> str | None:
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


def launch_editor(
    ref_audio: Path,
    srt_path: Path,
    output_dir: Path | None = None,
    youtube_url: str = "",
    persona: str = "graham",
) -> None:
    """Launch the follow-along recording editor.

    Args:
        ref_audio: Path to reference audio (vocals.wav from stems).
        srt_path: Path to SRT file with segment timestamps.
        output_dir: Output directory for alignment.json + recordings.
                    Defaults to ref_audio's parent directory.
        youtube_url: Optional YouTube embed URL for preview panel.
        persona: Persona name for persistent takes directory.
    """
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    # Scale UI for large/high-DPI monitors (override with QT_SCALE_FACTOR env var)
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")
    # Chromium flags for WebEngine YouTube playback on Linux
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
        "--autoplay-policy=no-user-gesture-required "
        "--disable-features=UseChromeOSDirectVideoDecoder "
        "--enable-gpu-rasterization"
    )

    # Compute persistent takes directory when YouTube URL is provided
    if youtube_url:
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
            logger.info(f"Persistent takes dir: {takes_dir}")

    # WebEngine must be initialized before QGuiApplication
    from PySide6.QtWebEngineQuick import QtWebEngineQuick
    QtWebEngineQuick.initialize()

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType

    from content_provider import ContentProvider
    from editor_bridge import VoiceLabBridge
    from waveform_painter import WaveformPainter

    if output_dir is None:
        output_dir = ref_audio.parent

    # Register custom QML types
    qmlRegisterType(WaveformPainter, "VoiceLab", 1, 0, "WaveformPainter")

    # Bootstrap HorusStyle.qml if not present
    qml_dir = Path(__file__).parent / "qml"
    horus_style = qml_dir / "HorusStyle.qml"
    if not horus_style.exists():
        source = Path.home() / "workspace/experiments/horus/apps/horus-overlay/src/ui/HorusStyle.qml"
        if source.exists():
            shutil.copy2(source, horus_style)
            logger.info(f"Copied HorusStyle.qml from horus-overlay")

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    # Create bridge and load session (pass persistent output dir)
    bridge = VoiceLabBridge()
    bridge.loadSession(str(ref_audio), str(srt_path), str(output_dir))

    # Backward compat: if youtube_url provided at launch, auto-set as initial video source
    if youtube_url:
        # Normalize to embed format for WebEngineView
        embed_url = _to_embed_url(youtube_url)
        bridge.setVideoSource(embed_url, "youtube", "YouTube")

    # Create content provider (Jellyfin search bridge)
    content_provider = ContentProvider()

    # Create QML engine
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("contentProvider", content_provider)

    # Add QML import path for HorusStyle singleton
    engine.addImportPath(str(qml_dir))

    # Load editor QML
    editor_qml = qml_dir / "Editor.qml"
    engine.load(QUrl.fromLocalFile(str(editor_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load Editor.qml")
        sys.exit(1)

    logger.info(f"Editor launched: {ref_audio.name}" + (f" (YouTube: {youtube_url})" if youtube_url else ""))
    app.exec()
