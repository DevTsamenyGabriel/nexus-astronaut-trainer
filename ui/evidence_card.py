"""Right-column NASA evidence card.
Shows retrieval-only evidence for the current event or a daily science briefing.
Display only: never decides outcomes."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QSizePolicy, QTextBrowser

from . import theme
from .common import Panel, mono

CLIP = 200


def _clip(text: str) -> str:
    """Truncate to ~CLIP chars at a word boundary. Full text stays stored elsewhere."""
    text = " ".join(str(text or "").split())
    if len(text) <= CLIP:
        return text
    cut = text[:CLIP]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:.") + "…"


class EvidenceCard(Panel):
    def __init__(self, parent=None):
        super().__init__(
            "NASA EVIDENCE",
            accent=theme.GREEN,
            title_color=theme.GREEN,
            tint=("rgba(10,32,20,238)", "rgba(10,20,14,238)"),
            parent=parent,
        )
        self.body.setSpacing(4)

        self.mode = QLabel("")
        self.mode.setFont(mono(8.5, True, 1.2))
        self.mode.setStyleSheet(f"color:{theme.GREEN};")
        self.body.addWidget(self.mode)

        self.title = QLabel("")
        self.title.setWordWrap(True)
        self.title.setFont(mono(11, True))
        self.title.setStyleSheet("color:#ffffff;")
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.title.setMinimumHeight(2 * self.title.fontMetrics().lineSpacing())
        self.body.addWidget(self.title)

        self.excerpt = QTextBrowser()
        self.excerpt.setReadOnly(True)
        self.excerpt.setFrameShape(QFrame.Shape.NoFrame)
        self.excerpt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.excerpt.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.excerpt.setFixedHeight(70)
        self.excerpt.setFont(mono(9.5))
        self.excerpt.document().setDocumentMargin(0)
        self.excerpt.setStyleSheet(
            "QTextBrowser{background:transparent;border:none;color:#d8f6e3;}"
            "QScrollBar:vertical{background:transparent;}")
        self.body.addWidget(self.excerpt)
        self.excerpt.setVisible(False)
        self._excerpt_full = ""

        self.source = QLabel("")
        self.source.setWordWrap(True)
        self.source.setFont(mono(8.5))
        self.source.setStyleSheet(f"color:{theme.MUTED};")
        self.body.addWidget(self.source)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setFont(mono(8.5, True))
        self.status.setStyleSheet(f"color:{theme.CYAN};")
        self.body.addWidget(self.status)

        self.body.addStretch(1)
        self.setMinimumHeight(150)
        self.clear()

    def show_evidence(self, mode: str, title: str, excerpt: str, source: str, status_text: str) -> None:
        self._excerpt_full = str(excerpt or "")
        self.mode.setText(mode)
        self.title.setText(title)
        self.excerpt.setPlainText(_clip(self._excerpt_full))
        self.source.setText(source)
        self.status.setText(status_text)

    def show_empty(self, title: str, message: str) -> None:
        self._excerpt_full = str(message or "")
        self.mode.setText("NO MATCH IN INDEX")
        self.title.setText(title)
        self.excerpt.setPlainText(_clip(self._excerpt_full))
        self.source.setText("")
        self.status.setText("Retrieval only. No NASA excerpt was found for this topic.")

    def clear(self) -> None:
        self._excerpt_full = "Waiting for a mission event or daily science topic."
        self.mode.setText("RETRIEVAL ONLY · NO AI REWRITING")
        self.title.setText("Daily science briefing")
        self.excerpt.setPlainText(self._excerpt_full)
        self.source.setText("")
        self.status.setText("Indexed NASA/NOAA evidence appears here.")
