"""Center-column views other than chat: placeholder, scenario and progress."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QTextEdit, QVBoxLayout, QWidget)

from state import MissionState
from . import theme
from .common import BarWidget, Panel, mono

BTN_QSS = f"""
QPushButton {{
    background:rgba(127,211,255,22); color:{theme.CYAN};
    border:1px solid {theme.CYAN}; border-radius:10px; padding:10px 28px;
}}
QPushButton:hover {{ background:rgba(127,211,255,50); }}
QPushButton:disabled {{ color:{theme.MUTED}; border-color:{theme.BORDER}; }}
"""

PROFILES_FILE = Path(__file__).resolve().parent.parent / "profiles.json"  # local only; add to .gitignore
_ITERATIONS = 200_000


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS).hex()


def _load_profiles() -> dict:
    try:
        return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def verify_or_create(name: str, password: str) -> tuple[bool, str]:
    """New name creates a local profile. A known name needs the right password."""
    profiles = _load_profiles()
    key = name.casefold()
    rec = profiles.get(key)
    if rec is None:
        salt = os.urandom(16)
        profiles[key] = {"name": name, "salt": salt.hex(),
                         "hash": _hash_password(password, salt)}
        try:
            PROFILES_FILE.write_text(json.dumps(profiles, indent=2), encoding="utf-8")
        except OSError:
            pass  # the demo keeps working even if the disk is read-only
        return True, ""
    try:
        ok = hmac.compare_digest(rec["hash"], _hash_password(password, bytes.fromhex(rec["salt"])))
    except (KeyError, ValueError):
        return False, "Profile data is damaged. Delete profiles.json to reset."
    return (True, "") if ok else (False, "Wrong password for this profile.")


class LoginView(QWidget):
    """Entry screen: commander name, then Continue. No password."""

    completed = pyqtSignal(str)   # commander name

    FIELD_QSS = (f"QLineEdit{{background:#0a1830;color:{theme.TEXT};"
                 f"border:1px solid {theme.BORDER};border-radius:10px;"
                 f"padding:4px 10px;text-align:center;}}"
                 f"QLineEdit:focus{{border:1px solid {theme.CYAN};}}")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("login")
        self.setStyleSheet(f"QWidget#login{{background:{theme.BG};}}")
        outer = QVBoxLayout(self)
        outer.addStretch(1)

        box = QWidget()
        box.setMaximumWidth(380)
        form = QVBoxLayout(box)
        form.setSpacing(12)

        title = QLabel("NEXUS TRAINER")
        title.setFont(mono(28, True, 3.0))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{theme.CYAN};")
        sub = QLabel("ENTER YOUR NAME, COMMANDER")
        sub.setFont(mono(9, False, 1.5))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{theme.MUTED};")

        self.name = QLineEdit()
        self.name.setPlaceholderText("Commander name")
        self.name.setMaxLength(24)
        self.name.setFont(mono(10, True))
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name.setStyleSheet(self.FIELD_QSS)
        self.name.setMinimumHeight(32)
        self.name.setMaximumHeight(32)
        self.name.returnPressed.connect(self._submit)

        self.error = QLabel("")
        self.error.setStyleSheet(f"color:{theme.RED};")

        go = QPushButton("CONTINUE  ›")
        go.setFont(mono(12, True, 1.2))
        go.setStyleSheet(BTN_QSS)
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.clicked.connect(self._submit)

        for w in (title, sub, self.name, self.error, go):
            form.addWidget(w)
        outer.addWidget(box, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

    def _submit(self) -> None:
        name = self.name.text().strip()
        if not name:
            self.error.setText("Enter your name to continue.")
            return
        self.error.setText("")
        self.completed.emit(name)


class PlaceholderView(Panel):
    """Simple 'coming soon' panel for modules that are not built yet."""

    def __init__(self, title: str, symbol: str, parent=None):
        super().__init__(title.upper(), parent=parent)
        self.body.addStretch(1)
        icon = QLabel(symbol)
        icon.setFont(mono(48))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"color:{theme.BORDER};")
        name = QLabel(title)
        name.setFont(mono(16, True, 2.0))
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(f"color:{theme.CYAN};")
        note = QLabel("Module placeholder: this panel is not part of the demo build yet.")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.MUTED};")
        for w in (icon, name, note):
            self.body.addWidget(w)
        self.body.addStretch(1)


class ScenarioView(Panel):
    """Shows the active simulation event with one button per option.
    The simulation decides the outcome; this view only shows choices and the
    fixed result text. Nothing here is scored or invented."""

    option_chosen = pyqtSignal(str)   # option id -> Controller calls backend.apply_choice
    submitted = pyqtSignal(int)       # kept so old connections do not break; never emitted

    OPTION_QSS = f"""
    QPushButton {{
        background:rgba(255,179,71,20); color:{theme.TEXT};
        border:1px solid {theme.AMBER}; border-radius:10px;
        padding:12px 16px; text-align:left;
    }}
    QPushButton:hover {{ background:rgba(255,179,71,50); }}
    QPushButton:disabled {{ color:{theme.MUTED}; border-color:{theme.BORDER}; }}
    """

    def __init__(self, state: MissionState, parent=None):
        super().__init__("SCENARIO · ACTIVE EVENT (SIM)", accent=theme.AMBER,
                         title_color=theme.AMBER, parent=parent)
        self.state = state
        self._shown_key = "unset"

        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        self.prompt.setFont(mono(11))
        self.prompt.setStyleSheet(
            "color:#ffd9a0;background:rgba(255,179,71,18);"
            "border:1px solid rgba(255,179,71,90);border-radius:10px;padding:12px;")
        self.body.addWidget(self.prompt)

        self.options_box = QVBoxLayout()
        self.options_box.setSpacing(10)
        self.body.addLayout(self.options_box)

        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setFont(mono(10.5))
        self.result.setStyleSheet(
            f"color:{theme.TEXT};background:rgba(74,163,255,18);"
            f"border:1px solid {theme.BLUE};border-radius:10px;padding:12px;")
        self.result.hide()
        self.body.addWidget(self.result)
        self.body.addStretch(1)

        state.changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ API
    def show_result(self, text: str) -> None:
        """Show the fixed outcome text returned by the simulation."""
        text = (text or "").strip()
        if text:
            self.result.setText(f"Result (simulation): {text}")
            self.result.show()

    # ------------------------------------------------------------ internals
    def _clear_options(self) -> None:
        while self.options_box.count():
            w = self.options_box.takeAt(0).widget()
            if w is not None:
                w.deleteLater()

    def _choose(self, option_id) -> None:
        if not option_id:
            return
        for i in range(self.options_box.count()):      # stop double clicks
            w = self.options_box.itemAt(i).widget()
            if w is not None:
                w.setEnabled(False)
        self.option_chosen.emit(str(option_id))

    def refresh(self) -> None:
        s = self.state
        ev = getattr(s, "active_event", None)
        status = getattr(s, "status", "active")
        key = (ev.get("id"), getattr(s, "day", 0)) if ev else ("none", status)
        if key == self._shown_key:        # state.changed fires every second
            return
        self._shown_key = key
        self._clear_options()

        if ev:
            self.result.hide()
            self.prompt.setText(f"{ev.get('title', 'Event')}\n\n{ev.get('question', '')}")
            for opt in ev.get("options", []):
                b = QPushButton(str(opt.get("label", "Option")))
                b.setFont(mono(10.5, True, 0.5))
                b.setStyleSheet(self.OPTION_QSS)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                b.clicked.connect(lambda _=False, oid=opt.get("id"): self._choose(oid))
                self.options_box.addWidget(b)
        elif status in ("success", "failed"):
            self.prompt.setText("Mission finished (simulation). See the Progress view.")
        else:
            self.prompt.setText("No event right now. Conditions are being monitored.")


class ProgressView(Panel):
    """Four training items with PASSED / FAILED / PENDING plus overall readiness."""

    COLORS = {"PASSED": theme.GREEN, "FAILED": theme.RED, "PENDING": theme.AMBER}

    def __init__(self, state: MissionState, parent=None):
        super().__init__("MISSION CHECKS (SIMULATION)", parent=parent)
        self.state = state

        top = QHBoxLayout()
        lbl = QLabel("OVERALL READINESS")
        lbl.setFont(mono(10, True, 1.5))
        lbl.setStyleSheet(f"color:{theme.MUTED};")
        self.pct = QLabel()
        self.pct.setFont(mono(26, True))
        self.pct.setStyleSheet(f"color:{theme.GREEN};")
        top.addWidget(lbl)
        top.addStretch(1)
        top.addWidget(self.pct)
        self.body.addLayout(top)
        self.bar = BarWidget(theme.GREEN, 10)
        self.body.addWidget(self.bar)
        self.body.addSpacing(10)

        self.rows: list[tuple[QLabel, QLabel]] = []
        for _ in range(len(state.training)):
            row = QFrame()
            row.setStyleSheet("QFrame{background:rgba(74,163,255,12);"
                              "border:1px solid #16385c;border-radius:10px;}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14, 12, 14, 12)
            name = QLabel()
            name.setFont(mono(11))
            name.setStyleSheet("border:none;background:transparent;")
            chip = QLabel()
            chip.setFont(mono(9.5, True, 1.2))
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setMinimumWidth(96)
            rl.addWidget(name, 1)
            rl.addWidget(chip)
            self.body.addWidget(row)
            self.rows.append((name, chip))
        self.body.addStretch(1)

        state.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        s = self.state
        running = bool(getattr(s, "crew", None))
        if running:
            self.pct.setText(f"{s.readiness_pct}%")
            self.bar.set_value(s.readiness_pct / 100)
        else:
            self.pct.setText("--")
            self.bar.set_value(0)
        for (name, chip), (title, status) in zip(self.rows, s.training):
            shown = status if running else "PENDING"
            if name.text() != title:
                name.setText(title)
            if chip.text() != shown:
                color = self.COLORS.get(shown, theme.MUTED)
                chip.setText(shown)
                chip.setStyleSheet(f"color:{color};border:1px solid {color};"
                                   "border-radius:8px;padding:3px 8px;background:transparent;")
