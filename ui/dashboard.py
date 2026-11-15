"""Main window: space background + three-column mission-control layout.
Column widths adapt to the window so it fits 1280x720 up to 1920x1080."""
from __future__ import annotations

import random

from PyQt6.QtCore import QEvent, Qt, QPointF, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QMainWindow, QStackedWidget,
                             QVBoxLayout, QWidget)

from state import MissionState
from . import theme
from .common import panel_qss
from .chat import ChatView
from .panels import (AlertBanner, CommanderCard, HeaderBar, LiveFeeds, NavPanel,
                     StatusFooter)
from .radar import RadarPanel
from .levers import LeverBar
from .scene import SceneView
from .event_card import EventCard
from .intel_panel import IntelPanel
from .result_card import ResultCard
from .briefing_card import BriefingCard
from .info_views import KnowledgeView, SpaceHazardsView
from .report_strip import ReportStrip
from .evidence_card import EvidenceCard
from .active_event_card import ActiveEventCard
from .nexus_prompt import NexusBar, ChoiceBar, Scrim
from .views import PlaceholderView, ProgressView, ScenarioView

# Column width limits (pixels) and share of the window width.
LEFT_MIN, LEFT_MAX, LEFT_SHARE = 230, 290, 0.15
RIGHT_MIN, RIGHT_MAX, RIGHT_SHARE = 280, 360, 0.19
RADAR_MIN_HEIGHT = 150         # lets the right column fit at 720p


