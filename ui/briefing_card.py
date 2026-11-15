"""Briefing card: first thing a new player sees. Explains the game loop in plain words and
offers quick-run and full-mission start buttons. It decides nothing; the Controller starts
the mission."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

CYAN = "#7fd3ff"
AMBER = "#f5b942"
GREEN = "#3ddc84"
BLUE = "#4aa3ff"

LINES = (
    ("1", "Quick Run is a 3-day demo. Full Mission is the real 30-day game."),
    ("2", "Each day, pick where extra crew effort goes: power, oxygen, water or food."),
    ("3", "Events will test you. Ask NEXUS why: answers come only from NASA and NOAA documents."),
)


class BriefingCard(QFrame):
    start = pyqtSignal(str)        # "moon", "mars", "moon-quick", "mars-quick"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BriefingCard")
        self.setStyleSheet(
            f"QFrame#BriefingCard{{background:rgba(6,12,28,0.93);"
            f"border:2px solid {CYAN};border-radius:16px;}}"
            "QLabel{background:transparent;}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)

        tag = QLabel("NEXUS  \u00b7  MISSION BRIEFING")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag.setStyleSheet(f"color:{CYAN};font-weight:bold;letter-spacing:3px;font-size:13px;")
        layout.addWidget(tag)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{background:transparent;}")
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(10)
        for number, text in LINES:
            row = QHBoxLayout()
            row.setSpacing(12)
            badge = QLabel(number)
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"color:#05070f;background:{AMBER};border-radius:14px;font-weight:bold;")
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet("color:#ffffff;font-size:15px;")
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(label, 1)
            inner_layout.addLayout(row)
        inner_layout.addStretch(1)
        self._scroll.setWidget(inner)
        layout.addWidget(self._scroll)

        quick_lbl = QLabel("QUICK RUN · 3 DAYS")
        quick_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quick_lbl.setStyleSheet(f"color:{GREEN};font-weight:bold;letter-spacing:2px;font-size:12px;")
        layout.addWidget(quick_lbl)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(14)
        self._buttons = []
        for dest, label in (("moon-quick", "QUICK RUN · MOON"),
                            ("mars-quick", "QUICK RUN · MARS")):
            button = QPushButton(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(52)
            button.setStyleSheet(
                f"QPushButton{{background:rgba(61,220,132,0.10);color:{GREEN};"
                f"border:2px solid {GREEN};border-radius:12px;font-weight:bold;"
                f"letter-spacing:2px;font-size:14px;}}"
                f"QPushButton:hover{{background:{GREEN};color:#05070f;}}")
            button.clicked.connect(lambda _=False, d=dest: self.start.emit(d))
            quick_row.addWidget(button)
            self._buttons.append(button)
        layout.addLayout(quick_row)

        full_lbl = QLabel("FULL MISSION · 30 DAYS")
        full_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        full_lbl.setStyleSheet(f"color:{BLUE};font-weight:bold;letter-spacing:2px;font-size:12px;")
        layout.addWidget(full_lbl)

        full_row = QHBoxLayout()
        full_row.setSpacing(14)
        for dest, label in (("moon", "FULL MISSION · MOON"),
                            ("mars", "FULL MISSION · MARS")):
            button = QPushButton(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(42)
            button.setStyleSheet(
                f"QPushButton{{background:rgba(74,163,255,0.08);color:{BLUE};"
                f"border:2px solid {BLUE};border-radius:12px;font-weight:bold;"
                f"letter-spacing:1px;font-size:12px;}}"
                f"QPushButton:hover{{background:{BLUE};color:#05070f;}}")
            button.clicked.connect(lambda _=False, d=dest: self.start.emit(d))
            full_row.addWidget(button)
            self._buttons.append(button)
        layout.addLayout(full_row)

        note = QLabel("All mission values are simulation values. Radiation is a planning "
                      "reference, never medical clearance. You can also type commands: "
                      "\"quick run on moon\" or \"train on mars\".")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color:#7f93b3;font-size:11px;")
        layout.addWidget(note)
        self.hide()

    # ------------------------------------------------------------ API
    def show_briefing(self) -> None:
        self.show()
        self.raise_()

    def hide_briefing(self) -> None:
        self.hide()

    def place(self, parent_width: int, parent_height: int) -> None:
        """Centre the card on the parent, capped so it never covers the lever bar."""
        width = int(min(parent_width * 0.76, 760))
        self._scroll.setMaximumHeight(max(80, int(parent_height * 0.32)))
        self.setFixedWidth(width)
        self.adjustSize()
        height = min(self.height(), int(parent_height * 0.90))
        self.setFixedHeight(height)
        self.move(max((parent_width - width) // 2, 0),
                  max((parent_height - height) // 2, 0))

    def start_buttons(self) -> list:
        return list(self._buttons)
