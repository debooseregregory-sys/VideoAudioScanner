from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from scanner import VIDEO_EXTENSIONS, MediaScanner


@dataclass
class QualityResult:
    path: str
    name: str
    resolution: str
    bitrate: str
    duration: str
    video_codec: str
    audio_codec: str
    fps: str
    size: str
    score: int
    grade: str
    status: str


def _number(text: str) -> float:
    try:
        return float(text.replace(".", "", 1).replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def _resolution(value: str) -> tuple[int, int]:
    try:
        left, right = value.replace("×", "x").split("x", 1)
        return int(left.strip()), int(right.strip())
    except (ValueError, AttributeError):
        return 0, 0


def _bitrate(value: str) -> float:
    try:
        return float(value.split()[0].replace(",", "."))
    except (ValueError, IndexError, AttributeError):
        return 0.0


def calculate_quality(result) -> tuple[int, str]:
    width, height = _resolution(result.resolution)
    pixels = width * height
    bitrate = _bitrate(result.bitrate)
    fps = _number(result.fps)
    score = 0.0
    if pixels >= 3840 * 2160:
        score += 50
    elif pixels >= 2560 * 1440:
        score += 44
    elif pixels >= 1920 * 1080:
        score += 38
    elif pixels >= 1280 * 720:
        score += 28
    elif pixels >= 854 * 480:
        score += 18
    elif pixels:
        score += 8
    if bitrate >= 20000:
        score += 25
    elif bitrate >= 10000:
        score += 21
    elif bitrate >= 6000:
        score += 17
    elif bitrate >= 3000:
        score += 12
    elif bitrate >= 1500:
        score += 7
    codec = (result.video_codec or "").casefold()
    if codec in {"hevc", "h265", "av1"}:
        score += 10
    elif codec in {"h264", "avc1", "vp9"}:
        score += 8
    elif codec:
        score += 5
    if fps >= 50:
        score += 7
    elif fps >= 24:
        score += 5
    elif fps > 0:
        score += 2
    if result.audio_codec not in {"—", ""}:
        score += 3
    score = max(0, min(100, round(score)))
    grade = "A+" if score >= 95 else "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "E"
    return int(score), grade


class QualityWorker(QThread):
    progress = Signal(int, int)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, folder: str, ffprobe: str | None):
        super().__init__()
        self.folder = folder
        self.ffprobe = ffprobe

    def run(self):
        try:
            scanner = MediaScanner(self.ffprobe)
            paths = sorted((p for p in Path(self.folder).rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS), key=lambda p: str(p).casefold())
            total = len(paths)
            for index, path in enumerate(paths, 1):
                item = scanner._inspect(path)
                score, grade = calculate_quality(item)
                self.result.emit(QualityResult(item.path, item.name, item.resolution, item.bitrate, item.duration_text, item.video_codec, item.audio_codec, item.fps, item.size_text, score, grade, item.status))
                self.progress.emit(index, total)
        except Exception as exc:
            self.error.emit(str(exc))


class QualityAnalyzerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner — Quality Analyzer")
        self.resize(1450, 820)
        self.worker: QualityWorker | None = None
        self.rows: list[QualityResult] = []
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("QUALITY ANALYZER")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        credit = QLabel("MADE BY KID ACID")
        credit.setObjectName("credit")
        header.addWidget(credit)
        layout.addLayout(header)
        info = QLabel("Beoordeel videokwaliteit op basis van resolutie, bitrate, codec, FPS en audio. De score is een praktische vergelijking en geen objectieve beeldkwaliteitsmeting.")
        info.setWordWrap(True)
        info.setObjectName("subtitle")
        layout.addWidget(info)
        source = QFrame()
        source.setObjectName("panel")
        source_layout = QHBoxLayout(source)
        self.folder = QLabel("Geen map gekozen")
        self.folder.setObjectName("path")
        choose = QPushButton("Bladeren…")
        choose.clicked.connect(self.choose_folder)
        self.scan_button = QPushButton("📊 Analyse starten")
        self.scan_button.setObjectName("primary")
        self.scan_button.clicked.connect(self.start_scan)
        source_layout.addWidget(self.folder, 1)
        source_layout.addWidget(choose)
        source_layout.addWidget(self.scan_button)
        layout.addWidget(source)
        stats = QFrame()
        stats.setObjectName("panel")
        stats_layout = QHBoxLayout(stats)
        self.total = QLabel("0")
        self.avg = QLabel("0")
        self.best = QLabel("—")
        self.lowest = QLabel("—")
        for caption, widget in (("Video's", self.total), ("Gemiddelde score", self.avg), ("Beste", self.best), ("Laagste", self.lowest)):
            box = QVBoxLayout()
            label = QLabel(caption)
            label.setObjectName("statCaption")
            widget.setObjectName("statValue")
            box.addWidget(label)
            box.addWidget(widget)
            stats_layout.addLayout(box)
            stats_layout.addStretch(1)
        layout.addWidget(stats)
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m")
        layout.addWidget(self.progress)
        self.status = QLabel("Klaar om te analyseren.")
        self.status.setObjectName("status")
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["Score", "Grade", "Bestand", "Resolutie", "Bitrate", "Duur", "Video codec", "Audio codec", "FPS", "Grootte", "Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for index, width in enumerate([75, 70, 360, 120, 110, 90, 105, 105, 80, 105, 230]):
            self.table.setColumnWidth(index, width)
        self.table.cellDoubleClicked.connect(self.open_selected)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        export = QPushButton("CSV exporteren")
        export.clicked.connect(self.export_csv)
        open_button = QPushButton("Openen in Windows")
        open_button.clicked.connect(self.open_selected)
        actions.addWidget(export)
        actions.addWidget(open_button)
        actions.addStretch(1)
        close = QPushButton("Sluiten")
        close.clicked.connect(self.close)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background:#15171b; color:#e8eaed; font-size:13px; }
            QMainWindow { background:#101216; }
            QLabel#title { font-size:28px; font-weight:800; color:#fff; }
            QLabel#credit { font-size:17px; font-weight:800; padding:9px 14px; background:#15181d; border:1px solid #3d434d; border-radius:8px; }
            QLabel#subtitle { color:#929aa7; padding-bottom:5px; }
            QFrame#panel { background:#191c22; border:1px solid #303640; border-radius:9px; }
            QLabel#path { color:#c8ccd3; padding:7px; }
            QLabel#statCaption { color:#858c98; }
            QLabel#statValue { font-size:20px; font-weight:800; color:#fff; }
            QLabel#status { color:#aeb5c0; }
            QPushButton { background:#292e36; border:1px solid #3c424c; border-radius:6px; padding:9px 14px; font-weight:600; }
            QPushButton:hover { background:#353b45; }
            QPushButton#primary { background:#315f9e; border-color:#4679bd; }
            QTableWidget { background:#1e2127; border:1px solid #353a43; gridline-color:#30343c; }
            QHeaderView::section { background:#252a31; color:#cfd4dc; padding:8px; border:0; }
            QTableWidget::item:selected { background:#304a70; }
            QProgressBar { background:#1e2127; border:1px solid #353a43; border-radius:5px; height:18px; text-align:center; }
            QProgressBar::chunk { background:#477dcc; border-radius:4px; }
        """)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies een map met video's")
        if folder:
            self.folder.setText(folder)

    def start_scan(self):
        folder = self.folder.text().strip()
        if not folder or folder == "Geen map gekozen" or not os.path.isdir(folder):
            QMessageBox.information(self, "Quality Analyzer", "Kies eerst een geldige map.")
            return
        if self.worker and self.worker.isRunning():
            return
        scanner = MediaScanner()
        if not scanner.ffprobe:
            QMessageBox.critical(self, "FFprobe", "FFprobe is niet gevonden.")
            return
        self.rows.clear()
        self.table.setRowCount(0)
        self.progress.setRange(0, 0)
        self.status.setText("Video's analyseren…")
        self.scan_button.setEnabled(False)
        self.worker = QualityWorker(folder, scanner.ffprobe)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.add_result)
        self.worker.finished.connect(self.scan_finished)
        self.worker.error.connect(self.scan_error)
        self.worker.start()

    def update_progress(self, current, total):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(current)
        self.status.setText(f"Video {current} van {total} analyseren…")

    def add_result(self, result: QualityResult):
        self.rows.append(result)
        self.table.setSortingEnabled(False)
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [str(result.score), result.grade, result.name, result.resolution, result.bitrate, result.duration, result.video_codec, result.audio_codec, result.fps, result.size, result.status]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, result.score)
            if column == 2:
                item.setToolTip(result.path)
                item.setData(Qt.ItemDataRole.UserRole, result.path)
            self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)

    def scan_finished(self):
        self.scan_button.setEnabled(True)
        self._update_stats()
        self.status.setText(f"Klaar — {len(self.rows)} video's geanalyseerd.")

    def scan_error(self, message):
        self.scan_button.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        QMessageBox.critical(self, "Quality Analyzer", message)
        self.status.setText("Analyse mislukt.")

    def _update_stats(self):
        if not self.rows:
            self.total.setText("0")
            self.avg.setText("0")
            self.best.setText("—")
            self.lowest.setText("—")
            return
        scores = [row.score for row in self.rows]
        best = max(self.rows, key=lambda row: row.score)
        lowest = min(self.rows, key=lambda row: row.score)
        self.total.setText(str(len(self.rows)))
        self.avg.setText(f"{sum(scores) / len(scores):.0f} / 100")
        self.best.setText(f"{best.grade} — {best.name}")
        self.lowest.setText(f"{lowest.grade} — {lowest.name}")

    def open_selected(self, row=None, _column=None):
        if row is None:
            row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 2)
        path = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not path:
            return
        try:
            os.startfile(path)
        except OSError as exc:
            QMessageBox.warning(self, "Openen", f"Kon bestand niet openen:\n{exc}")

    def export_csv(self):
        if not self.rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV exporteren", "QualityAnalyzer.csv", "CSV-bestanden (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["Score", "Grade", "Bestand", "Pad", "Resolutie", "Bitrate", "Duur", "Video codec", "Audio codec", "FPS", "Grootte", "Status"])
            for row in self.rows:
                writer.writerow([row.score, row.grade, row.name, row.path, row.resolution, row.bitrate, row.duration, row.video_codec, row.audio_codec, row.fps, row.size, row.status])
        self.status.setText(f"CSV opgeslagen: {path}")


def main():
    app = QApplication(sys.argv)
    window = QualityAnalyzerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
