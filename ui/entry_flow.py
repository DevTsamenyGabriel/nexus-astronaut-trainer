"""Entry flow: login -> destination -> transition video. Emits ready(name, dest) once."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QStackedWidget

from .dashboard import SpaceBackground
from .destination_screen import DestinationScreen
from .ready_screen import ReadyScreen
from .transition_video import TransitionVideo
from .views import LoginView


class EntryWindow(QStackedWidget):
    # (commander name, "moon" | "mars" | "moon-quick" | "mars-quick")
    ready = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg = SpaceBackground(self)      # same stars and planet glow as the dashboard
        self.setWindowTitle("NEXUS TRAINER")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.login = LoginView()
        self.destination = DestinationScreen()
        self.video = TransitionVideo()
        self.ready_screen = ReadyScreen()
        for page in (self.login, self.destination, self.video, self.ready_screen):
            self.addWidget(page)
        self._name = ""
        self._dest = ""
        self._emitted = False
        self.login.completed.connect(self._on_name)
        self.destination.selected.connect(self._on_dest)
        self.video.finished.connect(self._on_video_done)
        self.ready_screen.go.connect(self._on_go)
        self._bg.lower()                      # keep it behind the pages (last line of __init__)

    def _on_name(self, name: str) -> None:
        self._name = name
        self.destination.set_commander(name)
        self.destination.reset()
        self.setCurrentWidget(self.destination)

    def _on_dest(self, dest: str) -> None:
        self._dest = dest
        self._emitted = False
        self.setCurrentWidget(self.video)
        self.video.play(dest)          # a missing or broken video emits finished at once

    def _on_video_done(self) -> None:
        if self._emitted:
            return
        self._emitted = True
        self.ready_screen.prepare(self._name, self._dest)
        self.setCurrentWidget(self.ready_screen)
        self.ready_screen.setFocus()

    def _on_go(self) -> None:
        self.ready.emit(self._name, self._dest)

    def back_to_destination(self) -> None:
        """Called if the mission could not start: let the player choose again."""
        self._emitted = False
        self.destination.reset()
        self.setCurrentWidget(self.destination)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._bg.setGeometry(self.rect())
        self._bg.lower()
