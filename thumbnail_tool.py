from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from video_tools import VIDEO_EXTENSIONS, find_ffmpeg


class ThumbnailToolWindow(QDialog):
    """Standalone thumbnail generator used by the Video Suite.

    Supports one or multiple videos, previewing a frame before generation,
    JPG/PNG output, optional resizing, and safe collision handling.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Thumbnail Tool")
        self.resize(980, 700)
        self.selected_files: list[str] = []
        self._preview_path: str | None = None
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
            "Maak één of meerdere thumbnails uit je video's met FFmpeg."
        )
        subtitle.setObjectName("subtitle")
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        count = QLabel("0 video's geselecteerd")
        count.setObjectName("count")
        self.count_label = count
        header.addWidget(count, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        top = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(12)

        source_frame = QFrame()
        source_frame.setObjectName("panel")
        source_layout = QVBoxLayout(source_frame)
        source_layout.setContentsMargins(16, 14, 16, 14)
        source_title = QLabel("1. Video's kiezen")
        source_title.setObjectName("panelTitle")
        source_layout.addWidget(source_title)

        source_buttons = QHBoxLayout()
        choose_files = QPushButton("Video's kiezen…")
        choose_files.clicked.connect(self.choose_files)
        source_buttons.addWidget(choose_files)

        choose_folder = QPushButton("Map kiezen…")
        choose_folder.clicked.connect(self.choose_folder)
        source_buttons.addWidget(choose_folder)

        clear = QPushButton("Selectie wissen")
        clear.clicked.connect(self.clear_selection)
        source_buttons.addWidget(clear)
        source_buttons.addStretch(1)
        source_layout.addLayout(source_buttons)

        self.file_list = QLabel("Nog geen video's geselecteerd.")
        self.file_list.setObjectName("fileList")
        self.file_list.setWordWrap(True)
        self.file_list.setMinimumHeight(80)
        source_layout.addWidget(self.file_list)
        left.addWidget(source_frame)

        settings = QFrame()
        settings.setObjectName("panel")
        form = QFormLayout(settings)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        moment_row = QHBoxLayout()
        self.second = QSpinBox()
        self.second.setRange(0, 86400)
        self.second.setSuffix(" sec")
        self.second.setValue(5)
        moment_row.addWidget(self.second)
        moment_row.addStretch(1)
        form.addRow("Moment:", moment_row)

        self.format = QComboBox()
        self.format.addItem("JPG - compact", "jpg")
        self.format.addItem("PNG - maximale kwaliteit", "png")
        form.addRow("Afbeelding:", self.format)

        self.quality = QSpinBox()
        self.quality.setRange(1, 31)
        self.quality.setValue(2)
        self.quality.setToolTip("JPG-kwaliteit: 1 is hoogste kwaliteit, 31 laagste.")
        form.addRow("JPG kwaliteit:", self.quality)

        width_row = QHBoxLayout()
        self.width = QSpinBox()
        self.width.setRange(0, 7680)
        self.width.setValue(0)
        self.width.setSuffix(" px")
        self.width.setToolTip("0 = originele videobreedte behouden.")
        width_row.addWidget(self.width)
        width_row.addStretch(1)
        form.addRow("Breedte:", width_row)

        self.output = QLineEdit()
        output_button = QPushButton("Bladeren…")
        output_button.clicked.connect(self.choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output, 1)
        output_row.addWidget(output_button)
        form.addRow("Doelmap:", output_row)

        left.addWidget(settings)
        top.addLayout(left, 1)

        preview_panel = QFrame()
        preview_panel.setObjectName("panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(16, 14, 16, 14)

        preview_title = QLabel("Voorbeeld")
        preview_title.setObjectName("panelTitle")
        preview_layout.addWidget(preview_title)

        self.preview = QLabel("Kies een video en klik op Voorbeeld.")
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(390, 260)
        preview_layout.addWidget(self.preview, 1)

        self.preview_name = QLabel("")
        self.preview_name.setObjectName("previewName")
        self.preview_name.setWordWrap(True)
        preview_layout.addWidget(self.preview_name)

        preview_button = QPushButton("Voorbeeld maken")
        preview_button.setObjectName("secondary")
        preview_button.clicked.connect(self.make_preview)
        preview_layout.addWidget(preview_button)

        top.addWidget(preview_panel, 1)
        root.addLayout(top, 1)

        bottom = QHBoxLayout()
        self.status = QLabel("Klaar.")
        self.status.setObjectName("status")
        bottom.addWidget(self.status, 1)

        cancel = QPushButton("Sluiten")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)

        generate = QPushButton("Thumbnails maken")
        generate.setObjectName("primary")
        generate.clicked.connect(self.generate_thumbnails)
        bottom.addWidget(generate)
        root.addLayout(bottom)

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog { background: #101216; color: #e8eaed; }
            QLabel#title { color: #ffffff; font-size: 30px; font-weight: 900; }
            QLabel#subtitle { color: #8f96a3; font-size: 14px; }
            QLabel#count { color: #b9c8dc; background: #182235; border: 1px solid #315f9e; border-radius: 7px; padding: 8px 12px; }
            QFrame#panel { background: #171a20; border: 1px solid #303640; border-radius: 10px; }
            QLabel#panelTitle { color: #ffffff; font-size: 17px; font-weight: 800; }
            QLabel#fileList { color: #9da5b2; background: #12151a; border: 1px solid #282d35; border-radius: 7px; padding: 10px; }
            QLabel#preview { color: #737c89; background: #0c0f13; border: 1px dashed #3b424d; border-radius: 7px; }
            QLabel#previewName { color: #9da5b2; }
            QLabel#status { color: #aeb5c0; }
            QLineEdit, QComboBox, QSpinBox { background: #1e2127; border: 1px solid #353a43; border-radius: 6px; padding: 7px; color: #e8eaed; }
            QPushButton { background: #292e36; border: 1px solid #3c424c; border-radius: 7px; padding: 9px 14px; color: #e8eaed; font-weight: 600; }
            QPushButton:hover { background: #353b45; }
            QPushButton#primary { background: #315f9e; border-color: #4679bd; color: #ffffff; }
            QPushButton#primary:hover { background: #3b70b6; }
            QPushButton#secondary { background: #26384f; border-color: #3d638e; color: #ffffff; }
        """)

    @staticmethod
    def _creationflags() -> int:
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Kies video's",
            "",
            "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv *.mpeg *.mpg);;Alle bestanden (*)",
        )
        if paths:
            self._set_files(paths)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies videomap")
        if not folder:
            return
        paths = [
            str(p)
            for p in sorted(Path(folder).iterdir())
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        ]
        if not paths:
            QMessageBox.information(self, "Thumbnail Tool", "Geen ondersteunde video's in deze map gevonden.")
            return
        self._set_files(paths)

    def _set_files(self, paths: list[str]):
        unique = []
        seen = set()
        for path in paths:
            normalized = str(Path(path).resolve())
            if normalized not in seen and Path(normalized).is_file():
                seen.add(normalized)
                unique.append(normalized)
        self.selected_files = unique
        self._refresh_file_list()
        if self.selected_files and not self.output.text().strip():
            self.output.setText(str(Path(self.selected_files[0]).parent))
        self.make_preview()

    def _refresh_file_list(self):
        count = len(self.selected_files)
        self.count_label.setText(f"{count:,} video{'s' if count != 1 else ''} geselecteerd")
        if not self.selected_files:
            self.file_list.setText("Nog geen video's geselecteerd.")
            return
        lines = [Path(p).name for p in self.selected_files[:8]]
        if count > 8:
            lines.append(f"… en nog {count - 8:,} video's")
        self.file_list.setText("\n".join(lines))

    def clear_selection(self):
        self.selected_files.clear()
        self._refresh_file_list()
        self.preview.clear()
        self.preview.setText("Kies een video en klik op Voorbeeld.")
        self.preview_name.clear()
        self.status.setText("Selectie gewist.")

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies doelmap")
        if folder:
            self.output.setText(folder)

    def _run_ffmpeg(self, source: str, target: str, preview: bool = False) -> tuple[bool, str]:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return False, "FFmpeg kon niet worden gevonden."

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(self.second.value()),
            "-i", source,
            "-frames:v", "1",
        ]

        width = self.width.value()
        if width > 0:
            command += ["-vf", f"scale={width}:-2"]

        if self.format.currentData() == "jpg":
            command += ["-q:v", str(self.quality.value())]
        else:
            command += ["-compression_level", "6"]

        command += ["-y", target]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creationflags(),
            )
        except OSError as exc:
            return False, str(exc)

        if result.returncode != 0:
            message = result.stderr.strip() or "FFmpeg gaf een onbekende fout."
            return False, message
        if not Path(target).is_file() or Path(target).stat().st_size == 0:
            return False, "FFmpeg heeft geen geldige afbeelding aangemaakt."
        return True, ""

    def make_preview(self):
        if not self.selected_files:
            self.preview.setText("Kies eerst minstens één video.")
            return

        source = self.selected_files[0]
        suffix = ".jpg" if self.format.currentData() == "jpg" else ".png"
        temp_dir = Path(tempfile.gettempdir()) / "VideoAudioScanner"
        temp_dir.mkdir(parents=True, exist_ok=True)
        target = temp_dir / f"thumbnail_preview{suffix}"

        self.status.setText(f"Voorbeeld maken: {Path(source).name}")
        QApplication.processEvents()
        ok, error = self._run_ffmpeg(source, str(target), preview=True)
        if not ok:
            self.preview.clear()
            self.preview.setText("Voorbeeld kon niet worden gemaakt.")
            self.preview_name.setText(error)
            self.status.setText("Voorbeeld mislukt.")
            return

        pixmap = QPixmap(str(target))
        if pixmap.isNull():
            self.preview.clear()
            self.preview.setText("Afbeelding kon niet worden geladen.")
            self.status.setText("Voorbeeld mislukt.")
            return

        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.preview_name.setText(f"Voorbeeld: {Path(source).name} • {self.second.value()} sec")
        self._preview_path = str(target)
        self.status.setText("Voorbeeld klaar.")

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

        output_text = self.output.text().strip()
        output = Path(output_text) if output_text else Path(self.selected_files[0]).parent
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Thumbnail Tool", f"Doelmap kon niet worden aangemaakt.\n\n{exc}")
            return

        suffix = ".jpg" if self.format.currentData() == "jpg" else ".png"
        success = []
        failed = []

        for index, source in enumerate(self.selected_files, 1):
            self.status.setText(f"Thumbnail {index}/{len(self.selected_files)}: {Path(source).name}")
            QApplication.processEvents()
            target = self._unique_target(output, Path(source).stem, suffix)
            ok, error = self._run_ffmpeg(source, str(target))
            if ok:
                success.append(target)
            else:
                failed.append((source, error))

        if not failed:
            self.status.setText(f"Klaar: {len(success):,} thumbnail{'s' if len(success) != 1 else ''} gemaakt.")
            first = success[0] if success else output
            QMessageBox.information(
                self,
                "Thumbnail Tool",
                f"Klaar.\n\n{len(success):,} thumbnail{'s' if len(success) != 1 else ''} gemaakt.\n\nDoelmap:\n{output}\n\nEerste bestand:\n{first.name}",
            )
            return

        lines = [f"Gelukt: {len(success):,}", f"Mislukt: {len(failed):,}", ""]
        for source, error in failed[:5]:
            lines.append(f"{Path(source).name}: {error}")
        if len(failed) > 5:
            lines.append(f"… en nog {len(failed) - 5:,} fouten.")
        self.status.setText(f"Klaar met fouten: {len(success):,} gelukt, {len(failed):,} mislukt.")
        QMessageBox.warning(self, "Thumbnail Tool", "\n".join(lines))


def main():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("VideoAudioScanner")
    window = ThumbnailToolWindow()
    window.show()
    if QApplication.instance() is app:
        app.exec()


if __name__ == "__main__":
    main()
