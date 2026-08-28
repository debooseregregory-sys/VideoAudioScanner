from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from scanner import VIDEO_EXTENSIONS
except Exception:
    VIDEO_EXTENSIONS = {
        ".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm",
        ".ts", ".mts", ".m2ts", ".wmv", ".flv", ".mpeg", ".mpg",
    }


# ============================================================
# FFmpeg discovery
# ============================================================

def find_ffmpeg() -> str | None:
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    found = shutil.which(name)
    if found:
        return found

    here = Path(__file__).resolve().parent
    candidates = [
        here / "ffmpeg.exe",
        here / "ffmpeg" / "bin" / name,
        here / "tools" / name,
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return None


def find_ffprobe(ffmpeg: str | None = None) -> str | None:
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    found = shutil.which(name)
    if found:
        return found

    if ffmpeg:
        candidate = Path(ffmpeg).with_name(name)
        if candidate.is_file():
            return str(candidate)

    here = Path(__file__).resolve().parent
    candidates = [
        here / name,
        here / "ffmpeg" / "bin" / name,
        here / "tools" / name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def probe_duration(ffprobe: str | None, path: str) -> float | None:
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            timeout=20,
        )
        value = result.stdout.strip()
        duration = float(value)
        return duration if duration > 0 else None
    except Exception:
        return None


# ============================================================
# Help dialog
# ============================================================

class HelpDialog(QDialog):
    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Uitleg - " + title)
        self.setMinimumWidth(560)
        self.setMinimumHeight(280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        heading = QLabel(title)
        heading.setObjectName("helpTitle")
        layout.addWidget(heading)

        message = QLabel(text)
        message.setObjectName("helpText")
        message.setWordWrap(True)
        layout.addWidget(message, 1)

        close_button = QPushButton("Sluiten")
        close_button.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_button)
        layout.addLayout(row)

        self.setStyleSheet("""
            QDialog { background:#101216; color:#e8eaed; }
            QLabel#helpTitle { color:#fff; font-size:24px; font-weight:800; }
            QLabel#helpText { color:#c5cad2; font-size:14px; }
            QPushButton { background:#315f9e; border:1px solid #4679bd; border-radius:7px;
                          padding:9px 18px; color:#fff; font-weight:600; }
            QPushButton:hover { background:#3b70b6; }
        """)


# ============================================================
# Worker
# ============================================================

class ConvertWorker(QThread):
    # index, total, filename, percent, status
    progress = Signal(int, int, str, int, str)
    finished_ok = Signal(int, int, bool)
    error = Signal(str)

    def __init__(
        self,
        files: list[str],
        output_dir: str,
        container: str,
        video_codec: str,
        quality: str,
        resolution: str,
        audio_codec: str,
        overwrite: bool,
    ):
        super().__init__()
        self.files = list(files)
        self.output_dir = output_dir
        self.container = container
        self.video_codec = video_codec
        self.quality = quality
        self.resolution = resolution
        self.audio_codec = audio_codec
        self.overwrite = overwrite
        self.cancel_requested = False
        self._process: subprocess.Popen | None = None
        self._ffprobe = None

    def cancel(self):
        self.cancel_requested = True
        process = self._process
        if process is None or process.poll() is not None:
            return

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _build_command(self, ffmpeg: str, source: Path, target: Path) -> list[str]:
        command = [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-progress", "pipe:1",
            "-i", str(source),
        ]

        if self.video_codec == "copy":
            command += ["-c:v", "copy"]
        else:
            command += ["-c:v", self.video_codec]
            if self.video_codec in {"libx264", "libx265"}:
                command += ["-preset", "medium", "-crf", self.quality]
            elif self.video_codec == "libsvtav1":
                command += ["-preset", "6", "-crf", self.quality]

        if self.resolution != "Origineel":
            command += [
                "-vf",
                f"scale={self.resolution}:force_original_aspect_ratio=decrease",
            ]

        if self.audio_codec == "copy":
            command += ["-c:a", "copy"]
        elif self.audio_codec == "none":
            command += ["-an"]
        else:
            command += ["-c:a", self.audio_codec]
            if self.audio_codec == "aac":
                command += ["-b:a", "192k"]
            elif self.audio_codec == "libopus":
                command += ["-b:a", "160k"]

        if self.container == "mp4":
            command += ["-movflags", "+faststart"]

        command += ["-y" if self.overwrite else "-n", str(target)]
        return command

    def _emit_progress(self, index, total, name, percent, status):
        self.progress.emit(index, total, name, max(0, min(100, int(percent))), status)

    def _run_one(self, index: int, total: int, source: Path, target: Path, ffmpeg: str) -> bool:
        name = source.name
        duration = probe_duration(self._ffprobe, str(source))
        command = self._build_command(ffmpeg, source, target)

        self._emit_progress(index, total, name, 0, "Bezig...")

        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=(
                    subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                    if os.name == "nt" else 0
                ),
            )

            process = self._process
            last_percent = 0
            stderr_lines: list[str] = []

            # FFmpeg writes progress key/value pairs to stdout. stderr is
            # drained separately so a full stderr pipe can never deadlock.
            import threading

            def drain_stderr():
                if process.stderr is None:
                    return
                try:
                    for line in process.stderr:
                        text = line.strip()
                        if text:
                            stderr_lines.append(text)
                except Exception:
                    pass

            stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
            stderr_thread.start()

            if process.stdout is not None:
                for raw in process.stdout:
                    line = raw.strip()
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    if key != "out_time_ms":
                        continue
                    try:
                        seconds = float(value) / 1_000_000.0
                    except ValueError:
                        continue
                    if duration:
                        percent = int((seconds / duration) * 100)
                        if percent > last_percent:
                            last_percent = min(percent, 99)
                            self._emit_progress(index, total, name, last_percent, "Bezig...")

            returncode = process.wait()
            stderr_thread.join(timeout=2)
            self._process = None

            if self.cancel_requested:
                self._emit_progress(index, total, name, last_percent, "Geannuleerd")
                return False

            if returncode == 0 and target.is_file() and target.stat().st_size > 0:
                self._emit_progress(index, total, name, 100, "Klaar")
                return True

            self._emit_progress(index, total, name, last_percent, "Mislukt")
            return False

        except Exception as exc:
            self._process = None
            if self.cancel_requested:
                self._emit_progress(index, total, name, 0, "Geannuleerd")
            else:
                self._emit_progress(index, total, name, 0, "Mislukt")
            return False
        finally:
            self._process = None

    def run(self):
        ffmpeg = find_ffmpeg()
        self._ffprobe = find_ffprobe(ffmpeg)

        if not ffmpeg:
            self.error.emit(
                "FFmpeg is niet gevonden.\n\n"
                "Plaats ffmpeg.exe naast video_converter.py of installeer FFmpeg."
            )
            return

        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as exc:
            self.error.emit("De doelmap kan niet worden aangemaakt:\n\n" + str(exc))
            return

        success = 0
        failed = 0
        total = len(self.files)

        for index, source in enumerate(self.files, 1):
            if self.cancel_requested:
                break

            source_path = Path(source)
            target = Path(self.output_dir) / f"{source_path.stem}.{self.container}"
            if target.resolve() == source_path.resolve():
                target = Path(self.output_dir) / f"{source_path.stem}_converted.{self.container}"

            if self._run_one(index, total, source_path, target, ffmpeg):
                success += 1
            else:
                if not self.cancel_requested:
                    failed += 1

        self._process = None
        self.finished_ok.emit(success, failed, self.cancel_requested)


