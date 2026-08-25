from __future__ import annotations

import csv
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal, QSortFilterProxyModel, QAbstractTableModel, QModelIndex, QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QTableView, QVBoxLayout, QWidget,
    QHeaderView, QComboBox, QGroupBox, QGridLayout, QDialog, QDialogButtonBox,
    QFormLayout
)

from scanner import MediaScanner, MediaResult


class ResultsModel(QAbstractTableModel):
    HEADERS = ["Naam", "Type", "Duur", "Resolutie", "Video codec", "Audio codec", "Grootte", "Status"]

    def __init__(self):
        super().__init__()
        self.items: list[MediaResult] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.items)):
            return None
        item = self.items[index.row()]
        values = [item.name, item.media_type, item.duration_text, item.resolution,
                  item.video_codec, item.audio_codec, item.size_text, item.status]
        if role == Qt.ItemDataRole.DisplayRole:
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 0:
            return item.path
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def add(self, item: MediaResult):
        row = len(self.items)
        self.beginInsertRows(QModelIndex(), row, row)
        self.items.append(item)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self.items.clear()
        self.endResetModel()


class FilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text_filter = ""
        self.type_filter = "Alle"
        self.status_filter = "Alle"
        self.setDynamicSortFilter(True)

    def set_filters(self, text: str, media_type: str, status: str):
        self.text_filter = text.casefold().strip()
        self.type_filter = media_type
        self.status_filter = status
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        item = model.items[source_row]
        if self.type_filter != "Alle" and item.media_type != self.type_filter:
            return False
        if self.status_filter == "Fouten" and item.status == "OK":
            return False
        if self.status_filter == "OK" and item.status != "OK":
            return False
        if self.text_filter:
            haystack = " ".join([item.name, item.path, item.media_type, item.resolution,
                                  item.video_codec, item.audio_codec, item.status]).casefold()
            if self.text_filter not in haystack:
                return False
        return True


class ScanWorker(QObject):
    result = Signal(object)
    progress = Signal(int, int)
    finished = Signal(bool)
    error = Signal(str)

    def __init__(self, folder: str):
        super().__init__()
        self.folder = folder
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        cancelled = False
        try:
            scanner = MediaScanner()
            for index, item in enumerate(scanner.scan(self.folder), 1):
                if self._cancel:
                    cancelled = True
                    break
                self.result.emit(item)
                self.progress.emit(index, scanner.last_total)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit(cancelled)


