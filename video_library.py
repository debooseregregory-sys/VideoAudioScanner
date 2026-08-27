from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v",
    ".mpeg", ".mpg", ".ts", ".mts", ".m2ts", ".flv", ".3gp",
}


@dataclass
class VideoItem:
    path: str
    name: str
    size: int
    extension: str


class VideoCard(QFrame):
    def __init__(self, item: VideoItem, thumbnail: QPixmap | None, callback, parent=None):
        super().__init__(parent)
        self.item = item
        self.callback = callback
        self.setObjectName("libraryCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(250, 250)
        self.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        preview = QLabel()
        preview.setObjectName("libraryPreview")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setFixedHeight(145)
        preview.setMinimumWidth(220)
        if thumbnail and not thumbnail.isNull():
            preview.setPixmap(thumbnail.scaled(QSize(330, 145), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            preview.setText("▶")
            preview.setStyleSheet("font-size: 42px; color: #5d8fd0; background: #0d1015;")
        layout.addWidget(preview)

        title = QLabel(item.name)
        title.setObjectName("libraryTitle")
        title.setWordWrap(True)
        title.setToolTip(item.path)
        layout.addWidget(title)

        meta = QLabel(f"{item.extension.upper().lstrip('.')}  •  {format_size(item.size)}")
        meta.setObjectName("libraryMeta")
        layout.addWidget(meta)

        path_label = QLabel(str(Path(item.path).parent))
        path_label.setObjectName("libraryPath")
        path_label.setWordWrap(True)
        layout.addWidget(path_label, 1)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.callback(self.item.path)
        super().mouseDoubleClickEvent(event)


def format_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def make_thumbnail(path: str) -> QPixmap | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", "00:00:03", "-i", path,
             "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2", "pipe:1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=12,
            check=False,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        pixmap = QPixmap()
        pixmap.loadFromData(result.stdout, "JPEG")
        return pixmap if not pixmap.isNull() else None
    except (OSError, subprocess.SubprocessError):
        return None


class VideoLibraryWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Video Library")
        self.resize(1250, 850)
        self.items: list[VideoItem] = []
        self.folder = ""
        self.cards: list[VideoCard] = []
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("VIDEO LIBRARY")
        title.setObjectName("libraryHeader")
        title_box.addWidget(title)
        subtitle = QLabel("Visueel overzicht van je videobestanden")
        subtitle.setObjectName("librarySubtitle")
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.stats = QLabel("Nog geen map gescand")
        self.stats.setObjectName("libraryStats")
        header.addWidget(self.stats)
        layout.addLayout(header)

        controls = QHBoxLayout()
        choose = QPushButton("Map kiezen")
        choose.clicked.connect(self.choose_folder)
        controls.addWidget(choose)
        self.scan_button = QPushButton("Scan starten")
        self.scan_button.setObjectName("primary")
        self.scan_button.setEnabled(False)
        self.scan_button.clicked.connect(self.scan)
        controls.addWidget(self.scan_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Zoeken op bestandsnaam of pad…")
        self.search.textChanged.connect(self.refresh_cards)
        controls.addWidget(self.search, 1)
        self.sort_box = QComboBox()
        self.sort_box.addItems(["Naam", "Grootte — groot naar klein", "Grootte — klein naar groot"])
        self.sort_box.currentIndexChanged.connect(self.refresh_cards)
        controls.addWidget(self.sort_box)
        layout.addLayout(controls)

        self.folder_label = QLabel("Kies een map en klik daarna op Scan starten.")
        self.folder_label.setObjectName("libraryFolder")
        layout.addWidget(self.folder_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        self.status = QLabel("Gereed")
        self.status.setObjectName("libraryStatus")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background: #111318; color: #e8eaed; font-size: 13px; }
            QMainWindow { background: #0d0f13; }
            QLabel#libraryHeader { font-size: 30px; font-weight: 900; color: #fff; }
            QLabel#librarySubtitle, QLabel#libraryStatus { color: #8f96a3; }
            QLabel#libraryStats { color: #fff; font-weight: 800; background: #191c22; border: 1px solid #303640; border-radius: 8px; padding: 10px 14px; }
            QLabel#libraryFolder { color: #aeb5c0; background: #15181d; border: 1px solid #2d323a; border-radius: 7px; padding: 9px 12px; }
            QLineEdit, QComboBox { background: #1e2127; border: 1px solid #353a43; border-radius: 7px; padding: 8px 10px; }
            QPushButton { background: #292e36; border: 1px solid #3c424c; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
            QPushButton:hover { background: #353b45; }
            QPushButton#primary { background: #315f9e; border-color: #4679bd; color: #fff; }
            QPushButton#primary:hover { background: #3b70b6; }
            QScrollArea { border: 0; background: #111318; }
            QFrame#libraryCard { background: #191c22; border: 1px solid #303640; border-radius: 10px; }
            QFrame#libraryCard:hover { border: 1px solid #5686c4; background: #1c2027; }
            QLabel#libraryPreview { background: #0d1015; border-radius: 7px; color: #5d8fd0; }
            QLabel#libraryTitle { font-size: 15px; font-weight: 800; color: #fff; }
            QLabel#libraryMeta { color: #6f9bd0; font-weight: 700; }
            QLabel#libraryPath { color: #777f8c; font-size: 11px; }
        """)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies videomap", self.folder or "")
        if not folder:
            return
        self.folder = folder
        self.folder_label.setText(folder)
        self.scan_button.setEnabled(True)
        self.status.setText("Map gekozen. Klik op Scan starten.")

    def scan(self):
        if not self.folder or not os.path.isdir(self.folder):
            return
        self.status.setText("Video's zoeken…")
        self.scan_button.setEnabled(False)
        QApplication.processEvents()
        items: list[VideoItem] = []
        try:
            for path in Path(self.folder).rglob("*"):
                if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                try:
                    stat = path.stat()
                    items.append(VideoItem(str(path), path.name, stat.st_size, path.suffix.lower()))
                except OSError:
                    continue
        except OSError as exc:
            QMessageBox.critical(self, "Video Library", str(exc))
        self.items = items
        self.scan_button.setEnabled(True)
        self.refresh_cards()
        total = sum(i.size for i in items)
        self.stats.setText(f"{len(items):,} video's  •  {format_size(total)}")
        self.status.setText(f"Scan klaar: {len(items):,} video's gevonden.")

    def refresh_cards(self):
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()
        while self.grid.count():
            self.grid.takeAt(0)

        query = self.search.text().casefold().strip()
        items = [i for i in self.items if not query or query in i.name.casefold() or query in i.path.casefold()]
        if self.sort_box.currentIndex() == 1:
            items.sort(key=lambda i: i.size, reverse=True)
        elif self.sort_box.currentIndex() == 2:
            items.sort(key=lambda i: i.size)
        else:
            items.sort(key=lambda i: i.name.casefold())

        for index, item in enumerate(items):
            thumb = make_thumbnail(item.path)
            card = VideoCard(item, thumb, self.open_video, self.container)
            self.cards.append(card)
            self.grid.addWidget(card, index // 3, index % 3)
        self.grid.setRowStretch((len(items) + 2) // 3, 1)

    def open_video(self, path: str):
        try:
            os.startfile(path)
        except OSError as exc:
            QMessageBox.warning(self, "Video openen", str(exc))


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    window = VideoLibraryWindow()
    window.show()
    sys.exit(app.exec())
