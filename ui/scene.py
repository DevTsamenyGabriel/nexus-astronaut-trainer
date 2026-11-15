"""Outpost scene: image by destination plus hotspots pinned by fraction of image size."""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

IMAGE_DIR = Path(__file__).resolve().parent.parent / "dashboard_images"

# resource -> (fraction x, fraction y, label). First guesses: calibrate with NEXUS_CALIBRATE=1.
HOTSPOTS = {
    "moon": {
        "power": (0.30, 0.38, "SOLAR ARRAY"),
        "food": (0.80, 0.50, "HYDROPONICS"),
        "oxygen": (0.52, 0.45, "LIFE SUPPORT"),
        "water": (0.20, 0.62, "WATER TANK"),
    },
    "mars": {
        "power": (0.30, 0.38, "SOLAR ARRAY"),
        "food": (0.80, 0.50, "HYDROPONICS"),
        "oxygen": (0.52, 0.45, "LIFE SUPPORT"),
        "water": (0.20, 0.62, "WATER TANK"),
    },
}

GREEN, AMBER, RED, IDLE = "#3ddc84", "#f5b942", "#ff4d4d", "#7fa6d6"


def level_color(level) -> str:
    if level is None:
        return IDLE
    if level > 50:
        return GREEN
    if level >= 20:
        return AMBER
    return RED


class SceneView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dest = "moon"
        self._pix: QPixmap | None = None
        self._levels: dict = {}
        self._flash = None
        self._flash_on = False
        self._ticks = 0
        self._timer = QTimer(self)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.set_destination("moon")

    # ------------------------------------------------------------ API
    def set_destination(self, dest: str) -> None:
        self._dest = dest if dest in HOTSPOTS else "moon"
        pix = QPixmap(str(IMAGE_DIR / f"{self._dest}_dashboard.png"))
        self._pix = pix if not pix.isNull() else None
        self.update()

    def set_levels(self, resources) -> None:
        try:
            self._levels = {k: float(v) for k, v in dict(resources or {}).items()}
        except Exception:
            self._levels = {}
        self.update()

    def flash(self, resource: str) -> None:
        if resource not in HOTSPOTS[self._dest]:
            return
        self._flash, self._flash_on, self._ticks = resource, True, 8
        self._timer.start()
        self.update()

    def has_image(self) -> bool:
        return self._pix is not None

    # ------------------------------------------------------- internals
    def _tick(self) -> None:
        self._ticks -= 1
        self._flash_on = self._ticks % 2 == 0
        if self._ticks <= 0:
            self._timer.stop()
            self._flash, self._flash_on = None, False
        self.update()

    def _image_rect(self) -> QRectF:
        """Cover fit: the image fills the widget and overflow is cropped evenly.
        Hotspot fractions stay relative to the full image, so they stay on target."""
        w, h = self.width(), self.height()
        if self._pix is None:
            return QRectF(0, 0, w, h)
        scale = max(w / self._pix.width(), h / self._pix.height())
        iw, ih = self._pix.width() * scale, self._pix.height() * scale
        return QRectF((w - iw) / 2, (h - ih) / 2, iw, ih)

    def mousePressEvent(self, event) -> None:
        if os.environ.get("NEXUS_CALIBRATE") == "1":
            rect = self._image_rect()
            pos = event.position()
            fx = (pos.x() - rect.x()) / rect.width()
            fy = (pos.y() - rect.y()) / rect.height()
            print(f"CALIBRATE {self._dest}: ({fx:.2f}, {fy:.2f})")
        super().mousePressEvent(event)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self._image_rect()
        if self._pix is None:
            p.fillRect(self.rect(), QColor("#0a1224"))
            p.setPen(QColor(IDLE))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "OUTPOST IMAGE NOT FOUND (simulation still runs)")
            return
        p.drawPixmap(rect, self._pix, QRectF(self._pix.rect()))

        font = QFont("Consolas", max(7, int(rect.width() / 95)))
        font.setBold(True)
        p.setFont(font)
        metrics = QFontMetrics(font)
        radius = rect.width() * 0.032

        for key, (fx, fy, label) in HOTSPOTS[self._dest].items():
            cx = rect.x() + fx * rect.width()
            cy = rect.y() + fy * rect.height()
            level = self._levels.get(key)
            color = QColor(level_color(level))
            flashing = self._flash == key and self._flash_on

            fill = QColor(color)
            fill.setAlpha(210 if flashing else 110)
            p.setPen(QPen(QColor("#ffffff") if flashing else color, 3 if flashing else 2))
            p.setBrush(fill)
            p.drawEllipse(QPointF(cx, cy), radius, radius)

            text = label if level is None else f"{label} {level:.0f}"
            tw, th = metrics.horizontalAdvance(text) + 14, metrics.height() + 6
            pill = QRectF(cx - tw / 2, cy + radius + 4, tw, th)
            p.setPen(QPen(color, 1))
            p.setBrush(QColor(5, 10, 24, 215))
            p.drawRoundedRect(pill, 6, 6)
            p.setPen(color)
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
