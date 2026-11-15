"""Right-column ACTIVE EVENT card. Shows only whether a simulation event needs a decision.
Display only: it never decides anything."""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel

from . import theme
from .common import Panel, mono, panel_qss


class ActiveEventCard(Panel):
    def __init__(self, parent=None):
        super().__init__("ACTIVE EVENT (SIM)", title_color=theme.AMBER, parent=parent)
        self._key = "__unset__"

        self.status = QLabel("")
        self.status.setFont(mono(9.5, True, 1.2))
        self.body.addWidget(self.status)

        self.name = QLabel("")
        self.name.setWordWrap(True)
        self.name.setFont(mono(12, True))
        self.name.setStyleSheet("color:#ffffff;")
        self.body.addWidget(self.name)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setFont(mono(9))
        self.hint.setStyleSheet(f"color:{theme.MUTED};")
        self.body.addWidget(self.hint)

        self.body.addStretch(1)
        self.setMinimumHeight(130)
        self.set_event(None)

    def set_event(self, event) -> None:
        key = event.get("id") if isinstance(event, dict) else None
        if key == self._key:
            return
        self._key = key
        if key is None:
            self.setStyleSheet(panel_qss(theme.BORDER))
            self.status.setText("● ALL CLEAR")
            self.status.setStyleSheet(f"color:{theme.GREEN};")
            self.name.setText("No active event")
            self.hint.setText("Conditions are being monitored.")
        else:
            self.setStyleSheet(panel_qss(theme.RED))
            self.status.setText("● DECISION REQUIRED")
            self.status.setStyleSheet(f"color:{theme.RED};")
            self.name.setText(str(event.get("title", "Event")))
            self.hint.setText("Answer on the mission scene: pick a chip, or type 1, 2 or 3.")
