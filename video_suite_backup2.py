from __future__ import annotations

import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from duplicate_finder import DuplicateFinderWindow
from main import MainWindow as ScannerWindow
from quality_analyzer import QualityAnalyzerWindow
from storage_analyzer import StorageAnalyzerWindow
from thumbnail_tool import ThumbnailToolWindow
from video_tools import VideoToolsWindow
from video_converter import VideoConverterWindow
from video_library import VideoLibraryWindow
from video_player import VideoPlayerWindow


class ModuleCard(QFrame):
    def __init__(self, icon, title, description, button_text, callback, enabled=True, parent=None):
        super().__init__(parent)
        self.setObjectName("moduleCard")
        self.setMinimumHeight(210)
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
        description_label.setMinimumHeight(48)
        layout.addWidget(description_label, 1)
        button = QPushButton(button_text)
        button.setObjectName("moduleButton" if enabled else "moduleButtonDisabled")
        button.setEnabled(enabled)
        if enabled and callback:
            button.clicked.connect(callback)
        layout.addWidget(button)


class WizardWindow(QMainWindow):
    def __init__(self, suite):
        super().__init__(suite)
        self.suite = suite
        self.setWindowTitle("VideoAudioScanner - Wat wil je doen?")
        self.resize(900, 700)
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        title = QLabel("🧭  VIDEO WIZARD")
        title.setObjectName("wizardTitle")
        layout.addWidget(title)
        intro = QLabel("Je hoeft niet te weten welke module je nodig hebt. Kies gewoon wat je met je video's wilt doen.")
        intro.setObjectName("wizardIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        question = QLabel("Wat wil je doen?")
        question.setObjectName("question")
        layout.addWidget(question)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        choices = [
            ("🎬", "Video's bekijken", "Een of meerdere video's openen en afspelen.", self.suite.open_player),
            ("♻", "Dubbele video's zoeken", "Exact dezelfde of visueel bijna dezelfde video's vinden.", self.suite.open_duplicates),
            ("📊", "Videokwaliteit vergelijken", "Resolutie, bitrate, codec, FPS, audio en bestandsgrootte vergelijken.", self.suite.open_quality),
            ("🔄", "Video omzetten", "Een video converteren naar MP4, MKV of WebM.", self.suite.open_converter),
            ("🔎", "Mijn bestanden analyseren", "Video- en audiobestanden technisch laten analyseren.", self.suite.open_scanner),
            ("💾", "Opslagruimte bekijken", "Ontdekken welke bestanden de meeste ruimte innemen.", self.suite.open_storage),
            ("📚", "Video Library", "Een visueel overzicht met thumbnails, zoeken en sorteren.", self.suite.open_library),
            ("🖼", "Thumbnails maken", "Eén of meerdere thumbnails maken met voorbeeld, JPG/PNG en formaatkeuze.", self.suite.open_thumbnails),
        ]
        for index, (icon, text, desc, callback) in enumerate(choices):
            card = QFrame()
            card.setObjectName("wizardCard")
            card_layout = QVBoxLayout(card)
            icon_label = QLabel(icon)
            icon_label.setObjectName("wizardIcon")
            card_layout.addWidget(icon_label)
            title_label = QLabel(text)
            title_label.setObjectName("wizardCardTitle")
            card_layout.addWidget(title_label)
            desc_label = QLabel(desc)
            desc_label.setObjectName("wizardCardDescription")
            desc_label.setWordWrap(True)
            card_layout.addWidget(desc_label, 1)
            button = QPushButton("Deze functie gebruiken")
            button.clicked.connect(lambda checked=False, cb=callback: self._choose(cb))
            card_layout.addWidget(button)
            grid.addWidget(card, index // 2, index % 2)
        scroll.setWidget(host)
        layout.addWidget(scroll, 1)
        tip = QLabel("Twijfel je? Gebruik deze Wizard. Je hoeft alleen je doel te kiezen.")
        tip.setObjectName("wizardTip")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        close = QPushButton("Sluiten")
        close.clicked.connect(self.close)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(root)

    def _choose(self, callback):
        self.close()
        callback()

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background:#111318; color:#e8eaed; font-size:13px; }
            QMainWindow { background:#0d0f13; }
            QLabel#wizardTitle { font-size:30px; font-weight:900; color:#fff; }
            QLabel#wizardIntro { color:#aeb5c0; font-size:15px; }
            QLabel#question { color:#fff; font-size:20px; font-weight:800; }
            QFrame#wizardCard { background:#191c22; border:1px solid #303640; border-radius:10px; }
            QFrame#wizardCard:hover { border:1px solid #4b5666; background:#1c2027; }
            QLabel#wizardIcon { font-size:30px; background:transparent; }
            QLabel#wizardCardTitle { font-size:17px; font-weight:800; color:#fff; background:transparent; }
            QLabel#wizardCardDescription, QLabel#wizardTip { color:#929aa7; background:transparent; }
            QPushButton { background:#292e36; border:1px solid #3c424c; border-radius:7px; padding:9px 14px; font-weight:600; }
            QPushButton:hover { background:#353b45; }
        """)


class VideoSuiteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoAudioScanner - Video Suite")
        self.resize(1180, 850)
        self.scanner_window = None
        self.duplicate_window = None
        self.quality_window = None
        self.converter_window = None
        self.storage_window = None
        self.library_window = None
        self.thumbnail_window = None
        self.wizard_window = None
        self.video_tools_window = None
        self.player_windows = []
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("VIDEO SUITE")
        title.setObjectName("suiteTitle")
        title_box.addWidget(title)
        subtitle = QLabel("VideoAudioScanner")
        subtitle.setObjectName("suiteSubtitle")
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        wizard = QPushButton("🧭  Wizard")
        wizard.setObjectName("wizardButton")
        wizard.clicked.connect(self.open_wizard)
        header.addWidget(wizard)
        credit = QLabel("MADE BY KID ACID")
        credit.setObjectName("credit")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(credit)
        layout.addLayout(header)
        intro = QLabel("Kies een functie hieronder. Je hoeft niet alles te kennen: bij iedere module staat duidelijk waarvoor ze dient. Weet je het niet? Gebruik de Wizard.")
        intro.setObjectName("intro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        modules = [
            ("🔎", "MEDIA SCANNER", "Analyseert video- en audiobestanden met FFprobe.", "Scanner openen", self.open_scanner, True),
            ("♻", "DUPLICATEN", "Zoekt exacte duplicaten en video's die visueel sterk op elkaar lijken.", "Duplicaten zoeken", self.open_duplicates, True),
            ("🎬", "VIDEO PLAYER", "Bekijk video's rechtstreeks in de Video Suite en speel meerdere video's als playlist af.", "Video openen", self.open_player, True),
            ("📊", "QUALITY ANALYZER", "Vergelijkt video's op technische kwaliteit.", "Kwaliteit vergelijken", self.open_quality, True),
            ("🔄", "VIDEO CONVERTER", "Zet video's om naar MP4, MKV of WebM.", "Video converteren", self.open_converter, True),
            ("💾", "STORAGE ANALYZER", "Analyseert opslaggebruik en toont de grootste bestanden.", "Opslag analyseren", self.open_storage, True),
            ("📚", "VIDEO LIBRARY", "Een visuele bibliotheek met thumbnails, zoeken en sorteren.", "Library openen", self.open_library, True),
            ("🖼", "THUMBNAIL TOOL", "Maak één of meerdere thumbnails met voorbeeld, JPG/PNG en optionele breedte.", "Thumbnail Tool openen", self.open_thumbnails, True),
            ("🛠", "VIDEO TOOLS", "Extra gereedschap voor audio uit video, knippen, thumbnails, controle en streams.", "Video Tools openen", self.open_video_tools, True),
        ]
        for index, module in enumerate(modules):
            grid.addWidget(ModuleCard(*module, parent=self), index // 2, index % 2)
        scroll.setWidget(host)
        layout.addWidget(scroll, 1)
        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_text = QLabel("Tip: als je niet weet welke functie je nodig hebt, klik bovenaan op de Wizard.")
        footer_text.setObjectName("footerText")
        footer_layout.addWidget(footer_text)
        footer_layout.addStretch(1)
        close = QPushButton("Afsluiten")
        close.clicked.connect(self.close)
        footer_layout.addWidget(close)
        layout.addWidget(footer)
        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background:#111318; color:#e8eaed; font-size:13px; }
            QMainWindow { background:#0d0f13; }
            QLabel#suiteTitle { font-size:34px; font-weight:900; color:#fff; }
            QLabel#suiteSubtitle { font-size:15px; color:#8f96a3; }
            QLabel#intro { color:#aeb5c0; font-size:14px; padding:4px 2px 8px; }
            QLabel#credit { color:#fff; font-size:18px; font-weight:800; padding:10px 16px; background:#15181d; border:1px solid #3d434d; border-radius:8px; min-width:190px; }
            QPushButton { background:#292e36; border:1px solid #3c424c; border-radius:7px; padding:9px 14px; font-weight:600; }
            QPushButton:hover { background:#353b45; }
            QPushButton#wizardButton, QPushButton#moduleButton { background:#315f9e; border-color:#4679bd; color:#fff; }
            QPushButton#wizardButton:hover, QPushButton#moduleButton:hover { background:#3b70b6; }
            QFrame#moduleCard { background:#191c22; border:1px solid #303640; border-radius:12px; }
            QFrame#moduleCard:hover { border:1px solid #4b5666; background:#1c2027; }
            QLabel#moduleIcon { font-size:30px; background:transparent; }
            QLabel#moduleTitle { font-size:19px; font-weight:800; color:#fff; background:transparent; }
            QLabel#moduleDescription { color:#929aa7; background:transparent; padding-bottom:8px; }
            QPushButton#moduleButtonDisabled { color:#666d78; background:#202329; border-color:#2d323a; }
            QFrame#footer { background:#15181d; border:1px solid #2d323a; border-radius:8px; }
            QLabel#footerText { color:#7f8793; }
            QScrollArea { background:transparent; border:none; }
        """)

    def _show_window(self, attribute, factory):
        window = getattr(self, attribute)
        if window is None:
            window = factory()
            setattr(self, attribute, window)
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        window.show()
        window.raise_()
        window.activateWindow()

    def open_wizard(self):
        self._show_window("wizard_window", lambda: WizardWindow(self))

    def open_scanner(self): self._show_window("scanner_window", ScannerWindow)
    def open_duplicates(self): self._show_window("duplicate_window", DuplicateFinderWindow)
    def open_quality(self): self._show_window("quality_window", lambda: QualityAnalyzerWindow(self))
    def open_converter(self): self._show_window("converter_window", lambda: VideoConverterWindow(self))
    def open_storage(self): self._show_window("storage_window", lambda: StorageAnalyzerWindow(self))
    def open_library(self): self._show_window("library_window", lambda: VideoLibraryWindow(self))
    def open_thumbnails(self): self._show_window("thumbnail_window", lambda: ThumbnailToolWindow(self))
    def open_video_tools(self): self._show_window("video_tools_window", lambda: VideoToolsWindow(self))

    def open_player(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Kies video's", "", "Video's (*.mp4 *.mkv *.avi *.mov *.wmv *.webm *.m4v *.mpeg *.mpg *.ts *.mts *.m2ts);;Alle bestanden (*)")
        if not paths:
            return
        window = VideoPlayerWindow(paths[0], self, playlist=paths)
        self.player_windows.append(window)
        window.destroyed.connect(lambda: self.player_windows.remove(window) if window in self.player_windows else None)
        window.show()
        window.raise_()
        window.activateWindow()

    def closeEvent(self, event):
        for window in list(self.player_windows):
            try:
                window.close()
            except RuntimeError:
                pass
        for window in (self.scanner_window, self.duplicate_window, self.quality_window, self.converter_window, self.storage_window, self.library_window, self.thumbnail_window, self.video_tools_window, self.wizard_window):
            if window is not None:
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
    window.raise_()
    window.activateWindow()
    QTimer.singleShot(0, window.showMaximized)
    QTimer.singleShot(100, window.showMaximized)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

