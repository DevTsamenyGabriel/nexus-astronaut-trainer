"""Shared building blocks: fonts, Panel, PulseDot, BarWidget, RoundButton, Avatar."""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (QColor, QFont, QPainter, QPen, QBrush, QLinearGradient,
                         QRadialGradient, QPolygonF)
from PyQt6.QtWidgets import QAbstractButton, QFrame, QLabel, QVBoxLayout, QWidget, QSizePolicy

from . import theme
from .theme import qc


def mono(size: float = 10, bold: bool = False, spacing: float = 0.0) -> QFont:
    """Monospace font (Consolas -> Courier New -> monospace)."""
    f = QFont()
    f.setFamilies(theme.FONT_FAMILIES)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSizeF(size)
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def section_title(text: str, color: str = theme.CYAN) -> QLabel:
    """Small letter-spaced panel title."""
    lbl = QLabel(text)
    lbl.setFont(mono(9.5, True, 2.0))
    lbl.setStyleSheet(f"color:{color};")
    return lbl


def panel_qss(border: str, top: str = "rgba(15,29,51,238)",
              bottom: str = "rgba(11,20,38,238)") -> str:
    return (
        "QFrame#panel{"
        f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {top},stop:1 {bottom});"
        f"border:1px solid {border};border-radius:12px;}}"
    )


class Panel(QFrame):
    """Dark navy rounded panel with a thin blue border. Add children to self.body."""

    def __init__(self, title: str = "", accent: str = theme.BORDER,
                 title_color: str = theme.CYAN, tint: tuple[str, str] | None = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        if tint:
            self.setStyleSheet(panel_qss(accent, tint[0], tint[1]))
        else:
            self.setStyleSheet(panel_qss(accent))
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(8)
        if title:
            self.body.addWidget(section_title(title, title_color))


class PulseDot(QWidget):
    """Glowing dot, optionally pulsing."""

    def __init__(self, color: str, pulse: bool = True, size: int = 14, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._pulse = pulse
        self._phase = 0.0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance)
        if pulse:
            self._timer.start()

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def set_pulse(self, pulse: bool) -> None:
        self._pulse = pulse
        if pulse:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _advance(self) -> None:
        self._phase = (self._phase + 0.18) % (2 * math.pi)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = 0.5 + 0.5 * math.sin(self._phase) if self._pulse else 0.6
        c = QPointF(self.width() / 2, self.height() / 2)
        r = self.width() / 2
        g = QRadialGradient(c, r)
        g.setColorAt(0.0, qc(self._color.name(), int(190 * k + 40)))
        g.setColorAt(1.0, qc(self._color.name(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r, r)
        p.setBrush(self._color)
        p.drawEllipse(c, 3.6, 3.6)


class BarWidget(QWidget):
    """Thin rounded progress bar (value 0..1)."""

    def __init__(self, color: str, height: int = 8, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._value = 0.0
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, frac: float) -> None:
        frac = max(0.0, min(1.0, frac))
        if abs(frac - self._value) > 1e-4:
            self._value = frac
            self.update()

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#16273f"))
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        fw = w * self._value
        if fw > 0:
            g = QLinearGradient(0, 0, w, 0)
            g.setColorAt(0.0, self._color.darker(160))
            g.setColorAt(1.0, self._color)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(QRectF(0, 0, max(fw, h), h), h / 2, h / 2)


class Avatar(QLabel):
    """Circular avatar with initials."""

    def __init__(self, text: str, color: str, size: int = 36, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(mono(size / 3.6, True))
        c = QColor(color)
        self.setStyleSheet(
            f"background:rgba({c.red()},{c.green()},{c.blue()},40);"
            f"color:{color};border:1px solid {color};border-radius:{size // 2}px;"
        )


class RoundButton(QAbstractButton):
    """Round icon button painted in code. kind = 'mic' or 'send'."""

    def __init__(self, kind: str, size: int = 48, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._active = False
        self._phase = 0.0
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance)

    def set_active(self, active: bool) -> None:
        """Mic 'listening' look (pulsing red)."""
        self._active = active
        if active:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _advance(self) -> None:
        self._phase = (self._phase + 0.25) % (2 * math.pi)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.width() / 2
        c = QPointF(r, r)
        hover = self.underMouse()
        p.setPen(Qt.PenStyle.NoPen)

        if self.kind == "mic":
            if self._active:
                k = 0.5 + 0.5 * math.sin(self._phase)
                p.setBrush(qc(theme.RED, int(40 + 70 * k)))
                p.drawEllipse(c, r, r)
                fill, border, icon = qc(theme.RED, 235), QColor(theme.RED), QColor("#ffffff")
            else:
                fill = QColor("#12294a") if hover else QColor("#0c1a31")
                border, icon = QColor(theme.CYAN), QColor(theme.CYAN)
            p.setPen(QPen(border, 1.6))
            p.setBrush(fill)
            p.drawEllipse(c, r - 4, r - 4)
            self._draw_mic(p, c, icon)
        else:
            p.setBrush(QColor("#6bb7ff") if hover else QColor(theme.BLUE))
            p.drawEllipse(c, r - 2, r - 2)
            self._draw_send(p, c)

    @staticmethod
    def _draw_mic(p: QPainter, c: QPointF, color: QColor) -> None:
        p.save()
        p.translate(c)
        pen = QPen(color, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(-4, -11, 8, 14), 4, 4)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(-8, -7, 16, 14), 180 * 16, 180 * 16)
        p.drawLine(QPointF(0, 7), QPointF(0, 11))
        p.drawLine(QPointF(-4, 11), QPointF(4, 11))
        p.restore()

    @staticmethod
    def _draw_send(p: QPainter, c: QPointF) -> None:
        p.save()
        p.translate(c.x() + 1, c.y())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BG))
        p.drawPolygon(QPolygonF([QPointF(-8, -9), QPointF(10, 0),
                                 QPointF(-8, 9), QPointF(-4, 0)]))
        p.restore()
