from __future__ import annotations

import csv
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QObject, QSettings,
    QSortFilterProxyModel, Qt, QThread, Signal,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableView, QVBoxLayout, QWidget,
)

from duplicate_finder import DuplicateFinderWindow
from duplicate_fixes import install_fixes
from scanner import MediaResult, MediaScanner

# Apply duplicate-video improvements from the real application startup path.
install_fixes()


class ResultsModel(QAbstractTableModel):
    HEADERS = ["Naam", "Type", "Duur", "Resolutie", "Video codec", "Audio codec", "Bitrate", "Sample rate", "Kanalen", "FPS", "Container", "Grootte", "Status"]

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
        values = [item.name, item.media_type, item.duration_text, item.resolution, item.video_codec, item.audio_codec, item.bitrate, item.sample_rate, item.channels, item.fps, item.container, item.size_text, item.status]
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
        self.beginResetModel(); self.items.clear(); self.endResetModel()

    def remove_paths(self, paths: set[str]):
        if not paths: return
        self.beginResetModel()
        self.items = [item for item in self.items if item.path not in paths]
        self.endResetModel()


class FilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__(); self.text_filter = ""; self.type_filter = "Alle"; self.status_filter = "Alle"; self.setDynamicSortFilter(True)

    def set_filters(self, text: str, media_type: str, status: str):
        self.text_filter = text.casefold().strip(); self.type_filter = media_type; self.status_filter = status; self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        item = self.sourceModel().items[source_row]
        if self.type_filter != "Alle" and item.media_type != self.type_filter: return False
        if self.status_filter == "Fouten" and item.status == "OK": return False
        if self.status_filter == "OK" and item.status != "OK": return False
        if self.text_filter:
            haystack = " ".join([item.name, item.path, item.media_type, item.resolution, item.video_codec, item.audio_codec, item.bitrate, item.sample_rate, item.channels, item.fps, item.container, item.status]).casefold()
            if self.text_filter not in haystack: return False
        return True


class ScanWorker(QObject):
    result = Signal(object); progress = Signal(int, int); finished = Signal(bool); error = Signal(str)
    def __init__(self, folder: str, ffprobe: str | None = None):
        super().__init__(); self.folder = folder; self.ffprobe = ffprobe; self._cancel = False
    def cancel(self): self._cancel = True
    def run(self):
        cancelled = False
        try:
            scanner = MediaScanner(self.ffprobe)
            for index, item in enumerate(scanner.scan(self.folder), 1):
                if self._cancel: cancelled = True; break
                self.result.emit(item); self.progress.emit(index, scanner.last_total)
        except Exception as exc: self.error.emit(str(exc))
        finally: self.finished.emit(cancelled)


