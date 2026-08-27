from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, QObject
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from video_tools import VIDEO_EXTENSIONS, find_ffmpeg

VIDEO_FILTER = "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv *.mpeg *.mpg);;Alle bestanden (*)"

try:
    from PIL import Image, ImageOps, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class ThumbnailWorker:
    """Maak per video één contact sheet met screenshots gelijkmatig verdeeld over de video."""

    CELL_W = 480
    CELL_H = 270

    def __init__(self, source, target, image_format, quality, width, mode,
                 tasks=None, screenshot_count=20, columns=5):
        self.source = source
        self.target = target
        self.image_format = image_format
        self.quality = quality
        self.width = width
        self.mode = mode
        self.tasks = tasks or []
        self.screenshot_count = max(1, int(screenshot_count))
        self.columns = max(1, int(columns))
        self.stop_event = __import__("threading").Event()
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
            return False, (err or "FFmpeg gaf een onbekende fout.").strip()
        if target and (not Path(target).is_file() or Path(target).stat().st_size == 0):
            return False, "FFmpeg heeft geen geldige afbeelding aangemaakt."
        return True, ""

    def _ffprobe(self):
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return None
        candidate = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if candidate.exists():
            return str(candidate)
        # PATH fallback
        return shutil.which("ffprobe")

    def _duration(self, source):
        ffprobe = self._ffprobe()
        if not ffprobe:
            return None, "FFprobe kon niet worden gevonden naast FFmpeg."
        cmd = [
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", source,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creationflags(),
                check=False,
            )
            if result.returncode != 0:
                return None, (result.stderr or "FFprobe gaf een fout.").strip()
            duration = float(result.stdout.strip())
            if duration <= 0:
                return None, "De videolengte kon niet worden bepaald."
            return duration, ""
        except (OSError, ValueError) as exc:
            return None, str(exc)

    def _extract_frame(self, ffmpeg, source, timestamp, frame_path):
        # Eén simpel FFmpeg-proces per frame. Geen filter_complex, tile of xstack.
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-ss", f"{timestamp:.3f}", "-i", source,
            "-frames:v", "1",
            "-vf", f"scale={self.CELL_W}:{self.CELL_H}:force_original_aspect_ratio=decrease,"
                    f"pad={self.CELL_W}:{self.CELL_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1",
            "-frames:v", "1", "-q:v", "2", "-y", str(frame_path),
        ]
        return self._run(cmd, frame_path)

    def _make_grid(self, source, target):
        if not PIL_AVAILABLE:
            return False, "Pillow ontbreekt. Installeer met: python -m pip install Pillow"
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return False, "FFmpeg kon niet worden gevonden."
        duration, error = self._duration(source)
        if duration is None:
            return False, error

        count = self.screenshot_count
        columns = min(self.columns, count)
        rows = (count + columns - 1) // columns

        # Gebruik het midden van elk segment. Daardoor wordt de volledige video
        # automatisch en gelijkmatig verdeeld zonder handmatig interval.
        timestamps = [duration * (i + 0.5) / count for i in range(count)]
        temp_dir = Path(tempfile.mkdtemp(prefix="vas_thumb_"))
        frames = []
        try:
            for index, timestamp in enumerate(timestamps):
                if self.stop_event.is_set():
                    return False, "Gestopt door gebruiker."
                frame = temp_dir / f"frame_{index:03d}.jpg"
                ok, err = self._extract_frame(ffmpeg, source, timestamp, frame)
                if not ok:
                    return False, f"Screenshot {index + 1}/{count} mislukt: {err}"
                frames.append(frame)

            if self.stop_event.is_set():
                return False, "Gestopt door gebruiker."

            sheet = Image.new("RGB", (columns * self.CELL_W, rows * self.CELL_H), "black")
            for index, frame_path in enumerate(frames):
                if self.stop_event.is_set():
                    return False, "Gestopt door gebruiker."
                with Image.open(frame_path) as image:
                    image = image.convert("RGB")
                    x = (index % columns) * self.CELL_W
                    y = (index // columns) * self.CELL_H
                    sheet.paste(image, (x, y))

            if self.width > 0 and sheet.width != self.width:
                new_height = max(1, round(sheet.height * self.width / sheet.width))
                sheet = sheet.resize((int(self.width), new_height), Image.Resampling.LANCZOS)

            output = Path(target)
            output.parent.mkdir(parents=True, exist_ok=True)
            if self.image_format == "jpg":
                sheet.save(output, "JPEG", quality=max(1, min(100, 100 - (self.quality - 1) * 3)), optimize=True)
            else:
                sheet.save(output, "PNG", compress_level=6)
            sheet.close()
            return True, ""
        except Exception as exc:
            return False, f"Raster maken mislukt: {exc}"
        finally:
            for frame in frames:
                try:
                    frame.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                temp_dir.rmdir()
            except OSError:
                pass

    def run(self, signals):
        if self.mode == "preview":
            ok, err = self._make_grid(self.source, self.target)
            signals.finished.emit("preview", ok, self.target, err, self.screenshot_count if ok else 0, self.screenshot_count)
            return
        total = len(self.tasks)
        for index, (source, target) in enumerate(self.tasks, 1):
            if self.stop_event.is_set():
                break
            ok, err = self._make_grid(source, target)
            signals.progress.emit(index, total, Path(source).name, ok, err)
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
        return spin

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)
        header = QHBoxLayout()
        text_box = QVBoxLayout()
        title = QLabel("THUMBNAIL TOOL")
        title.setObjectName("title")
        text_box.addWidget(title)
        subtitle = QLabel("Maak automatisch één samengesteld raster uit screenshots verspreid over de volledige video.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        text_box.addWidget(subtitle)
        header.addLayout(text_box, 1)
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
        for text, fn in [("Video's kiezen…", self.choose_files), ("Map kiezen…", self.choose_folder), ("Selectie wissen", self.clear_selection)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            buttons.addWidget(b)
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
        self.screenshot_count = self._spin(20, 1, 100, " stuks")
        self.screenshot_count.setToolTip("Aantal screenshots. De tool verdeelt ze automatisch over de hele video.")
        form.addRow("Screenshots:", self.screenshot_count)
        self.columns = self._spin(5, 1, 20, " kolommen")
        self.columns.setToolTip("Aantal kolommen in het raster.")
        form.addRow("Kolommen:", self.columns)
        self.format = QComboBox()
        self.format.addItem("JPG - compact", "jpg")
        self.format.addItem("PNG - maximale kwaliteit", "png")
        self.format.currentIndexChanged.connect(self._format_changed)
        form.addRow("Afbeelding:", self.format)
        self.quality = self._spin(2, 1, 31)
        form.addRow("JPG kwaliteit:", self.quality)
        self.width = self._spin(0, 0, 7680, " px")
        self.width.setToolTip("0 = automatische rasterbreedte.")
        form.addRow("Rasterbreedte:", self.width)
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
        pl = QVBoxLayout(preview_panel)
        pl.setContentsMargins(16, 14, 16, 14)
        pt = QLabel("2. Voorbeeld raster")
        pt.setObjectName("panelTitle")
        pl.addWidget(pt)
        self.preview = QLabel("Kies een video en klik op\n‘Voorbeeld maken’.")
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(440, 320)
        pl.addWidget(self.preview, 1)
        self.preview_name = QLabel("")
        self.preview_name.setObjectName("previewName")
        self.preview_name.setWordWrap(True)
        pl.addWidget(self.preview_name)
        self.preview_button = QPushButton("Voorbeeld maken")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self.make_preview)
        pl.addWidget(self.preview_button)
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
        QDialog{background:#101216;color:#fff} QLabel{color:#fff} QLabel#title{color:#fff;font-size:30px;font-weight:900}
        QLabel#subtitle{color:#fff;font-size:14px} QLabel#count{color:#fff;background:#182235;border:1px solid #315f9e;border-radius:7px;padding:8px 12px}
        QWidget#panel{background:#171a20;border:1px solid #303640;border-radius:10px} QLabel#panelTitle{color:#fff;font-size:17px;font-weight:800}
        QLabel#fileList{color:#fff;background:#12151a;border:1px solid #282d35;border-radius:7px;padding:10px} QLabel#preview{color:#fff;background:#0c0f13;border:1px dashed #3b424d;border-radius:7px}
        QLabel#previewName{color:#fff} QLabel#status{color:#fff} QLineEdit,QComboBox,QSpinBox{background:#1e2127;border:1px solid #353a43;border-radius:6px;padding:7px;color:#fff;selection-color:#fff;selection-background-color:#315f9e}
        QComboBox QAbstractItemView{background:#1e2127;color:#fff;selection-background-color:#315f9e;selection-color:#fff} QPushButton{background:#292e36;border:1px solid #3c424c;border-radius:7px;padding:9px 14px;color:#fff;font-weight:600}
        QPushButton:hover{background:#353b45} QPushButton#primary{background:#315f9e;border-color:#4679bd;color:#fff} QPushButton#secondary{background:#26384f;border-color:#3d638e;color:#fff}
        QPushButton#cancel{background:#653636;border-color:#8b4a4a;color:#fff} QProgressBar{background:#171a20;border:1px solid #303640;border-radius:6px;text-align:center;color:#fff;min-height:18px}
        QProgressBar::chunk{background:#315f9e;border-radius:5px} QToolTip{background:#1e2127;color:#fff;border:1px solid #4a515d;padding:5px}
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
        self.file_list.setText("\n".join(names[:12]) + ((f"\n… en {len(names) - 12} meer." if len(names) > 12 else "")))
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
        return [(src, str(Path(folder) / (Path(src).stem + f"_grid.{ext}"))) for src in self.selected_files]

    def _start(self, worker):
        self._worker = worker
        self._thread = ThumbnailThread(worker, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.result.connect(self._on_result)
        self._set_busy(True)
        self._thread.start()

    def make_preview(self):
        if self._busy:
            return
        if not self.selected_files:
            self.status.setText("Kies eerst een video.")
            return
        if not PIL_AVAILABLE:
            self.status.setText("Pillow ontbreekt. Installeer met: python -m pip install Pillow")
            return
        src = self.selected_files[0]
        ext = self.format.currentData()
        target = str(Path(tempfile.gettempdir()) / f"thumbnail_preview.{ext}")
        worker = ThumbnailWorker(
            src, target, ext, self.quality.value(), self.width.value(), "preview",
            screenshot_count=self.screenshot_count.value(), columns=self.columns.value()
        )
        self.status.setText("Rastervoorbeeld wordt gemaakt…")
        self._start(worker)

    def generate_thumbnails(self):
        if self._busy:
            return
        if not self.selected_files:
            QMessageBox.information(self, "Thumbnail Tool", "Kies eerst minstens één video.")
            return
        if not PIL_AVAILABLE:
            QMessageBox.critical(self, "Thumbnail Tool", "Pillow ontbreekt. Installeer met: python -m pip install Pillow")
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
            "", "", self.format.currentData(), self.quality.value(), self.width.value(), "batch",
            tasks=tasks, screenshot_count=self.screenshot_count.value(), columns=self.columns.value()
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
                    f"{Path(self.selected_files[0]).name} — {self.screenshot_count.value()} beelden, automatisch verdeeld over de hele video"
                )
                self.status.setText("Voorbeeld klaar.")
            else:
                self.status.setText("Voorbeeld mislukt: " + error)
        else:
            self.progress.setValue(total)
            self.status.setText(
                f"Klaar: {self._batch_success} raster(s) gemaakt" +
                (f", {len(self._batch_failed)} mislukt" if self._batch_failed else "") + "."
            )

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
