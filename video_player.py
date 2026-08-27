from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


class VideoPlayerWindow(QMainWindow):
    """Ingebouwde videospeler met playlist, navigatie en Prullenbak."""

    def __init__(self, path: str, parent=None, playlist=None):
        super().__init__(parent)

        self.playlist = list(playlist or [path])
        self.current_index = 0

        if path in self.playlist:
            self.current_index = self.playlist.index(path)

        self.path = self.playlist[self.current_index]

        self.setWindowTitle(f"Video bekijken — {Path(self.path).name}")
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

        self.title = QLabel()
        self.title.setObjectName("playerTitle")
        self.title.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
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

        self.previous_button = QPushButton("Vorige")
        self.previous_button.setToolTip("Vorige video")
        self.previous_button.clicked.connect(self.previous_video)
        controls.addWidget(self.previous_button)

        self.play_button = QPushButton()
        self.play_button.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_MediaPlay
            )
        )
        self.play_button.setToolTip("Afspelen / pauzeren (spatie)")
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)

        self.next_button = QPushButton("Volgende")
        self.next_button.setToolTip("Volgende video")
        self.next_button.clicked.connect(self.next_video)
        controls.addWidget(self.next_button)

        stop = QPushButton()
        stop.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_MediaStop
            )
        )
        stop.setToolTip("Stop")
        stop.clicked.connect(self.stop)
        controls.addWidget(stop)

        self.repeat_button = QPushButton("Herhalen: uit")
        self.repeat_button.setCheckable(True)
        self.repeat_button.setToolTip(
            "Herhaal de huidige video wanneer deze afgelopen is"
        )
        self.repeat_button.toggled.connect(self._repeat_changed)
        controls.addWidget(self.repeat_button)

        controls.addWidget(QLabel("Volume"))

        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(85)
        self.volume.setFixedWidth(130)
        self.volume.valueChanged.connect(
            lambda value: self.audio.setVolume(value / 100.0)
        )
        controls.addWidget(self.volume)

        controls.addStretch(1)

        self.playlist_label = QLabel()
        self.playlist_label.setObjectName("playlistLabel")
        controls.addWidget(self.playlist_label)

        fullscreen = QPushButton("Volledig scherm")
        fullscreen.setToolTip("Volledig scherm (F11)")
        fullscreen.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(fullscreen)

        root.addLayout(controls)

        action_row = QHBoxLayout()

        self.delete_button = QPushButton(
            "Naar Prullenbak"
        )
        self.delete_button.setObjectName("danger")
        self.delete_button.setToolTip(
            "De huidige video naar de Windows Prullenbak verplaatsen"
        )
        self.delete_button.clicked.connect(
            self.delete_current_video
        )
        action_row.addWidget(self.delete_button)

        action_row.addStretch(1)

        root.addLayout(action_row)

        self.status = QLabel("Laden...")
        self.status.setObjectName("playerStatus")
        root.addWidget(self.status)

        self.setCentralWidget(central)

        self.setStyleSheet(
            """
            QWidget {
                background: #101216;
                color: #e8eaed;
                font-size: 13px;
            }

            QMainWindow {
                background: #101216;
            }

            QLabel#playerTitle {
                color: #ffffff;
                font-size: 17px;
                font-weight: 700;
                padding: 3px 2px;
            }

            QLabel#playerStatus {
                color: #8f96a3;
                padding: 2px;
            }

            QLabel#playlistLabel {
                color: #c8ccd3;
                font-weight: 600;
                padding: 4px 8px;
            }

            QVideoWidget {
                background: #050608;
                border: 1px solid #30343c;
                border-radius: 6px;
            }

            QPushButton {
                background: #292e36;
                border: 1px solid #3c424c;
                border-radius: 6px;
                padding: 8px 12px;
            }

            QPushButton:hover {
                background: #353b45;
            }

            QPushButton:checked {
                background: #315f9e;
                border-color: #5686c4;
            }

            QPushButton#danger {
                background: #54272b;
                border-color: #824047;
                font-weight: 600;
            }

            QPushButton#danger:hover {
                background: #6a3036;
            }

            QPushButton:disabled {
                color: #666c75;
                background: #202329;
            }

            QSlider::groove:horizontal {
                height: 5px;
                background: #30343c;
                border-radius: 2px;
            }

            QSlider::handle:horizontal {
                width: 13px;
                margin: -4px 0;
                border-radius: 6px;
                background: #6e8fbe;
            }
            """
        )

        self.player.positionChanged.connect(
            self._position_changed
        )

        self.player.durationChanged.connect(
            self._duration_changed
        )

        self.player.playbackStateChanged.connect(
            self._state_changed
        )

        self.player.mediaStatusChanged.connect(
            self._media_status_changed
        )

        self.player.errorOccurred.connect(
            self._error
        )

        QShortcut(
            QKeySequence(Qt.Key.Key_Space),
            self,
            activated=self.toggle_play,
        )

        QShortcut(
            QKeySequence("F11"),
            self,
            activated=self.toggle_fullscreen,
        )

        QShortcut(
            QKeySequence("Esc"),
            self,
            activated=self._leave_fullscreen,
        )

        QShortcut(
            QKeySequence(Qt.Key.Key_Right),
            self,
            activated=self.next_video,
        )

        QShortcut(
            QKeySequence(Qt.Key.Key_Left),
            self,
            activated=self.previous_video,
        )

        self._update_playlist_ui()
        self._load_current_video()

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        seconds = max(0, milliseconds // 1000)

        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"

        return f"{minutes:02d}:{seconds:02d}"

    def _update_playlist_ui(self):
        total = len(self.playlist)

        if total <= 1:
            self.playlist_label.setText("")
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
        else:
            self.playlist_label.setText(
                f"{self.current_index + 1} / {total}"
            )

            self.previous_button.setEnabled(
                self.current_index > 0
            )

            self.next_button.setEnabled(
                self.current_index < total - 1
            )

        self.title.setText(
            Path(self.playlist[self.current_index]).name
        )

        self.setWindowTitle(
            f"Video bekijken — "
            f"{Path(self.playlist[self.current_index]).name}"
        )

    def _load_current_video(self, autoplay=True):
        if not self.playlist:
            self.close()
            return

        self.path = self.playlist[self.current_index]

        self._update_playlist_ui()

        self.position.setRange(0, 0)
        self.current_time.setText("00:00")
        self.total_time.setText("00:00")
        self.status.setText("Laden...")

        if not os.path.isfile(self.path):
            self.status.setText(
                "Bestand bestaat niet meer."
            )
            return

        self.player.stop()
        self.player.setSource(
            QUrl.fromLocalFile(self.path)
        )

        if autoplay:
            self.player.play()

    def toggle_play(self):
        if (
            self.player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.player.pause()
        else:
            self.player.play()

    def stop(self):
        self.player.stop()
        self.player.setPosition(0)

    def previous_video(self):
        if self.current_index <= 0:
            return

        self.current_index -= 1
        self._load_current_video()

    def next_video(self):
        if self.current_index >= len(self.playlist) - 1:
            if self.repeat_button.isChecked():
                self.current_index = 0
                self._load_current_video()
            else:
                self.player.stop()
                self.status.setText(
                    "Playlist afgelopen"
                )
            return

        self.current_index += 1
        self._load_current_video()

    def _seek(self, value: int):
        self.player.setPosition(value)

    def _position_changed(self, position: int):
        if not self.position.isSliderDown():
            self.position.setValue(position)

        self.current_time.setText(
            self._format_time(position)
        )

    def _duration_changed(self, duration: int):
        self.position.setRange(
            0,
            max(0, duration)
        )

        self.total_time.setText(
            self._format_time(duration)
        )

    def _state_changed(self, state):
        playing = (
            state
            == QMediaPlayer.PlaybackState.PlayingState
        )

        self.play_button.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_MediaPause
                if playing
                else QStyle.StandardPixmap.SP_MediaPlay
            )
        )

        if playing:
            self.status.setText("Afspelen")
        elif (
            state
            == QMediaPlayer.PlaybackState.PausedState
        ):
            self.status.setText("Gepauzeerd")
        else:
            self.status.setText("Klaar")

    def _media_status_changed(self, status):
        if (
            status
            == QMediaPlayer.MediaStatus.EndOfMedia
        ):
            if self.repeat_button.isChecked():
                self.player.setPosition(0)
                self.player.play()
                return

            if self.current_index < len(self.playlist) - 1:
                self.current_index += 1
                self._load_current_video()
            else:
                self.status.setText(
                    "Playlist afgelopen"
                )

    def _repeat_changed(self, checked: bool):
        self.repeat_button.setText(
            "Herhalen: aan"
            if checked
            else "Herhalen: uit"
        )

    def delete_current_video(self):
        if not self.playlist:
            return

        path = self.playlist[self.current_index]

        if not os.path.isfile(path):
            self._remove_current_from_playlist()
            return

        answer = QMessageBox.question(
            self,
            "Naar Prullenbak",
            "Wil je deze video naar de Windows Prullenbak verplaatsen?\n\n"
            f"{Path(path).name}",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        if send2trash is None:
            QMessageBox.critical(
                self,
                "Prullenbak",
                "De module 'send2trash' is niet ge?nstalleerd.",
            )
            return

        try:
            # Eerst het afspelen stoppen.
            self.player.stop()

            # Daarna de mediabron volledig loskoppelen.
            # Alleen stop() kan het bestand nog tijdelijk open laten.
            self.player.setSource(QUrl())

            # Eventuele laatste positie terugzetten.
            self.position.setRange(0, 0)
            self.current_time.setText("00:00")
            self.total_time.setText("00:00")

            # Windows heeft soms een moment nodig om de
            # mediabestands-handle daadwerkelijk vrij te geven.
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.processEvents()

            send2trash(path)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Prullenbak",
                "De video kon niet naar de Prullenbak "
                f"worden verplaatst:\n\n{exc}",
            )
            return

        deleted_name = Path(path).name

        self._remove_current_from_playlist()

        if not self.playlist:
            QMessageBox.information(
                self,
                "Video verwijderd",
                f"{deleted_name} is naar de Prullenbak verplaatst.",
            )
            self.close()
            return

        self.status.setText(
            f"{deleted_name} naar de Prullenbak verplaatst."
        )

        self._load_current_video()

    def _remove_current_from_playlist(self):
        if not self.playlist:
            return

        self.playlist.pop(self.current_index)

        if not self.playlist:
            self.current_index = 0
            return

        if self.current_index >= len(self.playlist):
            self.current_index = len(self.playlist) - 1

        self._update_playlist_ui()

    def _error(self, error, error_string: str):
        if error != QMediaPlayer.Error.NoError:
            self.status.setText(
                "Kan video niet afspelen: "
                f"{error_string or 'onbekende fout'}"
            )

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