class SpaceBackground(QWidget):
    """Near-black background with scattered stars and a faint blue planet glow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        rng = random.Random(7)
        self._stars = [(rng.random(), rng.random(), rng.choice((0.8, 1.0, 1.4, 1.8)),
                        rng.randint(70, 200)) for _ in range(110)]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.BG))

        # Planet glow (top right)
        c = QPointF(w - 30, 20)
        g = QRadialGradient(c, 460)
        g.setColorAt(0.0, QColor(74, 163, 255, 85))
        g.setColorAt(0.35, QColor(40, 100, 190, 38))
        g.setColorAt(1.0, QColor(5, 7, 15, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, 460, 460)

        # Faint planet limb
        pc = QPointF(w + 10, -50)
        pg = QRadialGradient(pc, 170)
        pg.setColorAt(0.0, QColor(40, 90, 160, 70))
        pg.setColorAt(1.0, QColor(20, 50, 100, 18))
        p.setPen(QPen(QColor(127, 211, 255, 60), 1.2))
        p.setBrush(QBrush(pg))
        p.drawEllipse(pc, 170, 170)

        # Stars
        p.setPen(Qt.PenStyle.NoPen)
        for fx, fy, size, alpha in self._stars:
            p.setBrush(QColor(200, 225, 255, alpha))
            p.drawEllipse(QPointF(fx * w, fy * h), size, size)


EVENT_HOTSPOT = {
    "dust_storm": "power",
    "solar_particle": "power",
    "scrubber_fault": "oxygen",
    "crop_blight": "food",
    "equipment_failure": "water",
    "micrometeoroid": "oxygen",
    "regolith_dust": "oxygen",
}


class MissionView(QWidget):
    """Mission Control board: scene with overlays (briefing, event card, INTEL panel,
    day report, result), lever bar, and the chat input bar. Overlays never overlap."""

    locked = False              # True while the end-of-mission card is showing
    _event_active = False       # a real simulation event is waiting for a decision
    _card_waiting = False       # event card hidden while the INTEL panel is open
    debrief_active = False      # post-choice debrief is open; END DAY stays locked
    _card_mode = None           # "event", "daily" or None
    _daily_day = None
    CHAT_H_CLOSED = 92
    CHAT_H_OPEN = 300

    def __init__(self, chat, parent=None):
        super().__init__(parent)
        self.chat = chat
        self._chat_h = self.CHAT_H_CLOSED
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.scene = SceneView()
        self.levers = LeverBar()
        self.nexus_bar = NexusBar()
        self.choice_bar = ChoiceBar(self.scene)
        self.scrim = Scrim(self.scene)
        self.card = EventCard(self.nexus_bar, self.choice_bar)
        self.intel = IntelPanel(self.scene)
        self.result = ResultCard(self.scene)
        self.briefing = BriefingCard(self.scene)
        self.report = ReportStrip(self.scene)
        self.scene.installEventFilter(self)
        layout.addWidget(self.nexus_bar)
        layout.addWidget(self.scene, 1)
        layout.addWidget(self.levers)
        self.levers.hide()          # effort choices are NEXUS questions now

        chat.setParent(self.scene)  # glass input bar floating over the bottom of the scene
        chat.setStyleSheet(panel_qss(theme.BORDER, "rgba(8,16,36,0.88)",
                                     "rgba(8,16,36,0.88)"))
        chat.show()
        chat.raise_()

        self.intel.closed.connect(self._on_intel_closed)
        self.intel.continued.connect(self._on_debrief_done)
        toggled = getattr(chat, "log_toggled", None)
        if toggled is not None:
            toggled.connect(self._on_log_toggled)
        self._on_log_toggled(bool(getattr(chat, "_log_open", False)))
        self.briefing.show_briefing()

    def _on_log_toggled(self, is_open: bool) -> None:
        """Closed log = slim glass input bar. Open log = taller history drawer."""
        self._chat_h = self.CHAT_H_OPEN if is_open else self.CHAT_H_CLOSED
        self.chat.setMinimumHeight(0)
        self.chat.setMaximumHeight(16777215)
        self.place_chrome()

    def place_chrome(self) -> None:
        """Float the input bar and the choice chips over the bottom of the scene."""
        width, height = self.scene.width(), self.scene.height()
        if width <= 0 or height <= 0:
            return
        margin = 16
        chat_h = min(self._chat_h, max(80, height - 140))
        chat_y = height - chat_h - margin
        self.chat.setGeometry(margin, chat_y, max(200, width - 2 * margin), chat_h)
        bar_h = self.choice_bar.height() or 62
        chips_y = max(0, chat_y - bar_h - 18)
        self.choice_bar.setGeometry(0, chips_y, width, bar_h)
        top = (chips_y if not self.choice_bar.isHidden() else chat_y) - 28
        self.scrim.setGeometry(0, max(0, top), width, height - max(0, top))
        self.scrim.show()
        self.scrim.raise_()
        self.choice_bar.raise_()
        self.chat.raise_()
        for overlay in (self.report, self.intel, self.briefing, self.result):
            if not overlay.isHidden():
                overlay.raise_()

    def eventFilter(self, obj, event):
        if obj is self.scene and event.type() == QEvent.Type.Resize:
            self.place_card()
            self.place_chrome()
            self.place_intel()
            self.place_result()
            self.place_briefing()
            self.place_report()
        return False

    # ------------------------------------------------------------ briefing
    def place_briefing(self) -> None:
        if not self.briefing.isHidden():
            self.briefing.place(self.scene.width(), self.scene.height())

    def set_running(self, running: bool) -> None:
        """Briefing shows before a mission starts and hides once one is running."""
        if running:
            if not self.briefing.isHidden():
                self.briefing.hide_briefing()
        elif self.briefing.isHidden() and not self.locked:
            self.briefing.show_briefing()
            self.place_briefing()

    # ---------------------------------------------------------- event card
    def place_card(self) -> None:
        """The event card is a transparent overlay covering the scene (banner top, chips bottom)."""
        self.card.setGeometry(0, 0, self.scene.width(), self.scene.height())

    def show_event(self, event: dict) -> None:
        self._event_active = True
        self._card_mode = "event"
        self.card.show_event(event)
        self.place_card()
        if not self.intel.isHidden():       # INTEL panel is open: the card waits
            self._card_waiting = True
            self.card.hide()

    def hide_event(self) -> None:
        self._event_active = False
        self._card_waiting = False
        self._card_mode = None
        self._daily_day = None
        self.card.hide_event()

    def show_daily(self, day: int, question: str, items) -> None:
        """Daily question in the NEXUS bar with three chips below. Never over an event or debrief."""
        if self.locked or self.debrief_active or self._event_active or not self.intel.isHidden():
            return
        if self._card_mode == "daily" and self._daily_day == day and not self.card.isHidden():
            return
        self._card_mode = "daily"
        self._daily_day = day
        self.card.show_daily(question, items)
        self.place_card()

    def hide_daily(self) -> None:
        if self._card_mode == "daily":
            self._card_mode = None
            self._daily_day = None
            self.card.hide_event()

    # --------------------------------------------------------- intel panel
    def place_intel(self) -> None:
        if not self.intel.isHidden():
            self.intel.place(self.scene.width(), self.scene.height())

    def intel_start(self, question: str) -> None:
        if self.debrief_active:
            self.debrief_finish()
        self.intel.hide()
        if not self.report.isHidden():
            self.report.hide_report()
        self.nexus_bar.type_text("Retrieving from NASA sources...", prefix="NEXUS")

    def intel_append(self, sentence: str) -> None:
        self.nexus_bar.append_text(sentence)

    def intel_sources(self, sources, from_nasa: bool) -> None:
        labels = [str(s) for s in (sources or []) if str(s).strip()]
        if from_nasa and labels:
            self.nexus_bar.append_text("(Source: " + "; ".join(labels[:2]) + ")")
        else:
            self.nexus_bar.append_text("(Not from NASA sources.)")

    def intel_close(self) -> None:
        self.intel.hide_panel()

    def debrief_start(self, nasa_line: str, chip_label: str = "CONTINUE  ›  NEXT DAY",
                      prefix: str = "NASA") -> None:
        """Post-choice explanation in the bar, plus one CONTINUE chip. Locks the day."""
        if self.locked:
            return
        self.debrief_active = True
        self._card_waiting = False
        self._card_mode = "debrief"
        self.intel.hide()
        self.nexus_bar.type_text(nasa_line, alert=False, prefix=prefix)
        self.choice_bar.set_choices(
            [("nexus:continue", chip_label, "Continue")])
        self.levers.set_enabled(False)
        self.place_chrome()

    def debrief_finish(self) -> None:
        """CONTINUE picked: clear the debrief and unlock the controls."""
        if not self.debrief_active:
            return
        self.debrief_active = False
        self._card_mode = None
        self.report.hide_report()
        self.choice_bar.clear()
        if not self._event_active and not self.locked:
            self.levers.set_enabled(True)

    def _on_debrief_done(self) -> None:
        """CONTINUE clicked (or the panel was closed): unlock the controls."""
        was_active = self.debrief_active
        self.debrief_active = False
        self.intel.top_offset = 12
        if not was_active:
            return
        self.report.hide_report()
        if not self._event_active and not self.locked:
            self.levers.set_enabled(True)

    def _on_intel_closed(self) -> None:
        """Bring the decision card (event or daily question) back if it was waiting."""
        if (self._card_waiting and not self.locked and not self.debrief_active
                and (self._event_active or self._card_mode == "daily")):
            self._card_waiting = False
            self.card.show()
            self.card.raise_()
            self.place_card()
        else:
            self._card_waiting = False

    # --------------------------------------------------------- day report
    def place_report(self) -> None:
        if not self.report.isHidden():
            self.report.place(self.scene.width(), self.scene.height())

    def report_show(self, headline: str, status_text: str, level: str,
                    note: str, deltas) -> None:
        """Visible feedback after END DAY or a decision. Skipped while another overlay
        owns the top of the scene."""
        if self.locked or self._event_active or not self.intel.isHidden():
            return
        self.report.show_report(headline, status_text, level, note, deltas)
        self.place_report()

    def report_hide(self) -> None:
        self.report.hide_report()

    # --------------------------------------------------------- result card
    def place_result(self) -> None:
        if not self.result.isHidden():
            self.result.place(self.scene.width(), self.scene.height())

    def result_show(self, success: bool, headline: str, detail: str, stats) -> None:
        self.locked = True
        self._event_active = False
        self._card_waiting = False
        self.briefing.hide_briefing()
        self.report.hide_report()
        self.intel.hide_panel()
        self.card.hide_event()
        self.result.show_result(success, headline, detail, stats)
        self.place_result()
        self.levers.set_enabled(False)

    def result_hide(self) -> None:
        if self.locked or not self.result.isHidden():
            self.locked = False
            self.result.hide_result()


class DashboardWindow(QMainWindow):
    closing = pyqtSignal()
    command_requested = pyqtSignal(str)
    event_choice = pyqtSignal(str)
    _card_event_id = None
    sep_history = None

    # Stack indices (match NavPanel.ITEMS order)
    MISSION, SCENARIOS, HAZARDS, KNOWLEDGE, EVA, PROGRESS = range(6)

    def __init__(self, state: MissionState):
        super().__init__()
        self.state = state
        self._scene_dest = None
        self.setWindowTitle("NEXUS TRAINER — Mission Control")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()

        central = SpaceBackground()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 6, 14, 6)
        root.setSpacing(6)

        self.header = HeaderBar(state)
        root.addWidget(self.header)

        mid = QHBoxLayout()
        mid.setSpacing(14)
        root.addLayout(mid, 1)

        # --- Left column ---
        self._left = QWidget()
        ll = QVBoxLayout(self._left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(14)
        self.nav = NavPanel()
        ll.addWidget(self.nav)
        for index in (1, 4):          # Scenarios and EVA Planner are not part of this build
            self.nav.buttons[index].hide()
        self.commander = CommanderCard(state)
        ll.addWidget(self.commander)
        ll.addStretch(1)
        mid.addWidget(self._left)

        # --- Center column ---
        center = QVBoxLayout()
        center.setSpacing(6)
        self.alert_banner = AlertBanner(state)     # kept alive but not shown: events live on the scene
        self.alert_banner.hide()
        self.stack = QStackedWidget()
        self.chat = ChatView()
        self.mission = MissionView(self.chat)
        self.scene = self.mission.scene
        self.levers = self.mission.levers
        self.scenario_view = PlaceholderView("Scenarios", "⚑")
        self.stack.addWidget(self.mission)                                # 0
        self.stack.addWidget(self.scenario_view)                          # 1
        self.stack.addWidget(SpaceHazardsView())                          # 2
        self.stack.addWidget(KnowledgeView())                             # 3
        self.stack.addWidget(PlaceholderView("EVA Planner", "✦"))         # 4
        self.stack.addWidget(ProgressView(state))                         # 5
        center.addWidget(self.stack, 1)
        mid.addLayout(center, 1)

        # --- Right column ---
        self._right = QWidget()
        rl = QVBoxLayout(self._right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(14)
        self.feeds = LiveFeeds(state)
        self.radar_panel = RadarPanel()
        self.radar_panel.setMinimumHeight(RADAR_MIN_HEIGHT)
        rl.addWidget(self.feeds)
        rl.addWidget(self.radar_panel, 1)
        self.evidence_card = EvidenceCard()
        self.evidence_card.hide()
        self.active_card = ActiveEventCard()
        rl.addWidget(self.active_card)
        mid.addWidget(self._right)

        self.footer = StatusFooter()
        root.addWidget(self.footer)

        # --- Wiring ---
        self.nav.selected.connect(self.stack.setCurrentIndex)
        self.levers.command.connect(self.command_requested)
        self.mission.card.chosen.connect(self.event_choice)
        state.changed.connect(self._refresh_scene)

        self._fit_columns()
        self._refresh_scene()

    def _sync_event(self) -> None:
        """Show the event card while the real simulation has an active event."""
        event = getattr(self.state, "active_event", None)
        event_id = event.get("id") if isinstance(event, dict) else None
        if event_id and event_id != self._card_event_id:
            self._card_event_id = event_id
            self.mission.report_hide()          # report strip yields to a live decision
            self.mission.show_event(event)
            spot = EVENT_HOTSPOT.get(event_id)
            if spot:
                self.scene.flash(spot)
        elif not event_id and self._card_event_id:
            self._card_event_id = None
            self.mission.hide_event()
        self.active_card.set_event(event if event_id else None)
        self.chat.set_alert(bool(event_id))
        self.levers.set_enabled(not event_id and not self.mission.locked and not self.mission.debrief_active)

    def _refresh_scene(self) -> None:
        """Scene follows real state: destination image, hotspot levels, overlays."""
        try:
            dest = getattr(self.state, "destination", None) or "moon"
            if dest != self._scene_dest:
                self._scene_dest = dest
                self.scene.set_destination(dest)
            running = bool(getattr(self.state, "crew", None))
            self.scene.set_levels(getattr(self.state, "resources", None) if running else {})
            self.mission.set_running(running)
            self._sync_event()
        except Exception:
            pass          # a scene glitch must never crash the dashboard

    # ------------------------------------------------------------ layout
    def _fit_columns(self) -> None:
        """Side columns follow the window width, within limits."""
        if not hasattr(self, "_left") or not hasattr(self, "_right"):
            return          # a resize event can fire before the columns are built
        w = max(self.width(), 1)
        left = max(LEFT_MIN, min(LEFT_MAX, int(w * LEFT_SHARE)))
        right = max(RIGHT_MIN, min(RIGHT_MAX, int(w * RIGHT_SHARE)))
        self._left.setFixedWidth(left)
        self._right.setFixedWidth(right)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_columns()

    # --------------------------------------------------------------- API
    def set_space_weather(self, proton, sep) -> None:
        """Real NOAA/NASA space-weather data. Display only. Never feeds the simulation."""
        try:
            self.header.set_space_weather(proton)
            self.sep_history = sep          # used by the event card note (Step 5)
        except Exception:
            pass

    def set_ai_status(self, online) -> None:
        """Footer AI status. True = last AI call worked, False = it failed,
        None = not checked. Call this from a real check only."""
        self.footer.set_ai_online(online)

    def open_scenario(self) -> None:
        """Decisions now live on the Mission Control event card, so go there."""
        self.nav.select(self.MISSION)
        self.stack.setCurrentIndex(self.MISSION)

    def show_view(self, index: int) -> None:
        self.nav.select(index)
        self.stack.setCurrentIndex(index)

    def set_evidence(self, mode: str, title: str, excerpt: str, source: str, status_text: str) -> None:
        self.evidence_card.show_evidence(mode, title, excerpt, source, status_text)

    def set_evidence_empty(self, title: str, message: str) -> None:
        self.evidence_card.show_empty(title, message)

    def clear_evidence(self) -> None:
        self.evidence_card.clear()

    def flash(self, name: str) -> None:
        target = {
            "feeds": self.feeds,
            "radar": self.radar_panel,
            "readiness": self.commander,
            "evidence": self.evidence_card,
        }.get(name)
        if target is None:
            return
        target.setStyleSheet(panel_qss(theme.CYAN))
        QTimer.singleShot(
            900, lambda: target.setStyleSheet(panel_qss(theme.BORDER)))

    def closeEvent(self, event) -> None:
        self.closing.emit()
        event.accept()
