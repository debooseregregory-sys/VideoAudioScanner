from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSlider,
    QStyle, QVBoxLayout, QWidget,
)

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


class VideoPlayerWindow(QMainWindow):
    """Ingebouwde videospeler met playlist, FFmpeg-fallback en Prullenbak."""

    def __init__(self, path: str, parent=None, playlist=None):
        super().__init__(parent)
        self.parent_library = parent
        self.playlist = list(playlist or [path])
        self.current_index = self.playlist.index(path) if path in self.playlist else 0
        self.path = self.playlist[self.current_index]
        self._autoplay_requested = False
        self._ffmpeg_process = None
        self._ffmpeg_output = None
        self._using_ffmpeg_fallback = False
        self._ffmpeg_temp_dir = Path(tempfile.mkdtemp(prefix="videoaudio_player_"))

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
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.title)
        root.addWidget(self.video, 1)

        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setRange(0, 0)
        self.position.sliderMoved.connect(lambda value: self.player.setPosition(value))
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
        self.previous_button.clicked.connect(self.previous_video)
        controls.addWidget(self.previous_button)

        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setToolTip("Afspelen / pauzeren (spatie)")
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)

        self.next_button = QPushButton("Volgende")
        self.next_button.clicked.connect(self.next_video)
        controls.addWidget(self.next_button)

        stop = QPushButton()
        stop.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        stop.setToolTip("Stop")
        stop.clicked.connect(self.stop)
        controls.addWidget(stop)

        self.repeat_button = QPushButton("Herhalen: uit")
        self.repeat_button.setCheckable(True)
        self.repeat_button.toggled.connect(lambda checked: self.repeat_button.setText("Herhalen: aan" if checked else "Herhalen: uit"))
        controls.addWidget(self.repeat_button)

        controls.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(85)
        self.volume.setFixedWidth(130)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100.0))
        controls.addWidget(self.volume)
        controls.addStretch(1)

        self.playlist_label = QLabel()
        self.playlist_label.setObjectName("playlistLabel")
        controls.addWidget(self.playlist_label)

        fullscreen = QPushButton("Volledig scherm")
        fullscreen.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(fullscreen)
        root.addLayout(controls)

        action_row = QHBoxLayout()
        self.delete_button = QPushButton("Naar Prullenbak")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self.delete_current_video)
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        self.status = QLabel("Laden...")
        self.status.setObjectName("playerStatus")
        root.addWidget(self.status)
        self.setCentralWidget(central)

        self.setStyleSheet("""
            QWidget { background:#101216; color:#e8eaed; font-size:13px; }
            QMainWindow { background:#101216; }
            QLabel#playerTitle { color:#fff; font-size:17px; font-weight:700; padding:3px 2px; }
            QLabel#playerStatus { color:#8f96a3; padding:2px; }
            QLabel#playlistLabel { color:#c8ccd3; font-weight:600; padding:4px 8px; }
            QVideoWidget { background:#050608; border:1px solid #30343c; border-radius:6px; }
            QPushButton { background:#292e36; border:1px solid #3c424c; border-radius:6px; padding:8px 12px; }
            QPushButton:hover { background:#353b45; }
            QPushButton:checked { background:#315f9e; border-color:#5686c4; }
            QPushButton#danger { background:#54272b; border-color:#824047; font-weight:600; }
            QPushButton#danger:hover { background:#6a3036; }
            QPushButton:disabled { color:#666c75; background:#202329; }
        """)

        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._state_changed)
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self.player.errorOccurred.connect(self._error)

        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_play)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self._leave_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.next_video)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.previous_video)

        self._update_playlist_ui()
        self._load_current_video()

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        seconds = max(0, int(milliseconds) // 1000)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    def _update_playlist_ui(self):
        total = len(self.playlist)
        self.playlist_label.setText(f"{self.current_index + 1} / {total}" if total > 1 else "")
        self.previous_button.setEnabled(total > 1 and self.current_index > 0)
        self.next_button.setEnabled(total > 1 and self.current_index < total - 1)
        if self.playlist:
            name = Path(self.playlist[self.current_index]).name
            self.title.setText(name)
            self.setWindowTitle(f"Video bekijken — {name}")

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
        self._autoplay_requested = bool(autoplay)
        self._stop_ffmpeg_fallback()
        self._using_ffmpeg_fallback = False
        self.player.stop()
        self.player.setSource(QUrl())
        if not os.path.isfile(self.path):
            self._autoplay_requested = False
            self.status.setText("Bestand bestaat niet meer.")
            QTimer.singleShot(0, self._remove_missing_current)
            return
        self.player.setSource(QUrl.fromLocalFile(self.path))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self._autoplay_requested = True
            self.player.play()

    def stop(self):
        self._autoplay_requested = False
        self.player.stop()
        self.player.setPosition(0)

    def previous_video(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_video()

    def next_video(self):
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            self._load_current_video()
        elif self.repeat_button.isChecked() and self.playlist:
            self.current_index = 0
            self._load_current_video()
        else:
            self._autoplay_requested = False
            self.player.stop()
            self.status.setText("Playlist afgelopen")

    def _position_changed(self, position):
        if not self.position.isSliderDown():
            self.position.setValue(position)
        self.current_time.setText(self._format_time(position))

    def _duration_changed(self, duration):
        self.position.setRange(0, max(0, duration))
        self.total_time.setText(self._format_time(duration))

    def _state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay))
        if playing:
            self.status.setText("Afspelen" if not self._using_ffmpeg_fallback else "Afspelen via FFmpeg compatibiliteitsmodus")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.status.setText("Gepauzeerd")

    def _media_status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if self._autoplay_requested:
                self._autoplay_requested = False
                self.player.play()
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.repeat_button.isChecked():
                self.player.setPosition(0)
                self.player.play()
            elif self.current_index < len(self.playlist) - 1:
                self.current_index += 1
                self._load_current_video()
            else:
                self.status.setText("Playlist afgelopen")
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._start_ffmpeg_fallback()
        elif status == QMediaPlayer.MediaStatus.StalledMedia:
            self.status.setText("Video tijdelijk geblokkeerd — wachten...")

    def _error(self, error, error_string):
        if error == QMediaPlayer.Error.NoError:
            return
        if not self._using_ffmpeg_fallback:
            self._start_ffmpeg_fallback(error_string)
        else:
            self.status.setText("Kan video niet afspelen: " + (error_string or "onbekende fout"))

    def _find_ffmpeg(self):
        """Vind FFmpeg in de PyInstaller-app, PATH, WinGet en gangbare Windows-locaties."""
        candidates = []

        # PyInstaller: ffmpeg.exe naast de EXE of in _internal.
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates += [exe_dir / "ffmpeg.exe", exe_dir / "_internal" / "ffmpeg.exe"]
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidates.append(Path(meipass) / "ffmpeg.exe")

        # Ontwikkelomgeving: naast video_player.py.
        candidates.append(Path(__file__).resolve().parent / "ffmpeg.exe")

        # PATH en Windows where.exe.
        found = shutil.which("ffmpeg")
        if found:
            candidates.append(Path(found))
        try:
            where_result = subprocess.run(
                ["where.exe", "ffmpeg.exe"], capture_output=True, text=True, timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if where_result.returncode == 0:
                candidates.extend(Path(line.strip()) for line in where_result.stdout.splitlines() if line.strip())
        except Exception:
            pass

        # WinGet-installatie van Gyan.FFmpeg.Shared, zoals op deze pc.
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            try:
                for package_dir in winget_root.glob("Gyan.FFmpeg*"):
                    candidates.extend(package_dir.glob("**/bin/ffmpeg.exe"))
            except OSError:
                pass

        # Andere gebruikelijke Windows-installaties.
        for root in (
            Path("C:/ffmpeg"),
            Path("C:/Program Files/ffmpeg"),
            Path("C:/ProgramData/chocolatey/bin"),
        ):
            candidates.extend([root / "bin" / "ffmpeg.exe", root / "ffmpeg.exe"])

        seen = set()
        for candidate in candidates:
            try:
                candidate = candidate.resolve()
                key = str(candidate).lower()
                if key in seen:
                    continue
                seen.add(key)
                if candidate.is_file():
                    return str(candidate)
            except OSError:
                pass
        return None

    def _start_ffmpeg_fallback(self, qt_error=""):
        """Gebruik FFmpeg automatisch wanneer Qt de bron niet kan decoderen."""
        if self._using_ffmpeg_fallback or not os.path.isfile(self.path):
            return False

        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            self.status.setText("Codec niet ondersteund en FFmpeg is niet gevonden.")
            return False

        self._stop_ffmpeg_fallback()
        self._using_ffmpeg_fallback = True
        output = self._ffmpeg_temp_dir / f"fallback_{self.current_index}.mp4"
        self._ffmpeg_output = output
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass

        self.status.setText("Codec niet ondersteund — FFmpeg maakt automatisch een compatibele versie...")
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", self.path,
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output),
        ]
        try:
            self._ffmpeg_process = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            self._using_ffmpeg_fallback = False
            self.status.setText(f"FFmpeg kon niet starten: {exc}")
            return False

        process = self._ffmpeg_process

        def worker():
            try:
                stderr = process.communicate()[1]
                code = process.returncode
            except Exception as exc:
                stderr = str(exc).encode()
                code = -1
            message = stderr.decode("utf-8", errors="replace").strip()[-500:]
            if code == 0 and output.exists() and output.stat().st_size > 0:
                QTimer.singleShot(0, lambda: self._play_ffmpeg_output(output))
            else:
                QTimer.singleShot(0, lambda: self._ffmpeg_failed(message or qt_error))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _play_ffmpeg_output(self, output):
        if not self._using_ffmpeg_fallback or not output.exists():
            return
        self.status.setText("Afspelen via FFmpeg compatibiliteitsmodus")
        self._autoplay_requested = True
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(output)))

    def _ffmpeg_failed(self, message):
        self._using_ffmpeg_fallback = False
        self.status.setText("FFmpeg kon deze video niet converteren." + (f" {message}" if message else ""))

    def _stop_ffmpeg_fallback(self):
        process = self._ffmpeg_process
        self._ffmpeg_process = None
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=2)
            except Exception:
                pass
        self._using_ffmpeg_fallback = False

    def delete_current_video(self):
        if not self.playlist:
            return
        path = self.playlist[self.current_index]
        if not os.path.isfile(path):
            self._remove_missing_current()
            return
        answer = QMessageBox.question(
            self, "Naar Prullenbak",
            "Wil je deze video naar de Windows Prullenbak verplaatsen?\n\n" + Path(path).name,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if send2trash is None:
            QMessageBox.critical(self, "Prullenbak", "De module 'send2trash' is niet geïnstalleerd.")
            return

        deleted_name = Path(path).name
        try:
            self._autoplay_requested = False
            self._stop_ffmpeg_fallback()
            self.player.stop()
            self.player.setSource(QUrl())
            QCoreApplication.processEvents()
            send2trash(path)
        except Exception as exc:
            QMessageBox.critical(self, "Prullenbak", f"De video kon niet naar de Prullenbak worden verplaatst:\n\n{exc}")
            return

        self._notify_parent_video_deleted(path)
        self.playlist.pop(self.current_index)
        if not self.playlist:
            self.status.setText(f"{deleted_name} naar de Prullenbak verplaatst.")
            QTimer.singleShot(150, self.close)
            return
        if self.current_index >= len(self.playlist):
            self.current_index = len(self.playlist) - 1
        self._update_playlist_ui()
        self.status.setText(f"{deleted_name} naar de Prullenbak verplaatst.")
        self._load_current_video()

    def _notify_parent_video_deleted(self, path):
        """Houd de geopende Video Library en SQLite-index direct synchroon."""
        parent = self.parent_library
        if parent is None:
            return
        try:
            if hasattr(parent, "db"):
                parent.db.delete_video(path)
            if hasattr(parent, "items"):
                parent.items = [item for item in parent.items if getattr(item, "path", None) != path]
            if getattr(parent, "selected_path", None) == path:
                parent.selected_path = ""
                if hasattr(parent, "clear_details"):
                    parent.clear_details()
            if hasattr(parent, "refresh_cards"):
                parent.refresh_cards()
            if hasattr(parent, "stats") and hasattr(parent, "items"):
                total = sum(getattr(item, "size", 0) for item in parent.items)
                try:
                    from video_library import format_size
                    parent.stats.setText(f"{len(parent.items):,} video's  •  {format_size(total)}")
                except Exception:
                    parent.stats.setText(f"{len(parent.items):,} video's")
            if hasattr(parent, "status"):
                parent.status.setText(f"🗑 Naar Prullenbak: {Path(path).name}")
        except Exception:
            pass

    def _remove_missing_current(self):
        if not self.playlist:
            self.close()
            return
        path = self.playlist[self.current_index]
        self._notify_parent_video_deleted(path)
        self.playlist.pop(self.current_index)
        if not self.playlist:
            self.close()
            return
        if self.current_index >= len(self.playlist):
            self.current_index = len(self.playlist) - 1
        self._load_current_video()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def closeEvent(self, event):
        self._autoplay_requested = False
        self.player.stop()
        self.player.setSource(QUrl())
        self._stop_ffmpeg_fallback()
        shutil.rmtree(self._ffmpeg_temp_dir, ignore_errors=True)
        super().closeEvent(event)
