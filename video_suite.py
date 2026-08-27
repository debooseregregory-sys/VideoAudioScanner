from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from duplicate_finder import DuplicateFinderWindow
from main import MainWindow as ScannerWindow
from video_player import VideoPlayerWindow


class ModuleCard(QFrame):
    def __init__(
        self,
        icon: str,
        title: str,
        description: str,
        button_text: str,
        callback,
        enabled: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("moduleCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setObjectName("moduleIcon")
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setObjectName("moduleTitle")
        layout.addWidget(title_label)

        description_label = QLabel(description)
        description_label.setObjectName("moduleDescription")
        description_label.setWordWrap(True)
        layout.addWidget(description_label, 1)

        button = QPushButton(button_text)
        button.setObjectName("moduleButton" if enabled else "moduleButtonDisabled")
        button.setEnabled(enabled)
        if enabled:
            button.clicked.connect(callback)
        layout.addWidget(button)


class VideoSuiteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoAudioScanner — Video Suite")
        self.resize(1180, 820)
        self.scanner_window: ScannerWindow | None = None
        self.duplicate_window: DuplicateFinderWindow | None = None
        self.player_windows: list[VideoPlayerWindow] = []

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(18)

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel("VIDEO SUITE")
        title.setObjectName("suiteTitle")
        title_box.addWidget(title)

        subtitle = QLabel("VideoAudioScanner")
        subtitle.setObjectName("suiteSubtitle")
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch(1)

        credit = QLabel("MADE BY KID ACID")
        credit.setObjectName("credit")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(credit)
        root_layout.addLayout(header)

        intro = QLabel(
            "Kies hieronder een module. Elke functie werkt afzonderlijk, "
            "zodat de Video Suite overzichtelijk blijft en de bestaande "
            "scanner en duplicaatfuncties intact blijven."
        )
        intro.setObjectName("intro")
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        modules = [
            ("🔎", "MEDIA SCANNER", "Analyseer video- en audiobestanden met FFprobe.", "Scanner openen", self.open_scanner, True),
            ("♻", "DUPLICATEN", "Vind exacte en visuele duplicaten en vergelijk de kwaliteit.", "Duplicaten zoeken", self.open_duplicates, True),
            ("🎬", "VIDEO PLAYER", "Open een video rechtstreeks in de ingebouwde speler.", "Video openen", self.open_player, True),
            ("📊", "QUALITY ANALYZER", "Vergelijk resolutie, bitrate, codec, FPS, audio en bestandsgrootte.", "Binnenkort", None, False),
            ("💾", "STORAGE ANALYZER", "Ontdek de grootste bestanden en waar je opslagruimte naartoe gaat.", "Binnenkort", None, False),
            ("📚", "VIDEO LIBRARY", "Bouw een overzichtelijke bibliotheek van je videocollectie.", "Binnenkort", None, False),
            ("🖼", "THUMBNAIL TOOL", "Maak en exporteer thumbnails van geselecteerde video's.", "Binnenkort", None, False),
            ("🛠", "VIDEO TOOLS", "Extra gereedschap voor metadata, controle en videobeheer.", "Binnenkort", None, False),
        ]

        for index, module in enumerate(modules):
            row = index // 2
            column = index % 2
            card = ModuleCard(*module, parent=self)
            grid.addWidget(card, row, column)

        root_layout.addLayout(grid, 1)

        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 10)

        footer_text = QLabel(
            "De bestaande modules blijven afzonderlijk beschikbaar. "
            "Nieuwe modules worden later hier toegevoegd."
        )
        footer_text.setObjectName("footerText")
        footer_layout.addWidget(footer_text)
        footer_layout.addStretch(1)

        close_button = QPushButton("Afsluiten")
        close_button.clicked.connect(self.close)
        footer_layout.addWidget(close_button)

        root_layout.addWidget(footer)
        self.setCentralWidget(root)

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

            QLabel#suiteTitle {
                font-size: 34px;
                font-weight: 900;
                color: #ffffff;
                letter-spacing: 2px;
            }

            QLabel#suiteSubtitle {
                font-size: 15px;
                color: #8f96a3;
            }

            QLabel#intro {
                color: #aeb5c0;
                font-size: 14px;
                padding: 4px 2px 8px 2px;
            }

            QLabel#credit {
                color: #ffffff;
                font-size: 18px;
                font-weight: 800;
                letter-spacing: 1px;
                padding: 10px 16px;
                background: #15181d;
                border: 1px solid #3d434d;
                border-radius: 8px;
                min-width: 190px;
            }

            QFrame#moduleCard {
                background: #191c22;
                border: 1px solid #303640;
                border-radius: 12px;
            }

            QFrame#moduleCard:hover {
                border: 1px solid #4b5666;
                background: #1c2027;
            }

            QLabel#moduleIcon {
                font-size: 30px;
                background: transparent;
            }

            QLabel#moduleTitle {
                font-size: 19px;
                font-weight: 800;
                color: #ffffff;
                background: transparent;
            }

            QLabel#moduleDescription {
                color: #929aa7;
                line-height: 1.3;
                background: transparent;
                padding-bottom: 8px;
            }

            QPushButton {
                background: #292e36;
                border: 1px solid #3c424c;
                border-radius: 7px;
                padding: 9px 14px;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #353b45;
            }

            QPushButton#moduleButton {
                background: #315f9e;
                border-color: #4679bd;
                color: #ffffff;
            }

            QPushButton#moduleButton:hover {
                background: #3b70b6;
            }

            QPushButton#moduleButtonDisabled {
                color: #666d78;
                background: #202329;
                border-color: #2d323a;
            }

            QFrame#footer {
                background: #15181d;
                border: 1px solid #2d323a;
                border-radius: 8px;
            }

            QLabel#footerText {
                color: #7f8793;
            }
            """
        )

    def open_scanner(self):
        if self.scanner_window is None:
            self.scanner_window = ScannerWindow()
            self.scanner_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.scanner_window.show()
        self.scanner_window.raise_()
        self.scanner_window.activateWindow()

    def open_duplicates(self):
        if self.duplicate_window is None:
            self.duplicate_window = DuplicateFinderWindow()
            self.duplicate_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.duplicate_window.show()
        self.duplicate_window.raise_()
        self.duplicate_window.activateWindow()

    def open_player(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Kies video's",
            "",
            "Video's (*.mp4 *.mkv *.avi *.mov *.wmv *.webm *.m4v *.mpeg *.mpg *.ts *.mts *.m2ts);;Alle bestanden (*)",
        )
        if not paths:
            return

        window = VideoPlayerWindow(
            paths[0],
            self,
            playlist=paths,
        )
        self.player_windows.append(window)
        window.destroyed.connect(
            lambda: self.player_windows.remove(window)
            if window in self.player_windows
            else None
        )
        window.show()
        window.raise_()
        window.activateWindow()

    def closeEvent(self, event):
        for window in list(self.player_windows):
            try:
                window.close()
            except RuntimeError:
                pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VideoAudioScanner")
    app.setOrganizationName("VideoAudioScanner")
    window = VideoSuiteWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
