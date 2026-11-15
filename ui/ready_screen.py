"""Ready screen: 'Are you ready?' -> wish -> 3, 2, 1 -> LAUNCHING. Emits go() once.
It decides nothing about the mission; EntryWindow starts it after go()."""
from __future__ import annotations

import config
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .common import mono

BTN_QSS = f"""
QPushButton {{
    background:rgba(127,211,255,22); color:{theme.CYAN};
    border:1px solid {theme.CYAN}; border-radius:10px; padding:14px 40px;
}}
QPushButton:hover {{ background:rgba(127,211,255,50); }}
QPushButton:disabled {{ color:{theme.MUTED}; border-color:{theme.BORDER}; }}
"""


class ReadyScreen(QWidget):
    go = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ready")
        self.setStyleSheet(f"QWidget#ready{{background:{theme.BG};}}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._name = ""
        self._busy = False
        self._count = 0
        self._timer = QTimer(self)
        self._timer.setInterval(900)
        self._timer.timeout.connect(self._tick)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(60, 30, 60, 30)
        outer.setSpacing(18)
        outer.addStretch(1)

        self.title = QLabel("ARE YOU READY, COMMANDER?")
        self.title.setFont(mono(22, True, 4.0))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(f"color:{theme.CYAN};")
        self.sub = QLabel("")
        self.sub.setFont(mono(11, False, 1.5))
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setStyleSheet(f"color:{theme.MUTED};")
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet(f"color:{theme.TEXT};")
        self.message.setMinimumHeight(120)
        self.button = QPushButton("I'M READY")
        self.button.setFont(mono(13, True, 2.0))
        self.button.setStyleSheet(BTN_QSS)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.clicked.connect(self._start)

        for w in (self.title, self.sub, self.message):
            outer.addWidget(w)
        outer.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

    def prepare(self, name: str, dest: str) -> None:
        """Reset the screen for a new start. dest is moon, mars, moon-quick or mars-quick."""
        self._timer.stop()
        self._busy = False
        self._name = (name or "").strip()
        who = f", COMMANDER {self._name.upper()}" if self._name else ", COMMANDER"
        self.title.setText(f"ARE YOU READY{who}?")
        planet = str(dest).split("-")[0].upper()
        if str(dest).endswith("-quick"):
            length = f"QUICK RUN · {config.QUICK_DAYS} DAYS"
        else:
            length = f"FULL MISSION · {config.FULL_DAYS} DAYS"
        self.sub.setText(f"{planet} · {length}")
        self.message.setText("")
        self.button.setEnabled(True)
        self.button.show()

    def _start(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.button.setEnabled(False)
        self.button.hide()
        who = self._name or "Commander"
        self.message.setFont(mono(16, True, 1.5))
        self.message.setText(f"Good luck, Commander {who}. The crew is counting on you.")
        QTimer.singleShot(2000, self._begin_count)

    def _begin_count(self) -> None:
        self._count = 3
        self.message.setFont(mono(72, True, 4.0))
        self._tick()
        self._timer.start()

    def _tick(self) -> None:
        if self._count > 0:
            self.message.setText(str(self._count))
            self._count -= 1
        else:
            self._timer.stop()
            self.message.setFont(mono(22, True, 3.0))
            self.message.setText("LAUNCHING…")
            QTimer.singleShot(250, self.go.emit)   # lets the text paint before the heavy build

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._start()
        else:
            super().keyPressEvent(event)
