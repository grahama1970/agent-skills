"""PySide6 launcher for Assistant Lab KDE/QML app."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from bridge import AssistantLabBridge
from scale_helper import apply_auto_scale

QML_DIR = Path(__file__).resolve().parent / "qml"

TAB_MAP = {
    "registry": 0,
    "shadow": 1,
    "train": 2,
    "auto-improve": 3,
    "synthesis": 4,
}


def main(
    tab: str = typer.Option("registry", "--tab", help="Initial tab to display"),
) -> None:
    if tab not in TAB_MAP:
        raise typer.BadParameter(f"Invalid tab: {tab}. Choose from {list(TAB_MAP.keys())}")

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Assistant Lab")
    app.setOrganizationName("Embry")

    bridge = AssistantLabBridge()

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    engine.rootContext().setContextProperty("assistantBridge", bridge)
    engine.load(str(QML_DIR / "AssistantLabApp.qml"))

    if not engine.rootObjects():
        print("Failed to load QML", file=sys.stderr)
        sys.exit(1)

    apply_auto_scale(engine)

    root = engine.rootObjects()[0]
    root.setProperty("activeTab", TAB_MAP.get(tab, 0))

    bridge.refresh()

    sys.exit(app.exec())


if __name__ == "__main__":
    typer.run(main)
