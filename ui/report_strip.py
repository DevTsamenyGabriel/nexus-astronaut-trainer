"""Report strip: visible feedback after END DAY and after each decision.
Shows a headline, a status verdict, the fixed outcome note and what changed.
It only displays what the Controller computed from real simulation state."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

GREEN = "#3ddc84"
AMBER = "#f5b942"
RED = "#ff4d4d"
CYAN = "#7fd3ff"
MUTED = "#7f93b3"
LEVEL_COLORS = {"stable": GREEN, "caution": AMBER, "critical": RED}


class ReportStrip(QFrame):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReportStrip")
        self.setStyleSheet(
            f"QFrame#ReportStrip{{background:rgba(8,16,34,0.93);"
            f"border:1px solid {CYAN};border-radius:12px;}}"
            "QLabel{background:transparent;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(10)
        self._headline = QLabel("")
        self._headline.setWordWrap(True)
        self._headline.setStyleSheet("color:#ffffff;font-size:14px;font-weight:bold;"
                                     "letter-spacing:1px;")
        self._status = QLabel("")
        close = QPushButton("✕")
        close.setFixedSize(24, 24)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(
            "QPushButton{background:transparent;color:#cfe3ff;border:1px solid #3a4a68;"
            "border-radius:12px;}QPushButton:hover{background:#3a4a68;}")
        close.clicked.connect(self.hide_report)
        top.addWidget(self._headline, 1)
        top.addWidget(self._status, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        self._note = QLabel("")
        self._note.setWordWrap(True)
        self._note.setStyleSheet(f"color:{CYAN};font-size:12px;")
        layout.addWidget(self._note)

        self._chips = QHBoxLayout()
        self._chips.setSpacing(6)
        layout.addLayout(self._chips)

        self._texts: list[str] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(14000)
        self._timer.timeout.connect(self.hide_report)
        self.hide()

    # ------------------------------------------------------------ API
    def show_report(self, headline: str, status_text: str, level: str,
                    note: str, deltas) -> None:
        """deltas: list of (label, value, up_is_good). Values are real state differences."""
        color = LEVEL_COLORS.get(level, CYAN)
        self._headline.setText(str(headline))
        self._status.setText(str(status_text))
        self._status.setStyleSheet(
            f"color:{color};border:1px solid {color};border-radius:8px;padding:2px 8px;"
            "font-weight:bold;font-size:12px;letter-spacing:1px;")
        self._note.setText(str(note or ""))
        self._note.setVisible(bool(note))

        while self._chips.count():
            item = self._chips.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._texts = []
        for label, value, up_is_good in deltas or []:
            value = float(value)
            text = f"{label} {value:+.1f}"
            if abs(value) < 0.05:
                chip_color = MUTED
            else:
                chip_color = GREEN if (value > 0) == bool(up_is_good) else RED
            chip = QLabel(text)
            chip.setStyleSheet(
                f"color:{chip_color};border:1px solid {chip_color};border-radius:7px;"
                "padding:1px 6px;font-size:11px;font-weight:bold;")
            self._chips.addWidget(chip)
            self._texts.append(text)
        self._chips.addStretch(1)

        self.show()
        self.raise_()
        self._timer.start()

    def hide_report(self) -> None:
        self._timer.stop()
        self.hide()
        self.closed.emit()

    def place(self, parent_width: int, parent_height: int) -> None:
        """Centre the strip at the top of the parent."""
        width = max(420, int(min(parent_width * 0.92, 1000)))
        lay = self.layout()
        height = lay.totalHeightForWidth(width) if lay.hasHeightForWidth() else 0
        height = max(height, lay.sizeHint().height())
        self.setFixedSize(width, height)
        self.move(max((parent_width - width) // 2, 0), 8)

    def chip_texts(self) -> list:
        return list(self._texts)
