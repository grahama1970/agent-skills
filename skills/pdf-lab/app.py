"""PySide6 launcher for PDF Lab KDE/QML app."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from bridge import PdfLabBridge
from scale_helper import apply_auto_scale

QML_DIR = Path(__file__).resolve().parent / "qml"

TAB_MAP = {
    "tune": 0,
    "annotate": 1,
    "parameters": 2,
    "questions": 3,
    "history": 4,
}


def main(
    pdf: Optional[str] = typer.Option(None, "--pdf", help="PDF file to load on startup"),
    tab: str = typer.Option("tune", "--tab", help="Initial tab to display"),
) -> None:
    if tab not in TAB_MAP:
        raise typer.BadParameter(f"Invalid tab: {tab}. Choose from {list(TAB_MAP.keys())}")

    app = QGuiApplication(sys.argv)
    app.setApplicationName("PDF Lab")
    app.setOrganizationName("Embry")

    bridge = PdfLabBridge()

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    engine.rootContext().setContextProperty("pdfBridge", bridge)
    engine.load(str(QML_DIR / "PdfLabApp.qml"))

    if not engine.rootObjects():
        print("Failed to load QML", file=sys.stderr)
        sys.exit(1)

    apply_auto_scale(engine)

    # Set initial tab
    root = engine.rootObjects()[0]
    root.setProperty("activeTab", TAB_MAP.get(tab, 0))

    # Load PDF if provided
    if pdf:
        bridge.loadPdf(pdf)

    # Initial data load
    bridge.refresh()

    sys.exit(app.exec())


if __name__ == "__main__":
    typer.run(main)
