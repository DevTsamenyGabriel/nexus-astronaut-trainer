"""Dashboard panels: header, alert banner, navigation, commander card,
telemetry, active-event card and footer strip.
Everything shown is read from MissionState. All numbers are SIMULATION values."""
from __future__ import annotations

import config
import html

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QGraphicsDropShadowEffect,
                             QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from state import MissionState
from . import theme
from .common import Avatar, BarWidget, Panel, PulseDot, mono, section_title

DEST_NAMES = {"moon": "MOON", "mars": "MARS"}
DEST_SUBTITLES = {"moon": "MISSION CONTROL — LUNAR OUTPOST",
                  "mars": "MISSION CONTROL — MARS OUTPOST"}


def _rgb(color: str) -> str:
    c = QColor(color)
    return f"{c.red()},{c.green()},{c.blue()}"


def fmt_tminus(minutes: float) -> str:
    secs = max(0, int(round(minutes * 60)))
    return f"{secs // 60}:{secs % 60:02d}"


def level_color(value: float) -> str:
    """Color for a 0-100 'higher is better' value, using the theme thresholds."""
    if value >= theme.THRESH_WARN:
        return theme.GREEN
    if value >= theme.THRESH_CRIT:
        return theme.AMBER
    return theme.RED


def _fmt_pfu(flux: float) -> str:
    if flux >= 100:
        return f"{flux:.0f}"
    if flux >= 1:
        return f"{flux:.1f}"
    return f"{flux:.2f}"


# ---------------------------------------------------------------------------
class StatusBadge(QFrame):
    """Pill-shaped badge with a colored (optionally pulsing) dot."""

    def __init__(self, text: str, color: str, pulse: bool = False, parent=None,
                 font_size: float = 9.5):
        super().__init__(parent)
        self.setObjectName("badge")
        self.setFixedHeight(30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 12, 0)
        lay.setSpacing(6)
        self.dot = PulseDot(color, pulse, 12)
        self.label = QLabel()
        self.label.setFont(mono(font_size, True, 0.6))
        lay.addWidget(self.dot)
        lay.addWidget(self.label)
        self._color = None
        self.set_content(text, color, pulse)

    def set_content(self, text: str, color: str, pulse: bool) -> None:
        if self.label.text() != text:
            self.label.setText(text)
        if color != self._color:
            self._color = color
            rgb = _rgb(color)
            self.setStyleSheet(
                f"QFrame#badge{{background:rgba({rgb},35);"
                f"border:1px solid rgba({rgb},180);border-radius:15px;}}")
            self.label.setStyleSheet(f"color:{color};")
            self.dot.set_color(color)
        self.dot.set_pulse(pulse)


