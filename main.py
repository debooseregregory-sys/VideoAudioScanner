from __future__ import annotations

import csv
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView
)

from scanner import MediaScanner, MediaResult


class ScanWorker(QObject):
    result = Signal(object)
    progress = Signal(int, int)
    finished = Signal()
    error = Signal(str)

    def __init__(self, folder: str):
        super().__init__()
        self.folder = folder
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            scanner = MediaScanner()
            results = []
            for index, item in enumerate(scanner.scan(self.folder), 1):
                if self._cancel:
                    break
                results.append(item)
                self.result.emit(item)
                self.progress.emit(index, scanner.last_total)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    HEADERS = ["Name", "Type", "Duration", "Resolution", "Video codec", "Audio codec", "Size", "Status"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoAudioScanner")
        self.resize(1200, 720)
        self.results: list[MediaResult] = []
        self.thread: Optional[QThread] = None
        self.worker: Optional[ScanWorker] = None
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        title = QLabel("VideoAudioScanner")
        title.setObjectName("title")
        subtitle = QLabel("Scan video- en audiobestanden met FFprobe en exporteer de resultaten naar CSV.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Kies een map om te scannen…")
        browse = QPushButton("Bladeren…")
        browse.clicked.connect(self.choose_folder)
        self.scan_button = QPushButton("▶  Scan starten")
        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_button = QPushButton("■  Stop")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_scan)
        self.export_button = QPushButton("CSV exporteren")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_csv)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        row.addWidget(self.scan_button)
        row.addWidget(self.cancel_button)
        row.addWidget(self.export_button)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.status = QLabel("Klaar om te scannen.")
        layout.addWidget(self.status)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background: #17191d; color: #e7e9ed; font-size: 13px; }
            QMainWindow { background: #111317; }
            QLabel#title { font-size: 28px; font-weight: 700; color: #ffffff; padding-top: 6px; }
            QLabel#subtitle { color: #9da3ad; padding-bottom: 8px; }
            QLineEdit, QTableWidget { background: #202329; border: 1px solid #343941; border-radius: 6px; }
            QLineEdit { padding: 9px; }
            QPushButton { background: #2b3038; border: 1px solid #404650; border-radius: 6px; padding: 9px 14px; }
            QPushButton:hover { background: #353b45; }
            QPushButton:disabled { color: #666b73; background: #202329; }
            QProgressBar { background: #202329; border: 1px solid #343941; border-radius: 5px; height: 18px; text-align: center; }
            QProgressBar::chunk { background: #4f8cff; border-radius: 4px; }
            QHeaderView::section { background: #252931; color: #cfd4dc; padding: 7px; border: 0; }
            QTableWidget { gridline-color: #30343b; }
            QTableWidget::item { padding: 5px; }
            QTableWidget::item:selected { background: #304a70; }
        """)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies een map")
        if folder:
            self.folder.setText(folder)

    def start_scan(self):
        folder = self.folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Map ontbreekt", "Kies eerst een geldige map.")
            return
        self.results.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.status.setText("Scan wordt voorbereid…")
        self.scan_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.thread = QThread(self)
        self.worker = ScanWorker(folder)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.result.connect(self.add_result)
        self.worker.progress.connect(self.update_progress)
        self.worker.error.connect(lambda text: QMessageBox.critical(self, "Scanfout", text))
        self.worker.finished.connect(self.scan_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel()
            self.status.setText("Stoppen na het huidige bestand…")

    def add_result(self, item: MediaResult):
        self.results.append(item)
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [item.name, item.media_type, item.duration_text, item.resolution, item.video_codec,
                  item.audio_codec, item.size_text, item.status]
        for col, value in enumerate(values):
            self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.scrollToBottom()

    def update_progress(self, current: int, total: int):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(current)
        self.status.setText(f"Scannen: {current}/{total}")

    def scan_finished(self):
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.export_button.setEnabled(bool(self.results))
        self.status.setText(f"Klaar — {len(self.results)} bestanden verwerkt.")
        self.worker = None
        self.thread = None

    def export_csv(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV opslaan", "video_audio_scan.csv", "CSV-bestanden (*.csv)")
        if not path:
            return
        fields = list(asdict(self.results[0]).keys())
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(asdict(item) for item in self.results)
            self.status.setText(f"CSV opgeslagen: {Path(path).name}")
        except OSError as exc:
            QMessageBox.critical(self, "Exportfout", str(exc))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VideoAudioScanner")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
