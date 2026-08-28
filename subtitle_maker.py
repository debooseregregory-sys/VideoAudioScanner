from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


VIDEO_EXTENSIONS = (
    "*.mp4 *.mkv *.avi *.mov *.wmv *.webm "
    "*.m4v *.mpeg *.mpg *.ts *.mts *.m2ts *.flv"
)


def find_whisper() -> Path | None:
    """
    Zoek Faster-Whisper XXL op de standaardlocatie
    van Subtitle Edit.
    """

    appdata = os.environ.get("APPDATA")

    if not appdata:
        return None

    path = (
        Path(appdata)
        / "Subtitle Edit"
        / "SpeechToText"
        / "Purfview-Faster-Whisper-XXL"
        / "faster-whisper-xxl.exe"
    )

    if path.is_file():
        return path

    return None


class SubtitleMakerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.process = None
        self.source_file = None

        self.setWindowTitle("VideoAudioScanner - Subtitle Maker")
        self.resize(900, 700)

        self._build_ui()
        self._apply_theme()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()

        title_box = QVBoxLayout()

        title = QLabel("SUBTITLE MAKER")
        title.setObjectName("suiteTitle")
        title_box.addWidget(title)

        subtitle = QLabel(
            "Automatisch ondertitels maken met Faster-Whisper XXL"
        )
        subtitle.setObjectName("suiteSubtitle")
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch(1)

        credit = QLabel("MADE BY KID ACID")
        credit.setObjectName("credit")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header.addWidget(credit)

        layout.addLayout(header)

        # Info
        info = QLabel(
            "Kies een video of audiobestand. Faster-Whisper XXL "
            "herkent automatisch de gesproken taal en maakt een "
            "SRT-bestand. De vertaalmodus wordt gebruikt zodat "
            "de ondertitels naar het Engels worden vertaald."
        )

        info.setObjectName("info")
        info.setWordWrap(True)

        layout.addWidget(info)

        # File frame
        file_frame = QFrame()
        file_frame.setObjectName("panel")

        file_layout = QVBoxLayout(file_frame)

        file_title = QLabel("BRONBESTAND")
        file_title.setObjectName("sectionTitle")
        file_layout.addWidget(file_title)

        file_row = QHBoxLayout()

        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText(
            "Kies een video- of audiobestand..."
        )

        self.browse_button = QPushButton("Bladeren...")
        self.browse_button.clicked.connect(self.choose_source)

        file_row.addWidget(self.source_edit, 1)
        file_row.addWidget(self.browse_button)

        file_layout.addLayout(file_row)

        layout.addWidget(file_frame)

        # Settings
        settings_frame = QFrame()
        settings_frame.setObjectName("panel")

        settings_layout = QVBoxLayout(settings_frame)

        settings_title = QLabel("INSTELLINGEN")
        settings_title.setObjectName("sectionTitle")
        settings_layout.addWidget(settings_title)

        model_label = QLabel(
            "Model: large-v3"
        )
        model_label.setObjectName("setting")

        task_label = QLabel(
            "Taak: translate"
        )
        task_label.setObjectName("setting")

        format_label = QLabel(
            "Uitvoer: SRT"
        )
        format_label.setObjectName("setting")

        language_label = QLabel(
            "Taal: automatisch herkennen"
        )
        language_label.setObjectName("setting")

        settings_layout.addWidget(model_label)
        settings_layout.addWidget(task_label)
        settings_layout.addWidget(format_label)
        settings_layout.addWidget(language_label)

        layout.addWidget(settings_frame)

        # Output
        output_frame = QFrame()
        output_frame.setObjectName("panel")

        output_layout = QVBoxLayout(output_frame)

        output_title = QLabel("UITVOER")
        output_title.setObjectName("sectionTitle")
        output_layout.addWidget(output_title)

        self.output_label = QLabel(
            "De SRT wordt automatisch naast het bronbestand geplaatst."
        )

        self.output_label.setObjectName("outputLabel")
        self.output_label.setWordWrap(True)

        output_layout.addWidget(self.output_label)

        layout.addWidget(output_frame)

        # Progress
        progress_frame = QFrame()
        progress_frame.setObjectName("panel")

        progress_layout = QVBoxLayout(progress_frame)

        progress_title = QLabel("VOORTGANG")
        progress_title.setObjectName("sectionTitle")
        progress_layout.addWidget(progress_title)

        self.status_label = QLabel("Klaar om te starten.")
        self.status_label.setObjectName("status")

        progress_layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        progress_layout.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(320)

        progress_layout.addWidget(self.log)

        layout.addWidget(progress_frame, 1)

        # Buttons
        buttons = QHBoxLayout()

        buttons.addStretch(1)

        self.start_button = QPushButton(
            "▶  Ondertitels maken"
        )
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start_subtitles)

        self.cancel_button = QPushButton(
            "Stoppen"
        )
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.stop_process)

        close_button = QPushButton("Sluiten")
        close_button.clicked.connect(self.close)

        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(close_button)

        layout.addLayout(buttons)

        self.setCentralWidget(root)

    # ---------------------------------------------------------
    # THEME
    # ---------------------------------------------------------

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
            }

            QLabel#suiteSubtitle {
                font-size: 15px;
                color: #8f96a3;
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

            QLabel#info {
                color: #aeb5c0;
                font-size: 14px;
                padding: 4px;
            }

            QFrame#panel {
                background: #191c22;
                border: 1px solid #303640;
                border-radius: 10px;
            }

            QLabel#sectionTitle {
                color: #ffffff;
                font-size: 16px;
                font-weight: 800;
            }

            QLabel#setting {
                color: #b7bec9;
                padding: 3px;
            }

            QLabel#outputLabel {
                color: #929aa7;
            }

            QLabel#status {
                color: #ffffff;
                font-weight: 700;
            }

            QLineEdit {
                background: #1e2127;
                border: 1px solid #353a43;
                border-radius: 6px;
                padding: 9px;
                color: #e8eaed;
            }

            QTextEdit {
                background: #101216;
                border: 1px solid #303640;
                border-radius: 7px;
                color: #cbd1da;
                font-family: Consolas, monospace;
                font-size: 12px;
            }

            QProgressBar {
                background: #101216;
                border: 1px solid #353a43;
                border-radius: 6px;
                height: 12px;
                text-align: center;
            }

            QProgressBar::chunk {
                background: #315f9e;
                border-radius: 5px;
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

            QPushButton#primary:hover {
                background: #3b70b6;
            }

            QPushButton#danger {
                background: #6b3030;
                border-color: #8d4141;
                color: #ffffff;
            }

            QPushButton#danger:hover {
                background: #824040;
            }

            QPushButton:disabled {
                color: #666d78;
                background: #202329;
                border-color: #2d323a;
            }
        """)

    # ---------------------------------------------------------
    # FILE SELECT
    # ---------------------------------------------------------

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Kies video of audio",
            "",
            (
                "Video/audio bestanden ("
                "*.mp4 *.mkv *.avi *.mov *.wmv *.webm "
                "*.m4v *.mpeg *.mpg *.ts *.mts *.m2ts "
                "*.flv *.mp3 *.wav *.m4a *.aac *.flac *.ogg"
                ");;"
                "Alle bestanden (*)"
            ),
        )

        if not path:
            return

        self.source_file = Path(path)
        self.source_edit.setText(path)

        output = self.source_file.with_suffix(".srt")

        self.output_label.setText(
            f"SRT-uitvoer:\n{output}"
        )

        self.log.clear()
        self.status_label.setText(
            "Bestand geselecteerd. Klaar om te starten."
        )

    # ---------------------------------------------------------
    # START
    # ---------------------------------------------------------

    def start_subtitles(self):
        source_text = self.source_edit.text().strip()

        if not source_text:
            QMessageBox.warning(
                self,
                "Subtitle Maker",
                "Kies eerst een video- of audiobestand.",
            )
            return

        source = Path(source_text)

        if not source.is_file():
            QMessageBox.warning(
                self,
                "Subtitle Maker",
                "Het gekozen bestand bestaat niet.",
            )
            return

        whisper = find_whisper()

        if whisper is None:
            QMessageBox.critical(
                self,
                "Faster-Whisper XXL ontbreekt",
                (
                    "Faster-Whisper XXL kon niet worden gevonden.\n\n"
                    "Verwachte locatie:\n\n"
                    f"{os.environ.get('APPDATA', '%APPDATA%')}"
                    "\\Subtitle Edit\\SpeechToText\\"
                    "Purfview-Faster-Whisper-XXL\\"
                    "faster-whisper-xxl.exe"
                ),
            )
            return

        self.source_file = source

        output_dir = source.parent

        command = [
            str(whisper),
            str(source),
            "--model",
            "large-v3",
            "--task",
            "translate",
            "--output_format",
            "srt",
            "--output_dir",
            "source",
        ]

        self.log.clear()

        self.log.append("SUBTITLE MAKER")
        self.log.append("=" * 60)
        self.log.append("")
        self.log.append(f"Bronbestand: {source}")
        self.log.append(f"Model: large-v3")
        self.log.append(f"Taak: translate")
        self.log.append(f"Uitvoer: SRT")
        self.log.append("")
        self.log.append(
            "Faster-Whisper XXL wordt gestart..."
        )
        self.log.append("")

        self.status_label.setText(
            "Ondertitels worden gemaakt..."
        )

        self.progress.setVisible(True)

        self.start_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        self.process = QProcess(self)

        self.process.setProgram(str(whisper))
        self.process.setArguments(command[1:])

        self.process.readyReadStandardOutput.connect(
            self.read_output
        )

        self.process.readyReadStandardError.connect(
            self.read_error
        )

        self.process.finished.connect(
            self.process_finished
        )

        self.process.errorOccurred.connect(
            self.process_error
        )

        self.process.start()

    # ---------------------------------------------------------
    # OUTPUT
    # ---------------------------------------------------------

    def read_output(self):
        if self.process is None:
            return

        data = self.process.readAllStandardOutput()

        if not data:
            return

        text = bytes(data).decode(
            "utf-8",
            errors="replace",
        )

        # Faster-Whisper gebruikt soms \r voor voortgang.
        # Maak daar normale, leesbare regels van.
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")

        for line in text.split("\n"):
            line = line.strip()

            if line:
                self.log.append(line)

        # Altijd naar de nieuwste uitvoer scrollen.
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def read_error(self):
        if self.process is None:
            return

        data = self.process.readAllStandardError()

        if not data:
            return

        text = bytes(data).decode(
            "utf-8",
            errors="replace",
        )

        # Ook stderr kan voortgangsinformatie bevatten.
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")

        for line in text.split("\n"):
            line = line.strip()

            if line:
                self.log.append(line)

        # Altijd naar de nieuwste uitvoer scrollen.
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    # ---------------------------------------------------------
    # PROCESS FINISHED
    # ---------------------------------------------------------

    def process_finished(self, exit_code, exit_status):
        self.progress.setVisible(False)

        self.start_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        self.process = None

        source = self.source_file
        srt = source.with_suffix(".srt")

        self.log.append("")
        self.log.append("=" * 60)

        # Het daadwerkelijke SRT-bestand bepaalt of de opdracht gelukt is.
        if srt.is_file() and srt.stat().st_size > 0:
            self.status_label.setText(
                "Ondertitels succesvol gemaakt."
            )

            self.log.append("KLAAR")
            self.log.append("=" * 60)
            self.log.append("")
            self.log.append(f"SRT-bestand:")
            self.log.append(str(srt))

            QMessageBox.information(
                self,
                "Subtitle Maker",
                (
                    "De ondertitels zijn succesvol gemaakt.\n\n"
                    f"{srt}"
                ),
            )
            return

        self.status_label.setText(
            f"Fout tijdens maken van ondertitels (code {exit_code})."
        )

        self.log.append(
            f"FOUT - exit code {exit_code}"
        )
        self.log.append("=" * 60)

        QMessageBox.critical(
            self,
            "Subtitle Maker",
            (
                "Faster-Whisper XXL kon de ondertitels niet maken.\n\n"
                f"Exit code: {exit_code}\n\n"
                "Bekijk het logvenster voor meer informatie."
            ),
        )

    # ---------------------------------------------------------
    # PROCESS ERROR
    # ---------------------------------------------------------

    def process_error(self, error):
        # QProcess kan errorOccurred signaleren tijdens/na een proces-
        # levenscyclus. Alleen een fout waarbij het proces werkelijk
        # niet gestart kon worden behandelen we als startfout.
        if self.process is None:
            return

        if self.process.state() != QProcess.ProcessState.NotRunning:
            return

        # Als er al een geldig SRT-bestand bestaat, is de opdracht
        # geslaagd en mag deze signalering geen foutmelding veroorzaken.
        if self.source_file is not None:
            srt = self.source_file.with_suffix(".srt")

            if srt.is_file() and srt.stat().st_size > 0:
                return

        self.progress.setVisible(False)

        self.start_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        self.status_label.setText(
            "Fout bij starten van Faster-Whisper."
        )

        self.log.append("")
        self.log.append("=" * 60)
        self.log.append("FOUT BIJ STARTEN")
        self.log.append("=" * 60)
        self.log.append("")
        self.log.append(f"Procesfout: {error}")

        QMessageBox.critical(
            self,
            "Subtitle Maker",
            (
                "Faster-Whisper XXL kon niet worden gestart.\n\n"
                f"Fout: {error}"
            ),
        )

        self.process = None
    # ---------------------------------------------------------
    # STOP
    # ---------------------------------------------------------

    def stop_process(self):
        if self.process is None:
            return

        answer = QMessageBox.question(
            self,
            "Ondertitels stoppen",
            "Wil je het maken van de ondertitels stoppen?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.process.kill()

        self.status_label.setText(
            "Ondertiteling gestopt."
        )

        self.progress.setVisible(False)

        self.start_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        self.log.append("")
        self.log.append(
            "Proces door gebruiker gestopt."
        )

        self.process = None

    # ---------------------------------------------------------
    # CLOSE
    # ---------------------------------------------------------

    def closeEvent(self, event):
        if self.process is not None:
            answer = QMessageBox.question(
                self,
                "Subtitle Maker",
                (
                    "Faster-Whisper is nog bezig.\n\n"
                    "Wil je de bewerking stoppen en het "
                    "venster sluiten?"
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
            )

            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            self.process.kill()
            self.process = None

        event.accept()


def main():
    app = QApplication.instance()

    if app is None:
        app = QApplication([])

    app.setApplicationName("VideoAudioScanner")

    window = SubtitleMakerWindow()
    window.show()

    if QApplication.instance() is app:
        app.exec()


if __name__ == "__main__":
    main()





