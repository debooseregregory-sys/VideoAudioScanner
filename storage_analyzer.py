from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv",
    ".webm", ".m4v", ".mpeg", ".mpg",
    ".ts", ".mts", ".m2ts",
}


def format_size(value: int) -> str:
    size = float(value)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{value} B"


class StorageAnalyzerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("VideoAudioScanner - Storage Analyzer")
        self.resize(1100, 700)

        self.files: list[tuple[str, int]] = []

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("STORAGE ANALYZER")
        title.setObjectName("title")
        layout.addWidget(title)

        intro = QLabel(
            "Bekijk welke videobestanden de meeste opslagruimte gebruiken. "
            "Kies een map om alle video's daarin en in onderliggende mappen "
            "te analyseren."
        )
        intro.setWordWrap(True)
        intro.setObjectName("intro")
        layout.addWidget(intro)

        info = QFrame()
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(14, 10, 14, 10)

        self.folder_label = QLabel("Nog geen map gekozen")
        self.folder_label.setObjectName("folder")
        info_layout.addWidget(self.folder_label, 1)

        self.total_label = QLabel("0 bestanden • 0 B")
        self.total_label.setObjectName("total")
        info_layout.addWidget(self.total_label)

        layout.addWidget(info)

        buttons = QHBoxLayout()

        choose_button = QPushButton("Map kiezen")
        choose_button.clicked.connect(self.choose_folder)
        buttons.addWidget(choose_button)

        self.scan_button = QPushButton("Scan starten")
        self.scan_button.setObjectName("primary")
        self.scan_button.setEnabled(False)
        self.scan_button.clicked.connect(self.analyze_current_folder)
        buttons.addWidget(self.scan_button)

        buttons.addStretch(1)

        self.delete_button = QPushButton("Naar Prullenbak")
        self.delete_button.setObjectName("danger")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_selected)
        buttons.addWidget(self.delete_button)

        layout.addLayout(buttons)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            ["Bestand", "Grootte", "Pad"]
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(
            self._update_action_state
        )

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(
            0,
            header.ResizeMode.Interactive,
        )
        header.setSectionResizeMode(
            1,
            header.ResizeMode.ResizeToContents,
        )

        layout.addWidget(self.table, 1)

        self.status = QLabel("Klaar.")
        self.status.setObjectName("status")
        layout.addWidget(self.status)

        self.setCentralWidget(root)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Kies een map",
        )

        if folder:
            self.folder_label.setText(folder)
            self.folder_label.setProperty("folder", folder)
            self.scan_button.setEnabled(True)
            self.status.setText("Map gekozen. Klik op Scan starten.")

    def analyze_current_folder(self):
        folder = self.folder_label.property("folder")

        if folder and os.path.isdir(folder):
            self._analyze(folder)
        else:
            self.choose_folder()

    def _analyze(self, folder: str):
        self.folder_label.setText(folder)
        self.folder_label.setProperty("folder", folder)

        self.files.clear()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        self.status.setText("Analyseren…")
        QApplication.processEvents()

        total_size = 0

        try:
            for root, _, filenames in os.walk(folder):
                for filename in filenames:
                    path = Path(root) / filename

                    if path.suffix.lower() not in VIDEO_EXTENSIONS:
                        continue

                    try:
                        size = path.stat().st_size
                    except OSError:
                        continue

                    self.files.append((str(path), size))
                    total_size += size

        except OSError as exc:
            QMessageBox.critical(
                self,
                "Storage Analyzer",
                f"De map kon niet volledig worden gelezen:\n{exc}",
            )

        self.files.sort(key=lambda item: item[1], reverse=True)

        for path, size in self.files:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QTableWidgetItem(Path(path).name)
            size_item = QTableWidgetItem(format_size(size))
            path_item = QTableWidgetItem(path)

            size_item.setData(
                Qt.ItemDataRole.UserRole,
                size,
            )

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, path_item)

        self.table.setSortingEnabled(True)

        self.total_label.setText(
            f"{len(self.files)} bestanden • {format_size(total_size)}"
        )

        self.status.setText(
            f"Analyse klaar: {len(self.files)} videobestand(en)."
        )

        self._update_action_state()

    def _selected_paths(self) -> list[str]:
        paths = []

        for row in self.table.selectionModel().selectedRows():
            item = self.table.item(row.row(), 2)

            if item:
                paths.append(item.text())

        return paths

    def _update_action_state(self):
        self.delete_button.setEnabled(
            bool(self._selected_paths())
        )

    def delete_selected(self):
        paths = self._selected_paths()

        if not paths:
            return

        answer = QMessageBox.question(
            self,
            "Naar Prullenbak",
            f"Wil je {len(paths)} geselecteerd(e) bestand(en) "
            "naar de Windows Prullenbak verplaatsen?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        moved = []
        failed = []

        if os.name != "nt":
            QMessageBox.warning(
                self,
                "Prullenbak",
                "De Windows Prullenbak is alleen beschikbaar op Windows.",
            )
            return

        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.UINT),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        existing = []

        for path in paths:
            if Path(path).is_file():
                existing.append(path)
            else:
                failed.append(path)

        if existing:
            source = "".join(
                path + "\0"
                for path in existing
            ) + "\0"

            operation = SHFILEOPSTRUCTW(
                None,
                0x0003,
                source,
                None,
                0x0004
                | 0x0010
                | 0x0040
                | 0x0400,
                False,
                None,
                None,
            )

            result = ctypes.windll.shell32.SHFileOperationW(
                ctypes.byref(operation)
            )

            if (
                result == 0
                and not operation.fAnyOperationsAborted
            ):
                moved = existing
            else:
                failed.extend(existing)

        moved_set = set(moved)

        self.files = [
            item
            for item in self.files
            if item[0] not in moved_set
        ]

        for row in range(self.table.rowCount() - 1, -1, -1):
            path_item = self.table.item(row, 2)

            if path_item and path_item.text() in moved_set:
                self.table.removeRow(row)

        total_size = sum(
            size for _, size in self.files
        )

        self.total_label.setText(
            f"{len(self.files)} bestanden • {format_size(total_size)}"
        )

        self._update_action_state()

        if failed:
            QMessageBox.warning(
                self,
                "Prullenbak",
                f"{len(moved)} bestand(en) verplaatst. "
                f"{len(failed)} konden niet worden verplaatst.",
            )
        else:
            self.status.setText(
                f"{len(moved)} bestand(en) naar de Prullenbak verplaatst."
            )

    def _apply_theme(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #111318;
                color: #e8eaed;
                font-size: 13px;
            }

            QMainWindow {
                background: #0d0f13;
            }

            QLabel#title {
                font-size: 30px;
                font-weight: 900;
                color: #ffffff;
            }

            QLabel#intro {
                color: #9da5b1;
                font-size: 14px;
            }

            QLabel#folder {
                color: #d9dde3;
            }

            QLabel#total {
                color: #ffffff;
                font-weight: 700;
            }

            QPushButton {
                background: #292e36;
                border: 1px solid #3c424c;
                border-radius: 6px;
                padding: 9px 14px;
            }

            QPushButton:hover {
                background: #353b45;
            }

            QPushButton#danger {
                background: #54272b;
                border-color: #824047;
                font-weight: 600;
            }

            QPushButton#danger:hover {
                background: #6a3036;
            }

            QPushButton:disabled {
                color: #666c75;
                background: #202329;
            }

            QTableWidget {
                background: #1e2127;
                border: 1px solid #353a43;
                gridline-color: #30343b;
                alternate-background-color: #20242b;
            }

            QHeaderView::section {
                background: #252a31;
                color: #cfd4dc;
                padding: 8px;
                border: 0;
                border-right: 1px solid #343941;
            }

            QTableWidget::item:selected {
                background: #304a70;
            }

            QLabel#status {
                color: #aeb5c0;
            }
            """
        )


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    window = StorageAnalyzerWindow()
    window.show()
    app.exec()