# ---------------------------------------------------------------------------
class HeaderBar(QWidget):
    SOLAR = {
        "ACTIVE": ("SIM: SOLAR EVENT", theme.RED, True),
        "EVA_DELAYED": ("SIM: EVA DELAYED", theme.AMBER, False),
        "SHELTER": ("SIM: SHELTER ACTIVE", theme.AMBER, False),
        "CLEAR": ("SIM: NO SOLAR EVENT", theme.GREEN, False),
    }

    def __init__(self, state: MissionState, parent=None):
        super().__init__(parent)
        self.state = state
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(8)
        self.setFixedHeight(50)

        left = QVBoxLayout()
        left.setSpacing(0)
        title = QLabel("NEXUS TRAINER")
        title.setFont(mono(19, True, 3.0))
        title.setStyleSheet(f"color:{theme.CYAN};")
        glow = QGraphicsDropShadowEffect(title)
        glow.setBlurRadius(26)
        glow.setOffset(0, 0)
        glow.setColor(QColor(127, 211, 255, 170))
        title.setGraphicsEffect(glow)
        self.sub = QLabel()
        self.sub.setFont(mono(7.5, False, 1.2))
        self.sub.setStyleSheet(f"color:{theme.MUTED};")
        left.addWidget(title)
        left.addWidget(self.sub)

        lay.addLayout(left)
        lay.addStretch(1)

        fs = 8.5
        self.solar = StatusBadge("", theme.GREEN, False, font_size=fs)
        self.rad = StatusBadge("", theme.GREEN, False, font_size=fs)
        self.mission = StatusBadge("", theme.CYAN, False, font_size=fs)
        # Real NOAA chip: separate row, separate from the simulated badges.
        self.real = StatusBadge("NOAA: WAITING", theme.MUTED, False, font_size=fs)
        self.real.setToolTip("Real NOAA SWPC proton flux (>=10 MeV). Display only. "
                             "Not part of the simulation.")
        self.real.hide()

        self.solar.hide()
        self.rad.hide()
        right = QHBoxLayout()
        right.setSpacing(8)
        right.addStretch(1)
        right.addWidget(self.real)
        right.addWidget(self.mission)
        lay.addLayout(right)

        state.changed.connect(self.refresh)
        self.refresh()

    def set_space_weather(self, proton) -> None:
        """Real NOAA proton flux chip. Display only. Never touches the simulation."""
        try:
            ok = isinstance(proton, dict)
            status = proton.get("status") if ok else None
            flux = proton.get("flux_pfu") if ok else None
            level = proton.get("s_level") if ok else None
            if status in ("live", "cached") and flux is not None and level is not None:
                color = (theme.GREEN if level == 0
                         else theme.AMBER if level <= 2 else theme.RED)
                body = f"NOAA S{level} · {_fmt_pfu(float(flux))} pfu"
                if status == "live":
                    text = f"REAL · {body}"
                else:
                    text = f"CACHED · {body} · {str(proton.get('fetched', ''))[:10]}"
            else:
                text, color = "NOAA: NO DATA (offline)", theme.MUTED
        except Exception:
            text, color = "NOAA: NO DATA (offline)", theme.MUTED
        self.real.set_content(text, color, False)

    def refresh(self) -> None:
        s = self.state
        dest = str(getattr(s, "destination", "moon")).lower()
        self.sub.setText(DEST_SUBTITLES.get(dest, "MISSION CONTROL"))
        day = getattr(s, "mission_day", 1)
        self.mission.set_content(
            f"{DEST_NAMES.get(dest, dest.upper())} · DAY {day} / {config.MISSION_DAYS}", theme.CYAN, False)
        text, color, pulse = self.SOLAR.get(
            getattr(s, "solar_status", "CLEAR"), self.SOLAR["CLEAR"])
        self.solar.set_content(text, color, pulse)
        rad = float(getattr(s, "radiation_level", 0.0))
        self.rad.set_content(f"RADIATION {rad:.0f}/100 (SIM)",
                             level_color(100 - rad), False)


