"""Result card: end-of-mission screen. It only displays what the Controller gives it
from the real simulation state. It decides nothing."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

GREEN = "#3ddc84"
RED = "#ff4d4d"
CYAN = "#7fd3ff"


class ResultCard(QFrame):
    restart = pyqtSignal(str)      # "moon" or "mars"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ResultCard")
        self._color = GREEN
        self._apply_style(GREEN)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(10)

        tag = QLabel("MISSION REPORT (SIMULATION)")
        tag.setStyleSheet(f"color:{CYAN};font-weight:bold;letter-spacing:2px;")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel("")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setStyleSheet("color:#ffffff;font-size:15px;")
        self._stats = QLabel("")
        self._stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stats.setStyleSheet("color:#cfe3ff;")
        note = QLabel("All values are simulation values. Radiation is a planning "
                      "reference, never medical clearance.")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color:#7f93b3;font-size:11px;")
        for widget in (tag, self._title, self._detail, self._stats, note):
            layout.addWidget(widget)

        row = QHBoxLayout()
        row.setSpacing(12)
        self._buttons = []
        for dest, label in (("moon", "PLAY AGAIN · MOON"),
                            ("mars", "PLAY AGAIN · MARS")):
            button = QPushButton(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(44)
            button.setStyleSheet(
                f"QPushButton{{background:rgba(10,20,40,0.9);color:{CYAN};"
                f"border:2px solid {CYAN};border-radius:10px;font-weight:bold;"
                f"letter-spacing:1px;padding:6px 16px;}}"
                f"QPushButton:hover{{background:{CYAN};color:#05070f;}}")
            button.clicked.connect(lambda _=False, d=dest: self.restart.emit(d))
            row.addWidget(button)
            self._buttons.append(button)
        layout.addLayout(row)
        self.hide()

    def _apply_style(self, color: str) -> None:
        self._color = color
        self.setStyleSheet(
            f"QFrame#ResultCard{{background:rgba(6,12,28,0.94);"
            f"border:2px solid {color};border-radius:16px;}}"
            "QLabel{background:transparent;}")

    # ------------------------------------------------------------ API
    def show_result(self, success: bool, headline: str, detail: str, stats) -> None:
        color = GREEN if success else RED
        self._apply_style(color)
        self._title.setStyleSheet(
            f"color:{color};font-size:28px;font-weight:bold;letter-spacing:3px;")
        self._title.setText(str(headline))
        self._detail.setText(str(detail))
        self._stats.setText("\n".join(str(line) for line in (stats or [])))
        self.show()
        self.raise_()

    def hide_result(self) -> None:
        self.hide()

    def place(self, parent_width: int, parent_height: int) -> None:
        """Centre the card on the parent."""
        width = max(340, int(min(parent_width * 0.70, 640)))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move(max((parent_width - width) // 2, 0),
                  max((parent_height - self.height()) // 2, 0))

    def title_text(self) -> str:
        return self._title.text()

    def restart_buttons(self) -> list:
        return list(self._buttons)
