from __future__ import annotations

import ctypes
import os
import subprocess
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm",
    ".m4v", ".mpeg", ".mpg", ".ts", ".mts", ".m2ts",
}
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma",
}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff",
}


def format_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def file_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "Video"
    if suffix in AUDIO_EXTENSIONS:
        return "Audio"
    if suffix in IMAGE_EXTENSIONS:
        return "Afbeelding"
    return "Andere"


class StorageAnalyzerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Storage Analyzer")
        self.resize(1450, 920)
        self.files: list[tuple[str, int, str]] = []
        self.current_folder = ""
        self.preview_path = ""
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)

        title = QLabel("STORAGE ANALYZER")
        title.setObjectName("title")
        layout.addWidget(title)

        intro = QLabel(
            "Analyseer je opslag, ontdek grote bestanden en bekijk meteen een preview "
            "van het geselecteerde bestand. De scan werkt recursief door alle onderliggende mappen."
        )
        intro.setObjectName("intro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        info = QFrame()
        info.setObjectName("infoPanel")
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(16, 12, 16, 12)
        self.folder_label = QLabel("Nog geen map gekozen")
        self.folder_label.setObjectName("folder")
        info_layout.addWidget(self.folder_label, 1)
        self.total_label = QLabel("0 bestanden • 0 B")
        self.total_label.setObjectName("total")
        info_layout.addWidget(self.total_label)
        layout.addWidget(info)

        stats = QGridLayout()
        stats.setHorizontalSpacing(10)
        self.stat_files = self._stat_card("BESTANDEN", "0")
        self.stat_size = self._stat_card("TOTALE GROOTTE", "0 B")
        self.stat_largest = self._stat_card("GROOTSTE BESTAND", "0 B")
        self.stat_videos = self._stat_card("VIDEO'S", "0")
        stats.addWidget(self.stat_files, 0, 0)
        stats.addWidget(self.stat_size, 0, 1)
        stats.addWidget(self.stat_largest, 0, 2)
        stats.addWidget(self.stat_videos, 0, 3)
        layout.addLayout(stats)

        type_panel = QFrame()
        type_panel.setObjectName("typePanel")
        type_layout = QVBoxLayout(type_panel)
        type_layout.setContentsMargins(14, 12, 14, 12)
        section = QLabel("OPSLAG PER BESTANDSTYPE")
        section.setObjectName("sectionTitle")
        type_layout.addWidget(section)
        self.type_bars: dict[str, tuple[QProgressBar, QLabel]] = {}
        for kind in ("Video", "Audio", "Afbeelding", "Andere"):
            row = QHBoxLayout()
            name = QLabel(kind)
            name.setFixedWidth(90)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            value = QLabel("0 B • 0%")
            value.setObjectName("barValue")
            value.setFixedWidth(130)
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(value)
            type_layout.addLayout(row)
            self.type_bars[kind] = (bar, value)
        layout.addWidget(type_panel)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        choose = QPushButton("Map kiezen")
        choose.clicked.connect(self.choose_folder)
        controls.addWidget(choose)
        self.scan_button = QPushButton("Scan starten")
        self.scan_button.setObjectName("primary")
        self.scan_button.setEnabled(False)
        self.scan_button.clicked.connect(self.analyze_current_folder)
        controls.addWidget(self.scan_button)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Zoeken op bestandsnaam, pad of extensie…")
        self.filter_edit.textChanged.connect(self.apply_filter)
        controls.addWidget(self.filter_edit, 1)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Alle types", "Video", "Audio", "Afbeelding", "Andere"])
        self.type_combo.currentTextChanged.connect(self.apply_filter)
        controls.addWidget(self.type_combo)
        self.size_combo = QComboBox()
        self.size_combo.addItems(["Alle groottes", "> 1 GB", "> 5 GB", "> 10 GB"])
        self.size_combo.currentTextChanged.connect(self.apply_filter)
        controls.addWidget(self.size_combo)
        layout.addLayout(controls)

        actions = QHBoxLayout()
        self.open_button = QPushButton("Bestand openen")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_selected)
        actions.addWidget(self.open_button)
        self.folder_button = QPushButton("Map openen")
        self.folder_button.setEnabled(False)
        self.folder_button.clicked.connect(self.open_selected_folder)
        actions.addWidget(self.folder_button)
        actions.addStretch(1)
        self.delete_button = QPushButton("Naar Prullenbak")
        self.delete_button.setObjectName("danger")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(self.delete_button)
        layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Bestand", "Type", "Extensie", "Grootte", "Pad"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._update_action_state)
        self.table.itemSelectionChanged.connect(self.update_preview)
        self.table.cellDoubleClicked.connect(lambda row, _: self.open_path(self._path_at_row(row)))
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, header.ResizeMode.Interactive)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        splitter.addWidget(self.table)

        preview = QFrame()
        preview.setObjectName("previewPanel")
        preview.setMinimumWidth(360)
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(10)

        preview_title = QLabel("BESTAND PREVIEW")
        preview_title.setObjectName("sectionTitle")
        preview_layout.addWidget(preview_title)

        self.preview_image = QLabel("Selecteer een bestand")
        self.preview_image.setObjectName("previewImage")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumHeight(220)
        self.preview_image.setWordWrap(True)
        preview_layout.addWidget(self.preview_image, 1)

        self.preview_name = QLabel("Geen bestand geselecteerd")
        self.preview_name.setObjectName("previewName")
        self.preview_name.setWordWrap(True)
        preview_layout.addWidget(self.preview_name)

        self.preview_info = QLabel("")
        self.preview_info.setObjectName("previewInfo")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)

        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self.status = QLabel("Klaar. Kies een map om te beginnen.")
        self.status.setObjectName("status")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _stat_card(self, caption: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 10, 14, 10)
        label = QLabel(caption)
        label.setObjectName("statCaption")
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        box.addWidget(label)
        box.addWidget(value_label)
        card.value_label = value_label
        return card

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies een map")
        if folder:
            self.current_folder = folder
            self.folder_label.setText(folder)
            self.folder_label.setToolTip(folder)
            self.scan_button.setEnabled(True)
            self.status.setText("Map gekozen. Klik op Scan starten.")

    def analyze_current_folder(self):
        if self.current_folder and os.path.isdir(self.current_folder):
            self._analyze(self.current_folder)
        else:
            self.choose_folder()

    def _analyze(self, folder: str):
        self.current_folder = folder
        self.folder_label.setText(folder)
        self.folder_label.setToolTip(folder)
        self.files.clear()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._clear_preview()
        self._update_stats()
        self.status.setText("Analyseren…")
        self.scan_button.setEnabled(False)
        QApplication.processEvents()

        scanned = 0
        try:
            for root, _, filenames in os.walk(folder):
                for filename in filenames:
                    path = Path(root) / filename
                    try:
                        size = path.stat().st_size
                    except OSError:
                        continue
                    self.files.append((str(path), size, file_type(str(path))))
                    scanned += 1
                    if scanned % 250 == 0:
                        self.status.setText(f"Analyseren… {scanned:,} bestanden verwerkt".replace(",", "."))
                        QApplication.processEvents()
        except OSError as exc:
            QMessageBox.critical(self, "Storage Analyzer", f"De map kon niet volledig worden gelezen:\n{exc}")

        self.files.sort(key=lambda item: item[1], reverse=True)
        self._update_stats()
        self._refresh_table()
        self.scan_button.setEnabled(True)
        self.status.setText(f"Analyse klaar: {len(self.files):,} bestanden gevonden.".replace(",", "."))

    def _refresh_table(self):
        text = self.filter_edit.text().casefold().strip()
        selected_type = self.type_combo.currentText()
        size_filter = self.size_combo.currentText()
        minimum = {"> 1 GB": 1024**3, "> 5 GB": 5 * 1024**3, "> 10 GB": 10 * 1024**3}.get(size_filter, 0)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for path, size, kind in self.files:
            suffix = Path(path).suffix.lower() or "(geen)"
            if text and text not in path.casefold() and text not in suffix.casefold():
                continue
            if selected_type != "Alle types" and kind != selected_type:
                continue
            if size < minimum:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(Path(path).name))
            self.table.setItem(row, 1, QTableWidgetItem(kind))
            self.table.setItem(row, 2, QTableWidgetItem(suffix))
            size_item = QTableWidgetItem(format_size(size))
            size_item.setData(Qt.ItemDataRole.UserRole, size)
            self.table.setItem(row, 3, size_item)
            self.table.setItem(row, 4, QTableWidgetItem(path))
        self.table.setSortingEnabled(True)
        self._update_action_state()

    def apply_filter(self):
        self._refresh_table()
        visible = self.table.rowCount()
        self.status.setText(f"{visible:,} bestand(en) zichtbaar.".replace(",", "."))

    def _update_stats(self):
        total_size = sum(size for _, size, _ in self.files)
        largest = max((size for _, size, _ in self.files), default=0)
        videos = sum(1 for _, _, kind in self.files if kind == "Video")
        self.stat_files.value_label.setText(f"{len(self.files):,}".replace(",", "."))
        self.stat_size.value_label.setText(format_size(total_size))
        self.stat_largest.value_label.setText(format_size(largest))
        self.stat_videos.value_label.setText(f"{videos:,}".replace(",", "."))
        self.total_label.setText(f"{len(self.files):,} bestanden • {format_size(total_size)}".replace(",", "."))
        totals: dict[str, int] = defaultdict(int)
        for _, size, kind in self.files:
            totals[kind] += size
        for kind, (bar, value) in self.type_bars.items():
            amount = totals.get(kind, 0)
            percent = int(round(amount * 100 / total_size)) if total_size else 0
            bar.setValue(percent)
            value.setText(f"{format_size(amount)} • {percent}%")

    def _selected_paths(self) -> list[str]:
        return [self._path_at_row(index.row()) for index in self.table.selectionModel().selectedRows() if self._path_at_row(index.row())]

    def _path_at_row(self, row: int) -> str:
        item = self.table.item(row, 4)
        return item.text() if item else ""

    def _update_action_state(self):
        selected = bool(self._selected_paths())
        self.delete_button.setEnabled(selected)
        self.open_button.setEnabled(selected)
        self.folder_button.setEnabled(selected)

    def update_preview(self):
        paths = self._selected_paths()
        if not paths:
            self._clear_preview()
            return
        path = paths[0]
        self.preview_path = path
        size = 0
        kind = ""
        for candidate, candidate_size, candidate_kind in self.files:
            if candidate == path:
                size, kind = candidate_size, candidate_kind
                break
        self.preview_name.setText(Path(path).name)
        self.preview_info.setText(f"{kind} • {format_size(size)}\n{path}")
        self.preview_image.setPixmap(QPixmap())
        self.preview_image.setText("Preview laden…")
        QApplication.processEvents()

        if kind == "Afbeelding":
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self._set_preview_pixmap(pixmap)
            else:
                self.preview_image.setText("Afbeelding kan niet worden geladen.")
        elif kind == "Video":
            pixmap = self._video_thumbnail(path)
            if pixmap is not None and not pixmap.isNull():
                self._set_preview_pixmap(pixmap)
            else:
                self.preview_image.setText("Geen preview beschikbaar.\nDubbelklik om de video te openen.")
        elif kind == "Audio":
            self.preview_image.setText("🎵\n\nAudio-bestand\n\nDubbelklik om te openen.")
        else:
            self.preview_image.setText("📄\n\nBestand geselecteerd\n\nDubbelklik om te openen.")

    def _set_preview_pixmap(self, pixmap: QPixmap):
        self.preview_image.setText("")
        self.preview_image.setPixmap(pixmap.scaled(
            self.preview_image.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def _video_thumbnail(self, path: str):
        commands = [
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "5", "-i", path,
             "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
             "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
        ]
        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode == 0 and result.stdout:
                    pixmap = QPixmap()
                    if pixmap.loadFromData(result.stdout, "JPG"):
                        return pixmap
            except (OSError, subprocess.SubprocessError):
                continue
        return None

    def _clear_preview(self):
        self.preview_path = ""
        self.preview_image.setPixmap(QPixmap())
        self.preview_image.setText("Selecteer een bestand")
        self.preview_name.setText("Geen bestand geselecteerd")
        self.preview_info.setText("")

    def open_path(self, path: str):
        if not path or not Path(path).is_file():
            return
        try:
            os.startfile(path)
        except OSError as exc:
            QMessageBox.warning(self, "Bestand openen", str(exc))

    def open_selected(self):
        paths = self._selected_paths()
        if paths:
            self.open_path(paths[0])

    def open_selected_folder(self):
        paths = self._selected_paths()
        if paths:
            try:
                os.startfile(str(Path(paths[0]).parent))
            except OSError as exc:
                QMessageBox.warning(self, "Map openen", str(exc))

    def delete_selected(self):
        paths = self._selected_paths()
        if not paths:
            return
        answer = QMessageBox.question(
            self, "Naar Prullenbak",
            f"Wil je {len(paths)} geselecteerd(e) bestand(en) naar de Windows Prullenbak verplaatsen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes or os.name != "nt":
            return

        from ctypes import wintypes
        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.UINT), ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID), ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        existing = [path for path in paths if Path(path).is_file()]
        failed = [path for path in paths if path not in existing]
        moved: list[str] = []
        if existing:
            source = "".join(path + "\0" for path in existing) + "\0"
            flags = 0x0004 | 0x0010 | 0x0040 | 0x0400
            operation = SHFILEOPSTRUCTW(None, 0x0003, source, None, flags, False, None, None)
            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
            if result == 0 and not operation.fAnyOperationsAborted:
                moved = existing
            else:
                failed.extend(existing)

        moved_set = set(moved)
        self.files = [item for item in self.files if item[0] not in moved_set]
        self._refresh_table()
        self._update_stats()
        self._clear_preview()
        self.status.setText(f"{len(moved)} bestand(en) naar de Prullenbak verplaatst.")
        if failed:
            QMessageBox.warning(self, "Prullenbak", f"{len(moved)} verplaatst. {len(failed)} konden niet worden verplaatst.")

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background: #111318; color: #e8eaed; font-size: 13px; }
            QMainWindow { background: #0d0f13; }
            QLabel#title { font-size: 30px; font-weight: 900; color: #ffffff; }
            QLabel#intro { color: #9da5b1; font-size: 14px; }
            QFrame#infoPanel, QFrame#statCard, QFrame#typePanel, QFrame#previewPanel { background: #191c22; border: 1px solid #303640; border-radius: 10px; }
            QLabel#folder { color: #d9dde3; }
            QLabel#total { color: #ffffff; font-weight: 700; }
            QLabel#statCaption, QLabel#sectionTitle { color: #7f8793; font-size: 11px; font-weight: 800; }
            QLabel#statValue { color: #ffffff; font-size: 20px; font-weight: 800; }
            QLabel#barValue, QLabel#previewInfo { color: #aeb5c0; }
            QLabel#previewName { color: #ffffff; font-size: 16px; font-weight: 800; }
            QLabel#previewImage { background: #0d0f13; border: 1px solid #303640; border-radius: 8px; color: #7f8793; font-size: 15px; padding: 10px; }
            QLabel#status { color: #aeb5c0; padding: 3px; }
            QLineEdit, QComboBox, QTableWidget { background: #1e2127; border: 1px solid #353a43; border-radius: 6px; }
            QLineEdit { padding: 9px; }
            QComboBox { padding: 7px 10px; min-width: 105px; }
            QPushButton { background: #292e36; border: 1px solid #3c424c; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
            QPushButton:hover { background: #353b45; }
            QPushButton#primary { background: #315f9e; border-color: #4679bd; color: #ffffff; }
            QPushButton#primary:hover { background: #3b70b6; }
            QPushButton#danger { background: #54272b; border-color: #824047; color: #ffffff; }
            QPushButton#danger:hover { background: #6a3036; }
            QPushButton:disabled { color: #666c75; background: #202329; }
            QProgressBar { background: #20242a; border: 1px solid #353a43; border-radius: 5px; height: 14px; }
            QProgressBar::chunk { background: #477dcc; border-radius: 4px; }
            QTableWidget { gridline-color: #30343b; alternate-background-color: #20242b; }
            QHeaderView::section { background: #252a31; color: #cfd4dc; padding: 8px; border: 0; border-right: 1px solid #343941; }
            QTableWidget::item:selected { background: #304a70; }
        """)


if __name__ == "__main__":
    app = QApplication([])
    window = StorageAnalyzerWindow()
    window.show()
    app.exec()
