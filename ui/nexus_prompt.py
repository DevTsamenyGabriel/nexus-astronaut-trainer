"""NEXUS prompt bar (above the scene), choice chips and the bottom scrim.
They only display text and emit the id of the chip the player clicked. They decide nothing."""
from __future__ import annotations

import html

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

CYAN = "#38d6e8"
RED = "#ff5a5a"
GREEN = "#3ddc84"
WELCOME = "Welcome, Commander. Choose Quick Run or Full Mission to begin. All values are simulated."
IDLE = "Standing by. All values are simulated."


class NexusBar(QFrame):
    """Glass banner above the scene. Types its text out like a console."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NexusBar")
        self._alert = None
        self._prefix = "NEXUS"
        self._full = ""
        self._shown = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setStyleSheet(
            "background:transparent;color:#ffffff;font-size:14px;font-weight:bold;")
        layout.addWidget(self._label)
        self.setFixedHeight(92)
        self._timer = QTimer(self)
        self._timer.setInterval(22)
        self._timer.timeout.connect(self._tick)
        self.type_text(WELCOME)

    def _style(self, alert: bool) -> None:
        if alert == self._alert:
            return
        self._alert = alert
        color = RED if alert else CYAN
        self.setStyleSheet(
            f"QFrame#NexusBar{{background:rgba(8,16,36,0.90);"
            f"border:2px solid {color};border-radius:14px;}}")

    def set_text(self, text: str, alert: bool = False, prefix: str = "NEXUS") -> None:
        """Show text immediately, no typing."""
        self._timer.stop()
        self._prefix = prefix
        self._full = " ".join(str(text or "").split())
        self._shown = len(self._full)
        self._style(bool(alert))
        self._render()

    def type_text(self, text: str, alert: bool = False, prefix: str = "NEXUS") -> None:
        """Type the text out character by character."""
        self._prefix = prefix
        self._full = " ".join(str(text or "").split())
        self._shown = 0
        self._style(bool(alert))
        self._render()
        self._timer.start()

    def append_text(self, text: str) -> None:
        """Add a sentence to what is being typed (used while an answer streams in)."""
        extra = " ".join(str(text or "").split())
        if not extra:
            return
        self._full = f"{self._full} {extra}".strip()
        if not self._timer.isActive():
            self._timer.start()

    def set_idle(self) -> None:
        self.set_text(IDLE)

    def _tick(self) -> None:
        self._shown += 1
        if self._shown >= len(self._full):
            self._shown = len(self._full)
            self._timer.stop()
        self._render()

    def _render(self) -> None:
        if self._prefix == "NASA":
            color = GREEN
        else:
            color = RED if self._alert else CYAN
        caret = "▌" if self._timer.isActive() else ""
        body = html.escape(self._full[:self._shown])
        self._label.setText(
            f"<span style='color:{color};'>{html.escape(self._prefix)}:</span> {body}{caret}")


class Scrim(QWidget):
    """Soft dark gradient at the bottom of the scene so the HUD reads as a layer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, max(1, self.height()))
        gradient.setColorAt(0.0, QColor(3, 7, 18, 0))
        gradient.setColorAt(0.45, QColor(3, 7, 18, 170))
        gradient.setColorAt(1.0, QColor(3, 7, 18, 240))
        painter.fillRect(self.rect(), QBrush(gradient))


class ChoiceBar(QWidget):
    """Row of up to three small glass chips below the scene."""
    chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 2, 0, 2)
        self._lay.setSpacing(12)
        self._lay.addStretch(1)
        self._lay.addStretch(1)
        self._buttons: list[QPushButton] = []
        self.setFixedHeight(46)
        self.hide()

    def buttons(self) -> list:
        return list(self._buttons)

    def has_items(self) -> bool:
        return bool(self._buttons)

    def clear(self) -> None:
        for button in self._buttons:
            self._lay.removeWidget(button)
            button.deleteLater()
        self._buttons = []
        self.hide()

    def set_choices(self, items) -> None:
        """items: list of (id, short label, tooltip), at most three."""
        for button in self._buttons:
            self._lay.removeWidget(button)
            button.deleteLater()
        self._buttons = []
        for index, (option_id, short, tooltip) in enumerate(list(items)[:3]):
            label = f"{index + 1} · {short}" if len(items) > 1 else str(short)
            button = QPushButton(label)
            button.setToolTip(tooltip)
            button.setMinimumHeight(38)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton{{background:rgba(8,18,40,0.72);color:{CYAN};"
                f"border:1px solid rgba(56,214,232,0.75);border-radius:19px;"
                f"padding:7px 20px;font-size:12px;font-weight:bold;letter-spacing:1px;}}"
                f"QPushButton:hover{{background:rgba(56,214,232,0.90);color:#05070f;}}"
                f"QPushButton:disabled{{color:#4a5a73;border-color:#2a3550;}}")
            button.clicked.connect(lambda _=False, oid=option_id: self._pick(oid))
            self._lay.insertWidget(self._lay.count() - 1, button)
            self._buttons.append(button)
        self.setVisible(bool(self._buttons))

    def _pick(self, option_id: str) -> None:
        if not option_id:
            return
        for button in self._buttons:
            button.setEnabled(False)      # one pick per question
        self.chosen.emit(option_id)