# ---------------------------------------------------------------------------
class AlertBanner(QFrame):
    """Event banner. Reads the active event from state. Never claims live data."""

    def __init__(self, state: MissionState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setObjectName("banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)
        self.dot = PulseDot(theme.RED, True, 16)
        self.text = QLabel()
        self.text.setTextFormat(Qt.TextFormat.RichText)
        self.text.setWordWrap(True)
        self.text.setFont(mono(10, False, 0.3))
        self.tag = QLabel(theme.TITLE_ALERT_TAG)
        self.tag.setFont(mono(8.5, True, 1.5))
        lay.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.tag, 0, Qt.AlignmentFlag.AlignVCenter)
        self._color = None
        state.changed.connect(self.refresh)
        self.refresh()

    def _style(self, color: str) -> None:
        if color == self._color:
            return
        self._color = color
        rgb = _rgb(color)
        self.setStyleSheet(
            f"QFrame#banner{{background:rgba({rgb},26);"
            f"border:1px solid {color};border-radius:12px;}}")
        self.text.setStyleSheet(f"color:{theme.TEXT};")
        self.tag.setStyleSheet(
            f"color:{color};border:1px solid {color};border-radius:6px;padding:2px 8px;")
        self.dot.set_color(color)

    def refresh(self) -> None:
        s = self.state
        amber = f'<b style="color:{theme.AMBER}">'
        status = getattr(s, "status", "active")
        ev = getattr(s, "active_event", None)
        solar = getattr(s, "solar_status", "CLEAR")

        if status == "success":
            self._style(theme.GREEN)
            html_text = (f"<b>MISSION COMPLETE</b> (simulation) — "
                         f"readiness {getattr(s, 'readiness_pct', 0)}%")
            tag, pulse = "SIMULATION", False
        elif status == "failed":
            self._style(theme.RED)
            html_text = "<b>MISSION FAILED</b> (simulation) — see the Progress view"
            tag, pulse = "SIMULATION", False
        elif ev:
            self._style(theme.RED)
            title = html.escape(str(ev.get("title", "Event")))
            html_text = f"<b>{title}</b> — decision required"
            minutes = float(getattr(s, "minutes_to_peak", 0.0))
            if ev.get("id") == "solar_particle" and minutes > 0:
                html_text += f" — peak in {amber}T-minus {fmt_tminus(minutes)}</b>"
            tag, pulse = theme.TITLE_ALERT_TAG, True
        elif solar in ("SHELTER", "EVA_DELAYED"):
            self._style(theme.AMBER)
            label = html.escape(solar.replace("_", " ").title())
            html_text = f"Solar event decision logged: {label} — monitoring"
            tag, pulse = "SIMULATION", False
        else:
            self._style(theme.BLUE)
            day = getattr(s, "mission_day", 1)
            html_text = f"No active event — day {day}. Conditions are being monitored."
            tag, pulse = "SIMULATION", False

        self.text.setText(html_text)
        if self.tag.text() != tag:
            self.tag.setText(tag)
        self.dot.set_pulse(pulse)


# ---------------------------------------------------------------------------
class NavPanel(Panel):
    selected = pyqtSignal(int)
    ITEMS = [("◉", "Mission Control"), ("⚑", "Scenarios"), ("☄", "Space Hazards"),
             ("▤", "Knowledge Base"), ("✦", "EVA Planner"), ("▲", "Progress")]

    QSS = f"""
    QPushButton {{
        text-align:left; padding:10px 12px; border:1px solid transparent;
        border-radius:9px; color:{theme.MUTED}; background:transparent;
    }}
    QPushButton:hover {{ background:rgba(127,211,255,18); color:{theme.TEXT}; }}
    QPushButton:checked {{
        background:rgba(74,163,255,40); border:1px solid #2a6aa8; color:{theme.CYAN};
    }}
    """

    def __init__(self, parent=None):
        super().__init__("NAVIGATION", parent=parent)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QPushButton] = []
        for i, (icon, label) in enumerate(self.ITEMS):
            b = QPushButton(f" {icon}   {label}")
            b.setCheckable(True)
            b.setFont(mono(10.5, False, 0.5))
            b.setStyleSheet(self.QSS)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.group.addButton(b, i)
            self.buttons.append(b)
            self.body.addWidget(b)
        self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self.selected)

    def select(self, index: int) -> None:
        """Programmatic selection (does not emit `selected`)."""
        self.buttons[index].setChecked(True)