class FFprobeDialog(QDialog):
    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FFprobe instellingen")
        self.resize(650, 150)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.path_edit = QLineEdit(current)
        self.path_edit.setPlaceholderText("Automatisch detecteren als dit leeg is")
        browse = QPushButton("Bladeren…")
        browse.clicked.connect(self.browse)
        row = QHBoxLayout()
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        form.addRow("FFprobe:", row)
        layout.addLayout(form)
        self.info = QLabel("Laat leeg om automatische detectie te gebruiken.")
        self.info.setObjectName("status")
        layout.addWidget(self.info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Kies ffprobe", "", "FFprobe (ffprobe.exe ffprobe);;Alle bestanden (*)")
        if path:
            self.path_edit.setText(path)

    def value(self) -> str:
        return self.path_edit.text().strip()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("VideoAudioScanner", "VideoAudioScanner")
        self.setWindowTitle("VideoAudioScanner")
        self.resize(1450, 820)
        self.model = ResultsModel()
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.thread: Optional[QThread] = None
        self.worker: Optional[ScanWorker] = None
        self.scan_total = 0
        self._build_ui()
        self._build_menu()
        self._apply_theme()
        self._restore_state()
        self.refresh_ffprobe_status()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title = QLabel("VideoAudioScanner")
        title.setObjectName("title")
        subtitle = QLabel("Analyseer video- en audiobestanden met FFprobe")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        source_box = QGroupBox("Scanlocatie")
        source_layout = QHBoxLayout(source_box)
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Kies een map om recursief te scannen…")
        self.folder.returnPressed.connect(self.start_scan)
        browse = QPushButton("Bladeren…")
        browse.clicked.connect(self.choose_folder)
        self.scan_button = QPushButton("▶  Scan starten")
        self.scan_button.setObjectName("primary")
        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_button = QPushButton("■  Stop")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_scan)
        self.export_button = QPushButton("CSV exporteren")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_csv)
        source_layout.addWidget(self.folder, 1)
        source_layout.addWidget(browse)
        source_layout.addWidget(self.scan_button)
        source_layout.addWidget(self.cancel_button)
        source_layout.addWidget(self.export_button)
        layout.addWidget(source_box)

        ff_box = QGroupBox("FFprobe")
        ff_layout = QHBoxLayout(ff_box)
        self.ffprobe_status = QLabel("Controleren…")
        self.ffprobe_status.setObjectName("ffprobeStatus")
        self.ffprobe_path = QLabel("")
        self.ffprobe_path.setObjectName("status")
        ff_layout.addWidget(self.ffprobe_status)
        ff_layout.addWidget(self.ffprobe_path, 1)
        ff_settings = QPushButton("Instellingen…")
        ff_settings.clicked.connect(self.configure_ffprobe)
        ff_layout.addWidget(ff_settings)
        layout.addWidget(ff_box)

        stats = QGroupBox("Scanstatistieken")
        stats_layout = QGridLayout(stats)
        self.total_label = self._stat_label("0")
        self.video_label = self._stat_label("0")
        self.audio_label = self._stat_label("0")
        self.error_label = self._stat_label("0")
        self.size_label = self._stat_label("0 B")
        for col, (caption, widget) in enumerate([
            ("Totaal", self.total_label), ("Video", self.video_label),
            ("Audio", self.audio_label), ("Fouten", self.error_label),
            ("Totale grootte", self.size_label)
        ]):
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(4, 2, 4, 2)
            label = QLabel(caption)
            label.setObjectName("statCaption")
            box_layout.addWidget(label)
            box_layout.addWidget(widget)
            stats_layout.addWidget(box, 0, col)
        layout.addWidget(stats)

        filter_box = QGroupBox("Filter resultaten")
        filter_layout = QHBoxLayout(filter_box)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Zoeken op naam, pad, codec, resolutie…")
        self.search.textChanged.connect(self.apply_filters)
        self.type_filter = QComboBox()
        self.type_filter.addItems(["Alle", "Video", "Audio"])
        self.type_filter.currentTextChanged.connect(self.apply_filters)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Alle", "OK", "Fouten"])
        self.status_filter.currentTextChanged.connect(self.apply_filters)
        clear = QPushButton("Filters wissen")
        clear.clicked.connect(self.clear_filters)
        filter_layout.addWidget(self.search, 1)
        filter_layout.addWidget(QLabel("Type:"))
        filter_layout.addWidget(self.type_filter)
        filter_layout.addWidget(QLabel("Status:"))
        filter_layout.addWidget(self.status_filter)
        filter_layout.addWidget(clear)
        layout.addWidget(filter_box)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v / %m")
        layout.addWidget(self.progress)
        self.status = QLabel("Klaar om te scannen.")
        self.status.setObjectName("status")
        layout.addWidget(self.status)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self.open_selected)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate([330, 80, 95, 120, 120, 120, 110, 250]):
            self.table.setColumnWidth(col, width)
        layout.addWidget(self.table, 1)
        self.setCentralWidget(root)

    @staticmethod
    def _stat_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("statValue")
        return label

    def _build_menu(self):
        menu = self.menuBar().addMenu("Bestand")
        export = QAction("CSV exporteren", self)
        export.triggered.connect(self.export_csv)
        menu.addAction(export)
        open_file = QAction("Geselecteerd bestand openen", self)
        open_file.triggered.connect(self.open_selected)
        menu.addAction(open_file)
        menu.addSeparator()
        ff = QAction("FFprobe instellingen", self)
        ff.triggered.connect(self.configure_ffprobe)
        menu.addAction(ff)
        menu.addSeparator()
        quit_action = QAction("Afsluiten", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background: #15171b; color: #e8eaed; font-size: 13px; }
            QMainWindow, QMenuBar, QMenu { background: #101216; }
            QMenuBar::item { padding: 7px 12px; }
            QMenu::item { padding: 7px 22px; }
            QLabel#title { font-size: 30px; font-weight: 700; color: #ffffff; }
            QLabel#subtitle { color: #8f96a3; margin-bottom: 2px; }
            QGroupBox { border: 1px solid #30343c; border-radius: 8px; margin-top: 8px; padding: 10px 8px 8px 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #aeb5c0; }
            QLineEdit, QComboBox, QTableView { background: #1e2127; border: 1px solid #353a43; border-radius: 6px; }
            QLineEdit { padding: 9px; }
            QComboBox { padding: 7px 10px; min-width: 90px; }
            QPushButton { background: #292e36; border: 1px solid #3c424c; border-radius: 6px; padding: 9px 14px; }
            QPushButton:hover { background: #353b45; }
            QPushButton#primary { background: #315f9e; border-color: #4679bd; font-weight: 600; }
            QPushButton#primary:hover { background: #3b70b6; }
            QPushButton:disabled { color: #666c75; background: #202329; }
            QProgressBar { background: #1e2127; border: 1px solid #353a43; border-radius: 5px; height: 18px; text-align: center; }
            QProgressBar::chunk { background: #477dcc; border-radius: 4px; }
            QHeaderView::section { background: #252a31; color: #cfd4dc; padding: 8px; border: 0; border-right: 1px solid #343941; }
            QTableView { gridline-color: #30343b; }
            QTableView::item { padding: 6px; }
            QTableView::item:selected { background: #304a70; }
            QLabel#status { color: #aeb5c0; padding: 2px 4px; }
            QLabel#statCaption { color: #858c98; }
            QLabel#statValue { font-size: 19px; font-weight: 700; color: #ffffff; }
            QLabel#ffprobeStatus { font-weight: 700; }
        """)

    def _restore_state(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.folder.setText(str(self.settings.value("folder", "")))

    def _configured_ffprobe(self) -> str:
        return str(self.settings.value("ffprobe", "")).strip()

    def _make_scanner(self) -> MediaScanner:
        scanner = MediaScanner()
        configured = self._configured_ffprobe()
        if configured and os.path.isfile(configured):
            scanner.ffprobe = configured
        return scanner

    def refresh_ffprobe_status(self):
        scanner = self._make_scanner()
        if scanner.ffprobe:
            self.ffprobe_status.setText("● FFprobe gevonden")
            self.ffprobe_status.setStyleSheet("color: #65c47a; font-weight: 700;")
            self.ffprobe_path.setText(scanner.ffprobe)
        else:
            self.ffprobe_status.setText("● FFprobe niet gevonden")
            self.ffprobe_status.setStyleSheet("color: #e26d6d; font-weight: 700;")
            self.ffprobe_path.setText("Installeer FFmpeg of kies handmatig een ffprobe executable.")

    def configure_ffprobe(self):
        dialog = FFprobeDialog(self._configured_ffprobe(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.value()
        if value and not os.path.isfile(value):
            QMessageBox.warning(self, "FFprobe", "Het gekozen bestand bestaat niet.")
            return
        self.settings.setValue("ffprobe", value)
        self.refresh_ffprobe_status()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies een map")
        if folder:
            self.folder.setText(folder)

    def start_scan(self):
        folder = self.folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Map ontbreekt", "Kies eerst een geldige map.")
            return
        if self.thread and self.thread.isRunning():
            return
        scanner = self._make_scanner()
        if not scanner.ffprobe:
            answer = QMessageBox.warning(self, "FFprobe ontbreekt", "FFprobe is niet gevonden. Je kunt de scan toch starten, maar mediagegevens kunnen niet worden uitgelezen.\n\nWil je eerst FFprobe instellen?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                self.configure_ffprobe()
                scanner = self._make_scanner()
                if not scanner.ffprobe:
                    return
        self.model.clear()
        self.progress.setValue(0)
        self.progress.setMaximum(0)
        self._update_stats()
        self.status.setText("Scan wordt voorbereid…")
        self.scan_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.thread = QThread(self)
        self.worker = ScanWorker(folder)
        self.worker.scanner_override = scanner
        original_run = self.worker.run
        def run_with_scanner():
            cancelled = False
            try:
                for index, item in enumerate(scanner.scan(folder), 1):
                    if self.worker._cancel:
                        cancelled = True
                        break
                    self.worker.result.emit(item)
                    self.worker.progress.emit(index, scanner.last_total)
            except Exception as exc:
                self.worker.error.emit(str(exc))
            finally:
                self.worker.finished.emit(cancelled)
        self.worker.run = run_with_scanner
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.result.connect(self.add_result)
        self.worker.progress.connect(self.update_progress)
        self.worker.error.connect(self.show_scan_error)
        self.worker.finished.connect(self.scan_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("Stoppen na het huidige bestand…")

    def add_result(self, item: MediaResult):
        self.model.add(item)
        self._update_stats()

    def update_progress(self, current: int, total: int):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(current)
        name = self.model.items[-1].name if self.model.items else ""
        self.status.setText(f"Scannen: {current}/{total} — {name}")

    def scan_finished(self, cancelled: bool):
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.export_button.setEnabled(bool(self.model.items))
        if cancelled:
            self.status.setText(f"Scan gestopt — {len(self.model.items)} bestanden verwerkt.")
        else:
            self.status.setText(f"Klaar — {len(self.model.items)} bestanden verwerkt.")
        self.worker = None
        self.thread = None

    def show_scan_error(self, text: str):
        QMessageBox.critical(self, "Scanfout", text)

    def apply_filters(self):
        self.proxy.set_filters(self.search.text(), self.type_filter.currentText(), self.status_filter.currentText())
        self.status.setText(f"{self.proxy.rowCount()} van {len(self.model.items)} resultaten zichtbaar.")

    def clear_filters(self):
        self.search.clear()
        self.type_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)

    def _update_stats(self):
        items = self.model.items
        self.total_label.setText(str(len(items)))
        self.video_label.setText(str(sum(i.media_type == "Video" for i in items)))
        self.audio_label.setText(str(sum(i.media_type == "Audio" for i in items)))
        self.error_label.setText(str(sum(i.status != "OK" for i in items)))
        self.size_label.setText(self._format_size(sum(i.size_bytes for i in items)))

    @staticmethod
    def _format_size(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{value} B"

    def _selected_item(self) -> Optional[MediaResult]:
        index = self.table.currentIndex()
        if not index.isValid():
            return None
        source = self.proxy.mapToSource(index)
        return self.model.items[source.row()] if source.isValid() else None

    def open_selected(self, *_):
        item = self._selected_item()
        if not item:
            return
        if not os.path.exists(item.path):
            QMessageBox.warning(self, "Bestand ontbreekt", f"Het bestand bestaat niet meer:\n{item.path}")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(item.path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", item.path])
            else:
                subprocess.Popen(["xdg-open", item.path])
        except OSError as exc:
            QMessageBox.critical(self, "Openen mislukt", str(exc))

    def export_csv(self):
        if not self.model.items:
            QMessageBox.information(self, "Geen resultaten", "Voer eerst een scan uit.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV opslaan", "video_audio_scan.csv", "CSV-bestanden (*.csv)")
        if not path:
            return
        fields = list(asdict(self.model.items[0]).keys())
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(asdict(item) for item in self.model.items)
            self.status.setText(f"CSV opgeslagen: {Path(path).name}")
        except OSError as exc:
            QMessageBox.critical(self, "Exportfout", str(exc))

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("folder", self.folder.text())
        if self.worker and self.thread and self.thread.isRunning():
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait(3000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VideoAudioScanner")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
