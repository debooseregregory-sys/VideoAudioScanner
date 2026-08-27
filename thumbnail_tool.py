from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from video_tools import VIDEO_EXTENSIONS, find_ffmpeg

VIDEO_FILTER = (
    "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts "
    "*.wmv *.flv *.mpeg *.mpg);;Alle bestanden (*)"
)


class ThumbnailToolWindow(QDialog):
    """Thumbnail generator used by the Video Suite.

    The source video is never modified. Preview files are created only in the
    system temporary directory; final images are written to the destination.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Thumbnail Tool")
        self.resize(1040, 740)
        self.selected_files: list[str] = []
        self._preview_pixmap: QPixmap | None = None
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
        subtitle = QLabel("Maak één of meerdere thumbnails uit video's. Het originele videobestand blijft volledig onaangetast.")
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
        preview_button = QPushButton("Voorbeeld maken")
        preview_button.setObjectName("secondary")
        preview_button.clicked.connect(self.make_preview)
        preview_layout.addWidget(preview_button)
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
        close = QPushButton("Sluiten")
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        generate = QPushButton("Thumbnails maken")
        generate.setObjectName("primary")
        generate.clicked.connect(self.generate_thumbnails)
        bottom.addWidget(generate)
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
            QProgressBar { background:#171a20; border:1px solid #303640; border-radius:6px; text-align:center; color:#e8eaed; min-height:18px; }
        """)

    @staticmethod
    def _creationflags() -> int:
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def _format_changed(self):
        is_jpg = self.format.currentData() == "jpg"
        self.quality.setEnabled(is_jpg)
        if self.selected_files:
            self.status.setText("Instellingen gewijzigd. Klik op ‘Voorbeeld maken’.")

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Kies video's", "", VIDEO_FILTER)
        if paths:
            self._set_files(paths)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies videomap")
        if not folder:
            return
        try:
            paths = [str(p) for p in sorted(Path(folder).iterdir()) if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
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
        folder = QFileDialog.getExistingDirectory(self, "Kies doelmap")
        if folder:
            self.output.setText(folder)

    def _run_ffmpeg(self, source: str, target: str) -> tuple[bool, str]:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return False, "FFmpeg kon niet worden gevonden."
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", source, "-ss", str(self.second.value()), "-map", "0:v:0", "-frames:v", "1"]
        if self.width.value() > 0:
            command += ["-vf", f"scale={self.width.value()}:-2"]
        if self.format.currentData() == "jpg":
            command += ["-q:v", str(self.quality.value())]
        else:
            command += ["-compression_level", "6"]
        command += ["-y", target]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=self._creationflags())
        except OSError as exc:
            return False, str(exc)
        if result.returncode != 0:
            return False, result.stderr.strip() or "FFmpeg gaf een onbekende fout."
        try:
            valid = Path(target).is_file() and Path(target).stat().st_size > 0
        except OSError:
            valid = False
        return (True, "") if valid else (False, "FFmpeg heeft geen geldige afbeelding aangemaakt.")

    def make_preview(self):
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
        target = temp_dir / f"thumbnail_preview{suffix}"
        self.status.setText(f"Voorbeeld maken: {Path(source).name}")
        self.progress.setFormat("Voorbeeld maken…")
        QApplication.processEvents()
        ok, error = self._run_ffmpeg(source, str(target))
        if not ok:
            self.preview.clear()
            self.preview.setText("Voorbeeld kon niet worden gemaakt.")
            self.preview_name.setText(error)
            self.status.setText("Voorbeeld mislukt.")
            self.progress.setFormat("Voorbeeld mislukt")
            return
        pixmap = QPixmap(str(target))
        if pixmap.isNull():
            self.preview.clear()
            self.preview.setText("Afbeelding kon niet worden geladen.")
            self.preview_name.setText("FFmpeg maakte een bestand, maar Qt kon de afbeelding niet openen.")
            return
        self._preview_pixmap = pixmap
        self._show_preview_pixmap()
        self.preview_name.setText(f"Voorbeeld: {Path(source).name} • {self.second.value()} sec • {pixmap.width()}×{pixmap.height()} px")
        self.status.setText("Voorbeeld klaar. Pas het moment aan en maak opnieuw een voorbeeld voor een ander frame.")
        self.progress.setValue(100)
        self.progress.setFormat("Voorbeeld klaar")

    def _show_preview_pixmap(self):
        if self._preview_pixmap is not None:
            self.preview.setPixmap(self._preview_pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show_preview_pixmap()

    @staticmethod
    def _unique_target(folder: Path, stem: str, suffix: str) -> Path:
        target = folder / f"{stem}_thumbnail{suffix}"
        index = 2
        while target.exists():
            target = folder / f"{stem}_thumbnail_{index}{suffix}"
            index += 1
        return target

    def generate_thumbnails(self):
        if not self.selected_files:
            QMessageBox.warning(self, "Thumbnail Tool", "Kies eerst één of meerdere video's.")
            return
        output = Path(self.output.text().strip()) if self.output.text().strip() else Path(self.selected_files[0]).parent
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Thumbnail Tool", f"Doelmap kon niet worden aangemaakt.\n\n{exc}")
            return
        suffix = ".jpg" if self.format.currentData() == "jpg" else ".png"
        total = len(self.selected_files)
        success: list[Path] = []
        failed: list[tuple[str, str]] = []
        self.progress.setValue(0)
        for index, source in enumerate(self.selected_files, 1):
            self.status.setText(f"Thumbnail {index}/{total}: {Path(source).name}")
            self.progress.setFormat(f"{index}/{total} • {Path(source).name}")
            QApplication.processEvents()
            target = self._unique_target(output, Path(source).stem, suffix)
            ok, error = self._run_ffmpeg(source, str(target))
            if ok:
                success.append(target)
            else:
                failed.append((source, error))
            self.progress.setValue(int(index * 100 / total))
            QApplication.processEvents()
        if not failed:
            self.progress.setFormat(f"{len(success):,} thumbnail(s) klaar")
            self.status.setText(f"Klaar: {len(success):,} thumbnail(s) gemaakt.")
            QMessageBox.information(self, "Thumbnail Tool", f"Klaar.\n\n{len(success):,} thumbnail(s) gemaakt.\n\nDoelmap:\n{output}")
            return
        lines = [f"Gelukt: {len(success):,}", f"Mislukt: {len(failed):,}", ""]
        for source, error in failed[:8]:
            lines += [Path(source).name, error, ""]
        if len(failed) > 8:
            lines.append(f"… en nog {len(failed) - 8:,} fouten.")
        self.status.setText(f"Klaar met fouten: {len(success):,} gelukt, {len(failed):,} mislukt.")
        self.progress.setFormat(f"{len(success):,} gelukt / {len(failed):,} mislukt")
        QMessageBox.warning(self, "Thumbnail Tool", "\n".join(lines))


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