# ============================================================
# Wizard
# ============================================================

class ConvertWizard(QDialog):
    finished = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Converter - Wizard")
        self.resize(720, 600)
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel("VIDEO CONVERTER WIZARD")
        title.setObjectName("wizardTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Je hoeft niets van codecs of technische instellingen te kennen. "
            "Kies gewoon wat je met de video wilt bereiken."
        )
        intro.setObjectName("wizardIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        question = QLabel("Wat wil je bereiken?")
        question.setObjectName("question")
        layout.addWidget(question)
        self.choice = QComboBox()
        self.choice.addItem("Ik wil dat de video bijna overal afspeelt", "compatibility")
        self.choice.addItem("Ik wil een kleiner bestand", "smaller")
        self.choice.addItem("Ik wil zo klein mogelijk", "av1")
        self.choice.addItem("Ik wil vooral de beste beeldkwaliteit", "quality")
        self.choice.addItem("Ik wil alleen het formaat veranderen", "copy")
        self.choice.addItem("Ik wil de video kleiner maken voor een scherm", "resolution")
        layout.addWidget(self.choice)
        explanation_title = QLabel("Wat gaat de wizard doen?")
        explanation_title.setObjectName("sectionTitle")
        layout.addWidget(explanation_title)
        self.explanation = QLabel()
        self.explanation.setObjectName("explanation")
        self.explanation.setWordWrap(True)
        layout.addWidget(self.explanation)
        self.choice.currentIndexChanged.connect(self.update_explanation)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("separator")
        layout.addWidget(separator)
        destination_title = QLabel("Doelformaat")
        destination_title.setObjectName("sectionTitle")
        layout.addWidget(destination_title)
        destination_text = QLabel(
            "De wizard kiest automatisch een geschikt formaat. Je kunt het hieronder nog aanpassen."
        )
        destination_text.setObjectName("smallText")
        destination_text.setWordWrap(True)
        layout.addWidget(destination_text)
        self.container = QComboBox()
        self.container.addItems(["mp4", "mkv", "webm"])
        form = QFormLayout()
        form.addRow("Formaat:", self.container)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Annuleren")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        apply_button = QPushButton("Instellingen gebruiken")
        apply_button.setObjectName("primary")
        apply_button.clicked.connect(self.apply_settings)
        buttons.addWidget(apply_button)
        layout.addLayout(buttons)
        self.update_explanation()

    def update_explanation(self):
        mode = self.choice.currentData()
        explanations = {
            "compatibility": "De veilige keuze voor normaal gebruik. De wizard gebruikt MP4 met H.264-video en AAC-audio. Dit formaat werkt op de meeste computers, televisies, telefoons en mediaspelers.",
            "smaller": "De video wordt omgezet naar H.265/HEVC. Daarmee kun je meestal een kleiner bestand krijgen terwijl de beeldkwaliteit goed blijft. De conversie duurt wel langer dan bij H.264.",
            "av1": "AV1 probeert de video zo efficient mogelijk te comprimeren. Dit kan een zeer klein bestand opleveren, maar het omzetten kan veel langer duren en oudere apparaten ondersteunen AV1 niet altijd.",
            "quality": "Hier staat beeldkwaliteit voorop. De video wordt opnieuw gecodeerd met een hoge kwaliteit. Het bestand kan daardoor groter blijven.",
            "copy": "De bestaande video- en audiostreams worden niet opnieuw gecodeerd. Daardoor is er geen extra kwaliteitsverlies en gaat het veel sneller. Dit werkt alleen wanneer de streams geschikt zijn voor het gekozen formaat.",
            "resolution": "De video krijgt een lagere resolutie. Dit is handig voor bijvoorbeeld een telefoon, tablet of kleiner scherm. Een video van 4K kan bijvoorbeeld naar 1080p worden gebracht.",
        }
        self.explanation.setText(explanations.get(mode, ""))
        if mode == "copy":
            self.container.setCurrentText("mkv")
        elif mode == "av1":
            self.container.setCurrentText("webm")
        else:
            self.container.setCurrentText("mp4")

    def apply_settings(self):
        self.finished.emit({"mode": self.choice.currentData(), "container": self.container.currentText()})
        self.accept()

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog { background:#101216; color:#e8eaed; }
            QLabel#wizardTitle { font-size:28px; font-weight:900; color:#fff; }
            QLabel#wizardIntro { color:#aeb5c0; font-size:14px; }
            QLabel#question { color:#fff; font-size:21px; font-weight:800; }
            QLabel#sectionTitle { color:#fff; font-size:17px; font-weight:800; }
            QLabel#explanation { background:#191c22; border:1px solid #343b46; border-radius:9px; color:#c9ced6; padding:16px; font-size:14px; }
            QLabel#smallText { color:#8f97a4; font-size:13px; }
            QComboBox { background:#1e2127; border:1px solid #3b424d; border-radius:7px; padding:9px; color:#fff; min-height:20px; }
            QPushButton { background:#292e36; border:1px solid #3c424c; border-radius:7px; padding:9px 16px; color:#fff; font-weight:600; }
            QPushButton:hover { background:#353b45; }
            QPushButton#primary { background:#315f9e; border-color:#4679bd; }
        """)


# ============================================================
# Converter window
# ============================================================

class VideoConverterWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VideoAudioScanner - Video Converter")
        self.resize(1250, 850)
        self.files: list[str] = []
        self.worker: ConvertWorker | None = None
        self._closing = False
        self._build_ui()
        self._apply_theme()

    def make_help_button(self, title: str, text: str) -> QPushButton:
        button = QPushButton("?")
        button.setObjectName("helpButton")
        button.setFixedSize(32, 32)
        button.setToolTip("Klik voor uitleg over " + title)
        button.clicked.connect(lambda checked=False: self.show_help(title, text))
        return button

    def help_row(self, widget, title: str, text: str):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(7)
        row_layout.addWidget(widget, 1)
        row_layout.addWidget(self.make_help_button(title, text))
        return row

    def show_help(self, title: str, text: str):
        HelpDialog(title, text, self).exec()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("VIDEO CONVERTER")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        wizard_button = QPushButton("Wizard - help mij kiezen")
        wizard_button.setObjectName("wizardButton")
        wizard_button.clicked.connect(self.open_wizard)
        header.addWidget(wizard_button)
        credit = QLabel("MADE BY KID ACID")
        credit.setObjectName("credit")
        header.addWidget(credit)
        layout.addLayout(header)

        info = QLabel("Converteer een of meerdere video's naar een ander formaat. De originele bestanden worden niet gewijzigd.")
        info.setObjectName("subtitle")
        info.setWordWrap(True)
        layout.addWidget(info)

        source = QFrame()
        source.setObjectName("panel")
        source_layout = QHBoxLayout(source)
        source_layout.setContentsMargins(12, 10, 12, 10)
        self.source_label = QLabel("Geen video's geselecteerd")
        self.source_label.setObjectName("path")
        add_files = QPushButton("Video's toevoegen")
        add_files.clicked.connect(self.add_files)
        add_folder = QPushButton("Map toevoegen")
        add_folder.clicked.connect(self.add_folder)
        clear = QPushButton("Lijst wissen")
        clear.clicked.connect(self.clear_files)
        source_layout.addWidget(self.source_label, 1)
        source_layout.addWidget(add_files)
        source_layout.addWidget(add_folder)
        source_layout.addWidget(clear)
        layout.addWidget(source)

        options = QFrame()
        options.setObjectName("panel")
        form = QFormLayout(options)
        form.setContentsMargins(14, 14, 14, 14)
        form.setVerticalSpacing(10)

        self.output = QLineEdit()
        self.output.setPlaceholderText("Doelmap voor geconverteerde bestanden")
        browse_output = QPushButton("Bladeren...")
        browse_output.clicked.connect(self.choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output, 1)
        output_row.addWidget(browse_output)
        form.addRow("Doelmap:", output_row)

        self.container = QComboBox()
        self.container.addItems(["mp4", "mkv", "webm"])
        form.addRow("Formaat:", self.help_row(self.container, "Formaat", "MP4 is de meest universele keuze. MKV is flexibel. WebM is vooral gericht op modern webgebruik."))

        self.video_codec = QComboBox()
        self.video_codec.addItem("H.264 - compatibel", "libx264")
        self.video_codec.addItem("H.265 / HEVC - kleiner", "libx265")
        self.video_codec.addItem("AV1 - zeer efficient", "libsvtav1")
        self.video_codec.addItem("Video kopieren - geen hercodering", "copy")
        form.addRow("Video codec:", self.help_row(self.video_codec, "Video codec", "H.264 is de veiligste keuze voor compatibiliteit. H.265 maakt meestal kleinere bestanden. AV1 is efficient maar vraagt meer rekentijd. Kopieren voorkomt hercodering."))

        self.quality = QComboBox()
        self.quality.addItems(["18 - zeer hoog", "20 - hoog", "23 - standaard", "26 - kleiner bestand", "28 - sterk gecomprimeerd"])
        self.quality.setCurrentIndex(2)
        form.addRow("Kwaliteit:", self.help_row(self.quality, "Kwaliteit / CRF", "Een lager CRF-getal betekent hogere kwaliteit en meestal een groter bestand."))

        self.resolution = QComboBox()
        self.resolution.addItems(["Origineel", "3840:2160", "2560:1440", "1920:1080", "1280:720", "854:480"])
        form.addRow("Resolutie:", self.help_row(self.resolution, "Resolutie", "Kies Origineel om de resolutie te behouden, of een lagere resolutie om het bestand kleiner te maken."))

        self.audio_codec = QComboBox()
        self.audio_codec.addItem("AAC", "aac")
        self.audio_codec.addItem("Opus", "libopus")
        self.audio_codec.addItem("Audio behouden", "copy")
        self.audio_codec.addItem("Geen audio", "none")
        form.addRow("Audio:", self.help_row(self.audio_codec, "Audio", "AAC is zeer compatibel. Opus is efficient. Audio behouden kopieert de bestaande audiostream."))

        self.overwrite = QCheckBox("Bestaande doelbestanden overschrijven")
        form.addRow("Bestanden:", self.overwrite)
        layout.addWidget(options)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Bestand", "Pad", "Voortgang", "Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 500)
        self.table.setColumnWidth(2, 120)
        layout.addWidget(self.table, 1)

        overall_label = QLabel("Totale voortgang")
        overall_label.setObjectName("progressTitle")
        layout.addWidget(overall_label)
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m video's")
        layout.addWidget(self.progress)

        self.status = QLabel("Klaar om te converteren.")
        self.status.setObjectName("status")
        layout.addWidget(self.status)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Conversie starten")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start_conversion)
        self.cancel_button = QPushButton("Stoppen")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_conversion)
        close = QPushButton("Sluiten")
        close.clicked.connect(self.close)
        actions.addWidget(self.start_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background:#111318; color:#e8eaed; font-size:13px; }
            QMainWindow { background:#0d0f13; }
            QLabel#title { font-size:29px; font-weight:900; color:#fff; }
            QLabel#credit { color:#fff; font-size:16px; font-weight:800; padding:9px 14px; background:#15181d; border:1px solid #3d434d; border-radius:8px; }
            QLabel#subtitle { color:#9aa2ae; font-size:14px; }
            QLabel#path { color:#c8ccd3; padding:5px; }
            QLabel#status, QLabel#progressTitle { color:#aeb5c0; }
            QFrame#panel { background:#191c22; border:1px solid #303640; border-radius:10px; }
            QLineEdit, QComboBox { background:#1e2127; border:1px solid #353a43; border-radius:7px; padding:8px; color:#fff; }
            QLineEdit:focus, QComboBox:focus { border:1px solid #527fba; }
            QPushButton { background:#292e36; border:1px solid #3c424c; border-radius:7px; padding:9px 14px; font-weight:600; color:#fff; }
            QPushButton:hover { background:#353b45; }
            QPushButton#primary { background:#315f9e; border-color:#4679bd; }
            QPushButton#wizardButton { background:#394d68; border-color:#58769b; }
            QPushButton#helpButton { background:#315f9e; border:2px solid #6090c9; border-radius:16px; padding:0; color:#fff; font-size:17px; font-weight:900; }
            QPushButton:disabled { color:#666d78; background:#202329; }
            QCheckBox { spacing:8px; color:#d5d9df; }
            QTableWidget { background:#1e2127; border:1px solid #353a43; gridline-color:#30343c; color:#e8eaed; }
            QHeaderView::section { background:#252a31; color:#cfd4dc; padding:8px; border:0; }
            QProgressBar { background:#1e2127; border:1px solid #353a43; border-radius:6px; height:18px; text-align:center; }
            QProgressBar::chunk { background:#477dcc; border-radius:5px; }
        """)

    # --------------------------------------------------------
    # Files
    # --------------------------------------------------------

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Kies video's", "",
            "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv *.mpeg *.mpg);;Alle bestanden (*)",
        )
        self._add_paths(paths)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies een videomap")
        if not folder:
            return
        paths = [
            str(path) for path in Path(folder).rglob("*")
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        self._add_paths(paths)

    def _add_paths(self, paths: list[str]):
        existing = set(self.files)
        for path in paths:
            if path not in existing:
                self.files.append(path)
                existing.add(path)
        self._refresh_table()

    def clear_files(self):
        if self.worker and self.worker.isRunning():
            return
        self.files.clear()
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.files))
        for row, path in enumerate(self.files):
            self.table.setItem(row, 0, QTableWidgetItem(Path(path).name))
            self.table.setItem(row, 1, QTableWidgetItem(path))
            self.table.setItem(row, 2, QTableWidgetItem("0%"))
            self.table.setItem(row, 3, QTableWidgetItem("Wachten"))
        self.source_label.setText(
            f"{len(self.files)} video's geselecteerd" if self.files else "Geen video's geselecteerd"
        )

    # --------------------------------------------------------
    # Output / wizard
    # --------------------------------------------------------

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies doelmap")
        if folder:
            self.output.setText(folder)

    def open_wizard(self):
        wizard = ConvertWizard(self)
        wizard.finished.connect(self.apply_wizard_settings)
        wizard.exec()

    def apply_wizard_settings(self, settings: dict):
        mode = settings.get("mode", "compatibility")
        self.container.setCurrentText(settings.get("container", "mp4"))
        if mode == "compatibility":
            self.video_codec.setCurrentIndex(0); self.quality.setCurrentText("23 - standaard"); self.audio_codec.setCurrentIndex(0); self.resolution.setCurrentText("Origineel")
        elif mode == "smaller":
            self.video_codec.setCurrentIndex(1); self.quality.setCurrentText("23 - standaard"); self.audio_codec.setCurrentIndex(0); self.resolution.setCurrentText("Origineel")
        elif mode == "av1":
            self.video_codec.setCurrentIndex(2); self.quality.setCurrentText("26 - kleiner bestand"); self.audio_codec.setCurrentIndex(1); self.resolution.setCurrentText("Origineel")
        elif mode == "quality":
            self.video_codec.setCurrentIndex(0); self.quality.setCurrentText("18 - zeer hoog"); self.audio_codec.setCurrentIndex(0); self.resolution.setCurrentText("Origineel")
        elif mode == "copy":
            self.video_codec.setCurrentIndex(3); self.audio_codec.setCurrentIndex(2); self.resolution.setCurrentText("Origineel")
        elif mode == "resolution":
            self.video_codec.setCurrentIndex(0); self.quality.setCurrentText("23 - standaard"); self.audio_codec.setCurrentIndex(0); self.resolution.setCurrentText("1920:1080")
        self.status.setText("Wizard-instellingen toegepast.")

    # --------------------------------------------------------
    # Conversion
    # --------------------------------------------------------

    def start_conversion(self):
        if not self.files:
            QMessageBox.information(self, "Converter", "Voeg eerst een of meer video's toe.")
            return
        output = self.output.text().strip()
        if not output:
            QMessageBox.information(self, "Converter", "Kies eerst een doelmap.")
            return
        if self.worker and self.worker.isRunning():
            return
        if not find_ffmpeg():
            QMessageBox.critical(self, "FFmpeg ontbreekt", "FFmpeg is niet gevonden.")
            return

        total = len(self.files)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        for row in range(self.table.rowCount()):
            self.table.item(row, 2).setText("0%")
            self.table.item(row, 3).setText("Wachten")

        quality = self.quality.currentText().split(" ", 1)[0]
        self.worker = ConvertWorker(
            self.files, output, self.container.currentText(),
            self.video_codec.currentData(), quality,
            self.resolution.currentText(), self.audio_codec.currentData(),
            self.overwrite.isChecked(),
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.finished_ok.connect(self.conversion_finished)
        self.worker.error.connect(self.conversion_error)
        self.worker.start()

    def _find_row(self, name: str) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == name:
                return row
        return -1

    def update_progress(self, current: int, total: int, name: str, percent: int, status: str):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(max(0, current - 1 if status == "Bezig..." else current))
        row = self._find_row(name)
        if row >= 0:
            self.table.item(row, 2).setText(f"{percent}%")
            self.table.item(row, 3).setText(status)
        if status == "Bezig...":
            self.status.setText(f"Converteren: {name} — {percent}%")
        elif status == "Klaar":
            self.status.setText(f"Klaar: {name}")

    def conversion_finished(self, success: int, failed: int, cancelled: bool):
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        total = len(self.files)
        completed = success + failed
        if not cancelled:
            self.progress.setValue(total)
        else:
            self.progress.setValue(completed)

        if cancelled:
            self.status.setText(f"Conversie gestopt — {success} geslaagd, {failed} mislukt.")
            return

        self.status.setText(f"Klaar — {success} geslaagd, {failed} mislukt.")

        # Completion sound: one short Windows notification sound.
        try:
            if os.name == "nt":
                import winsound
                winsound.MessageBeep(winsound.MB_OK if failed == 0 else winsound.MB_ICONEXCLAMATION)
            else:
                QApplication.beep()
        except Exception:
            QApplication.beep()

        if failed:
            QMessageBox.warning(self, "Conversie", f"Conversie voltooid.\n\n{success} geslaagd\n{failed} mislukt")
        else:
            QMessageBox.information(self, "Conversie", f"Alle video's zijn geconverteerd.\n\n{success} geslaagd")

    def conversion_error(self, message: str):
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status.setText("Conversie mislukt.")
        QMessageBox.critical(self, "Video Converter", message)

    def cancel_conversion(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("Stoppen — FFmpeg wordt beëindigd...")
            self.cancel_button.setEnabled(False)

    # --------------------------------------------------------
    # Close
    # --------------------------------------------------------

    def closeEvent(self, event):
        self._closing = True
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            # Give FFmpeg a moment to terminate, then force the owned process.
            self.worker.wait(5000)
            if self.worker.isRunning():
                self.worker.cancel()
                self.worker.wait(2000)
        event.accept()


# ============================================================
# Standalone start
# ============================================================

def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setApplicationName("VideoAudioScanner")
    app.setOrganizationName("VideoAudioScanner")
    window = VideoConverterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
