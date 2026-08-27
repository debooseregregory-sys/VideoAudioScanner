from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm",
    ".ts", ".mts", ".m2ts", ".wmv", ".flv", ".mpeg", ".mpg"
}


def find_program(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    here = Path(__file__).resolve().parent

    candidates = [
        here / f"{name}.exe",
        here / "ffmpeg" / "bin" / f"{name}.exe",
        here / "tools" / f"{name}.exe",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return None


def find_ffmpeg() -> str | None:
    return find_program("ffmpeg")


def find_ffprobe() -> str | None:
    return find_program("ffprobe")


class HelpDialog(QDialog):
    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"Uitleg - {title}")
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("helpTitle")
        layout.addWidget(heading)

        message = QLabel(text)
        message.setObjectName("helpText")
        message.setWordWrap(True)
        layout.addWidget(message, 1)

        button = QPushButton("Sluiten")
        button.clicked.connect(self.accept)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignRight)

        self.setStyleSheet("""
            QDialog {
                background: #101216;
                color: #e8eaed;
            }

            QLabel#helpTitle {
                color: #ffffff;
                font-size: 24px;
                font-weight: 900;
            }

            QLabel#helpText {
                color: #c1c7d0;
                font-size: 14px;
                line-height: 150%;
            }

            QPushButton {
                background: #315f9e;
                border: 1px solid #4679bd;
                border-radius: 7px;
                padding: 9px 18px;
                color: white;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #3b70b6;
            }
        """)


class ToolCard(QFrame):
    def __init__(
        self,
        icon: str,
        title: str,
        description: str,
        callback,
        help_text: str,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName("toolCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(9)

        top = QHBoxLayout()

        icon_label = QLabel(icon)
        icon_label.setObjectName("toolIcon")
        top.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setObjectName("toolTitle")
        top.addWidget(title_label, 1)

        help_button = QPushButton("?")
        help_button.setObjectName("helpButton")
        help_button.setFixedSize(32, 32)
        help_button.setToolTip("Wat doet deze functie?")
        help_button.clicked.connect(
            lambda: HelpDialog(title, help_text, self).exec()
        )
        top.addWidget(help_button)

        layout.addLayout(top)

        description_label = QLabel(description)
        description_label.setObjectName("toolDescription")
        description_label.setWordWrap(True)
        layout.addWidget(description_label, 1)

        button = QPushButton("Openen")
        button.setObjectName("toolButton")
        button.clicked.connect(callback)
        layout.addWidget(button)


class AudioExtractDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Audio uit video halen")
        self.resize(620, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(14)

        title = QLabel("AUDIO UIT VIDEO")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        info = QLabel(
            "Kies een video en bepaal hoe je de audio wilt opslaan."
        )
        info.setWordWrap(True)
        info.setObjectName("dialogInfo")
        layout.addWidget(info)

        form = QFormLayout()

        self.source = QLineEdit()
        source_button = QPushButton("Bladeren...")
        source_button.clicked.connect(self.choose_source)

        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        source_row.addWidget(source_button)
        form.addRow("Video:", source_row)

        self.format = QComboBox()
        self.format.addItem("MP3 - algemeen gebruik", "mp3")
        self.format.addItem("M4A - goede kwaliteit", "m4a")
        self.format.addItem("WAV - ongecomprimeerd", "wav")
        form.addRow("Audio:", self.format)

        self.output = QLineEdit()
        output_button = QPushButton("Bladeren...")
        output_button.clicked.connect(self.choose_output)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output, 1)
        output_row.addWidget(output_button)
        form.addRow("Doelmap:", output_row)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        cancel = QPushButton("Annuleren")
        cancel.clicked.connect(self.reject)

        start = QPushButton("Audio maken")
        start.setObjectName("primary")
        start.clicked.connect(self.accept)

        buttons.addWidget(cancel)
        buttons.addWidget(start)
        layout.addLayout(buttons)

        self.setStyleSheet(DIALOG_STYLE)

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Kies video",
            "",
            "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts);;Alle bestanden (*)",
        )
        if path:
            self.source.setText(path)

            if not self.output.text():
                self.output.setText(str(Path(path).parent))

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies doelmap")
        if folder:
            self.output.setText(folder)

    def values(self):
        return (
            self.source.text().strip(),
            self.output.text().strip(),
            self.format.currentData(),
        )


class CutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Video knippen")
        self.resize(620, 340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(14)

        title = QLabel("VIDEO KNIPPEN")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        info = QLabel(
            "Geef aan vanaf welk moment de nieuwe video moet beginnen "
            "en wanneer hij moet eindigen. Het originele bestand blijft behouden."
        )
        info.setWordWrap(True)
        info.setObjectName("dialogInfo")
        layout.addWidget(info)

        form = QFormLayout()

        self.source = QLineEdit()
        source_button = QPushButton("Bladeren...")
        source_button.clicked.connect(self.choose_source)

        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        source_row.addWidget(source_button)
        form.addRow("Video:", source_row)

        self.start = QSpinBox()
        self.start.setRange(0, 86400)
        self.start.setSuffix(" sec")
        form.addRow("Begin:", self.start)

        self.end = QSpinBox()
        self.end.setRange(1, 86400)
        self.end.setSuffix(" sec")
        self.end.setValue(60)
        form.addRow("Einde:", self.end)

        self.output = QLineEdit()
        output_button = QPushButton("Bladeren...")
        output_button.clicked.connect(self.choose_output)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output, 1)
        output_row.addWidget(output_button)
        form.addRow("Doelmap:", output_row)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        cancel = QPushButton("Annuleren")
        cancel.clicked.connect(self.reject)

        start = QPushButton("Video knippen")
        start.setObjectName("primary")
        start.clicked.connect(self.validate_and_accept)

        buttons.addWidget(cancel)
        buttons.addWidget(start)
        layout.addLayout(buttons)

        self.setStyleSheet(DIALOG_STYLE)

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Kies video",
            "",
            "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts);;Alle bestanden (*)",
        )
        if path:
            self.source.setText(path)
            if not self.output.text():
                self.output.setText(str(Path(path).parent))

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies doelmap")
        if folder:
            self.output.setText(folder)

    def validate_and_accept(self):
        if not self.source.text().strip():
            QMessageBox.warning(self, "Video knippen", "Kies eerst een video.")
            return

        if self.end.value() <= self.start.value():
            QMessageBox.warning(
                self,
                "Video knippen",
                "Het eindpunt moet later zijn dan het beginpunt.",
            )
            return

        if not self.output.text().strip():
            self.output.setText(str(Path(self.source.text()).parent))

        self.accept()

    def values(self):
        return (
            self.source.text().strip(),
            self.output.text().strip(),
            self.start.value(),
            self.end.value(),
        )


class ThumbnailDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Thumbnail maken")
        self.resize(620, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(14)

        title = QLabel("THUMBNAIL MAKEN")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        info = QLabel(
            "Maak automatisch een JPG-afbeelding van een gekozen moment "
            "uit de video."
        )
        info.setWordWrap(True)
        info.setObjectName("dialogInfo")
        layout.addWidget(info)

        form = QFormLayout()

        self.source = QLineEdit()
        source_button = QPushButton("Bladeren...")
        source_button.clicked.connect(self.choose_source)

        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        source_row.addWidget(source_button)
        form.addRow("Video:", source_row)

        self.second = QSpinBox()
        self.second.setRange(0, 86400)
        self.second.setSuffix(" sec")
        form.addRow("Moment:", self.second)

        self.output = QLineEdit()
        output_button = QPushButton("Bladeren...")
        output_button.clicked.connect(self.choose_output)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output, 1)
        output_row.addWidget(output_button)
        form.addRow("Doelmap:", output_row)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        cancel = QPushButton("Annuleren")
        cancel.clicked.connect(self.reject)

        start = QPushButton("Thumbnail maken")
        start.setObjectName("primary")
        start.clicked.connect(self.accept)

        buttons.addWidget(cancel)
        buttons.addWidget(start)
        layout.addLayout(buttons)

        self.setStyleSheet(DIALOG_STYLE)

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Kies video",
            "",
            "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts);;Alle bestanden (*)",
        )
        if path:
            self.source.setText(path)
            if not self.output.text():
                self.output.setText(str(Path(path).parent))

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies doelmap")
        if folder:
            self.output.setText(folder)

    def values(self):
        return (
            self.source.text().strip(),
            self.output.text().strip(),
            self.second.value(),
        )


class VideoToolsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("VideoAudioScanner - Video Tools")
        self.resize(1100, 760)

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()

        title_box = QVBoxLayout()

        title = QLabel("VIDEO TOOLS")
        title.setObjectName("suiteTitle")
        title_box.addWidget(title)

        subtitle = QLabel("Praktische videobewerkingen zonder technische kennis")
        subtitle.setObjectName("suiteSubtitle")
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch(1)

        credit = QLabel("MADE BY KID ACID")
        credit.setObjectName("credit")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(credit)

        layout.addLayout(header)

        intro = QLabel(
            "Hier vind je functies om video's te bewerken of informatie eruit "
            "te halen. Je hoeft geen FFmpeg-kennis te hebben. Klik op ? voor "
            "uitleg voordat je een functie gebruikt."
        )
        intro.setObjectName("intro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        tools = [
            (
                "🎵",
                "AUDIO UIT VIDEO",
                "Haal de audio uit een video en bewaar hem als MP3, M4A of WAV.",
                self.open_audio,
                "Deze functie haalt alleen het geluid uit een video. "
                "De video zelf wordt niet aangepast. MP3 is handig voor "
                "algemeen gebruik, M4A voor goede kwaliteit met een klein "
                "bestand en WAV wanneer je ongecomprimeerde audio nodig hebt.",
            ),
            (
                "✂️",
                "VIDEO KNIPPEN",
                "Maak een kortere video door een begin- en eindpunt te kiezen.",
                self.open_cut,
                "Gebruik dit wanneer je bijvoorbeeld alleen een fragment "
                "uit een lange opname nodig hebt. Het originele bestand "
                "blijft bestaan. De nieuwe video wordt apart opgeslagen.",
            ),
            (
                "🖼️",
                "THUMBNAIL MAKEN",
                "Maak een JPG-afbeelding van een gekozen moment uit een video.",
                self.open_thumbnail,
                "Een thumbnail is een afbeelding die een video vertegenwoordigt. "
                "Handig voor een videobibliotheek, website, overzicht of "
                "eigen administratie.",
            ),
            (
                "🔍",
                "VIDEO CONTROLEREN",
                "Controleer of een videobestand technisch leesbaar is.",
                self.check_video,
                "FFprobe probeert het bestand te openen en leest de technische "
                "informatie. Zo kun je snel zien of een video beschadigd of "
                "onleesbaar is.",
            ),
            (
                "📋",
                "STREAMS BEKIJKEN",
                "Bekijk video, audio, ondertitels en andere streams in een bestand.",
                self.show_streams,
                "Een videobestand kan meerdere onderdelen bevatten: bijvoorbeeld "
                "een videostream, meerdere audiotalen, ondertitels en metadata. "
                "Deze functie laat zien wat er werkelijk in het bestand zit.",
            ),
        ]

        for index, tool in enumerate(tools):
            grid.addWidget(
                ToolCard(*tool, parent=self),
                index // 2,
                index % 2,
            )

        layout.addLayout(grid, 1)

        footer = QFrame()
        footer.setObjectName("footer")

        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 10)

        footer_text = QLabel(
            "Alle bewerkingen maken standaard een nieuw bestand."
        )
        footer_text.setObjectName("footerText")

        footer_layout.addWidget(footer_text)
        footer_layout.addStretch(1)

        close_button = QPushButton("Sluiten")
        close_button.clicked.connect(self.close)
        footer_layout.addWidget(close_button)

        layout.addWidget(footer)

        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet("""
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
            }

            QLabel#credit {
                color: #ffffff;
                font-size: 18px;
                font-weight: 800;
                padding: 10px 16px;
                background: #15181d;
                border: 1px solid #3d434d;
                border-radius: 8px;
                min-width: 190px;
            }

            QFrame#toolCard {
                background: #191c22;
                border: 1px solid #303640;
                border-radius: 12px;
            }

            QFrame#toolCard:hover {
                border: 1px solid #4b5666;
                background: #1c2027;
            }

            QLabel#toolIcon {
                font-size: 30px;
                background: transparent;
            }

            QLabel#toolTitle {
                font-size: 19px;
                font-weight: 800;
                color: #ffffff;
                background: transparent;
            }

            QLabel#toolDescription {
                color: #929aa7;
                background: transparent;
                padding: 4px 0 8px;
            }

            QPushButton {
                background: #292e36;
                border: 1px solid #3c424c;
                border-radius: 7px;
                padding: 9px 14px;
                font-weight: 600;
                color: #e8eaed;
            }

            QPushButton:hover {
                background: #353b45;
            }

            QPushButton#toolButton,
            QPushButton#primary {
                background: #315f9e;
                border-color: #4679bd;
                color: #ffffff;
            }

            QPushButton#toolButton:hover,
            QPushButton#primary:hover {
                background: #3b70b6;
            }

            QPushButton#helpButton {
                background: #315f9e;
                border: 1px solid #4679bd;
                border-radius: 16px;
                padding: 0;
                font-size: 17px;
                font-weight: 900;
                color: #ffffff;
            }

            QPushButton#helpButton:hover {
                background: #3b70b6;
            }

            QFrame#footer {
                background: #15181d;
                border: 1px solid #2d323a;
                border-radius: 8px;
            }

            QLabel#footerText {
                color: #7f8793;
            }

            QDialog {
                background: #101216;
                color: #e8eaed;
            }

            QLabel#dialogTitle {
                color: #ffffff;
                font-size: 25px;
                font-weight: 900;
            }

            QLabel#dialogInfo {
                color: #aeb5c0;
                font-size: 14px;
            }

            QLineEdit,
            QComboBox,
            QSpinBox {
                background: #1e2127;
                border: 1px solid #353a43;
                border-radius: 6px;
                padding: 7px;
                color: #e8eaed;
            }
        """)

    def open_audio(self):
        dialog = AudioExtractDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        source, output, fmt = dialog.values()

        if not source or not Path(source).is_file():
            QMessageBox.warning(self, "Audio", "De gekozen video bestaat niet.")
            return

        if not output:
            output = str(Path(source).parent)

        ffmpeg = find_ffmpeg()

        if not ffmpeg:
            QMessageBox.critical(
                self,
                "FFmpeg ontbreekt",
                "FFmpeg kon niet worden gevonden.",
            )
            return

        target = Path(output) / f"{Path(source).stem}.{fmt}"

        if fmt == "mp3":
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                source,
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                "-y",
                str(target),
            ]
        elif fmt == "m4a":
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                source,
                "-vn",
                "-codec:a",
                "aac",
                "-b:a",
                "192k",
                "-y",
                str(target),
            ]
        else:
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                source,
                "-vn",
                "-codec:a",
                "pcm_s16le",
                "-y",
                str(target),
            ]

        self.run_ffmpeg(
            command,
            "Audio maken",
            f"Audio opgeslagen als:\n{target}",
        )

    def open_cut(self):
        dialog = CutDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        source, output, start, end = dialog.values()

        ffmpeg = find_ffmpeg()

        if not ffmpeg:
            QMessageBox.critical(
                self,
                "FFmpeg ontbreekt",
                "FFmpeg kon niet worden gevonden.",
            )
            return

        source_path = Path(source)
        target = Path(output) / (
            f"{source_path.stem}_knip{source_path.suffix}"
        )

        duration = end - start

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(start),
            "-i",
            source,
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-y",
            str(target),
        ]

        self.run_ffmpeg(
            command,
            "Video knippen",
            f"Nieuw videofragment opgeslagen als:\n{target}",
        )

    def open_thumbnail(self):
        dialog = ThumbnailDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        source, output, second = dialog.values()

        ffmpeg = find_ffmpeg()

        if not ffmpeg:
            QMessageBox.critical(
                self,
                "FFmpeg ontbreekt",
                "FFmpeg kon niet worden gevonden.",
            )
            return

        target = Path(output) / f"{Path(source).stem}_thumbnail.jpg"

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(second),
            "-i",
            source,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(target),
        ]

        self.run_ffmpeg(
            command,
            "Thumbnail maken",
            f"Thumbnail opgeslagen als:\n{target}",
        )

    def check_video(self):
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Kies video om te controleren",
            "",
            "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv);;Alle bestanden (*)",
        )

        if not source:
            return

        ffprobe = find_ffprobe()

        if not ffprobe:
            QMessageBox.critical(
                self,
                "FFprobe ontbreekt",
                "FFprobe kon niet worden gevonden.",
            )
            return

        command = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=filename,duration,size,format_name",
            "-show_streams",
            "-of",
            "json",
            source,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if os.name == "nt"
                    else 0
                ),
            )

            if result.returncode != 0:
                QMessageBox.critical(
                    self,
                    "Video controleren",
                    "Het bestand kon niet correct worden gelezen.\n\n"
                    + result.stderr.strip(),
                )
                return

            QMessageBox.information(
                self,
                "Video controleren",
                "Het videobestand kan technisch worden gelezen.\n\n"
                f"Bestand:\n{Path(source).name}",
            )

        except OSError as exc:
            QMessageBox.critical(
                self,
                "Video controleren",
                str(exc),
            )

    def show_streams(self):
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Kies video",
            "",
            "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv);;Alle bestanden (*)",
        )

        if not source:
            return

        ffprobe = find_ffprobe()

        if not ffprobe:
            QMessageBox.critical(
                self,
                "FFprobe ontbreekt",
                "FFprobe kon niet worden gevonden.",
            )
            return

        command = [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            source,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if os.name == "nt"
                    else 0
                ),
            )

            if result.returncode != 0:
                QMessageBox.critical(
                    self,
                    "Streams",
                    result.stderr.strip(),
                )
                return

            data = json.loads(result.stdout)

            lines = [
                f"Bestand: {Path(source).name}",
                "",
                "STREAMS",
                "=======",
            ]

            for index, stream in enumerate(data.get("streams", []), 1):
                codec_type = stream.get("codec_type", "onbekend")
                codec = stream.get("codec_name", "onbekend")
                language = (
                    stream.get("tags", {}).get("language", "")
                )

                line = f"{index}. {codec_type.upper()} - {codec}"

                if language:
                    line += f" - taal: {language}"

                if codec_type == "video":
                    width = stream.get("width")
                    height = stream.get("height")
                    fps = stream.get("r_frame_rate")

                    if width and height:
                        line += f" - {width}x{height}"

                    if fps:
                        line += f" - {fps} FPS"

                if codec_type == "audio":
                    channels = stream.get("channels")
                    sample_rate = stream.get("sample_rate")

                    if channels:
                        line += f" - {channels} kanalen"

                    if sample_rate:
                        line += f" - {sample_rate} Hz"

                lines.append(line)

            format_data = data.get("format", {})

            lines.extend([
                "",
                "CONTAINER",
                "=========",
                f"Formaat: {format_data.get('format_name', 'onbekend')}",
                f"Duur: {format_data.get('duration', 'onbekend')} sec",
                f"Grootte: {format_data.get('size', 'onbekend')} bytes",
            ])

            dialog = QDialog(self)
            dialog.setWindowTitle("Video Streams")
            dialog.resize(760, 560)

            dialog_layout = QVBoxLayout(dialog)

            text = QLabel("\n".join(lines))
            text.setWordWrap(True)
            text.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            text.setStyleSheet(
                "font-family: Consolas, monospace; "
                "font-size: 13px; padding: 12px;"
            )

            dialog_layout.addWidget(text, 1)

            close = QPushButton("Sluiten")
            close.clicked.connect(dialog.accept)
            dialog_layout.addWidget(
                close,
                alignment=Qt.AlignmentFlag.AlignRight,
            )

            dialog.setStyleSheet("""
                QDialog {
                    background: #101216;
                    color: #e8eaed;
                }

                QLabel {
                    color: #d9dde4;
                    background: #191c22;
                    border: 1px solid #303640;
                    border-radius: 8px;
                }

                QPushButton {
                    background: #315f9e;
                    border: 1px solid #4679bd;
                    border-radius: 7px;
                    padding: 9px 18px;
                    color: white;
                }
            """)

            dialog.exec()

        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(
                self,
                "Streams",
                str(exc),
            )

    def run_ffmpeg(self, command, title, success_message):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if os.name == "nt"
                    else 0
                ),
            )

            if result.returncode == 0:
                QMessageBox.information(
                    self,
                    title,
                    success_message,
                )
            else:
                QMessageBox.critical(
                    self,
                    title,
                    "FFmpeg kon de bewerking niet uitvoeren.\n\n"
                    + result.stderr.strip(),
                )

        except OSError as exc:
            QMessageBox.critical(
                self,
                title,
                str(exc),
            )


DIALOG_STYLE = """
    QDialog {
        background: #101216;
        color: #e8eaed;
    }

    QLabel#dialogTitle {
        color: #ffffff;
        font-size: 25px;
        font-weight: 900;
    }

    QLabel#dialogInfo {
        color: #aeb5c0;
        font-size: 14px;
    }

    QLineEdit,
    QComboBox,
    QSpinBox {
        background: #1e2127;
        border: 1px solid #353a43;
        border-radius: 6px;
        padding: 7px;
        color: #e8eaed;
    }

    QPushButton {
        background: #292e36;
        border: 1px solid #3c424c;
        border-radius: 7px;
        padding: 9px 14px;
        font-weight: 600;
        color: #e8eaed;
    }

    QPushButton:hover {
        background: #353b45;
    }

    QPushButton#primary {
        background: #315f9e;
        border-color: #4679bd;
        color: #ffffff;
    }
"""


def main():
    app = QApplication.instance()

    if app is None:
        app = QApplication([])

    app.setApplicationName("VideoAudioScanner")

    window = VideoToolsWindow()
    window.show()

    if QApplication.instance() is app:
        app.exec()


if __name__ == "__main__":
    main()
