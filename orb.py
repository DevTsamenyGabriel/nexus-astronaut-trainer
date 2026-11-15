"""Floating NEXUS orb: a frameless, always-on-top, translucent, draggable window.

States: idle | listening | thinking | speaking | alert
Signals: clicked (toggle listening), show_dashboard_requested, quit_requested
"""
from __future__ import annotations

import math
import random
import time

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFontMetricsF, QPainter, QPen, QPolygonF,
                         QRadialGradient)
from PyQt6.QtWidgets import QMenu, QWidget

from ui import theme
from ui.common import mono

STATE_COLORS = {
    "idle": (127, 211, 255),       # calm cyan
    "listening": (61, 220, 151),   # green
    "thinking": (74, 163, 255),    # blue
    "speaking": (160, 225, 255),   # bright cyan
    "alert": (255, 110, 60),       # orange-red
}


def wrap_text(text: str, fm: QFontMetricsF, width: float, max_lines: int = 5) -> list[str]:
    """Simple word wrapper (avoids Qt flag/enum quirks)."""
    lines, cur = [], ""
    for word in text.split():
        trial = word if not cur else f"{cur} {word}"
        if fm.horizontalAdvance(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,;") + "…"
    return lines


class NexusOrb(QWidget):
    clicked = pyqtSignal()
    show_dashboard_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    W, H = 280, 340
    CY = 232            # orb center y
    RING_R = 62         # waveform ring base radius
    N_POINTS = 72

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("NEXUS Orb")
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self.state_name = "idle"
        self.simulate_mic = True          # set False and call set_mic_level() for real input
        self._rgb = list(STATE_COLORS["idle"])
        self._level = 0.0
        self._target_level = 0.0
        self._next_level = 0.0
        self._t0 = time.monotonic()
        self._talking = False
        self._talk = 0.0
        self._voice_target = 0.0
        self._next_syllable = 0.0

        self._bubble_lines: list[str] = []
        self._bubble_t0 = 0.0
        self._bubble_deadline = 0.0
        self._bubble_font = mono(9)

        self._press_global = None
        self._drag_offset = None
        self._moved = False

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------------ API
    def set_state(self, name: str) -> None:
        if name in STATE_COLORS and name != self.state_name:
            self.state_name = name
            if name != "listening":
                self._target_level = 0.0

    def set_mic_level(self, level: float) -> None:
        """Feed a real 0..1 mic level here later (and set simulate_mic = False)."""
        self._target_level = max(0.0, min(1.0, level))

    def set_talking(self, on: bool) -> None:
        self._talking = on

    def say(self, text: str, seconds: float = 6.0) -> None:
        """Show a text bubble above the orb; it fades out after `seconds`."""
        text = " ".join(text.split())
        if len(text) > 150:
            text = text[:147].rstrip() + "…"
        fm = QFontMetricsF(self._bubble_font)
        self._bubble_lines = wrap_text(text, fm, 232)
        self._bubble_t0 = time.monotonic()
        self._bubble_deadline = self._bubble_t0 + seconds

    def hide_bubble(self) -> None:
        self._bubble_lines = []

    # ------------------------------------------------------------ animation
    def _tick(self) -> None:
        now = time.monotonic()
        target = STATE_COLORS[self.state_name]
        for i in range(3):
            self._rgb[i] += (target[i] - self._rgb[i]) * 0.10
        if self.state_name == "listening" and self.simulate_mic and now >= self._next_level:
            self._target_level = random.random()
            self._next_level = now + 0.09
        self._level += (self._target_level - self._level) * 0.25
        if self._talking:
            if now >= self._next_syllable:
                self._voice_target = (
                    random.uniform(0.35, 1.0)
                    if random.random() > 0.18 else 0.1)
                self._next_syllable = now + random.uniform(0.08, 0.18)
            goal = self._voice_target
        else:
            goal = 0.0
        self._talk += (goal - self._talk) * (
            0.35 if goal > self._talk else 0.22)
        self.update()

    def _amp(self, th: float, t: float) -> float:
        s = self.state_name
        if s == "idle":
            return 2.0 + 1.5 * math.sin(3 * th + t * 0.9)
        if s == "listening":
            return self._level * 18 * (0.55 + 0.45 * math.sin(5 * th + t * 7)) \
                * (0.6 + 0.4 * math.sin(3 * th - t * 5)) + 1.5
        if s == "thinking":
            return 3.0 + 2.0 * math.sin(6 * th - t * 4)
        if s == "speaking":
            return 2.0 + 17.0 * self._talk * (
                0.5 + 0.5 * math.sin(4 * th + t * 6))
        pulse = 0.5 + 0.5 * math.sin(t * 5.5)      # alert
        return 3 + 9 * pulse * (0.6 + 0.4 * math.sin(8 * th + t * 3))

    def _wave(self, cx: float, cy: float, base: float, t: float, scale: float) -> QPolygonF:
        pts = []
        for i in range(self.N_POINTS):
            th = 2 * math.pi * i / self.N_POINTS
            r = base + self._amp(th, t) * scale
            pts.append(QPointF(cx + r * math.cos(th), cy + r * math.sin(th)))
        return QPolygonF(pts)

    # --------------------------------------------------------------- paint
    def paintEvent(self, _):
        now = time.monotonic()
        t = now - self._t0
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, g, b = (int(v) for v in self._rgb)
        cx, cy = self.W / 2, float(self.CY)
        s = self.state_name

        if s == "idle":
            pulse = 0.5 + 0.5 * math.sin(t * 1.0)
            gi = 0.55 + 0.15 * pulse
        elif s == "listening":
            pulse = 0.4 + 0.6 * self._level
            gi = 0.7 + 0.3 * self._level
        elif s == "thinking":
            pulse = 0.5 + 0.5 * math.sin(t * 4.5)
            gi = 0.7 + 0.3 * pulse
        elif s == "speaking":
            pulse = 0.25 + 0.75 * self._talk
            gi = 0.6 + 0.4 * self._talk
        else:
            pulse = 0.5 + 0.5 * math.sin(t * 5.5)
            gi = 0.7 + 0.4 * pulse

        center = QPointF(cx, cy)

        # Outer glow
        glow_r = 96 + 14 * pulse
        gg = QRadialGradient(center, glow_r)
        gg.setColorAt(0.0, QColor(r, g, b, int(120 * min(gi, 1.0))))
        gg.setColorAt(0.45, QColor(r, g, b, int(40 * gi)))
        gg.setColorAt(1.0, QColor(r, g, b, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gg))
        p.drawEllipse(center, glow_r, glow_r)

        # Waveform ring (soft wide stroke + bright thin stroke + inner echo)
        p.setBrush(Qt.BrushStyle.NoBrush)
        poly = self._wave(cx, cy, self.RING_R, t, 1.0)
        p.setPen(QPen(QColor(r, g, b, 55), 7, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolygon(poly)
        p.setPen(QPen(QColor(r, g, b, 235), 2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolygon(poly)
        p.setPen(QPen(QColor(r, g, b, 110), 1.2))
        p.drawPolygon(self._wave(cx, cy, self.RING_R - 7, t + 0.6, 0.6))

        # Thinking: rotating scan arcs
        if s == "thinking":
            rect = QRectF(cx - self.RING_R - 9, cy - self.RING_R - 9,
                          2 * (self.RING_R + 9), 2 * (self.RING_R + 9))
            start = -(t * 260) % 360
            p.setPen(QPen(QColor(r, g, b, 230), 3, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, int(start * 16), 70 * 16)
            p.setPen(QPen(QColor(r, g, b, 110), 3, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, int((start + 180) * 16), 40 * 16)

        # Core orb
        core_r = 36 + 4 * pulse
        cg = QRadialGradient(center, core_r, QPointF(cx - core_r * 0.3, cy - core_r * 0.35))
        cg.setColorAt(0.0, QColor(min(255, r + 110), min(255, g + 90), min(255, b + 70), 255))
        cg.setColorAt(0.55, QColor(r, g, b, 210))
        cg.setColorAt(1.0, QColor(int(r * 0.35), int(g * 0.35), int(b * 0.45), 240))
        p.setBrush(QBrush(cg))
        p.setPen(QPen(QColor(r, g, b, 200), 1.5))
        p.drawEllipse(center, core_r, core_r)

        self._paint_bubble(p, now, (r, g, b))

    def _paint_bubble(self, p: QPainter, now: float, rgb) -> None:
        if not self._bubble_lines:
            return
        left = self._bubble_deadline - now
        if left <= 0:
            self._bubble_lines = []
            return
        alpha = min(1.0, (now - self._bubble_t0) / 0.25, left / 0.8)
        fm = QFontMetricsF(self._bubble_font)
        lh = fm.height()
        w = max(fm.horizontalAdvance(l) for l in self._bubble_lines) + 26
        h = lh * len(self._bubble_lines) + 18
        x, bottom = (self.W - w) / 2, 146.0
        y = bottom - h
        p.setOpacity(max(0.0, alpha))
        p.setBrush(QColor(8, 18, 36, 235))
        p.setPen(QPen(QColor(rgb[0], rgb[1], rgb[2], 170), 1.2))
        p.drawRoundedRect(QRectF(x, y, w, h), 12, 12)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(8, 18, 36, 235))
        mid = self.W / 2
        p.drawPolygon(QPolygonF([QPointF(mid - 7, bottom - 0.5), QPointF(mid + 7, bottom - 0.5),
                                 QPointF(mid, bottom + 8)]))
        p.setFont(self._bubble_font)
        p.setPen(QColor(theme.TEXT))
        ty = y + 9 + fm.ascent()
        for line in self._bubble_lines:
            p.drawText(QPointF(mid - fm.horizontalAdvance(line) / 2, ty), line)
            ty += lh
        p.setOpacity(1.0)

    # --------------------------------------------------- mouse / menu events
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.frameGeometry().topLeft()
            self._moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if (e.buttons() & Qt.MouseButton.LeftButton) and self._drag_offset is not None:
            gp = e.globalPosition().toPoint()
            if (gp - self._press_global).manhattanLength() > 4:
                self._moved = True
            if self._moved:
                self.move(gp - self._drag_offset)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
