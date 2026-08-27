from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from video_tools import VIDEO_EXTENSIONS, find_ffmpeg

VIDEO_FILTER = (
    "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts "
    "*.wmv *.flv *.mpeg *.mpg);;Alle bestanden (*)"
)


class ThumbnailWorker:
    """Background FFmpeg worker.

    All FFmpeg work runs outside the Qt GUI thread. The worker communicates
    through Qt signals and never touches widgets directly.
    """

    def __init__(self, source, target, second, image_format, quality, width, mode, index=1, total=1, tasks=None):
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
        self.stop_event = threading.Event()
        self.process: subprocess.Popen | None = None

    def request_stop(self):
        self.stop_event.set()
        if self.process is not None:
            try:
                self.process.terminate()
            except OSError:
                pass

    def _creationflags(self) -> int:
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def _command(self, source: str, target: str) -> list[str]:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg kon niet worden gevonden.")

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(self.second),
            "-i",
            source,
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
        ]

        if self.width > 0:
            command += ["-vf", f"scale={self.width}:-2"]

        if self.image_format == "jpg":
            command += ["-q:v", str(self.quality)]
        else:
            command += ["-compression_level", "6"]

        command += ["-y", target]
        return command

    def _run_one(self, source: str, target: str) -> tuple[bool, str]:
        if self.stop_event.is_set():
            return False, "Gestopt door gebruiker."

        try:
            command = self._command(source, target)
        except RuntimeError as exc:
            return False, str(exc)

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
        except OSError as exc:
            self.process = None
            return False, str(exc)

        stderr_text = ""
        try:
            while True:
                if self.stop_event.is_set():
                    try:
                        self.process.terminate()
                    except OSError:
                        pass
                try:
                    _, stderr_text = self.process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            process = self.process
            self.process = None

        if self.stop_event.is_set():
            try:
                Path(target).unlink(missing_ok=True)
            except OSError:
                pass
            return False, "Gestopt door gebruiker."

        if process is None or process.returncode != 0:
            return False, (stderr_text or "").strip() or "FFmpeg gaf een onbekende fout."

        try:
            valid = Path(target).is_file() and Path(target).stat().st_size > 0
        except OSError:
            valid = False

        return (True, "") if valid else (False, "FFmpeg heeft geen geldige afbeelding aangemaakt.")

    def run(self, signals):
        if self.mode == "preview":
            ok, error = self._run_one(self.source, self.target)
            signals.finished.emit("preview", ok, self.target, error, 1, 1)
            return

        total = len(self.tasks)
        for index, (source, target) in enumerate(self.tasks, 1):
            if self.stop_event.is_set():
                break
            ok, error = self._run_one(source, target)
            signals.progress.emit(index, total, Path(source).name, ok, error)
            if self.stop_event.is_set():
                break

        signals.finished.emit("batch", not self.stop_event.is_set(), "", "", 0, total)


from PySide6.QtCore import QObject


class _WorkerSignals(QObject):
    progress = Signal(int, int, str, bool, str)
    finished = Signal(str, bool, str, str, int, int)


class ThumbnailThread(QThread):
    progress = Signal(int, int, str, bool, str)
    finished = Signal(str, bool, str, str, int, int)

    def __init__(self, worker: ThumbnailWorker, parent=None):
        super().__init__(parent)
        self.worker = worker

    def run(self):
        signals = _WorkerSignals()
        signals.progress.connect(self.progress.emit)
        signals.finished.connect(self.finished.emit)
        self.worker.run(signals)


