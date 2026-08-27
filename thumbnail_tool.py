from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, QObject
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from video_tools import VIDEO_EXTENSIONS, find_ffmpeg

VIDEO_FILTER = "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv *.mpeg *.mpg);;Alle bestanden (*)"


class ThumbnailWorker:
    def __init__(self, source, target, second, image_format, quality, width, mode,
                 index=1, total=1, tasks=None, interval_minutes=2, screenshot_count=15,
                 columns=5, start_minute=0):
        self.source = source
        self.target = target
        self.second = second
        self.image_format = image_format
        self.quality = quality
        self.width = width
        self.mode = mode
        self.index = index
        self.total = total
        self.tasks = tasks or []
        self.interval_minutes = interval_minutes
        self.screenshot_count = screenshot_count
        self.columns = columns
        self.start_minute = start_minute
        self.stop_event = threading.Event()
        self.process = None

    def request_stop(self):
        self.stop_event.set()
        if self.process:
            try:
                self.process.terminate()
            except OSError:
                pass

    def _creationflags(self):
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def _run(self, command, target=None):
        if self.stop_event.is_set():
            return False, "Gestopt door gebruiker."
        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creationflags(),
            )
            _, err = self.process.communicate()
        except OSError as exc:
            self.process = None
            return False, str(exc)
        process = self.process
        self.process = None
        if self.stop_event.is_set():
            if target:
                try:
                    Path(target).unlink(missing_ok=True)
                except OSError:
                    pass
            return False, "Gestopt door gebruiker."
        if process.returncode != 0:
            return False, (err or "").strip() or "FFmpeg gaf een onbekende fout."
        if target and (not Path(target).is_file() or Path(target).stat().st_size == 0):
            return False, "FFmpeg heeft geen geldige afbeelding aangemaakt."
        return True, ""

    def _extract_frames(self, source, folder):
        """Extract up to N frames in one FFmpeg pass.

        Using the fps filter means a video shorter than the requested grid simply
        produces fewer frames instead of generating a long list of EOF errors.
        """
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return False, [], "FFmpeg kon niet worden gevonden."

        interval_seconds = max(1, self.interval_minutes * 60)
        start_seconds = max(0, self.start_minute * 60)
        pattern = str(Path(folder) / "frame_%03d.jpg")
        vf = f"fps=1/{interval_seconds}"
        if self.width > 0:
            vf += f",scale={self.width}:-2"

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(start_seconds),
            "-i", source,
            "-map", "0:v:0",
            "-vf", vf,
            "-frames:v", str(self.screenshot_count),
            "-q:v", str(self.quality),
            "-y", pattern,
        ]
        ok, err = self._run(command)
        if not ok:
            return False, [], err

        frames = sorted(Path(folder).glob("frame_*.jpg"))
        if not frames:
            return False, [], "Geen screenshots konden uit de video worden gehaald."
        return True, [str(p) for p in frames], ""

    def _make_grid(self, frames, target):
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return False, "FFmpeg kon niet worden gevonden."
        if not frames:
            return False, "Geen screenshots beschikbaar voor het raster."

        rows = (len(frames) + self.columns - 1) // self.columns
        command = [ffmpeg, "-hide_banner", "-loglevel", "error"]
        for frame in frames:
            command += ["-i", frame]

        filters = []
        for i in range(len(frames)):
            filters.append(
                f"[{i}:v]scale=480:270:force_original_aspect_ratio=decrease,"
                f"pad=480:270:(ow-iw)/2:(oh-ih)/2:color=black,setpts=PTS-STARTPTS[v{i}]"
            )
        inputs = "".join(f"[v{i}]" for i in range(len(frames)))
        filters.append(f"{inputs}tile={self.columns}x{rows}:padding=2:margin=2")

        command += ["-filter_complex", ";".join(filters), "-frames:v", "1"]
        if self.image_format == "jpg":
            command += ["-q:v", str(self.quality)]
        else:
            command += ["-compression_level", "6"]
        command += ["-y", target]
        return self._run(command, target)

    def _make_one_grid(self, source, target):
        with tempfile.TemporaryDirectory(prefix="thumbgrid_") as folder:
            ok, frames, err = self._extract_frames(source, folder)
            if not ok:
                return False, err, 0
            if self.stop_event.is_set():
                return False, "Gestopt door gebruiker.", len(frames)
            ok, err = self._make_grid(frames, target)
            return ok, err, len(frames)

    def run(self, signals):
        if self.mode == "preview":
            ok, err, count = self._make_one_grid(self.source, self.target)
            signals.finished.emit("preview", ok, self.target if ok else "", err, count, count)
            return

        total = len(self.tasks)
        for index, (source, target) in enumerate(self.tasks, 1):
            if self.stop_event.is_set():
                break
            ok, err, count = self._make_one_grid(source, target)
            if ok:
                message = f"{Path(source).name} — {count} screenshots"
            else:
                message = Path(source).name
            signals.progress.emit(index, total, message, ok, err)
        signals.finished.emit("batch", not self.stop_event.is_set(), "", "", 0, total)


