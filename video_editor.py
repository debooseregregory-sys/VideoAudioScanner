from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)


def find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    here = Path(__file__).resolve().parent
    for candidate in (
        here / "ffmpeg.exe",
        here / "ffmpeg" / "bin" / "ffmpeg.exe",
        here / "tools" / "ffmpeg.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def fmt_ms(ms: int) -> str:
    ms = max(0, int(ms))
    total, milli = divmod(ms, 1000)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milli:03d}"


VIDEO_FILTER = "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv *.mpeg *.mpg)"


class VideoCutterWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Video Cutter")
        self.resize(1100, 760)
        self.setMinimumSize(850, 620)
        self.source: Path | None = None
        self.duration = 0

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.video = QVideoWidget(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.audio.setVolume(0.85)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("VIDEO CUTTER")
        title.setStyleSheet("font-size:30px;font-weight:900;color:white;")
        header.addWidget(title)
        header.addStretch(1)
        browse = QPushButton("Video kiezen")
        browse.clicked.connect(self.choose_source)
        header.addWidget(browse)
        layout.addLayout(header)

        layout.addWidget(self.video, 1)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.seek)
        layout.addWidget(self.slider)

        times = QHBoxLayout()
        self.current = QLabel("00:00:00.000")
        self.total = QLabel("00:00:00.000")
        times.addWidget(self.current)
        times.addStretch(1)
        times.addWidget(self.total)
        layout.addLayout(times)

        controls = QHBoxLayout()
        self.play = QPushButton("▶ Afspelen")
        self.play.clicked.connect(self.toggle_play)
        self.set_start = QPushButton("Begin hier")
        self.set_start.clicked.connect(lambda: self.set_mark("start"))
        self.set_end = QPushButton("Einde hier")
        self.set_end.clicked.connect(lambda: self.set_mark("end"))
        controls.addWidget(self.play)
        controls.addWidget(self.set_start)
        controls.addWidget(self.set_end)
        controls.addStretch(1)
        layout.addLayout(controls)

        marks = QHBoxLayout()
        self.start_label = QLabel("Begin: 00:00:00.000")
        self.end_label = QLabel("Einde: niet ingesteld")
        marks.addWidget(self.start_label)
        marks.addStretch(1)
        marks.addWidget(self.end_label)
        layout.addLayout(marks)

        output_row = QHBoxLayout()
        self.output = QLineEdit()
        self.output.setPlaceholderText("Doelbestand wordt naast de video geplaatst")
        output_row.addWidget(self.output, 1)
        out_button = QPushButton("Opslaan als...")
        out_button.clicked.connect(self.choose_output)
        output_row.addWidget(out_button)
        layout.addLayout(output_row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cut = QPushButton("✂ Video knippen")
        cut.clicked.connect(self.cut)
        close = QPushButton("Sluiten")
        close.clicked.connect(self.close)
        buttons.addWidget(cut)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.setCentralWidget(root)
        self.setStyleSheet("""
            QWidget{background:#111318;color:#e8eaed;font-size:13px;}
            QPushButton{background:#292e36;border:1px solid #3c424c;border-radius:7px;padding:9px 14px;font-weight:600;color:#e8eaed;}
            QPushButton:hover{background:#353b45;}
            QLineEdit{background:#1e2127;border:1px solid #353a43;border-radius:6px;padding:7px;color:#e8eaed;}
        """)

        self.start_ms = 0
        self.end_ms: int | None = None

    def load_path(self, path: str | Path, autoplay: bool = True) -> bool:
        """Laad een video (o.a. vanuit de scanner via rechtsklik)."""
        path = Path(path)
        if not path.is_file():
            QMessageBox.warning(self, "Video Cutter", f"Bestand niet gevonden:\n{path}")
            return False
        self.source = path
        self.start_ms = 0
        self.end_ms = None
        self.start_label.setText("Begin: 00:00:00.000")
        self.end_label.setText("Einde: niet ingesteld")
        self.output.setText(str(self.source.with_name(self.source.stem + "_knip" + self.source.suffix)))
        self.setWindowTitle(f"Video Cutter — {path.name}")
        self.player.setSource(QUrl.fromLocalFile(str(self.source)))
        if autoplay:
            self.player.play()
        return True

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Kies video", "", VIDEO_FILTER + ";;Alle bestanden (*)")
        if not path:
            return
        self.load_path(path)

    def duration_changed(self, duration):
        self.duration = max(0, int(duration))
        self.slider.setRange(0, self.duration)
        self.total.setText(fmt_ms(self.duration))
        if self.end_ms is None:
            self.end_ms = self.duration
            self.end_label.setText(f"Einde: {fmt_ms(self.end_ms)}")

    def position_changed(self, position):
        self.slider.blockSignals(True)
        self.slider.setValue(int(position))
        self.slider.blockSignals(False)
        self.current.setText(fmt_ms(position))

    def seek(self, position):
        self.player.setPosition(int(position))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play.setText("▶ Afspelen")
        else:
            self.player.play()
            self.play.setText("⏸ Pauzeren")

    def set_mark(self, which):
        pos = int(self.player.position())
        if which == "start":
            self.start_ms = pos
            self.start_label.setText(f"Begin: {fmt_ms(pos)}")
            if self.end_ms is not None and self.end_ms <= pos:
                self.end_ms = self.duration
                self.end_label.setText(f"Einde: {fmt_ms(self.end_ms)}")
        else:
            self.end_ms = pos
            self.end_label.setText(f"Einde: {fmt_ms(pos)}")

    def choose_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Opslaan als", str(self.output.text() or ""), "MP4 video (*.mp4);;Alle bestanden (*)")
        if path:
            self.output.setText(path)

    def cut(self):
        if not self.source or not self.source.is_file():
            QMessageBox.warning(self, "Video Cutter", "Kies eerst een video.")
            return
        end = self.end_ms if self.end_ms is not None else self.duration
        if end <= self.start_ms:
            QMessageBox.warning(self, "Video Cutter", "Het eindpunt moet later zijn dan het beginpunt.")
            return
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            QMessageBox.critical(self, "FFmpeg ontbreekt", "FFmpeg kon niet worden gevonden.")
            return
        target = Path(self.output.text().strip()) if self.output.text().strip() else self.source.with_name(self.source.stem + "_knip.mp4")
        self.player.pause()
        duration = (end - self.start_ms) / 1000
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{self.start_ms / 1000:.3f}", "-i", str(self.source), "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-y", str(target)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError as exc:
            QMessageBox.critical(self, "Video Cutter", str(exc))
            return
        if result.returncode == 0 and target.is_file():
            QMessageBox.information(self, "Video Cutter", f"Videofragment opgeslagen als:\n{target}")
        else:
            QMessageBox.critical(self, "Video Cutter", "FFmpeg kon het fragment niet maken.\n\n" + result.stderr.strip())

    def closeEvent(self, event):
        self.player.stop()
        self.player.setSource(QUrl())
        # QAudioOutput heeft geen stop(); volume dempen is voldoende.
        try:
            self.audio.setVolume(0.0)
        except Exception:
            pass
        event.accept()


class VideoMergerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Video Merger")
        self.resize(850, 650)
        self.setMinimumSize(700, 500)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel("VIDEO MERGER")
        title.setStyleSheet("font-size:30px;font-weight:900;color:white;")
        layout.addWidget(title)
        info = QLabel("Voeg meerdere video's toe, zet ze in de gewenste volgorde en maak er één video van. Voor het betrouwbaarste resultaat gebruik je video's met dezelfde codec, resolutie en FPS.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#aeb5c0;font-size:14px;")
        layout.addWidget(info)

        self.files = QListWidget()
        layout.addWidget(self.files, 1)

        row = QHBoxLayout()
        add = QPushButton("Video's toevoegen")
        add.clicked.connect(self.add_files)
        up = QPushButton("Omhoog")
        up.clicked.connect(self.move_up)
        down = QPushButton("Omlaag")
        down.clicked.connect(self.move_down)
        remove = QPushButton("Verwijderen")
        remove.clicked.connect(self.remove_file)
        row.addWidget(add)
        row.addWidget(up)
        row.addWidget(down)
        row.addWidget(remove)
        layout.addLayout(row)

        output_row = QHBoxLayout()
        self.output = QLineEdit()
        self.output.setPlaceholderText("Doelbestand, bijvoorbeeld samengevoegd.mp4")
        output_row.addWidget(self.output, 1)
        choose = QPushButton("Opslaan als...")
        choose.clicked.connect(self.choose_output)
        output_row.addWidget(choose)
        layout.addLayout(output_row)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        merge = QPushButton("🔗 Video's samenvoegen")
        merge.clicked.connect(self.merge)
        close = QPushButton("Sluiten")
        close.clicked.connect(self.close)
        bottom.addWidget(merge)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self.setCentralWidget(root)
        self.setStyleSheet("""
            QWidget{background:#111318;color:#e8eaed;font-size:13px;}
            QPushButton{background:#292e36;border:1px solid #3c424c;border-radius:7px;padding:9px 14px;font-weight:600;color:#e8eaed;}
            QPushButton:hover{background:#353b45;}
            QLineEdit,QListWidget{background:#1e2127;border:1px solid #353a43;border-radius:6px;padding:7px;color:#e8eaed;}
            QListWidget::item{padding:8px;}
            QListWidget::item:selected{background:#315f9e;}
        """)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Kies video's", "", VIDEO_FILTER + ";;Alle bestanden (*)")
        for path in paths:
            if not any(self.files.item(i).data(Qt.ItemDataRole.UserRole) == path for i in range(self.files.count())):
                item = QListWidgetItem(Path(path).name)
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
                self.files.addItem(item)
        if self.files.count() and not self.output.text():
            first = Path(self.files.item(0).data(Qt.ItemDataRole.UserRole))
            self.output.setText(str(first.with_name(first.stem + "_merged.mp4")))

    def move_up(self):
        row = self.files.currentRow()
        if row > 0:
            item = self.files.takeItem(row)
            self.files.insertItem(row - 1, item)
            self.files.setCurrentRow(row - 1)

    def move_down(self):
        row = self.files.currentRow()
        if 0 <= row < self.files.count() - 1:
            item = self.files.takeItem(row)
            self.files.insertItem(row + 1, item)
            self.files.setCurrentRow(row + 1)

    def remove_file(self):
        row = self.files.currentRow()
        if row >= 0:
            self.files.takeItem(row)

    def choose_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Opslaan als", self.output.text(), "MP4 video (*.mp4);;MKV video (*.mkv);;Alle bestanden (*)")
        if path:
            self.output.setText(path)

    def merge(self):
        if self.files.count() < 2:
            QMessageBox.warning(self, "Video Merger", "Voeg minstens twee video's toe.")
            return
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            QMessageBox.critical(self, "FFmpeg ontbreekt", "FFmpeg kon niet worden gevonden.")
            return
        target = Path(self.output.text().strip()) if self.output.text().strip() else Path(self.files.item(0).data(Qt.ItemDataRole.UserRole)).with_name("samengevoegd.mp4")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, list_name = tempfile.mkstemp(suffix=".txt", prefix="video_concat_")
        os.close(fd)
        try:
            with open(list_name, "w", encoding="utf-8", newline="\n") as handle:
                for i in range(self.files.count()):
                    path = str(Path(self.files.item(i).data(Qt.ItemDataRole.UserRole)).resolve()).replace("'", "'\\''")
                    handle.write(f"file '{path}'\n")
            command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_name, "-c", "copy", "-y", str(target)]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if result.returncode == 0 and target.is_file():
                QMessageBox.information(self, "Video Merger", f"Video's succesvol samengevoegd:\n{target}")
            else:
                QMessageBox.critical(self, "Video Merger", "De video's konden niet zonder kwaliteitsverlies worden samengevoegd. Controleer of codec, resolutie, FPS en audio-indeling gelijk zijn.\n\n" + result.stderr.strip())
        except OSError as exc:
            QMessageBox.critical(self, "Video Merger", str(exc))
        finally:
            try:
                os.unlink(list_name)
            except OSError:
                pass


if __name__ == "__main__":
    app = QApplication([])
    window = VideoCutterWindow()
    window.show()
    app.exec()