class ThumbnailToolWindow(QDialog):
    """Full thumbnail generator used by the Video Suite.

    The original video is never modified. Preview files are stored in the
    system temporary directory; final thumbnails are written to the chosen
    destination. FFmpeg processing runs in a background thread.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Thumbnail Tool")
        self.resize(1040, 740)
        self.selected_files: list[str] = []
        self._preview_pixmap: QPixmap | None = None
        self._thread: ThumbnailThread | None = None
        self._worker: ThumbnailWorker | None = None
        self._busy = False
        self._batch_success = 0
        self._batch_failed: list[tuple[str, str]] = []
        self._batch_stopped = False
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("THUMBNAIL TOOL")
        title.setObjectName("title")
        title_box.addWidget(title)
        subtitle = QLabel(
            "Maak één of meerdere thumbnails uit video's. Het originele "
            "videobestand blijft volledig onaangetast."
        )
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

        source_panel = QWidget()
        source_panel.setObjectName("panel")
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(16, 14, 16, 14)
        source_layout.setSpacing(10)
        source_title = QLabel("1. Video's kiezen")
        source_title.setObjectName("panelTitle")
        source_layout.addWidget(source_title)
        buttons = QHBoxLayout()
        choose = QPushButton("Video's kiezen…")
        choose.clicked.connect(self.choose_files)
        buttons.addWidget(choose)
        folder = QPushButton("Map kiezen…")
        folder.clicked.connect(self.choose_folder)
        buttons.addWidget(folder)
        clear = QPushButton("Selectie wissen")
        clear.clicked.connect(self.clear_selection)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        source_layout.addLayout(buttons)
        self.file_list = QLabel("Nog geen video's geselecteerd.")
        self.file_list.setObjectName("fileList")
        self.file_list.setWordWrap(True)
        self.file_list.setMinimumHeight(110)
        source_layout.addWidget(self.file_list)
        left.addWidget(source_panel)

        settings = QWidget()
        settings.setObjectName("panel")
        form = QFormLayout(settings)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(11)

        self.second = QSpinBox()
        self.second.setRange(0, 86400)
        self.second.setValue(5)
        self.second.setSuffix(" sec")
        self.second.setToolTip("Het moment in seconden waarvan de thumbnail wordt genomen.")
        form.addRow("Moment:", self.second)

        self.format = QComboBox()
        self.format.addItem("JPG - compact", "jpg")
        self.format.addItem("PNG - maximale kwaliteit", "png")
        self.format.currentIndexChanged.connect(self._format_changed)
        form.addRow("Afbeelding:", self.format)

        self.quality = QSpinBox()
        self.quality.setRange(1, 31)
        self.quality.setValue(2)
        self.quality.setToolTip("JPG: 1 is hoogste kwaliteit, 31 is laagste kwaliteit.")
        form.addRow("JPG kwaliteit:", self.quality)

        self.width = QSpinBox()
        self.width.setRange(0, 7680)
        self.width.setValue(0)
        self.width.setSuffix(" px")
        self.width.setToolTip("0 = originele videobreedte behouden.")
        form.addRow("Breedte:", self.width)

        output_row = QHBoxLayout()
        self.output = QLineEdit()
        self.output.setPlaceholderText("Doelmap voor thumbnails")
        output_row.addWidget(self.output, 1)
        browse = QPushButton("Bladeren…")
        browse.clicked.connect(self.choose_output)
        output_row.addWidget(browse)
        form.addRow("Doelmap:", output_row)

        left.addWidget(settings)
        left.addStretch(1)
        content.addLayout(left, 1)

        preview_panel = QWidget()
        preview_panel.setObjectName("panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(16, 14, 16, 14)
        preview_layout.setSpacing(10)
        preview_title = QLabel("2. Voorbeeld")
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

        self.generate_button = QPushButton("Thumbnails maken")
        self.generate_button.setObjectName("primary")
        self.generate_button.clicked.connect(self.generate_thumbnails)
        bottom.addWidget(self.generate_button)
        root.addLayout(bottom)

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog { background:#101216; color:#e8eaed; }
            QLabel#title { color:#fff; font-size:30px; font-weight:900; }
            QLabel#subtitle { color:#8f96a3; font-size:14px; }
            QLabel#count { color:#b9c8dc; background:#182235; border:1px solid #315f9e; border-radius:7px; padding:8px 12px; }
            QWidget#panel { background:#171a20; border:1px solid #303640; border-radius:10px; }
            QLabel#panelTitle { color:#fff; font-size:17px; font-weight:800; }
            QLabel#fileList { color:#9da5b2; background:#12151a; border:1px solid #282d35; border-radius:7px; padding:10px; }
            QLabel#preview { color:#737c89; background:#0c0f13; border:1px dashed #3b424d; border-radius:7px; }
            QLabel#previewName { color:#9da5b2; }
            QLabel#status { color:#aeb5c0; }
            QLineEdit,QComboBox,QSpinBox { background:#1e2127; border:1px solid #353a43; border-radius:6px; padding:7px; color:#e8eaed; }
            QPushButton { background:#292e36; border:1px solid #3c424c; border-radius:7px; padding:9px 14px; color:#e8eaed; font-weight:600; }
            QPushButton:hover { background:#353b45; }
            QPushButton#primary { background:#315f9e; border-color:#4679bd; color:#fff; }
            QPushButton#primary:hover { background:#3b70b6; }
            QPushButton#secondary { background:#26384f; border-color:#3d638e; color:#fff; }
            QPushButton#cancel { background:#653636; border-color:#8b4a4a; color:#fff; }
            QProgressBar { background:#171a20; border:1px solid #303640; border-radius:6px; text-align:center; color:#e8eaed; min-height:18px; }
        """)

    def _format_changed(self):
        is_jpg = self.format.currentData() == "jpg"
        self.quality.setEnabled(is_jpg)
        if self.selected_files and not self._busy:
            self.status.setText("Instellingen gewijzigd. Klik op ‘Voorbeeld maken’.")

    def _set_busy(self, busy: bool):
        self._busy = busy
        controls = [
            self.preview_button,
            self.generate_button,
            self.close_button,
            self.cancel_button,
        ]
        for control in controls:
            control.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setVisible(busy)

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
            paths = [
                str(p)
                for p in sorted(Path(folder).iterdir())
                if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
            ]
        except OSError as exc:
            QMessageBox.critical(self, "Thumbnail Tool", f"De videomap kon niet worden gelezen.\n\n{exc}")
            return
        if not paths:
            QMessageBox.information(self, "Thumbnail Tool", "Geen ondersteunde video's in deze map gevonden.")
            return
        self._set_files(paths)

    def _set_files(self, paths: list[str]):
        unique = []
        seen = set()
        for path in paths:
            try:
                normalized = str(Path(path).resolve())
            except OSError:
                continue
            if normalized not in seen and Path(normalized).is_file():
                seen.add(normalized)
                unique.append(normalized)
        self.selected_files = unique
        self._refresh_file_list()
        if self.selected_files and not self.output.text().strip():
            self.output.setText(str(Path(self.selected_files[0]).parent))
        self.progress.setValue(0)
        self.progress.setFormat("Klaar")
        self.make_preview()

    def _refresh_file_list(self):
        count = len(self.selected_files)
        noun = "video" if count == 1 else "video's"
        self.count_label.setText(f"{count:,} {noun} geselecteerd")
        if not self.selected_files:
            self.file_list.setText("Nog geen video's geselecteerd.")
            return
        lines = [Path(p).name for p in self.selected_files[:10]]
        if count > 10:
            lines.append(f"… en nog {count - 10:,} video's")
        self.file_list.setText("\n".join(lines))

    def clear_selection(self):
        if self._busy:
            return
        self.selected_files.clear()
        self._refresh_file_list()
        self.preview.clear()
        self.preview.setText("Kies een video en klik op\n‘Voorbeeld maken’.")
        self.preview_name.clear()
        self._preview_pixmap = None
        self.progress.setValue(0)
        self.progress.setFormat("Klaar")
        self.status.setText("Selectie gewist.")

    def choose_output(self):
        if self._busy:
            return
        folder = QFileDialog.getExistingDirectory(self, "Kies doelmap")
        if folder:
            self.output.setText(folder)

    def _unique_target(self, folder: Path, stem: str, suffix: str, reserved: set[Path] | None = None) -> Path:
        reserved = reserved or set()
        target = folder / f"{stem}_thumbnail{suffix}"
        index = 2
        while target.exists() or target in reserved:
            target = folder / f"{stem}_thumbnail_{index}{suffix}"
            index += 1
        return target

    def make_preview(self):
        if self._busy:
            return
        if not self.selected_files:
            self.preview.clear()
            self.preview.setText("Kies eerst minstens één video.")
            self.preview_name.clear()
            return

        source = self.selected_files[0]
        suffix = ".jpg" if self.format.currentData() == "jpg" else ".png"
        temp_dir = Path(tempfile.gettempdir()) / "VideoAudioScanner"
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.preview.setText("Voorbeeld kon niet worden voorbereid.")
            self.preview_name.setText(str(exc))
            return

        target = temp_dir / f"thumbnail_preview_{os.getpid()}{suffix}"
        self.status.setText(f"Voorbeeld maken: {Path(source).name}")
        self.progress.setValue(0)
        self.progress.setFormat("Voorbeeld maken…")
        self._start_worker(
            ThumbnailWorker(
                source=source,
                target=str(target),
                second=self.second.value(),
                image_format=self.format.currentData(),
                quality=self.quality.value(),
                width=self.width.value(),
                mode="preview",
            )
        )

    def _start_worker(self, worker: ThumbnailWorker):
        self._worker = worker
        self._thread = ThumbnailThread(worker, self)
        self._thread.progress.connect(self._worker_progress)
        self._thread.finished.connect(self._worker_finished)
        self._thread.finished.connect(self._thread_finished)
        self._set_busy(True)
        self._thread.start()

    def _worker_progress(self, index, total, name, ok, error):
        if total:
            self.progress.setValue(int(index * 100 / total))
        self.progress.setFormat(f"{index}/{total} • {name}")
        if ok:
            self._batch_success += 1
            self.status.setText(f"Thumbnail {index}/{total} klaar: {name}")
        else:
            self._batch_failed.append((name, error))
            self.status.setText(f"Thumbnail {index}/{total} mislukt: {name}")

    def _worker_finished(self, mode, ok, target, error, _index, total):
        if mode == "preview":
            if ok:
                pixmap = QPixmap(target)
                if pixmap.isNull():
                    self.preview.clear()
                    self.preview.setText("Afbeelding kon niet worden geladen.")
                    self.preview_name.setText(
                        "FFmpeg maakte een bestand, maar Qt kon de afbeelding niet openen."
                    )
                    self.status.setText("Voorbeeld mislukt.")
                else:
                    self._preview_pixmap = pixmap
                    self._show_preview_pixmap()
                    source = self.selected_files[0]
                    self.preview_name.setText(
                        f"Voorbeeld: {Path(source).name} • {self.second.value()} sec • "
                        f"{pixmap.width()}×{pixmap.height()} px"
                    )
                    self.status.setText(
                        "Voorbeeld klaar. Pas het moment aan en maak opnieuw een voorbeeld "
                        "voor een ander frame."
                    )
                    self.progress.setValue(100)
                    self.progress.setFormat("Voorbeeld klaar")
            else:
                self.preview.clear()
                self.preview.setText("Voorbeeld kon niet worden gemaakt.")
                self.preview_name.setText(error)
                self.status.setText("Voorbeeld mislukt.")
                self.progress.setFormat("Voorbeeld mislukt")
        else:
            worker = self._worker
            self._batch_stopped = worker.stop_event.is_set() if worker is not None else self._batch_stopped
            if self._batch_stopped:
                self.status.setText(
                    f"Gestopt: {self._batch_success:,} gelukt, "
                    f"{len(self._batch_failed):,} mislukt."
                )
                self.progress.setFormat("Gestopt")
            elif not self._batch_failed:
                self.status.setText(f"Klaar: {self._batch_success:,} thumbnail(s) gemaakt.")
                self.progress.setValue(100)
                self.progress.setFormat(f"{self._batch_success:,} thumbnail(s) klaar")
            else:
                self.status.setText(
                    f"Klaar met fouten: {self._batch_success:,} gelukt, "
                    f"{len(self._batch_failed):,} mislukt."
                )
                self.progress.setValue(100)
                self.progress.setFormat(
                    f"{self._batch_success:,} gelukt / {len(self._batch_failed):,} mislukt"
                )

            self._show_batch_result()

    def _thread_finished(self):
        thread = self._thread
        self._thread = None
        self._worker = None
        self._set_busy(False)
        if thread is not None:
            thread.deleteLater()

    def _show_batch_result(self):
        if self._batch_stopped:
            QMessageBox.information(
                self,
                "Thumbnail Tool",
                f"De verwerking is gestopt.\n\n"
                f"Gelukt: {self._batch_success:,}\n"
                f"Mislukt: {len(self._batch_failed):,}",
            )
            return

        if not self._batch_failed:
            output = self.output.text().strip() or str(Path(self.selected_files[0]).parent)
            QMessageBox.information(
                self,
                "Thumbnail Tool",
                f"Klaar.\n\n{self._batch_success:,} thumbnail(s) gemaakt.\n\n"
                f"Doelmap:\n{output}",
            )
            return

        lines = [
            f"Gelukt: {self._batch_success:,}",
            f"Mislukt: {len(self._batch_failed):,}",
            "",
        ]
        for name, error in self._batch_failed[:8]:
            lines.extend([name, error, ""])
        if len(self._batch_failed) > 8:
            lines.append(f"… en nog {len(self._batch_failed) - 8:,} fouten.")
        QMessageBox.warning(self, "Thumbnail Tool", "\n".join(lines))

    def generate_thumbnails(self):
        if self._busy:
            return
        if not self.selected_files:
            QMessageBox.warning(self, "Thumbnail Tool", "Kies eerst één of meerdere video's.")
            return

        output = (
            Path(self.output.text().strip())
            if self.output.text().strip()
            else Path(self.selected_files[0]).parent
        )
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Thumbnail Tool",
                f"Doelmap kon niet worden aangemaakt.\n\n{exc}",
            )
            return

        suffix = ".jpg" if self.format.currentData() == "jpg" else ".png"
        reserved: set[Path] = set()
        tasks: list[tuple[str, str]] = []
        for source in self.selected_files:
            target = self._unique_target(output, Path(source).stem, suffix, reserved)
            reserved.add(target)
            tasks.append((source, str(target)))

        self._batch_success = 0
        self._batch_failed = []
        self._batch_stopped = False
        self.progress.setValue(0)
        self.progress.setFormat(f"0/{len(tasks)}")
        self.status.setText(f"Starten: {len(tasks):,} thumbnail(s)…")

        self._start_worker(
            ThumbnailWorker(
                source="",
                target="",
                second=self.second.value(),
                image_format=self.format.currentData(),
                quality=self.quality.value(),
                width=self.width.value(),
                mode="batch",
                tasks=tasks,
            )
        )

    def cancel_operation(self):
        if self._busy and self._worker is not None:
            self.status.setText("Stoppen… huidige FFmpeg-bewerking wordt beëindigd.")
            self.cancel_button.setEnabled(False)
            self._worker.request_stop()

    def _show_preview_pixmap(self):
        if self._preview_pixmap is not None:
            self.preview.setPixmap(
                self._preview_pixmap.scaled(
                    self.preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show_preview_pixmap()

    def reject(self):
        if self._busy:
            QMessageBox.information(
                self,
                "Thumbnail Tool",
                "Stop eerst de huidige verwerking voordat je het venster sluit.",
            )
            return
        super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            QMessageBox.information(
                self,
                "Thumbnail Tool",
                "Stop eerst de huidige verwerking voordat je het venster sluit.",
            )
            return
        event.accept()


def main():
    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication([])
    window = ThumbnailToolWindow()
    window.show()
    return app.exec() if owns_app else 0


if __name__ == "__main__":
    raise SystemExit(main())
