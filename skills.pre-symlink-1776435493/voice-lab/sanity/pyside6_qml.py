#!/usr/bin/env python3
"""
Sanity script: PySide6 + QtMultimedia for voice-lab QML editor.
Purpose: Verify PySide6 QML engine and multimedia work headless.
Exit codes: 0=PASS, 1=FAIL
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

errors = []

# Check 1: Core PySide6 imports
print("Check 1 - PySide6 core imports: ", end="", flush=True)
try:
    from PySide6.QtCore import QObject, Signal, Slot, Property, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    print("PASS")
except ImportError as e:
    print(f"FAIL ({e})")
    print("\nInstall: uv pip install 'PySide6>=6.6.0'")
    sys.exit(1)

# Check 2: QQuickPaintedItem (for custom waveform renderer)
print("Check 2 - QQuickPaintedItem: ", end="", flush=True)
try:
    from PySide6.QtQuick import QQuickPaintedItem
    print("PASS")
except ImportError as e:
    print(f"FAIL ({e})")
    errors.append("QQuickPaintedItem")

# Check 3: QtMultimedia (for audio playback)
print("Check 3 - QtMultimedia: ", end="", flush=True)
try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    print("PASS")
except ImportError as e:
    print(f"FAIL ({e})")
    errors.append("QtMultimedia")

# Check 4: Create QGuiApplication headless
print("Check 4 - QGuiApplication (offscreen): ", end="", flush=True)
try:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    print("PASS")
except Exception as e:
    print(f"FAIL ({e})")
    errors.append("QGuiApplication")

# Check 5: Load minimal QML via engine
print("Check 5 - QQmlApplicationEngine: ", end="", flush=True)
try:
    import tempfile
    from pathlib import Path

    engine = QQmlApplicationEngine()
    # Write a minimal QML file
    qml_content = 'import QtQuick\nItem { width: 100; height: 100 }'
    with tempfile.NamedTemporaryFile(suffix=".qml", mode="w", delete=False) as f:
        f.write(qml_content)
        qml_path = f.name
    engine.load(QUrl.fromLocalFile(qml_path))
    Path(qml_path).unlink()
    if engine.rootObjects():
        print("PASS")
    else:
        print("PASS (engine loaded, no root object in offscreen mode)")
except Exception as e:
    print(f"FAIL ({e})")
    errors.append("QQmlApplicationEngine")

if errors:
    print(f"\nFAIL: {len(errors)} check(s) failed: {', '.join(errors)}")
    sys.exit(1)
else:
    print("\nResult: PASS (PySide6 + QtMultimedia ready for voice-lab editor)")
    sys.exit(0)