# ---------------------------------------------------------------------------
class CommanderCard(Panel):
    def __init__(self, state: MissionState, parent=None):
        super().__init__("COMMANDER", parent=parent)
        self.state = state
        row = QHBoxLayout()
        row.setSpacing(10)
        self.avatar = Avatar("CM", theme.GREEN, 46)
        row.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.name = QLabel()
        self.name.setFont(mono(14, True, 1.0))
        self.name.setWordWrap(True)
        self.name.setStyleSheet("color:#ffffff;")
        self.dest = QLabel()
        self.dest.setStyleSheet(f"color:{theme.MUTED};")
        col.addWidget(self.name)
        col.addWidget(self.dest)
        row.addLayout(col, 1)
        self.body.addLayout(row)

        self.rank = QLabel()
        self.rank.setStyleSheet(f"color:{theme.TEXT};")
        self.body.addWidget(self.rank)

        # --- Mission progress: days completed out of 30, starts at 0 ---
        pr = QHBoxLayout()
        plbl = QLabel("Mission progress")
        plbl.setStyleSheet(f"color:{theme.MUTED};")
        self.prog_text = QLabel()
        self.prog_text.setFont(mono(10, True))
        self.prog_text.setStyleSheet(f"color:{theme.CYAN};")
        pr.addWidget(plbl)
        pr.addStretch(1)
        pr.addWidget(self.prog_text)
        self.body.addLayout(pr)
        self.prog_bar = BarWidget(theme.CYAN, 8)
        self.body.addWidget(self.prog_bar)

        # --- Crew readiness: a health meter, shown smaller ---
        rr = QHBoxLayout()
        lbl = QLabel("Crew readiness")
        lbl.setStyleSheet(f"color:{theme.MUTED};")
        self.pct = QLabel()
        self.pct.setFont(mono(10, True))
        rr.addWidget(lbl)
        rr.addStretch(1)
        rr.addWidget(self.pct)
        self.body.addLayout(rr)
        self.bar = BarWidget(theme.GREEN, 5)
        self.body.addWidget(self.bar)

        state.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        s = self.state
        running = bool(getattr(s, "crew", None))
        name = (getattr(s, "commander_name", "") or "").strip() or "Commander"
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "CM"
        self.name.setText(name.upper())
        self.avatar.setText(initials)
        dest = str(getattr(s, "destination", "moon")).title()
        self.dest.setText(f"Destination: {dest}")
        if running:
            day = int(getattr(s, "mission_day", 1) or 1)
            done = max(0, min(day - 1, config.MISSION_DAYS))
            self.rank.setText(f"Junior Astronaut · Day {min(day, config.MISSION_DAYS)}")
            self.prog_text.setText(f"{done}/{config.MISSION_DAYS} days")
            self.prog_bar.set_value(done / max(config.MISSION_DAYS, 1))
            pct = int(getattr(s, "readiness_pct", 0))
            color = level_color(pct)
            self.pct.setText(f"{pct}%")
            self.pct.setStyleSheet(f"color:{color};")
            self.bar.set_value(pct / 100)
            self.bar.set_color(color)
        else:
            self.rank.setText("Junior Astronaut · awaiting mission")
            self.prog_text.setText(f"0/{config.MISSION_DAYS} days")
            self.prog_bar.set_value(0)
            self.pct.setText("--")
            self.pct.setStyleSheet(f"color:{theme.MUTED};")
            self.bar.set_value(0)
            self.bar.set_color(theme.MUTED)


# ---------------------------------------------------------------------------
class LiveFeeds(Panel):
    """Mission telemetry: simulated resources and crew radiation (0-100)."""
    ROWS = [("power", "Power"), ("oxygen", "Oxygen"), ("water", "Water"),
            ("food", "Food"), ("rad", "Radiation")]

    def __init__(self, state: MissionState, parent=None):
        super().__init__(theme.TITLE_TELEMETRY, parent=parent)
        self.state = state
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        self.rows: dict[str, tuple[BarWidget, QLabel]] = {}
        self._last_color: dict[str, str] = {}
        for r, (key, label) in enumerate(self.ROWS):
            name = QLabel(label)
            name.setFont(mono(9.5))
            name.setStyleSheet(f"color:{theme.MUTED};")
            bar = BarWidget(theme.GREEN, 6)
            val = QLabel()
            val.setFont(mono(10, True))
            val.setMinimumWidth(72)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(name, r, 0)
            grid.addWidget(bar, r, 1)
            grid.addWidget(val, r, 2)
            self.rows[key] = (bar, val)
        self.body.addLayout(grid)
        note = QLabel("Simulation values")
        note.setFont(mono(8))
        note.setStyleSheet(f"color:{theme.MUTED};")
        self.body.addWidget(note)
        state.changed.connect(self.refresh)
        self.refresh()

    def _set_row(self, key: str, text: str, frac: float, color: str) -> None:
        bar, lbl = self.rows[key]
        lbl.setText(text)
        bar.set_value(frac)
        if self._last_color.get(key) != color:
            self._last_color[key] = color
            bar.set_color(color)
            lbl.setStyleSheet(f"color:{color};")

    def refresh(self) -> None:
        s = self.state
        if not bool(getattr(s, "crew", None)):
            for key in ("power", "oxygen", "water", "food", "rad"):
                self._set_row(key, "--", 0.0, theme.MUTED)
            return
        res = getattr(s, "resources", {}) or {}
        for key in ("power", "oxygen", "water", "food"):
            v = float(res.get(key, 0.0))
            self._set_row(key, f"{v:.0f}%", v / 100, level_color(v))
        rad = float(getattr(s, "radiation_level", 0.0))
        self._set_row("rad", f"{rad:.0f}/100", rad / 100, level_color(100 - rad))


