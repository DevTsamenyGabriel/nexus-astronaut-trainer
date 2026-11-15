"""Info pages. Space Hazards is built from the real events table (same data the simulation
uses). Knowledge Base lists the documents the RAG index holds. Display only; decides nothing."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from . import theme
from .common import Panel, mono
from .event_card import EXPLAIN_QUESTIONS

ROW_QSS = "QFrame{background:rgba(74,163,255,12);border:1px solid #16385c;border-radius:10px;}"


def _label(text: str, color: str, size: float = 10, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setFont(mono(size, bold))
    label.setStyleSheet(f"color:{color};border:none;background:transparent;")
    return label


def _scroll_body(panel: Panel) -> QVBoxLayout:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
    scroll.viewport().setAutoFillBackground(False)
    content = QWidget()
    content.setObjectName("infoContent")
    content.setStyleSheet("QWidget#infoContent{background:transparent;}")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(4, 4, 8, 4)
    layout.setSpacing(10)
    scroll.setWidget(content)
    panel.body.addWidget(scroll, 1)
    return layout


def _row(title: str, detail: str, chip_text=None, chip_color: str = theme.MUTED) -> QFrame:
    row = QFrame()
    row.setStyleSheet(ROW_QSS)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(14, 10, 14, 10)
    column = QVBoxLayout()
    column.setSpacing(2)
    column.addWidget(_label(title, theme.TEXT, 11, True))
    column.addWidget(_label(detail, theme.MUTED, 9.5))
    lay.addLayout(column, 1)
    if chip_text:
        chip = QLabel(chip_text)
        chip.setFont(mono(9, True, 1.0))
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet(f"color:{chip_color};border:1px solid {chip_color};"
                           "border-radius:8px;padding:3px 8px;background:transparent;")
        lay.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
    return row


class SpaceHazardsView(Panel):
    def __init__(self, parent=None):
        super().__init__("SPACE HAZARDS (SIMULATED EVENTS)", parent=parent)
        layout = _scroll_body(self)
        layout.addWidget(_label(
            "These are the hazards the mission simulation can trigger. Outcomes are fixed "
            "simulation values defined in code. The AI never decides them.",
            theme.TEXT, 10))
        try:
            from events import EVENTS
            events = list(EVENTS)
        except Exception:
            events = []
        for event in events:
            if len(event.destinations) > 1:
                where = "Moon and Mars"
            else:
                where = f"{event.destinations[0].capitalize()} only"
            detail = (f"{where}  ·  days {event.day_min} to {event.day_max}  ·  "
                      f"about {event.chance * 100:.0f}% per day (simulation value)")
            if event.id in EXPLAIN_QUESTIONS:
                chip_text, chip_color = "NASA EXPLAIN", theme.GREEN
            else:
                chip_text, chip_color = "NO NASA EXCERPT", theme.MUTED
            layout.addWidget(_row(event.title, detail, chip_text, chip_color))
        layout.addWidget(_label(
            "Real NASA NeoWs asteroid data and the NOAA space-weather chip are shown in "
            "Mission Control as display only. They never change the simulation.",
            theme.CYAN, 9.5))
        layout.addStretch(1)


class KnowledgeView(Panel):
    DOCUMENTS = (
        ("NASA HRP SPE Report, 2016",
         "Evidence report: risk of acute radiation syndromes due to solar particle events."),
        ("NASA EVA Ops, Ch. 5.4",
         "Extravehicular activities, space physiology and medicine."),
        ("NOAA Space Weather 101",
         "Factsheet on the types of space weather and their effects."),
        ("NASA Artemis Plan, 2020",
         "NASA's lunar exploration plan."),
    )
    EXAMPLES = (
        "Why is acute radiation syndrome unlikely during a solar particle event?",
        "What dose ranges do large solar particle events contribute?",
        "What are the abort triggers during an extravehicular activity?",
    )

    def __init__(self, parent=None):
        super().__init__("KNOWLEDGE BASE (WHAT NEXUS KNOWS)", parent=parent)
        layout = _scroll_body(self)
        layout.addWidget(_label(
            "NEXUS answers science questions only from these documents, and shows the "
            "document and page for every answer. If the answer is not in them, NEXUS says: "
            "\"I don't have that in my NASA sources.\"", theme.TEXT, 10))
        for title, detail in self.DOCUMENTS:
            layout.addWidget(_row(title, detail, "INDEXED", theme.GREEN))
        layout.addWidget(_label("TRY ASKING IN MISSION CONTROL", theme.CYAN, 9.5, True))
        for question in self.EXAMPLES:
            layout.addWidget(_row(question, "Type it or say it. The answer opens in the NEXUS INTEL panel."))
        layout.addWidget(_label(
            "Radiation numbers are mission-planning references, not medical clearance.",
            theme.MUTED, 9.5))
        layout.addStretch(1)
