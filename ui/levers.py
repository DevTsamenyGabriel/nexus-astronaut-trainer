"""Lever bar: choose where the crew's extra effort goes today, then end the day.
Emits plain command strings only. The Controller sends them through handle_command(),
same as typed text."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

BOOSTS = (
    ("power", "POWER", "#f5b942"),
    ("oxygen", "OXYGEN", "#4aa3ff"),
    ("water", "WATER", "#38d6e8"),
    ("food", "FOOD", "#3ddc84"),
)
GO_COLOR = "#ff8a3d"
MUTED = "#7f93b3"
CYAN = "#7fd3ff"


def _qss(color: str, active: bool) -> str:
    fill = color if active else "rgba(10,20,40,0.85)"
    text = "#05070f" if active else color
    return (
        f"QPushButton{{background:{fill};color:{text};border:2px solid {color};"
        f"border-radius:10px;padding:10px 14px;font-weight:bold;letter-spacing:1px;}}"
        f"QPushButton:hover{{background:{color};color:#05070f;}}"
        f"QPushButton:disabled{{color:#4a5a73;border-color:#2a3550;"
        f"background:rgba(10,20,40,0.5);}}"
    )


class LeverBar(QWidget):
    command = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons: dict[str, QPushButton] = {}
        self._colors: dict[str, str] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # --- step headers ---
        heads = QHBoxLayout()
        heads.setSpacing(10)
        step1 = QLabel("1 · WHERE DOES THE CREW WORK TODAY?")
        step1.setStyleSheet(f"color:{CYAN};font-weight:bold;letter-spacing:2px;font-size:11px;")
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{MUTED};font-size:11px;")
        step2 = QLabel("2 · THEN END THE DAY")
        step2.setStyleSheet(f"color:{GO_COLOR};font-weight:bold;letter-spacing:2px;font-size:11px;")
        heads.addWidget(step1)
        heads.addWidget(self._status, 1)
        heads.addWidget(step2)
        outer.addLayout(heads)

        # --- buttons ---
        row = QHBoxLayout()
        row.setSpacing(10)
        tips = {
            "power": "Send extra crew effort to power. Applies when you end the day.",
            "oxygen": "Send extra crew effort to oxygen and CO2 scrubbing. Applies when you end the day.",
            "water": "Send extra crew effort to water. Applies when you end the day.",
            "food": "Send extra crew effort to food growing. Applies when you end the day.",
        }
        for key, label, color in BOOSTS:
            button = self._make(key, label, color, f"boost {key}")
            button.setToolTip(tips[key] + " (simulation values)")
            row.addWidget(button, 2)
        go = self._make("go", "END DAY  ▶", GO_COLOR, "go")
        go.setToolTip("Advance the simulation by one day (simulation values)")
        go.setMinimumHeight(go.sizeHint().height() + 8)
        row.addWidget(go, 3)
        outer.addLayout(row)

        self.set_selected(None)

    def _make(self, key: str, label: str, color: str, text: str) -> QPushButton:
        button = QPushButton(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(_qss(color, False))
        button.clicked.connect(lambda _=False, t=text: self.command.emit(t))
        self.buttons[key] = button
        self._colors[key] = color
        return button

    def set_selected(self, resource) -> None:
        """Highlight the pending extra effort. None clears the highlight."""
        for key, _label, color in BOOSTS:
            self.buttons[key].setStyleSheet(_qss(color, key == resource))
        if resource:
            self._status.setText(f"Extra effort today: {str(resource).upper()}")
            self._status.setStyleSheet("color:#f5b942;font-size:11px;font-weight:bold;")
        else:
            self._status.setText("Extra effort today: none (balanced crew)")
            self._status.setStyleSheet(f"color:{MUTED};font-size:11px;")

    def status_text(self) -> str:
        return self._status.text()

    def set_enabled(self, enabled: bool) -> None:
        for button in self.buttons.values():
            button.setEnabled(bool(enabled))