# ---------------------------------------------------------------------------
class ScenarioCard(Panel):
    respond_clicked = pyqtSignal()

    BTN = f"""
    QPushButton {{
        background:transparent; color:{theme.AMBER}; border:2px solid {theme.AMBER};
        border-radius:10px; padding:12px;
    }}
    QPushButton:hover {{ background:rgba(255,179,71,40); }}
    QPushButton:pressed {{ background:rgba(255,179,71,70); }}
    QPushButton:disabled {{ color:{theme.MUTED}; border:2px solid {theme.BORDER}; }}
    """

    def __init__(self, state: MissionState, parent=None):
        super().__init__("ACTIVE EVENT (SIM)", accent=theme.AMBER,
                         title_color=theme.AMBER,
                         tint=("rgba(52,36,12,238)", "rgba(28,20,10,238)"),
                         parent=parent)
        self.state = state
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setFont(mono(10.5))
        self.text.setStyleSheet("color:#ffd9a0;")
        self.body.addWidget(self.text)
        self.body.addStretch(1)
        self.btn = QPushButton("RESPOND NOW →")
        self.btn.setFont(mono(13, True, 1.5))
        self.btn.setStyleSheet(self.BTN)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn.clicked.connect(self.respond_clicked)
        self.body.addWidget(self.btn)
        state.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        s = self.state
        ev = getattr(s, "active_event", None)
        status = getattr(s, "status", "active")
        if ev:
            t = str(ev.get("question") or ev.get("title") or "Event")
        elif status in ("success", "failed"):
            t = "Mission finished (simulation). See the Progress view."
        else:
            t = "No event right now. Conditions are being monitored."
        if self.text.text() != t:
            self.text.setText(t)
        self.btn.setEnabled(bool(ev))


# ---------------------------------------------------------------------------
class StatusFooter(QFrame):
    """Footer strip. Statuses come from theme.footer_statuses(). Honest by default.
    Call set_ai_online(True/False) from a real check; None = not checked."""

    TIPS = {
        "MODE": "All mission numbers are simulation values.",
        "AI": "ONLINE/OFFLINE comes from the last real AI call. NOT CHECKED until then.",
        "VOICE": "Speech-to-text uses an online service and needs internet.",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("footer")
        self.setStyleSheet("QFrame#footer{background:rgba(11,20,38,210);"
                           "border:1px solid #16385c;border-radius:10px;}")
        self._ai = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(20)
        self._items = QHBoxLayout()
        self._items.setSpacing(20)
        lay.addLayout(self._items)
        lay.addStretch(1)
        right = QLabel(theme.FOOTER_TEXT)
        right.setFont(mono(8.5, False, 0.8))
        right.setStyleSheet(f"color:{theme.MUTED};")
        lay.addWidget(right)
        self._rebuild()

    def set_ai_online(self, online) -> None:
        if online != self._ai:
            self._ai = online
            self._rebuild()

    def _rebuild(self) -> None:
        while self._items.count():
            w = self._items.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for label, value, color in theme.footer_statuses(self._ai):
            item = QLabel(
                f'<span style="color:{color}">●</span> '
                f'<span style="color:{theme.MUTED}">{label}</span> '
                f'<span style="color:{color};font-weight:bold">{value}</span>')
            item.setTextFormat(Qt.TextFormat.RichText)
            item.setFont(mono(8.5, False, 0.8))
            item.setToolTip(self.TIPS.get(label, ""))
            self._items.addWidget(item)