class _WorkerSignals(QObject):
    progress = Signal(int, int, str, bool, str)
    finished = Signal(str, bool, str, str, int, int)


class ThumbnailThread(QThread):
    progress = Signal(int, int, str, bool, str)
    result = Signal(str, bool, str, str, int, int)

    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self.worker = worker

    def run(self):
        signals = _WorkerSignals()
        signals.progress.connect(self.progress.emit)
        signals.finished.connect(self.result.emit)
        self.worker.run(signals)


class ThumbnailToolWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Thumbnail Tool")
        self.resize(1040, 760)
        self.selected_files = []
        self._preview_pixmap = None
        self._thread = None
        self._worker = None
        self._busy = False
        self._batch_success = 0
        self._batch_failed = []
        self._build_ui()
        self._apply_theme()

    def _spin(self, value, minimum, maximum, suffix=""):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        return spin

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("THUMBNAIL TOOL")
        title.setObjectName("title")
        title_box.addWidget(title)
        subtitle = QLabel("Maak één samengesteld raster met meerdere screenshots per video.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.count_label = QLabel("0 video's geselecteerd")
        self.count_label.setObjectName("count")
        header.addWidget(self.count_label, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(12)

        source = QWidget()
        source.setObjectName("panel")
        sl = QVBoxLayout(source)
        sl.setContentsMargins(16, 14, 16, 14)
        st = QLabel("1. Video's kiezen")
        st.setObjectName("panelTitle")
        sl.addWidget(st)
        buttons = QHBoxLayout()
        for text, fn in [
            ("Video's kiezen…", self.choose_files),
            ("Map kiezen…", self.choose_folder),
            ("Selectie wissen", self.clear_selection),
        ]:
            button = QPushButton(text)
            button.clicked.connect(fn)
            buttons.addWidget(button)
        buttons.addStretch()
        sl.addLayout(buttons)
        self.file_list = QLabel("Nog geen video's geselecteerd.")
        self.file_list.setObjectName("fileList")
        self.file_list.setWordWrap(True)
        self.file_list.setMinimumHeight(110)
        sl.addWidget(self.file_list)
        left.addWidget(source)

        settings = QWidget()
        settings.setObjectName("panel")
        form = QFormLayout(settings)
        form.setContentsMargins(16, 14, 16, 14)
        form.setVerticalSpacing(11)

        self.interval = self._spin(2, 1, 1440, " min")
        self.interval.setToolTip("Maak één screenshot per gekozen aantal minuten.")
        form.addRow("Interval:", self.interval)

        self.screenshot_count = self._spin(15, 1, 100, " stuks")
        self.screenshot_count.setToolTip("Aantal screenshots dat maximaal uit elke video wordt genomen.")
        form.addRow("Screenshots:", self.screenshot_count)

        self.columns = self._spin(5, 1, 20, " kolommen")
        self.columns.setToolTip("Aantal beelden naast elkaar in het raster. Het aantal rijen wordt automatisch berekend.")
        form.addRow("Kolommen:", self.columns)

        self.start = self._spin(0, 0, 1440, " min")
        self.start.setToolTip("Begin pas vanaf dit aantal minuten in de video.")
        form.addRow("Start:", self.start)

        self.format = QComboBox()
        self.format.addItem("JPG - compact", "jpg")
        self.format.addItem("PNG - maximale kwaliteit", "png")
        self.format.currentIndexChanged.connect(self._format_changed)
        form.addRow("Afbeelding:", self.format)

        self.quality = self._spin(2, 1, 31)
        self.quality.setToolTip("JPG: 1 is hoogste kwaliteit, 31 is laagste kwaliteit.")
        form.addRow("JPG kwaliteit:", self.quality)

        self.width = self._spin(0, 0, 7680, " px")
        self.width.setToolTip("0 = originele videobreedte behouden tijdens het maken van screenshots.")
        form.addRow("Breedte per beeld:", self.width)

        output_row = QHBoxLayout()
        self.output = QLineEdit()
        self.output.setPlaceholderText("Doelmap voor rasters")
        output_row.addWidget(self.output, 1)
        browse = QPushButton("Bladeren…")
        browse.clicked.connect(self.choose_output)
        output_row.addWidget(browse)
        form.addRow("Doelmap:", output_row)

        left.addWidget(settings)
        left.addStretch()
        content.addLayout(left, 1)

        preview_panel = QWidget()
        preview_panel.setObjectName("panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(16, 14, 16, 14)
        preview_title = QLabel("2. Voorbeeld raster")
        preview_title.setObjectName("panelTitle")
        preview_layout.addWidget(preview_title)
        self.preview = QLabel("Kies een video en klik op\n‘Voorbeeld maken’.")
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(440, 320)
        preview_layout.addWidget(self.preview, 1)
        self.preview_name = QLabel("")
        self.preview_name.setObjectName("previewName")
        self.preview_name.setWordWrap(True)
        preview_layout.addWidget(self.preview_name)
        self.preview_button = QPushButton("Voorbeeld maken")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self.make_preview)
        preview_layout.addWidget(self.preview_button)
        content.addWidget(preview_panel, 1)
        root.addLayout(content, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Klaar")
        root.addWidget(self.progress)

        bottom = QHBoxLayout()
        self.status = QLabel("Klaar.")
        self.status.setObjectName("status")
        bottom.addWidget(self.status, 1)
        self.close_button = QPushButton("Sluiten")
        self.close_button.clicked.connect(self.reject)
        bottom.addWidget(self.close_button)
        self.cancel_button = QPushButton("Stoppen")
        self.cancel_button.setObjectName("cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_operation)
        bottom.addWidget(self.cancel_button)
        self.generate_button = QPushButton("Rasters maken")
        self.generate_button.setObjectName("primary")
        self.generate_button.clicked.connect(self.generate_thumbnails)
        bottom.addWidget(self.generate_button)
        root.addLayout(bottom)

    def _apply_theme(self):
        self.setStyleSheet("""
        QDialog { background:#101216; color:#ffffff; }
        QLabel { color:#ffffff; }
        QLabel#title { color:#ffffff; font-size:30px; font-weight:900; }
        QLabel#subtitle { color:#ffffff; font-size:14px; }
        QLabel#count { color:#ffffff; background:#182235; border:1px solid #315f9e; border-radius:7px; padding:8px 12px; }
        QWidget#panel { background:#171a20; border:1px solid #303640; border-radius:10px; }
        QLabel#panelTitle { color:#ffffff; font-size:17px; font-weight:800; }
        QLabel#fileList { color:#ffffff; background:#12151a; border:1px solid #282d35; border-radius:7px; padding:10px; }
        QLabel#preview { color:#ffffff; background:#0c0f13; border:1px dashed #3b424d; border-radius:7px; }
        QLabel#previewName { color:#ffffff; }
        QLabel#status { color:#ffffff; }
        QLineEdit, QComboBox, QSpinBox { background:#1e2127; border:1px solid #353a43; border-radius:6px; padding:7px; color:#ffffff; selection-color:#ffffff; selection-background-color:#315f9e; }
        QComboBox QAbstractItemView { background:#1e2127; color:#ffffff; selection-background-color:#315f9e; selection-color:#ffffff; }
        QPushButton { background:#292e36; border:1px solid #3c424c; border-radius:7px; padding:9px 14px; color:#ffffff; font-weight:600; }
        QPushButton:hover { background:#353b45; }
        QPushButton:disabled { color:#ffffff; }
        QPushButton#primary { background:#315f9e; border-color:#4679bd; color:#ffffff; }
        QPushButton#secondary { background:#26384f; border-color:#3d638e; color:#ffffff; }
        QPushButton#cancel { background:#653636; border-color:#8b4a4a; color:#ffffff; }
        QProgressBar { background:#171a20; border:1px solid #303640; border-radius:6px; text-align:center; color:#ffffff; min-height:18px; }
        QProgressBar::chunk { background:#315f9e; border-radius:5px; }
        QToolTip { background:#1e2127; color:#ffffff; border:1px solid #4a515d; padding:5px; }
        """)

    def _format_changed(self):
        self.quality.setEnabled(self.format.currentData() == "jpg")

    def _set_busy(self, busy):
        self._busy = busy
        for control in (self.preview_button, self.generate_button, self.close_button):
            control.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)

    def choose_files(self):
        if self._busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Kies video's", "", VIDEO_FILTER)
        if paths:
            self._set_files(paths)

    def choose_folder(self):
        if self._busy:
            return
        folder = QFileDialog.getExistingDirectory(self, "Kies videomap")
        if not folder:
            return
        try:
            paths = [str(p) for p in sorted(Path(folder).iterdir()) if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
        except OSError as exc:
            QMessageBox.critical(self, "Thumbnail Tool", f"De videomap kon niet worden gelezen.\n\n{exc}")
            return
        self._set_files(paths)

    def _set_files(self, paths):
        self.selected_files = list(dict.fromkeys(paths))
        self.count_label.setText(f"{len(self.selected_files)} video's geselecteerd")
        names = [Path(p).name for p in self.selected_files]
        text = "\n".join(names[:12])
        if len(names) > 12:
            text += f"\n… en {len(names) - 12} meer."
        self.file_list.setText(text or "Nog geen video's geselecteerd.")
        self.status.setText("Selectie bijgewerkt.")

    def clear_selection(self):
        self.selected_files = []
        self.count_label.setText("0 video's geselecteerd")
        self.file_list.setText("Nog geen video's geselecteerd.")
        self.preview.clear()
        self.preview_name.clear()
        self.status.setText("Selectie gewist.")

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies doelmap")
        if folder:
            self.output.setText(folder)

    def _output_folder(self):
        folder = self.output.text().strip()
        if not folder and self.selected_files:
            folder = str(Path(self.selected_files[0]).parent / "thumbnails")
        return folder

    def _tasks(self):
        folder = self._output_folder()
        Path(folder).mkdir(parents=True, exist_ok=True)
        ext = self.format.currentData()
        return [(src, str(Path(folder) / f"{Path(src).stem}_grid.{ext}")) for src in self.selected_files]

    def _start(self, worker):
        self._worker = worker
        self._thread = ThumbnailThread(worker, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.result.connect(self._on_result)
        self._set_busy(True)
        self._thread.start()

    def make_preview(self):
        if self._busy or not self.selected_files:
            return
        src = self.selected_files[0]
        ext = self.format.currentData()
        target = str(Path(tempfile.gettempdir()) / f"thumbnail_preview.{ext}")
        worker = ThumbnailWorker(
            src, target, 0, ext, self.quality.value(), self.width.value(), "preview",
            interval_minutes=self.interval.value(), screenshot_count=self.screenshot_count.value(),
            columns=self.columns.value(), start_minute=self.start.value(),
        )
        self.status.setText("Rastervoorbeeld wordt gemaakt…")
        self._start(worker)

    def generate_thumbnails(self):
        if self._busy:
            return
        if not self.selected_files:
            QMessageBox.information(self, "Thumbnail Tool", "Kies eerst minstens één video.")
            return
        try:
            tasks = self._tasks()
        except OSError as exc:
            QMessageBox.critical(self, "Thumbnail Tool", f"Doelmap kon niet worden aangemaakt.\n\n{exc}")
            return
        self._batch_success = 0
        self._batch_failed = []
        self.progress.setRange(0, len(tasks))
        self.progress.setValue(0)
        worker = ThumbnailWorker(
            "", "", 0, self.format.currentData(), self.quality.value(), self.width.value(), "batch",
            tasks=tasks, interval_minutes=self.interval.value(), screenshot_count=self.screenshot_count.value(),
            columns=self.columns.value(), start_minute=self.start.value(),
        )
        self.status.setText("Rasters worden gemaakt…")
        self._start(worker)

    def cancel_operation(self):
        if self._worker:
            self._worker.request_stop()
            self.status.setText("Stoppen…")

    def _on_progress(self, index, total, name, ok, error):
        self.progress.setValue(index)
        self.progress.setFormat(f"{index}/{total}")
        self.status.setText(("Klaar: " if ok else "Fout: ") + name + (f" — {error}" if error else ""))
        if ok:
            self._batch_success += 1
        else:
            self._batch_failed.append((name, error))

    def _on_result(self, mode, ok, target, error, done, total):
        self._set_busy(False)
        if mode == "preview":
            if ok:
                pix = QPixmap(target)
                self._preview_pixmap = pix
                self._update_preview()
                self.preview_name.setText(
                    f"{self.selected_files[0]} — {done} beelden, elke {self.interval.value()} min"
                )
                self.status.setText("Voorbeeld klaar.")
            else:
                self.status.setText("Voorbeeld mislukt: " + error)
        else:
            self.progress.setValue(total)
            message = f"Klaar: {self._batch_success} raster(s) gemaakt"
            if self._batch_failed:
                message += f", {len(self._batch_failed)} mislukt"
            self.status.setText(message + ".")

    def _update_preview(self):
        if not self._preview_pixmap or self._preview_pixmap.isNull():
            return
        self.preview.setPixmap(
            self._preview_pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_preview()

    def reject(self):
        if self._busy:
            QMessageBox.information(self, "Thumbnail Tool", "Stop de huidige bewerking eerst.")
            return
        super().reject()


def open_thumbnail_tool(parent=None):
    return ThumbnailToolWindow(parent)


def main():
    app = QApplication.instance() or QApplication([])
    win = ThumbnailToolWindow()
    win.exec()


if __name__ == "__main__":
    main()
