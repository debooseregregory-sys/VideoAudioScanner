from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from video_editor import VideoCutterWindow, VideoMergerWindow
from video_tools import VideoToolsWindow


class VideoToolsHubWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Video Tools")
        self.resize(1050, 720)
        self.cutter = None
        self.merger = None
        self.legacy = None

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("VIDEO TOOLS")
        title.setStyleSheet("font-size:34px;font-weight:900;color:#fff;")
        title_box.addWidget(title)
        subtitle = QLabel("Bewerken, samenvoegen en praktische videofuncties")
        subtitle.setStyleSheet("font-size:15px;color:#8f96a3;")
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        credit = QLabel("MADE BY KID ACID")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setStyleSheet("color:#fff;font-size:18px;font-weight:800;padding:10px 16px;background:#15181d;border:1px solid #3d434d;border-radius:8px;min-width:190px;")
        header.addWidget(credit)
        layout.addLayout(header)

        intro = QLabel("Nieuwe videobewerkingen staan bovenaan. De bestaande Video Tools blijven volledig beschikbaar.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#aeb5c0;font-size:14px;")
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.addWidget(self.card("✂️", "VIDEO CUTTER", "Bekijk de video, speel hem af en zet exact een begin- en eindpunt op de tijdlijn.", self.open_cutter), 0, 0)
        grid.addWidget(self.card("🔗", "VIDEO MERGER", "Voeg meerdere video's toe, wijzig de volgorde en maak er één video van.", self.open_merger), 0, 1)
        grid.addWidget(self.card("🛠", "ANDERE VIDEO TOOLS", "Audio extraheren, thumbnails maken, video controleren en streams bekijken.", self.open_legacy), 1, 0, 1, 2)
        layout.addLayout(grid, 1)

        close = QPushButton("Sluiten")
        close.clicked.connect(self.close)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(root)
        self.setStyleSheet("""
            QWidget{background:#111318;color:#e8eaed;font-size:13px;}
            QFrame{background:#191c22;border:1px solid #303640;border-radius:12px;}
            QFrame:hover{border:1px solid #4b5666;background:#1c2027;}
            QPushButton{background:#292e36;border:1px solid #3c424c;border-radius:7px;padding:9px 14px;font-weight:600;color:#e8eaed;}
            QPushButton:hover{background:#353b45;}
            QPushButton#primary{background:#315f9e;border-color:#4679bd;color:#fff;}
            QPushButton#primary:hover{background:#3b70b6;}
        """)

    def card(self, icon, title, description, callback):
        card = QFrame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size:30px;background:transparent;border:none;")
        layout.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size:20px;font-weight:800;color:#fff;background:transparent;border:none;")
        layout.addWidget(title_label)
        text = QLabel(description)
        text.setWordWrap(True)
        text.setStyleSheet("color:#929aa7;background:transparent;border:none;")
        layout.addWidget(text, 1)
        button = QPushButton("Openen")
        button.setObjectName("primary")
        button.clicked.connect(callback)
        layout.addWidget(button)
        return card

    def open_cutter(self):
        if self.cutter is None:
            self.cutter = VideoCutterWindow(self)
            self.cutter.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.cutter.show(); self.cutter.raise_(); self.cutter.activateWindow()

    def open_merger(self):
        if self.merger is None:
            self.merger = VideoMergerWindow(self)
            self.merger.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.merger.show(); self.merger.raise_(); self.merger.activateWindow()

    def open_legacy(self):
        if self.legacy is None:
            self.legacy = VideoToolsWindow(self)
            self.legacy.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.legacy.show(); self.legacy.raise_(); self.legacy.activateWindow()

    def closeEvent(self, event):
        for window in (self.cutter, self.merger, self.legacy):
            if window is not None:
                try:
                    window.close()
                except RuntimeError:
                    pass
        event.accept()