class FFprobeDialog(QDialog):
    def __init__(self, current: str, parent=None):
        super().__init__(parent); self.setWindowTitle("FFprobe instellingen"); self.resize(650, 150)
        layout = QVBoxLayout(self); form = QFormLayout(); self.path_edit = QLineEdit(current); self.path_edit.setPlaceholderText("Automatisch detecteren als dit leeg is")
        browse = QPushButton("Bladeren…"); browse.clicked.connect(self.browse); row = QHBoxLayout(); row.addWidget(self.path_edit, 1); row.addWidget(browse); form.addRow("FFprobe:", row); layout.addLayout(form)
        self.info = QLabel("Laat leeg om automatische detectie te gebruiken."); self.info.setObjectName("status"); layout.addWidget(self.info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Kies ffprobe", "", "FFprobe (ffprobe.exe ffprobe);;Alle bestanden (*)")
        if path: self.path_edit.setText(path)
    def value(self) -> str: return self.path_edit.text().strip()


def move_to_recycle_bin(paths: list[str]) -> tuple[list[str], list[str]]:
    if not paths: return [], []
    if os.name != "nt": raise RuntimeError("Windows Prullenbak is alleen beschikbaar op Windows.")
    import ctypes
    from ctypes import wintypes
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR), ("fFlags", wintypes.UINT), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", wintypes.LPVOID), ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE = 0x0003; FOF_SILENT = 0x0004; FOF_NOCONFIRMATION = 0x0010; FOF_ALLOWUNDO = 0x0040; FOF_NOERRORUI = 0x0400
    existing, failed = [], []
    for path in paths:
        try:
            (existing if Path(path).is_file() else failed).append(path)
        except OSError: failed.append(path)
    if not existing: return [], failed
    source = "".join(path + "\0" for path in existing) + "\0"
    operation = SHFILEOPSTRUCTW(None, FO_DELETE, source, None, FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI, False, None, None)
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted: return [], failed + existing
    return existing, failed


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.settings = QSettings("VideoAudioScanner", "VideoAudioScanner"); self.setWindowTitle("VideoAudioScanner"); self.resize(1550, 850)
        self.model = ResultsModel(); self.proxy = FilterProxy(); self.proxy.setSourceModel(self.model); self.thread: Optional[QThread] = None; self.worker: Optional[ScanWorker] = None; self.duplicate_window: Optional[DuplicateFinderWindow] = None
        self._build_ui(); self._build_menu(); self._apply_theme(); self._restore_state(); self.refresh_ffprobe_status(); self._update_action_state()

    def _build_ui(self):
        root = QWidget(); layout = QVBoxLayout(root); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("VideoAudioScanner"); title.setObjectName("title")
        credit = QLabel("Made by Kid Acid"); credit.setObjectName("credit")
        header.addWidget(title); header.addStretch(1); header.addWidget(credit)
        layout.addLayout(header)
        subtitle = QLabel("Analyseer video- en audiobestanden met FFprobe"); subtitle.setObjectName("subtitle"); layout.addWidget(subtitle)
        source_box = QGroupBox("Scanlocatie"); source_layout = QHBoxLayout(source_box); self.folder = QLineEdit(); self.folder.setPlaceholderText("Kies een map om recursief te scannen…"); self.folder.returnPressed.connect(self.start_scan)
        browse = QPushButton("Bladeren…"); browse.clicked.connect(self.choose_folder); self.scan_button = QPushButton("▶  Scan starten"); self.scan_button.setObjectName("primary"); self.scan_button.clicked.connect(self.start_scan); self.duplicate_button = QPushButton("🎞  Dubbele video's"); self.duplicate_button.setObjectName("secondary"); self.duplicate_button.clicked.connect(self.open_duplicate_finder); self.cancel_button = QPushButton("■  Stop"); self.cancel_button.setEnabled(False); self.cancel_button.clicked.connect(self.cancel_scan); self.export_button = QPushButton("CSV exporteren"); self.export_button.setEnabled(False); self.export_button.clicked.connect(self.export_csv)
        source_layout.addWidget(self.folder, 1); source_layout.addWidget(browse); source_layout.addWidget(self.scan_button); source_layout.addWidget(self.duplicate_button); source_layout.addWidget(self.cancel_button); source_layout.addWidget(self.export_button); layout.addWidget(source_box)
        ff_box = QGroupBox("FFprobe"); ff_layout = QHBoxLayout(ff_box); self.ffprobe_status = QLabel("Controleren…"); self.ffprobe_status.setObjectName("ffprobeStatus"); self.ffprobe_path = QLabel(""); self.ffprobe_path.setObjectName("status"); ff_layout.addWidget(self.ffprobe_status); ff_layout.addWidget(self.ffprobe_path, 1); ff_settings = QPushButton("Instellingen…"); ff_settings.clicked.connect(self.configure_ffprobe); ff_layout.addWidget(ff_settings); layout.addWidget(ff_box)
        stats = QGroupBox("Scanstatistieken"); stats_layout = QGridLayout(stats); self.total_label = self._stat_label("0"); self.video_label = self._stat_label("0"); self.audio_label = self._stat_label("0"); self.error_label = self._stat_label("0"); self.size_label = self._stat_label("0 B")
        for col, (caption, widget) in enumerate([("Totaal", self.total_label), ("Video", self.video_label), ("Audio", self.audio_label), ("Fouten", self.error_label), ("Totale grootte", self.size_label)]):
            box = QWidget(); box_layout = QVBoxLayout(box); box_layout.setContentsMargins(4, 2, 4, 2); label = QLabel(caption); label.setObjectName("statCaption"); box_layout.addWidget(label); box_layout.addWidget(widget); stats_layout.addWidget(box, 0, col)
        layout.addWidget(stats)
        filter_box = QGroupBox("Filter resultaten"); filter_layout = QHBoxLayout(filter_box); self.search = QLineEdit(); self.search.setPlaceholderText("Zoeken op naam, pad, codec, resolutie…"); self.search.textChanged.connect(self.apply_filters); self.type_filter = QComboBox(); self.type_filter.addItems(["Alle", "Video", "Audio"]); self.type_filter.currentTextChanged.connect(self.apply_filters); self.status_filter = QComboBox(); self.status_filter.addItems(["Alle", "OK", "Fouten"]); self.status_filter.currentTextChanged.connect(self.apply_filters); clear = QPushButton("Filters wissen"); clear.clicked.connect(self.clear_filters); self.select_all_button = QPushButton("Alles selecteren"); self.select_all_button.clicked.connect(self.select_all_visible); self.delete_button = QPushButton("🗑  Naar Prullenbak"); self.delete_button.setObjectName("danger"); self.delete_button.clicked.connect(self.delete_selected)
        filter_layout.addWidget(self.search, 1); filter_layout.addWidget(QLabel("Type:")); filter_layout.addWidget(self.type_filter); filter_layout.addWidget(QLabel("Status:")); filter_layout.addWidget(self.status_filter); filter_layout.addWidget(clear); filter_layout.addWidget(self.select_all_button); filter_layout.addWidget(self.delete_button); layout.addWidget(filter_box)
        self.progress = QProgressBar(); self.progress.setTextVisible(True); self.progress.setFormat("%v / %m"); layout.addWidget(self.progress); self.status = QLabel("Klaar om te scannen."); self.status.setObjectName("status"); layout.addWidget(self.status)
        self.table = QTableView(); self.table.setModel(self.proxy); self.table.setSortingEnabled(True); self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows); self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection); self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers); self.table.setAlternatingRowColors(True); self.table.doubleClicked.connect(self.open_selected); self.table.selectionModel().selectionChanged.connect(self._update_action_state)
        header = self.table.horizontalHeader(); header.setStretchLastSection(False); header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate([300, 75, 85, 115, 105, 105, 95, 105, 80, 80, 115, 105, 250]): self.table.setColumnWidth(col, width)
        layout.addWidget(self.table, 1); self.setCentralWidget(root)

    @staticmethod
    def _stat_label(text: str) -> QLabel:
        label = QLabel(text); label.setObjectName("statValue"); return label

    def _build_menu(self):
        menu = self.menuBar().addMenu("Bestand"); export = QAction("CSV exporteren", self); export.triggered.connect(self.export_csv); menu.addAction(export); open_file = QAction("Geselecteerde bestanden openen", self); open_file.triggered.connect(self.open_selected); menu.addAction(open_file); duplicate = QAction("Dubbele video's", self); duplicate.triggered.connect(self.open_duplicate_finder); menu.addAction(duplicate); menu.addSeparator(); self.delete_action = QAction("Geselecteerde bestanden naar Prullenbak", self); self.delete_action.triggered.connect(self.delete_selected); menu.addAction(self.delete_action); menu.addSeparator(); ff = QAction("FFprobe instellingen", self); ff.triggered.connect(self.configure_ffprobe); menu.addAction(ff); menu.addSeparator(); quit_action = QAction("Afsluiten", self); quit_action.triggered.connect(self.close); menu.addAction(quit_action)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background: #15171b; color: #e8eaed; font-size: 13px; }
            QMainWindow, QMenuBar, QMenu { background: #101216; }
            QMenuBar::item { padding: 7px 12px; } QMenu::item { padding: 7px 22px; }
            QLabel#title { font-size: 30px; font-weight: 700; color: #ffffff; }
            QLabel#subtitle { color: #8f96a3; margin-bottom: 2px; }
            QLabel#credit { color: #ffffff; font-size: 18px; font-weight: 700; padding: 7px 12px; background: #101216; border: 1px solid #2c3037; border-radius: 6px; }
            QGroupBox { border: 1px solid #30343c; border-radius: 8px; margin-top: 8px; padding: 10px 8px 8px 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #aeb5c0; }
            QLineEdit, QComboBox, QTableView { background: #1e2127; border: 1px solid #353a43; border-radius: 6px; }
            QLineEdit { padding: 9px; } QComboBox { padding: 7px 10px; min-width: 90px; }
            QPushButton { background: #292e36; border: 1px solid #3c424c; border-radius: 6px; padding: 9px 14px; }
            QPushButton:hover { background: #353b45; } QPushButton#primary { background: #315f9e; border-color: #4679bd; font-weight: 600; } QPushButton#primary:hover { background: #3b70b6; } QPushButton#secondary { background: #3b313f; border-color: #66536b; font-weight: 600; } QPushButton#secondary:hover { background: #4b3d50; } QPushButton#danger { background: #54272b; border-color: #824047; font-weight: 600; } QPushButton#danger:hover { background: #6a3036; } QPushButton:disabled { color: #666c75; background: #202329; }
            QProgressBar { background: #1e2127; border: 1px solid #353a43; border-radius: 5px; height: 18px; text-align: center; } QProgressBar::chunk { background: #477dcc; border-radius: 4px; }
            QHeaderView::section { background: #252a31; color: #cfd4dc; padding: 8px; border: 0; border-right: 1px solid #343941; } QTableView { gridline-color: #30343b; } QTableView::item { padding: 6px; } QTableView::item:selected { background: #304a70; }
            QLabel#status { color: #aeb5c0; padding: 2px 4px; } QLabel#statCaption { color: #858c98; } QLabel#statValue { font-size: 19px; font-weight: 700; color: #ffffff; } QLabel#ffprobeStatus { font-weight: 700; }
        """)

    def open_duplicate_finder(self):
        folder = self.folder.text().strip()
        self.duplicate_window = DuplicateFinderWindow()
        if folder and os.path.isdir(folder):
            self.duplicate_window.folder.setText(folder)
        self.duplicate_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.duplicate_window.show()
        self.duplicate_window.raise_()
        self.duplicate_window.activateWindow()

    def _restore_state(self):
        geometry = self.settings.value("geometry")
        if geometry: self.restoreGeometry(geometry)
        self.folder.setText(str(self.settings.value("folder", "")))
    def _configured_ffprobe(self) -> str: return str(self.settings.value("ffprobe", "")).strip()
    def _make_scanner(self) -> MediaScanner:
        scanner = MediaScanner(); configured = self._configured_ffprobe()
        if configured and os.path.isfile(configured): scanner.ffprobe = configured
        return scanner
    def refresh_ffprobe_status(self):
        scanner = self._make_scanner()
        if scanner.ffprobe: self.ffprobe_status.setText("● FFprobe gevonden"); self.ffprobe_status.setStyleSheet("color: #65c47a; font-weight: 700;"); self.ffprobe_path.setText(scanner.ffprobe)
        else: self.ffprobe_status.setText("● FFprobe niet gevonden"); self.ffprobe_status.setStyleSheet("color: #e26d6d; font-weight: 700;"); self.ffprobe_path.setText("Installeer FFmpeg of kies handmatig een ffprobe executable.")
    def configure_ffprobe(self):
        dialog = FFprobeDialog(self._configured_ffprobe(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        value = dialog.value()
        if value and not os.path.isfile(value): QMessageBox.warning(self, "FFprobe", "Het gekozen bestand bestaat niet."); return
        self.settings.setValue("ffprobe", value); self.refresh_ffprobe_status()
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies scanmap", self.folder.text() or str(Path.home()))
        if folder: self.folder.setText(folder); self.settings.setValue("folder", folder)
    def start_scan(self):
        folder = self.folder.text().strip()
        if not folder or not os.path.isdir(folder): QMessageBox.warning(self, "Scan", "Kies eerst een geldige map."); return
        self.model.clear(); self.progress.setValue(0); self.progress.setMaximum(0); self.status.setText("Scan bezig…"); self.scan_button.setEnabled(False); self.cancel_button.setEnabled(True); self.export_button.setEnabled(False); self._update_action_state(); self.settings.setValue("folder", folder)
        self.thread = QThread(self); self.worker = ScanWorker(folder, self._configured_ffprobe() or None); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.result.connect(self.model.add); self.worker.progress.connect(self.update_progress); self.worker.error.connect(self.scan_error); self.worker.finished.connect(self.scan_finished); self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater); self.thread.start()
    def cancel_scan(self):
        if self.worker: self.worker.cancel(); self.status.setText("Scan wordt gestopt…")
    def update_progress(self, current, total): self.progress.setMaximum(total); self.progress.setValue(current); self.status.setText(f"Scannen… {current} / {total}")
    def scan_error(self, message): QMessageBox.critical(self, "Scanfout", message)
    def scan_finished(self, cancelled):
        self.scan_button.setEnabled(True); self.cancel_button.setEnabled(False); self.export_button.setEnabled(self.model.rowCount() > 0); self.update_stats(); self._update_action_state(); self.status.setText("Scan gestopt." if cancelled else f"Scan klaar: {self.model.rowCount()} bestanden.")
    def update_stats(self):
        items = self.model.items; self.total_label.setText(str(len(items))); self.video_label.setText(str(sum(i.media_type == "Video" for i in items))); self.audio_label.setText(str(sum(i.media_type == "Audio" for i in items))); self.error_label.setText(str(sum(i.status != "OK" for i in items))); self.size_label.setText(self._format_total_size(sum(i.size_bytes for i in items)))
    @staticmethod
    def _format_total_size(value):
        size = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB": return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{value} B"
    def apply_filters(self): self.proxy.set_filters(self.search.text(), self.type_filter.currentText(), self.status_filter.currentText()); self._update_action_state()
    def clear_filters(self): self.search.clear(); self.type_filter.setCurrentIndex(0); self.status_filter.setCurrentIndex(0)
    def select_all_visible(self): self.table.selectAll(); self._update_action_state()
    def _selected_items(self) -> list[MediaResult]:
        items = []
        for proxy_index in self.table.selectionModel().selectedRows():
            source_index = self.proxy.mapToSource(proxy_index); item = source_index.data(Qt.ItemDataRole.UserRole)
            if item: items.append(item)
        return items
    def _update_action_state(self, *args):
        enabled = bool(self._selected_items()) if hasattr(self, "table") else False
        if hasattr(self, "delete_button"): self.delete_button.setEnabled(enabled)
        if hasattr(self, "delete_action"): self.delete_action.setEnabled(enabled)
    def delete_selected(self):
        items = self._selected_items()
        if not items: return
        answer = QMessageBox.question(self, "Naar Prullenbak", f"Wil je {len(items)} geselecteerd(e) bestand(en) naar de Windows Prullenbak verplaatsen?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes: return
        try: moved, failed = move_to_recycle_bin([item.path for item in items])
        except Exception as exc: QMessageBox.critical(self, "Verwijderen", str(exc)); return
        self.model.remove_paths(set(moved)); self.update_stats(); self._update_action_state()
        if failed: QMessageBox.warning(self, "Prullenbak", f"{len(moved)} bestand(en) verplaatst. {len(failed)} konden niet worden verplaatst.")
        else: self.status.setText(f"{len(moved)} bestand(en) naar de Prullenbak verplaatst.")
        self.export_button.setEnabled(self.model.rowCount() > 0)
    def open_selected(self):
        items = self._selected_items()
        if not items: return
        try: os.startfile(items[0].path)
        except Exception as exc: QMessageBox.warning(self, "Openen", f"Kon bestand niet openen:\n{exc}")
    def export_csv(self):
        if not self.model.items: return
        path, _ = QFileDialog.getSaveFileName(self, "CSV exporteren", "VideoAudioScanner.csv", "CSV-bestanden (*.csv)")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(asdict(self.model.items[0]).keys()), delimiter=";"); writer.writeheader(); writer.writerows(asdict(item) for item in self.model.items)
        self.status.setText(f"CSV opgeslagen: {path}")
    def closeEvent(self, event):
        if self.worker: self.worker.cancel()
        self.settings.setValue("geometry", self.saveGeometry()); super().closeEvent(event)


def main():
    app = QApplication(sys.argv); app.setApplicationName("VideoAudioScanner"); window = MainWindow(); window.show(); sys.exit(app.exec())

if __name__ == "__main__": main()
