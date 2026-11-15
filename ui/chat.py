"""Chat area: message rows, typing indicator, scroll area and input bar."""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import theme
from .common import Avatar, Panel, RoundButton, mono, section_title

NEXUS_NAME = "NEXUS"
USER_NAME = "COMMANDER GABBY"

BUBBLE_NEXUS = (f"QLabel#bubble{{background:rgba(20,45,80,210);color:{theme.TEXT};"
                f"border:1px solid {theme.BORDER};border-radius:12px;padding:10px 14px;}}")
BUBBLE_USER = (f"QLabel#bubble{{background:rgba(30,75,125,210);color:#ffffff;"
               f"border:1px solid {theme.BLUE};border-radius:12px;padding:10px 14px;}}")


class MessageRow(QWidget):
    """One chat message: NEXUS on the left, commander on the right."""

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        color = theme.GREEN if is_user else theme.CYAN
        avatar = Avatar("KM" if is_user else "NX", color, 38)

        name = QLabel(USER_NAME if is_user else NEXUS_NAME)
        name.setFont(mono(8.5, True, 1.2))
        name.setStyleSheet(f"color:{color};")
        stamp = QLabel(datetime.now().strftime("%H:%M"))
        stamp.setFont(mono(8))
        stamp.setStyleSheet(f"color:{theme.MUTED};")

        head = QHBoxLayout()
        head.setSpacing(8)
        if is_user:
            head.addStretch(1)
            head.addWidget(stamp)
            head.addWidget(name)
        else:
            head.addWidget(name)
            head.addWidget(stamp)
            head.addStretch(1)

        bubble = QLabel(text)
        self.bubble = bubble
        bubble.setObjectName("bubble")
        bubble.setWordWrap(True)
        bubble.setFont(mono(10.5))
        bubble.setMaximumWidth(560)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setStyleSheet(BUBBLE_USER if is_user else BUBBLE_NEXUS)

        col = QVBoxLayout()
        col.setSpacing(4)
        col.addLayout(head)
        col.addWidget(bubble, 0,
                      Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        if is_user:
            lay.addStretch(1)
            lay.addLayout(col)
            lay.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        else:
            lay.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            lay.addLayout(col)
            lay.addStretch(1)

        self._fade_in()

    def append_text(self, text: str) -> None:
        self.bubble.setText(self.bubble.text() + " " + text)

    def _fade_in(self) -> None:
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        self._anim = QPropertyAnimation(eff, b"opacity", self)
        self._anim.setDuration(350)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.finished.connect(self._fade_done)
        self._anim.start()

    def _fade_done(self) -> None:
        self.setGraphicsEffect(None)


class TypingRow(QWidget):
    """'NEXUS is analysing...' indicator shown during the simulated delay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(Avatar("NX", theme.CYAN, 38), 0, Qt.AlignmentFlag.AlignTop)
        self.label = QLabel("NEXUS is analysing")
        self.label.setObjectName("bubble")
        self.label.setFont(mono(10))
        self.label.setStyleSheet(BUBBLE_NEXUS.replace(theme.TEXT, theme.MUTED))
        lay.addWidget(self.label)
        lay.addStretch(1)
        self._n = 0
        self._timer = QTimer(self)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._step)
        self._timer.start()

    def _step(self) -> None:
        self._n = (self._n + 1) % 4
        self.label.setText("NEXUS is analysing" + "." * self._n)


class SourceRow(QWidget):
    """Muted, typed-out source line shown under a NEXUS answer. Display only, never spoken."""

    def __init__(self, sources: list, from_nasa: bool = True, parent=None):
        super().__init__(parent)
        lines = [str(s).strip() for s in (sources or []) if s and str(s).strip()]
        lines = [l[7:].strip() if l.lower().startswith("source:") else l for l in lines]
        from_nasa = bool(from_nasa and lines)
        color = theme.CYAN if from_nasa else theme.AMBER
        tag_text = "NASA SOURCE" if from_nasa else "NOT FROM NASA SOURCES"
        self._full = ("\n".join("• " + l for l in lines) if from_nasa
                      else "This answer is not backed by retrieved NASA excerpts.")

        tag = QLabel(tag_text)
        tag.setFont(mono(8, True, 1.2))
        tag.setStyleSheet(f"color:{color};")
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.text.setFont(mono(8.5))
        self.text.setMaximumWidth(560)
        self.text.setStyleSheet(f"color:{theme.MUTED};border-left:2px solid {color};"
                                "padding-left:8px;")
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(tag)
        col.addWidget(self.text)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(48, 0, 0, 0)   # lines up with the NEXUS bubble (avatar 38 + gap 10)
        lay.addLayout(col)
        lay.addStretch(1)

        self._pos = 0
        self._step = max(1, len(self._full) // 90)   # whole line types in about 1.4 s
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)
        QTimer.singleShot(250, self._timer.start)    # short pause after the answer

    def _tick(self) -> None:
        self._pos = min(len(self._full), self._pos + self._step)
        self.text.setText(self._full[:self._pos])
        if self._pos >= len(self._full):
            self._timer.stop()


class ChatView(Panel):
    submitted = pyqtSignal(str)   # user pressed Enter / send
    mic_clicked = pyqtSignal()    # user clicked the mic button
    stop_clicked = pyqtSignal()   # user clicked STOP while NEXUS is speaking
    log_toggled = pyqtSignal(bool)   # history drawer opened (True) or closed (False)
    _alert = False

    EDIT_QSS = f"""
    QLineEdit {{
        background:#0a1830; color:{theme.TEXT}; border:1px solid {theme.BORDER};
        border-radius:24px; padding:12px 20px; selection-background-color:#2a6aa8;
    }}
    QLineEdit:focus {{ border:1px solid {theme.CYAN}; }}
    QLineEdit:disabled {{ color:{theme.MUTED}; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._typing: TypingRow | None = None
        self._log_open = True
        # --- Header with the simulation-mode label ---
        head = QHBoxLayout()
        self._title = section_title("MISSION COMMS")
        head.addWidget(self._title)
        head.addStretch(1)
        self._hint = QLabel("AI explains · mission values are simulated")
        self._hint.setFont(mono(8))
        self._hint.setStyleSheet(f"color:{theme.MUTED};")
        self._tag = QLabel("● SIMULATION MODE")
        self._tag.setFont(mono(8.5, True, 1.2))
        self._tag.setStyleSheet(f"color:{theme.AMBER};border:1px solid {theme.AMBER};"
                                "border-radius:8px;padding:2px 9px;")
        self._tag.setToolTip("Mission values are simulation values, not real mission data.")
        head.addWidget(self._hint)
        head.addSpacing(8)
        head.addWidget(self._tag)
        self.body.addLayout(head)

        self._divider = QFrame()
        self._divider.setFixedHeight(1)
        self._divider.setStyleSheet("background:#16385c;border:none;")
        self.body.addWidget(self._divider)

        # --- Scrollable message list ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setObjectName("chatContent")
        content.setStyleSheet("QWidget#chatContent{background:transparent;}")
        self.msgs = QVBoxLayout(content)
        self.msgs.setContentsMargins(4, 8, 8, 8)
        self.msgs.setSpacing(16)
        self.msgs.addStretch(1)
        self.scroll.setWidget(content)
        self.body.addWidget(self.scroll, 1)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._on_range)

        # --- Input bar: mic, text field, STOP, LOG, send ---
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.mic = RoundButton("mic", 48)
        self.mic.setToolTip("Click to talk (or hold Space). Simulated voice input.")
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Speak your command or type here...")
        self.edit.setFont(mono(10.5))
        self.edit.setStyleSheet(self.EDIT_QSS)
        self.edit.setMinimumHeight(48)
        self.send = RoundButton("send", 48)
        self.stop = QPushButton("■ STOP")
        self.stop.setFont(mono(9, True, 1.0))
        self.stop.setMinimumHeight(48)
        self.stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.stop.setStyleSheet(
            f"QPushButton{{color:{theme.AMBER};background:rgba(255,179,71,22);"
            f"border:1px solid {theme.AMBER};border-radius:24px;padding:0 18px;}}"
            "QPushButton:hover{background:rgba(255,179,71,50);}")
        self.stop.hide()
        self.log_btn = QPushButton("LOG ▲")
        self.log_btn.setFont(mono(9, True, 1.0))
        self.log_btn.setMinimumHeight(48)
        self.log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.log_btn.setToolTip("Show or hide the conversation history")
        self.log_btn.setStyleSheet(
            f"QPushButton{{color:{theme.CYAN};background:rgba(127,211,255,18);"
            f"border:1px solid {theme.BORDER};border-radius:24px;padding:0 18px;}}"
            "QPushButton:hover{background:rgba(127,211,255,50);}")
        bar.addWidget(self.mic)
        bar.addWidget(self.edit, 1)
        bar.addWidget(self.stop)
        bar.addWidget(self.log_btn)
        bar.addWidget(self.send)
        self.body.addLayout(bar)

        self.mic.clicked.connect(self.mic_clicked)
        self.stop.clicked.connect(self.stop_clicked)
        self.send.clicked.connect(self._submit)
        self.edit.returnPressed.connect(self._submit)
        self.log_btn.clicked.connect(lambda: self.set_log_visible(not self._log_open))

        self.set_log_visible(False)       # history starts closed; the input bar stays

    def set_log_visible(self, visible: bool) -> None:
        """Show or hide the header and message history. The input bar always stays."""
        self._log_open = bool(visible)
        for widget in (self._title, self._hint, self._tag, self._divider, self.scroll):
            widget.setVisible(self._log_open)
        self.log_btn.setText("LOG ▼" if self._log_open else "LOG ▲")
        self.log_toggled.emit(self._log_open)

    # ------------------------------------------------------------------ API
    def add_message(self, text: str, is_user: bool) -> MessageRow:
        row = MessageRow(text, is_user)
        self.msgs.insertWidget(self.msgs.count() - 1, row)
        QTimer.singleShot(60, self._scroll_bottom)
        return row

    def add_action_chip(self, text: str) -> None:
        chip = QLabel(f"⚙ {text}")
        chip.setFont(mono(8.5, True, 1.0))
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet(
            f"color:{theme.CYAN};background:rgba(127,211,255,18);"
            f"border:1px solid {theme.BORDER};border-radius:9px;padding:3px 10px;")
        self.msgs.insertWidget(
            self.msgs.count() - 1, chip, 0, Qt.AlignmentFlag.AlignHCenter)
        QTimer.singleShot(60, self._scroll_bottom)

    def add_sources(self, sources: list, from_nasa: bool = True) -> "SourceRow":
        """Show the citation line under the last answer. Pass from_nasa=False when no sources."""
        row = SourceRow(sources, from_nasa)
        self.msgs.insertWidget(self.msgs.count() - 1, row)
        QTimer.singleShot(60, self._scroll_bottom)
        return row

    def show_typing(self) -> None:
        if self._typing is None:
            self._typing = TypingRow()
            self.msgs.insertWidget(self.msgs.count() - 1, self._typing)
            QTimer.singleShot(60, self._scroll_bottom)

    def hide_typing(self) -> None:
        if self._typing is not None:
            self._typing.setParent(None)
            self._typing.deleteLater()
            self._typing = None

    def set_listening(self, listening: bool) -> None:
        self.mic.set_active(listening)

    def set_busy(self, busy: bool) -> None:
        self.edit.setEnabled(not busy)
        self.send.setEnabled(not busy)
        if not busy:
            self.edit.setFocus()

    def set_speaking(self, speaking: bool) -> None:
        """Show the STOP button only while NEXUS is speaking."""
        self.stop.setVisible(bool(speaking))

    def set_alert(self, active: bool) -> None:
        """Red input bar while a simulation event waits for a decision."""
        active = bool(active)
        if active == self._alert:
            return
        self._alert = active
        if active:
            self.edit.setPlaceholderText("Pick a choice, or type 1, 2 or 3 ...")
            self.edit.setStyleSheet(
                self.EDIT_QSS
                + f"QLineEdit{{border:1px solid {theme.RED};background:#2a0f16;}}"
                + f"QLineEdit:focus{{border:1px solid {theme.RED};}}")
        else:
            self.edit.setPlaceholderText("Speak your command or type here...")
            self.edit.setStyleSheet(self.EDIT_QSS)

    # ------------------------------------------------------------ internals
    def _submit(self) -> None:
        text = self.edit.text().strip()
        if text:
            self.edit.clear()
            self.submitted.emit(text)

    def _on_range(self, _lo: int, hi: int) -> None:
        self.scroll.verticalScrollBar().setValue(hi)

    def _scroll_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
