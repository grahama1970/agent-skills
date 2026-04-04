"""QQuickPaintedItem waveform renderer for voice-lab editor.

Renders audio waveform peaks using QPainter with Horus design tokens.
Peaks-only renderer — playhead, I/O markers, and recording glow are
handled by QML overlays in Timeline.qml.
"""
from __future__ import annotations

from PySide6.QtCore import Property, Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtQuick import QQuickPaintedItem


class WaveformPainter(QQuickPaintedItem):
    """Custom QML item that paints an audio waveform from peak data."""

    peaksChanged = Signal()
    waveColorChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peaks = []  # Interleaved [min0, max0, min1, max1, ...]
        self._wave_color = QColor(74, 158, 255, 102)  # rgba(74,158,255,0.4) - reference blue

        # Horus design tokens
        self._bg_color = QColor("#141414")
        self._center_line_color = QColor(255, 255, 255, 25)  # rgba(255,255,255,0.1)

    # -- Properties --

    @Property("QVariantList", notify=peaksChanged)
    def peaks(self):
        return self._peaks

    @peaks.setter
    def peaks(self, value):
        self._peaks = value
        self.peaksChanged.emit()
        self.update()

    @Property(QColor, notify=waveColorChanged)
    def waveColor(self):
        return self._wave_color

    @waveColor.setter
    def waveColor(self, value):
        self._wave_color = QColor(value) if isinstance(value, str) else value
        self.waveColorChanged.emit()
        self.update()

    def paint(self, painter: QPainter):
        """Render the waveform peaks only."""
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        # Background
        painter.fillRect(QRectF(0, 0, w, h), self._bg_color)

        # Center line
        center_y = h / 2
        painter.setPen(QPen(self._center_line_color, 1))
        painter.drawLine(0, int(center_y), int(w), int(center_y))

        # Waveform bars
        if self._peaks:
            n_pairs = len(self._peaks) // 2
            if n_pairs > 0:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(self._wave_color))

                step = w / n_pairs
                for i in range(n_pairs):
                    mn = self._peaks[i * 2]
                    mx = self._peaks[i * 2 + 1]

                    # Map -1..1 to pixel coordinates (center-aligned)
                    y_top = center_y - (mx * center_y)
                    y_bot = center_y - (mn * center_y)
                    bar_h = max(1, y_bot - y_top)

                    x = i * step
                    bar_w = max(1, step - 0.5)
                    painter.drawRect(QRectF(x, y_top, bar_w, bar_h))
