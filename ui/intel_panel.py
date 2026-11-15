"""NEXUS INTEL: glass panel that shows a science answer and its NASA sources.
It only displays text it is given. Sources come from knowledge.ask(), never invented.
In debrief mode it also shows a CONTINUE button; closing the panel then counts as continuing."""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout)

CYAN = "#7fd3ff"
AMBER = "#f5b942"
SRC_RE = re.compile(r"\[(.+?)\].*?p\.\s*(\d+)\s*$", re.S)


def short_sources(sources) -> list:
    """Turn long citation strings into 'Document name, p. N', without duplicates."""
    result, seen = [], set()
    for raw in sources or []:
        text = str(raw).strip()
        match = SRC_RE.search(text)
        label = f"{match.group(1)}, p. {match.group(2)}" if match else text[:90]
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result


class IntelPanel(QFrame):
    closed = pyqtSignal()
    continued = pyqtSignal()      # debrief finished (Continue clicked or panel closed)
    top_offset = 12               # y position inside the scene; raised to sit below the report strip

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("IntelPanel")
        self.setStyleSheet(
            "QFrame#IntelPanel{background:rgba(10,22,46,0.80);"
            "border:1px solid rgba(127,211,255,0.55);border-radius:14px;}"
            "QLabel{background:transparent;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("NEXUS INTEL  ·  SIMULATION MODE")
        title.setStyleSheet(f"color:{CYAN};font-weight:bold;letter-spacing:2px;")
        close = QPushButton("✕")
        close.setFixedSize(28, 28)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(
            "QPushButton{background:transparent;color:#cfe3ff;border:1px solid #3a4a68;"
            "border-radius:14px;}QPushButton:hover{background:#3a4a68;}")
        close.clicked.connect(self.hide_panel)
        header.addWidget(title, 1)
        header.addWidget(close)
        layout.addLayout(header)

        self._question = QLabel("")
        self._question.setWordWrap(True)
        self._question.setStyleSheet("color:#9fb8d8;font-style:italic;")
        layout.addWidget(self._question)

        self._answer = QLabel("")
        self._answer.setWordWrap(True)
        self._answer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._answer.setStyleSheet("color:#ffffff;font-size:14px;")
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background:transparent;")
        self._scroll.setMinimumHeight(60)
        self._scroll.setMaximumHeight(170)
        self._scroll.setWidget(self._answer)
        layout.addWidget(self._scroll)

        self._source_card = QFrame()
        self._source_card.setObjectName("SourceCard")
        self._source_card.setStyleSheet(
            "QFrame#SourceCard{background:rgba(5,10,24,0.70);"
            "border:1px solid rgba(61,220,132,0.6);border-radius:8px;}")
        card_layout = QVBoxLayout(self._source_card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        self._source_label = QLabel("")
        self._source_label.setWordWrap(True)
        card_layout.addWidget(self._source_label)
        layout.addWidget(self._source_card)

        self._continue = QPushButton("CONTINUE  ›  NEXT DAY")
        self._continue.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue.setStyleSheet(
            "QPushButton{background:rgba(61,220,132,0.15);color:#3ddc84;"
            "border:1px solid #3ddc84;border-radius:10px;padding:8px;font-weight:bold;"
            "letter-spacing:2px;}QPushButton:hover{background:rgba(61,220,132,0.35);}")
        self._continue.clicked.connect(self.hide_panel)
        self._continue.hide()
        layout.addWidget(self._continue)

        self._text = ""
        self.hide()

    # ------------------------------------------------------------ API
    def start(self, question: str) -> None:
        self._text = ""
        self._question.setText(str(question or ""))
        self._answer.setText("Retrieving from NASA sources...")
        self._source_card.hide()
        self.show()
        self.raise_()

    def set_continue_visible(self, visible: bool) -> None:
        """Debrief mode: show the CONTINUE button. Normal EXPLAIN keeps it hidden."""
        self._continue.setVisible(bool(visible))

    def append_answer(self, sentence: str) -> None:
        sentence = str(sentence or "").strip()
        if not sentence:
            return
        self._text = f"{self._text} {sentence}".strip()
        self._answer.setText(self._text)
        QTimer.singleShot(0, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))

    def set_sources(self, sources, from_nasa: bool) -> None:
        labels = short_sources(sources)
        if from_nasa and labels:
            lines = "".join(f"<br>• {label}" for label in labels)
            self._source_label.setText(
                f"<span style='color:#3ddc84;font-weight:bold;'>NASA SOURCE</span>{lines}")
            self._source_label.setStyleSheet("color:#cfe3ff;")
        else:
            self._source_label.setText(
                f"<span style='color:{AMBER};font-weight:bold;'>NOT FROM NASA SOURCES</span>")
        self._source_card.show()

    def hide_panel(self) -> None:
        was_debrief = not self._continue.isHidden()
        self._continue.hide()
        self.hide()
        self.closed.emit()
        if was_debrief:
            self.continued.emit()

    def place(self, parent_width: int, parent_height: int) -> None:
        """Centre horizontally; top edge at top_offset (below the report strip in debrief)."""
        width = max(320, int(min(parent_width * 0.72, 720)))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move(max((parent_width - width) // 2, 0), int(self.top_offset))

    def answer_text(self) -> str:
        return self._text
