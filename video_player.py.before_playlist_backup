from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QPushButton, QSlider, QStyle, QVBoxLayout, QWidget


class VideoPlayerWindow(QMainWindow):
    """Ingebouwde videospeler voor VideoAudioScanner."""

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"Video bekijken — {Path(path).name}")
        self.resize(1100, 720)
        self.setMinimumSize(760, 500)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.video = QVideoWidget(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.audio.setVolume(0.85)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.title = QLabel(Path(path).name)
        self.title.setObjectName("playerTitle")
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.title)
        root.addWidget(self.video, 1)

        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setRange(0, 0)
        self.position.sliderMoved.connect(self._seek)
        root.addWidget(self.position)

        time_row = QHBoxLayout()
        self.current_time = QLabel("00:00")
        self.total_time = QLabel("00:00")
        time_row.addWidget(self.current_time)
        time_row.addStretch(1)
        time_row.addWidget(self.total_time)
        root.addLayout(time_row)

        controls = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setToolTip("Afspelen / pauzeren (spatie)")
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)

        stop = QPushButton()
        stop.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        stop.setToolTip("Stop")
        stop.clicked.connect(self.stop)
        controls.addWidget(stop)

        controls.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(85)
        self.volume.setFixedWidth(130)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100.0))
        controls.addWidget(self.volume)
        controls.addStretch(1)

        fullscreen = QPushButton("Volledig scherm")
        fullscreen.setToolTip("Volledig scherm (F11)")
        fullscreen.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(fullscreen)
        root.addLayout(controls)

        self.status = QLabel("Laden…")
        self.status.setObjectName("playerStatus")
        root.addWidget(self.status)

        self.setCentralWidget(central)
        self.setStyleSheet("""
            QWidget { background: #101216; color: #e8eaed; font-size: 13px; }
            QMainWindow { background: #101216; }
            QLabel#playerTitle { color: #ffffff; font-size: 17px; font-weight: 700; padding: 3px 2px; }
            QLabel#playerStatus { color: #8f96a3; padding: 2px; }
            QVideoWidget { background: #050608; border: 1px solid #30343c; border-radius: 6px; }
            QPushButton { background: #292e36; border: 1px solid #3c424c; border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover { background: #353b45; }
            QSlider::groove:horizontal { height: 5px; background: #30343c; border-radius: 2px; }
            QSlider::handle:horizontal { width: 13px; margin: -4px 0; border-radius: 6px; background: #6e8fbe; }
        """)

        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._state_changed)
        self.player.errorOccurred.connect(self._error)

        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_play)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self._leave_fullscreen)

        if os.path.isfile(path):
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.play()
        else:
            self.status.setText("Bestand bestaat niet meer.")

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        seconds = max(0, milliseconds // 1000)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self):
        self.player.stop()
        self.player.setPosition(0)

    def _seek(self, value: int):
        self.player.setPosition(value)

    def _position_changed(self, position: int):
        if not self.position.isSliderDown():
            self.position.setValue(position)
        self.current_time.setText(self._format_time(position))

    def _duration_changed(self, duration: int):
        self.position.setRange(0, max(0, duration))
        self.total_time.setText(self._format_time(duration))

    def _state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay))
        if playing:
            self.status.setText("Afspelen")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.status.setText("Gepauzeerd")
        else:
            self.status.setText("Klaar")

    def _error(self, error, error_string: str):
        if error != QMediaPlayer.Error.NoError:
            self.status.setText(f"Kan video niet afspelen: {error_string or 'onbekende fout'}")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)
