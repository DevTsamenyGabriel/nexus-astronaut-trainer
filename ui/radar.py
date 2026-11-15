"""Asteroid radar: real NASA NeoWs close approaches on a log-distance radar.

Display only. Not part of the simulation. Dot angles are arbitrary (derived from
the object name) because NeoWs gives no direction. Distance and size are real.
"""
from __future__ import annotations

import math
import time
import zlib

from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import (QBrush, QColor, QConicalGradient, QPainter,
                         QPainterPath, QPen, QRadialGradient)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from . import theme
from .common import Panel, mono
from .theme import qc

YELLOW = "#ffd84a"
LD_KM = 384400.0       # one lunar distance in km
MAX_LD = 75.0          # outer edge of the radar on the log scale
MAX_OBJECTS = 8


class RadarWidget(QWidget):
    SWEEP_DEG_PER_SEC = 70.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(120, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._t0 = time.monotonic()
        self._dots: list[dict] = []
        self.nearest: dict | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def set_data(self, neo) -> None:
        """neo is the dict from nasa_data.get_neo(), or None. Never raises."""
        dots: list[dict] = []
        nearest = None
        try:
            if isinstance(neo, dict) and neo.get("status") in ("live", "cached"):
                objs = []
                for o in neo.get("objects") or []:
                    try:
                        objs.append({"name": str(o.get("name", "?")),
                                     "miss_km": float(o["miss_km"]),
                                     "speed_kms": float(o["speed_kms"]),
                                     "diameter_m": float(o["diameter_m"]),
                                     "hazardous": bool(o.get("hazardous"))})
                    except (KeyError, TypeError, ValueError, AttributeError):
                        continue
                objs.sort(key=lambda o: o["miss_km"])
                objs = objs[:MAX_OBJECTS]
                for o in objs:
                    ld = o["miss_km"] / LD_KM
                    frac = math.log10(1.0 + ld) / math.log10(1.0 + MAX_LD)
                    frac = min(0.97, max(0.08, frac))
                    dots.append({
                        "angle": float(zlib.crc32(o["name"].encode("utf-8")) % 360),
                        "frac": frac,
                        "size": 3.0 + min(3.5, math.log10(1.0 + max(0.0, o["diameter_m"])) * 1.2),
                        "hazardous": o["hazardous"]})
                if objs:
                    nearest = dict(objs[0], ld=objs[0]["miss_km"] / LD_KM)
        except Exception:
            dots, nearest = [], None
        self._dots = dots
        self.nearest = nearest
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 8
        center = QPointF(cx, cy)
        angle = ((time.monotonic() - self._t0) * self.SWEEP_DEG_PER_SEC) % 360.0

        # Background disc + outer ring
        p.setPen(QPen(qc(theme.BORDER), 1.5))
        p.setBrush(QColor(7, 16, 31))
        p.drawEllipse(center, r, r)

        # Concentric rings
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qc(theme.BLUE, 70), 1))
        for k in (0.25, 0.5, 0.75):
            p.drawEllipse(center, r * k, r * k)

        # Crosshair
        p.setPen(QPen(qc(theme.BLUE, 60), 1))
        p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
        p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))

        # Sweep trail (conical gradient, clipped to the disc)
        clip = QPainterPath()
        clip.addEllipse(center, r, r)
        p.save()
        p.setClipPath(clip)
        cg = QConicalGradient(center, (360.0 - angle) % 360.0)
        cg.setColorAt(0.0, qc(theme.CYAN, 120))
        cg.setColorAt(0.18, qc(theme.CYAN, 0))
        cg.setColorAt(1.0, qc(theme.CYAN, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cg))
        p.drawEllipse(center, r, r)
        p.restore()

        # Sweep line
        rad = math.radians(angle)
        p.setPen(QPen(qc(theme.CYAN, 230), 2))
        p.drawLine(center, QPointF(cx + r * math.cos(rad), cy + r * math.sin(rad)))

        # Base (blue center dot with glow)
        g = QRadialGradient(center, 16)
        g.setColorAt(0.0, qc(theme.BLUE, 170))
        g.setColorAt(1.0, qc(theme.BLUE, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(center, 16, 16)
        p.setBrush(QColor(theme.BLUE))
        p.drawEllipse(center, 4.5, 4.5)

        # Real objects, farthest first so the nearest is drawn on top.
        # Each dot brightens right after the sweep passes it.
        for d in reversed(self._dots):
            a = math.radians(d["angle"])
            pt = QPointF(cx + r * d["frac"] * math.cos(a),
                         cy + r * d["frac"] * math.sin(a))
            color = theme.RED if d["hazardous"] else YELLOW
            since = (angle - d["angle"]) % 360.0
            glow = max(0.0, 1.0 - since / 140.0)
            g2 = QRadialGradient(pt, 14)
            g2.setColorAt(0.0, qc(color, int(60 + 150 * glow)))
            g2.setColorAt(1.0, qc(color, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g2))
            p.drawEllipse(pt, 14, 14)
            p.setBrush(qc(color, int(170 + 85 * glow)))
            p.drawEllipse(pt, d["size"], d["size"])
            if d is self._dots[0]:      # ring marks the nearest object (named below)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(qc(color, 200), 1.2))
                p.drawEllipse(pt, d["size"] + 5, d["size"] + 5)


class RadarPanel(Panel):
    NOTE = "Display only · distances from Earth"

    def __init__(self, parent=None):
        super().__init__("ASTEROID RADAR (NASA NeoWs)", parent=parent)
        self.radar = RadarWidget()
        self.radar.setMinimumHeight(130)
        self.body.addWidget(self.radar, 1)

        self.nearest = QLabel("")
        self.nearest.setWordWrap(True)
        self.nearest.setFont(mono(8))
        self.nearest.setStyleSheet(f"color:{theme.TEXT};")
        self.status = QLabel("WAITING FOR DATA...")
        self.status.setFont(mono(8, True, 0.6))
        self.status.setStyleSheet(f"color:{theme.MUTED};")
        self.note = QLabel(self.NOTE)
        self.note.setFont(mono(7.5))
        self.note.setStyleSheet(f"color:{theme.MUTED};")
        for lab in (self.nearest, self.status, self.note):
            self.body.addWidget(lab)
        self.nearest.hide()
        self.status.setWordWrap(True)

    def set_data(self, neo) -> None:
        """neo is the dict from nasa_data.get_neo(), or None. Never raises."""
        try:
            self.radar.set_data(neo)
            status = neo.get("status") if isinstance(neo, dict) else None
            if status == "live":
                text = f"LIVE · {neo.get('date', '')}"
                color = theme.GREEN
            elif status == "cached":
                text = f"CACHED · fetched {str(neo.get('fetched', ''))[:10]}"
                color = theme.AMBER
            else:
                text, color = "NO DATA (offline)", theme.MUTED
            self.status.setText(text)
            self.status.setStyleSheet(f"color:{color};")
            n = self.radar.nearest
            if n:
                self.nearest.setText(
                    f"{n['name']} · {n['ld']:.1f} LD from Earth · {n['speed_kms']:.1f} km/s")
                self.nearest.setToolTip(
                    f"Miss distance {n['miss_km']:,.0f} km. Source: NASA NeoWs.")
            elif status in ("live", "cached"):
                self.nearest.setText("No close approaches listed for this date.")
                self.nearest.setToolTip("")
            else:
                self.nearest.setText("")
                self.nearest.setToolTip("")
        except Exception:
            self.radar.set_data(None)
            self.status.setText("NO DATA (offline)")
            self.status.setStyleSheet(f"color:{theme.MUTED};")
            self.nearest.setText("")
