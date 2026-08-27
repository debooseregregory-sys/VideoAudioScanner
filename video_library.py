from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from video_player import VideoPlayerWindow


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


class ThumbnailSignals(QObject):
    finished = Signal(str, object)


class ThumbnailTask(QRunnable):
    def __init__(self, path: str, signals: ThumbnailSignals):
        super().__init__()
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        pixmap = make_thumbnail(self.path)
        self.signals.finished.emit(self.path, pixmap)


class MetadataSignals(QObject):
    finished = Signal(str, object)


class MetadataTask(QRunnable):
    def __init__(self, path: str, signals: MetadataSignals):
        super().__init__()
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        self.signals.finished.emit(self.path, read_metadata(self.path))


class VideoCard(QFrame):
    def __init__(self, item: VideoItem, select_callback, open_callback, parent=None):
        super().__init__(parent)
        self.item = item
        self.select_callback = select_callback
        self.open_callback = open_callback
        self.setObjectName("libraryCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(250, 250)
        self.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        self.preview = QLabel("Preview laden…")
        self.preview.setObjectName("libraryPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(145)
        self.preview.setMinimumWidth(220)
        self.preview.setStyleSheet(
            "font-size: 14px; color: #7f8793; background: #0d1015;"
        )
        layout.addWidget(self.preview)

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

    def set_thumbnail(self, thumbnail: QPixmap | None):
        if thumbnail and not thumbnail.isNull():
            self.preview.setStyleSheet("background: #0d1015; border-radius: 7px;")
            self.preview.setPixmap(
                thumbnail.scaled(
                    QSize(330, 145),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.preview.setText("▶")
            self.preview.setStyleSheet(
                "font-size: 42px; color: #5d8fd0; background: #0d1015;"
            )

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.select_callback(self.item.path)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_callback(self.item.path)
        super().mouseDoubleClickEvent(event)


def format_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def format_duration(seconds) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "—"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_rate(value) -> str:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "—"
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.1f} Mbps"
    if rate >= 1_000:
        return f"{rate / 1_000:.0f} kbps"
    return f"{int(rate)} bps"


def format_fps(value: str) -> str:
    if not value or value in {"0/0", "N/A"}:
        return "—"
    if "/" in value:
        try:
            num, den = value.split("/", 1)
            if float(den) != 0:
                return f"{float(num) / float(den):.3f} FPS"
        except (ValueError, ZeroDivisionError):
            pass
    return value


def read_metadata(path: str) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"error": "FFprobe niet gevonden."}
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries",
                "format=duration,bit_rate,format_name:stream=index,codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate,bit_rate",
                "-of", "json",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return {"error": result.stderr.decode("utf-8", "replace").strip() or "FFprobe kon het bestand niet lezen."}
        return json.loads(result.stdout.decode("utf-8", "replace"))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}


def make_thumbnail(path: str) -> QPixmap | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        result = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", "00:00:03",
                "-i", path, "-frames:v", "1", "-vf", "scale=640:-2",
                "-f", "image2", "pipe:1",
            ],
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
        self.resize(1450, 900)
        self.items: list[VideoItem] = []
        self.folder = ""
        self.cards: list[VideoCard] = []
        self.card_by_path: dict[str, VideoCard] = {}
        self.selected_path = ""
        self.metadata_cache: dict[str, dict] = {}
        self.thumbnail_signals = ThumbnailSignals()
        self.thumbnail_signals.finished.connect(self._thumbnail_finished)
        self.metadata_signals = MetadataSignals()
        self.metadata_signals.finished.connect(self._metadata_finished)
        self.thread_pool = QThreadPool(self)
        self.player_windows: list[VideoPlayerWindow] = []
        self.thumbnail_total = 0
        self.thumbnail_done = 0
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
        subtitle = QLabel("Visueel overzicht, metadata en afspelen vanuit één bibliotheek")
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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.scroll.setWidget(self.container)
        splitter.addWidget(self.scroll)

        details = QFrame()
        details.setObjectName("detailsPanel")
        details.setMinimumWidth(350)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(10)

        self.detail_preview = QLabel("Selecteer een video")
        self.detail_preview.setObjectName("detailPreview")
        self.detail_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_preview.setMinimumHeight(190)
        details_layout.addWidget(self.detail_preview)

        self.detail_title = QLabel("Geen video geselecteerd")
        self.detail_title.setObjectName("detailTitle")
        self.detail_title.setWordWrap(True)
        details_layout.addWidget(self.detail_title)

        self.detail_form = QFormLayout()
        self.detail_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.detail_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.detail_labels: dict[str, QLabel] = {}
        for key, label in [
            ("size", "Grootte"), ("duration", "Duur"), ("resolution", "Resolutie"),
            ("video_codec", "Video codec"), ("fps", "FPS"), ("video_bitrate", "Video bitrate"),
            ("audio_codec", "Audio codec"), ("channels", "Kanalen"),
            ("sample_rate", "Sample rate"), ("container", "Container"),
        ]:
            value = QLabel("—")
            value.setWordWrap(True)
            value.setObjectName("detailValue")
            self.detail_labels[key] = value
            self.detail_form.addRow(label + ":", value)
        details_layout.addLayout(self.detail_form)

        self.detail_path = QLabel("")
        self.detail_path.setObjectName("detailPath")
        self.detail_path.setWordWrap(True)
        details_layout.addWidget(self.detail_path)

        details_layout.addStretch(1)
        actions = QVBoxLayout()
        self.play_button = QPushButton("▶  Afspelen in Video Suite Player")
        self.play_button.setObjectName("primary")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_selected)
        actions.addWidget(self.play_button)

        self.folder_button = QPushButton("📁  Map openen")
        self.folder_button.setEnabled(False)
        self.folder_button.clicked.connect(self.open_selected_folder)
        actions.addWidget(self.folder_button)

        self.analyze_button = QPushButton("🔎  Openen in Media Scanner")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analyze_selected)
        actions.addWidget(self.analyze_button)
        details_layout.addLayout(actions)

        splitter.addWidget(details)
        splitter.setSizes([1020, 400])
        layout.addWidget(splitter, 1)

        self.status = QLabel("Gereed")
        self.status.setObjectName("libraryStatus")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet(
            """
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
            QPushButton:disabled { color: #666c75; background: #202329; }
            QScrollArea { border: 0; background: #111318; }
            QFrame#libraryCard { background: #191c22; border: 1px solid #303640; border-radius: 10px; }
            QFrame#libraryCard:hover { border: 1px solid #5686c4; background: #1c2027; }
            QFrame#libraryCard[selected="true"] { border: 2px solid #5d8fd0; background: #1d2632; }
            QLabel#libraryPreview { background: #0d1015; border-radius: 7px; }
            QLabel#libraryTitle { font-size: 15px; font-weight: 800; color: #fff; }
            QLabel#libraryMeta { color: #6f9bd0; font-weight: 700; }
            QLabel#libraryPath { color: #777f8c; font-size: 11px; }
            QFrame#detailsPanel { background: #171a20; border: 1px solid #303640; border-radius: 10px; }
            QLabel#detailPreview { background: #0b0d11; border: 1px solid #303640; border-radius: 8px; color: #6f7784; }
            QLabel#detailTitle { color: #fff; font-size: 18px; font-weight: 800; }
            QLabel#detailValue { color: #e8eaed; }
            QLabel#detailPath { color: #777f8c; font-size: 11px; padding-top: 6px; }
            """
        )

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
            QMessageBox.warning(self, "Video Library", "Kies eerst een geldige videomap.")
            return
        self.status.setText("Video's zoeken…")
        self.scan_button.setEnabled(False)
        self.items = []
        self.selected_path = ""
        self.clear_details()
        self.refresh_cards()
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
        self.status.setText(f"Scan klaar: {len(items):,} video's gevonden. Preview's worden geladen…")
        QApplication.processEvents()
        self._start_thumbnail_loading()

    def _visible_items(self) -> list[VideoItem]:
        query = self.search.text().casefold().strip()
        items = [i for i in self.items if not query or query in i.name.casefold() or query in i.path.casefold()]
        if self.sort_box.currentIndex() == 1:
            items.sort(key=lambda i: i.size, reverse=True)
        elif self.sort_box.currentIndex() == 2:
            items.sort(key=lambda i: i.size)
        else:
            items.sort(key=lambda i: i.name.casefold())
        return items

    def refresh_cards(self):
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()
        self.card_by_path.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        items = self._visible_items()
        for index, item in enumerate(items):
            card = VideoCard(item, self.select_video, self.open_video, self.container)
            card.set_selected(item.path == self.selected_path)
            self.cards.append(card)
            self.card_by_path[item.path] = card
            self.grid.addWidget(card, index // 3, index % 3)
        rows = max(1, (len(items) + 2) // 3)
        self.grid.setRowStretch(rows, 1)

    def _start_thumbnail_loading(self):
        self.thumbnail_total = len(self.card_by_path)
        self.thumbnail_done = 0
        if self.thumbnail_total == 0:
            self.status.setText("Geen video's gevonden.")
            return
        self.status.setText(f"Preview's laden: 0 / {self.thumbnail_total}")
        self.thread_pool.clear()
        for path in self.card_by_path:
            self.thread_pool.start(ThumbnailTask(path, self.thumbnail_signals))

    def _thumbnail_finished(self, path: str, thumbnail):
        self.thumbnail_done += 1
        card = self.card_by_path.get(path)
        if card is not None:
            card.set_thumbnail(thumbnail)
        if self.thumbnail_done >= self.thumbnail_total:
            self.status.setText(f"Klaar: {len(self.items):,} video's • {self.thumbnail_total:,} previews geladen.")
        else:
            self.status.setText(f"Preview's laden: {self.thumbnail_done} / {self.thumbnail_total}")

    def select_video(self, path: str):
        if not os.path.isfile(path):
            return
        self.selected_path = path
        for item_path, card in self.card_by_path.items():
            card.set_selected(item_path == path)
        self.show_details(path)

    def show_details(self, path: str):
        item = next((i for i in self.items if i.path == path), None)
        if item is None:
            return
        self.detail_title.setText(item.name)
        self.detail_path.setText(item.path)
        self.detail_labels["size"].setText(format_size(item.size))
        self.detail_labels["container"].setText(item.extension.upper().lstrip("."))
        self.play_button.setEnabled(True)
        self.folder_button.setEnabled(True)
        self.analyze_button.setEnabled(True)
        self.detail_preview.setText("Metadata laden…")
        self.detail_preview.setPixmap(QPixmap())
        self.metadata_cache.pop(path, None)
        self.thread_pool.start(MetadataTask(path, self.metadata_signals))
        thumb = self.card_by_path.get(path)
        if thumb is not None and thumb.preview.pixmap() is not None:
            pix = thumb.preview.pixmap()
            if pix and not pix.isNull():
                self.detail_preview.setText("")
                self.detail_preview.setPixmap(pix.scaled(500, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _metadata_finished(self, path: str, data: dict):
        if path != self.selected_path:
            return
        self.metadata_cache[path] = data
        if data.get("error"):
            self.detail_preview.setText("Preview beschikbaar • FFprobe: fout")
            self.status.setText(f"FFprobe: {data['error']}")
            return
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        fmt = data.get("format", {})
        resolution = "—"
        if video.get("width") and video.get("height"):
            resolution = f"{video['width']} × {video['height']}"
        self.detail_labels["duration"].setText(format_duration(fmt.get("duration")))
        self.detail_labels["resolution"].setText(resolution)
        self.detail_labels["video_codec"].setText(str(video.get("codec_name") or "—").upper())
        self.detail_labels["fps"].setText(format_fps(str(video.get("r_frame_rate") or "")))
        self.detail_labels["video_bitrate"].setText(format_rate(video.get("bit_rate")))
        self.detail_labels["audio_codec"].setText(str(audio.get("codec_name") or "—").upper())
        channels = audio.get("channels")
        self.detail_labels["channels"].setText(str(channels) if channels else "—")
        self.detail_labels["sample_rate"].setText(f"{audio['sample_rate']} Hz" if audio.get("sample_rate") else "—")
        self.detail_labels["container"].setText(str(fmt.get("format_name") or self._extension_for(path)).upper())
        self.detail_preview.setText("")
        self.status.setText("Metadata geladen.")

    def _extension_for(self, path: str) -> str:
        return Path(path).suffix.lstrip(".") or "—"

    def clear_details(self):
        self.detail_title.setText("Geen video geselecteerd")
        self.detail_preview.setPixmap(QPixmap())
        self.detail_preview.setText("Selecteer een video")
        self.detail_path.setText("")
        for label in self.detail_labels.values():
            label.setText("—")
        self.play_button.setEnabled(False)
        self.folder_button.setEnabled(False)
        self.analyze_button.setEnabled(False)

    def play_selected(self):
        if self.selected_path:
            self.open_video(self.selected_path)

    def open_video(self, path: str):
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Video openen", "Het videobestand bestaat niet meer.")
            return
        playlist = [item.path for item in self._visible_items() if os.path.isfile(item.path)]
        if path not in playlist:
            playlist.insert(0, path)
        try:
            window = VideoPlayerWindow(path, self, playlist=playlist)
            self.player_windows.append(window)
            window.destroyed.connect(lambda: self.player_windows.remove(window) if window in self.player_windows else None)
            window.show()
            window.raise_()
            window.activateWindow()
        except Exception as exc:
            QMessageBox.critical(self, "Video Player", f"De ingebouwde speler kon niet worden geopend:\n\n{exc}")

    def open_selected_folder(self):
        if not self.selected_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.selected_path).parent)))

    def analyze_selected(self):
        if not self.selected_path:
            return
        try:
            from main import MainWindow as ScannerWindow
            window = ScannerWindow()
            window.folder.setText(str(Path(self.selected_path).parent))
            window.show()
            window.raise_()
            window.activateWindow()
            self._scanner_window = window
        except Exception as exc:
            QMessageBox.critical(self, "Media Scanner", f"De Media Scanner kon niet worden geopend:\n\n{exc}")

    def closeEvent(self, event):
        self.thread_pool.clear()
        self.thread_pool.waitForDone(1500)
        for window in list(self.player_windows):
            try:
                window.close()
            except RuntimeError:
                pass
        scanner = getattr(self, "_scanner_window", None)
        if scanner is not None:
            try:
                scanner.close()
            except RuntimeError:
                pass
        event.accept()


if __name__ == "__main__":
    app = QApplication([])
    window = VideoLibraryWindow()
    window.show()
    app.exec()
