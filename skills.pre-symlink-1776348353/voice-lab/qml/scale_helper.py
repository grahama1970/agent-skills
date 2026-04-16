"""Auto-detect display scale factor for EmbryStyle QML apps.

Usage in app.py (after engine.load succeeds):
    from scale_helper import apply_auto_scale
    apply_auto_scale(app, engine)
"""
from __future__ import annotations

import os

from PySide6.QtCore import QMetaObject, Qt, Q_ARG
from PySide6.QtGui import QGuiApplication


def detect_scale_factor() -> float:
    """Return a scale factor based on primary screen DPI.

    Base DPI = 96 (standard 1080p).  A 4K 27" monitor is ~163 DPI -> 1.7x.
    Clamped to [1.0, 2.5] range matching EmbryStyle limits.
    Override with EMBRY_SCALE env var.
    """
    env = os.environ.get("EMBRY_SCALE")
    if env:
        try:
            return max(0.8, min(float(env), 2.5))
        except ValueError:
            pass

    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return 1.0

    dpi = screen.physicalDotsPerInch()
    factor = dpi / 96.0
    # Round to nearest 0.1
    factor = round(factor, 1)
    return max(1.0, min(factor, 2.5))


def apply_auto_scale(engine) -> float:
    """Set EmbryStyle.scaleFactor on the QML singleton. Returns the factor.

    Call after engine.load() succeeds and rootObjects() is non-empty.
    """
    factor = detect_scale_factor()
    if factor <= 1.0:
        return factor

    root_objects = engine.rootObjects()
    if not root_objects:
        return factor

    root = root_objects[0]
    # Use QML evaluate to set the singleton property
    from PySide6.QtQml import QQmlExpression
    ctx = engine.rootContext()
    expr = QQmlExpression(ctx, root, f"EmbryStyle.scaleFactor = {factor}")
    expr.evaluate()
    return factor
