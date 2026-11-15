"""Transition video: plays the Moon or Mars clip, then emits `finished`.
Any problem (missing file, no codec, stalled playback) skips the video. It never blocks a start."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .common import mono

VIDEO_DIR = Path(__file__).resolve().parent.parent / "Live_Nasa_Planet_Video"
CREDIT = "Video: NASA"        # replace with the exact credit line from the NASA page
START_TIMEOUT_MS = 4000       # not playing after this long -> skip the video
MAX_PLAY_MS = 20000           # hard limit for any clip


class TransitionVideo(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("transition")
        self.setStyleSheet("QWidget#transition{background:#000000;}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._done = True

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.0)                 # silent
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget(self)
        self.player.setVideoOutput(self.video)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)

        self._max_timer = QTimer(self)
        self._max_timer.setSingleShot(True)
        self._max_timer.timeout.connect(self._finish)

        credit = QLabel(CREDIT)
        credit.setFont(mono(9))
        credit.setStyleSheet(f"color:{theme.MUTED};background:transparent;")
        skip = QPushButton("SKIP  ›")
        skip.setFont(mono(10, True, 1.0))
        skip.setCursor(Qt.CursorShape.PointingHandCursor)
        skip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        skip.setStyleSheet(f"QPushButton{{color:{theme.CYAN};background:transparent;"
                           f"border:1px solid {theme.BORDER};border-radius:8px;padding:6px 14px;}}"
                           f"QPushButton:hover{{background:rgba(127,211,255,40);}}")
        skip.clicked.connect(self._finish)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(16, 6, 16, 10)
        bottom.addWidget(credit)
        bottom.addStretch(1)
        bottom.addWidget(skip)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.video, 1)
        lay.addLayout(bottom)

    def play(self, dest: str) -> None:
        """dest: 'moon', 'mars', 'moon-quick' or 'mars-quick'."""
        self._done = False
        name = "moon" if str(dest).startswith("moon") else "mars"
        path = VIDEO_DIR / f"{name}_live_video.mp4"
        if not path.is_file():
            self._finish()
            return
        self.setFocus()
        try:
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()
        except Exception:
            self._finish()
            return
        self._max_timer.start(MAX_PLAY_MS)
        QTimer.singleShot(START_TIMEOUT_MS, self._check_started)

    def _check_started(self) -> None:
        if (not self._done and
                self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState):
            self._finish()

    def _on_status(self, status) -> None:
        if status in (QMediaPlayer.MediaStatus.EndOfMedia,
                      QMediaPlayer.MediaStatus.InvalidMedia):
            self._finish()

    def _on_error(self, *_args) -> None:
        self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._max_timer.stop()
        try:
            self.player.stop()
            self.player.setSource(QUrl())
        except Exception:
            pass
        self.finished.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space, Qt.Key.Key_Return):
            self._finish()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        self._finish()
