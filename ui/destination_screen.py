"""Destination screen: choose Moon or Mars, then Quick Run or Full Mission."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from . import theme
from .common import mono

IMAGE_DIR = Path(__file__).resolve().parent.parent / "Nasa_planet_images"

BTN_QSS = f"""
QPushButton {{
    background:rgba(127,211,255,22); color:{theme.CYAN};
    border:1px solid {theme.CYAN}; border-radius:10px; padding:12px 20px;
}}
QPushButton:hover {{ background:rgba(127,211,255,50); }}
QPushButton:disabled {{ color:{theme.MUTED}; border-color:{theme.BORDER}; }}
"""
CARD_QSS = (f"QFrame#card{{background:rgba(15,29,51,230);"
            f"border:1px solid {theme.BORDER};border-radius:14px;}}")


class DestinationScreen(QWidget):
    selected = pyqtSignal(str)   # "moon" | "mars" | "moon-quick" | "mars-quick"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("destination")
        self.setStyleSheet(f"QWidget#destination{{background:{theme.BG};}}")
        self._locked = False
        self._buttons: list[QPushButton] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(60, 30, 60, 30)
        outer.setSpacing(16)
        outer.addStretch(1)

        self.greeting = QLabel("CHOOSE YOUR MISSION")
        self.greeting.setFont(mono(22, True, 4.0))
        self.greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.greeting.setStyleSheet(f"color:{theme.CYAN};")
        sub = QLabel("Pick a destination and a mission length")
        sub.setFont(mono(10, False, 1.2))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{theme.MUTED};")
        outer.addWidget(self.greeting)
        outer.addWidget(sub)

        row = QHBoxLayout()
        row.setSpacing(36)
        row.addWidget(self._card("moon", "MOON", "NasaMon.png"), 1)
        row.addWidget(self._card("mars", "MARS", "NasaMars.png"), 1)
        outer.addLayout(row)
        outer.addStretch(1)

    def set_commander(self, name: str) -> None:
        name = (name or "").strip()
        self.greeting.setText(f"COMMANDER {name.upper()}, CHOOSE YOUR MISSION"
                              if name else "CHOOSE YOUR MISSION")

    def reset(self) -> None:
        """Unlock the buttons (for example after a failed start)."""
        self._locked = False
        for b in self._buttons:
            b.setEnabled(True)

    def _card(self, dest: str, title: str, image_name: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(CARD_QSS)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        pic = QLabel()
        pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(str(IMAGE_DIR / image_name))
        if not pix.isNull():   # a missing image must never crash the screen
            pic.setPixmap(pix.scaled(QSize(520, 240),
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        heading = QLabel(title)
        heading.setFont(mono(18, True, 3.0))
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"color:{theme.TEXT};")

        quick = QPushButton("QUICK RUN  ·  3 days")
        full = QPushButton("FULL MISSION  ·  30 days")
        for b, value in ((quick, f"{dest}-quick"), (full, dest)):
            b.setFont(mono(11, True, 1.0))
            b.setStyleSheet(BTN_QSS)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=value: self._choose(v))
            self._buttons.append(b)

        for w in (pic, heading, quick, full):
            lay.addWidget(w)
        return card

    def _choose(self, value: str) -> None:
        if self._locked:       # ignore double clicks
            return
        self._locked = True
        for b in self._buttons:
            b.setEnabled(False)
        self.selected.emit(value)
