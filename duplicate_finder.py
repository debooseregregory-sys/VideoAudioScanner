from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QDialog

from scanner import VIDEO_EXTENSIONS, MediaScanner


@dataclass
class VideoInfo:
    path: str
    name: str
    size: int
    duration: float
    duration_text: str
    resolution: str
    width: int
    height: int
    bitrate: int
    bitrate_text: str
    video_codec: str
    audio_codec: str
    fps: str
    container: str
    video_hash: str = ""


@dataclass
class DuplicateCandidate:
    group: int
    similarity: int
    info: VideoInfo
    recommended_delete: bool
    reason: str


def find_ffmpeg() -> str | None:
    names = ["ffmpeg.exe", "ffmpeg"] if os.name == "nt" else ["ffmpeg"]
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    here = Path(__file__).resolve().parent
    for candidate in (here / "ffmpeg.exe", here / "ffmpeg" / "bin" / "ffmpeg.exe", here / "tools" / "ffmpeg.exe"):
        if candidate.is_file():
            return str(candidate)
    return None


def normalize_name(name: str) -> str:
    stem = Path(name).stem.casefold()
    for token in (" (1)", " (2)", " (3)", " copy", " kopie", "_copy", "-copy"):
        if stem.endswith(token):
            stem = stem[: -len(token)]
    return " ".join(stem.replace("_", " ").replace("-", " ").split())


def parse_resolution(value: str) -> tuple[int, int]:
    try:
        left, right = value.replace("×", "x").split("x", 1)
        return int(left.strip()), int(right.strip())
    except (ValueError, AttributeError):
        return 0, 0


def parse_bitrate(value: str) -> int:
    try:
        return int(float(value.split()[0]) * 1000)
    except (ValueError, IndexError, AttributeError):
        return 0


def exact_hash(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def visual_fingerprint(ffmpeg: str, path: str, duration: float) -> bytes:
    points = [0.0] if duration <= 0 else [duration * fraction for fraction in (0.10, 0.35, 0.60, 0.85)]
    result = bytearray()
    for point in points:
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{point:.3f}", "-i", path, "-frames:v", "1", "-vf", "scale=32:18,format=gray", "-f", "rawvideo", "pipe:1"]
        completed = subprocess.run(command, capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if completed.returncode == 0 and completed.stdout:
            result.extend(completed.stdout)
    return bytes(result)


def visual_similarity(first: bytes, second: bytes) -> int:
    if not first or not second:
        return 0
    length = min(len(first), len(second))
    if not length:
        return 0
    difference = sum(abs(first[index] - second[index]) for index in range(length)) / length
    return max(0, min(100, int(round(100 - difference / 255 * 100))))


def quality_score(info: VideoInfo) -> float:
    pixels = info.width * info.height
    bitrate = info.bitrate or 0
    duration = max(info.duration, 1.0)
    return pixels * 1000 + bitrate + info.size / duration


def analyse_videos(folder: str, ffprobe: str | None, ffmpeg: str | None, progress=None) -> list[DuplicateCandidate]:
    if not ffprobe:
        raise RuntimeError("FFprobe is niet gevonden.")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is niet gevonden. FFmpeg is nodig om de videobeelden te vergelijken.")
    scanner = MediaScanner(ffprobe)
    root = Path(folder)
    paths = sorted((p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS), key=lambda p: str(p).casefold())
    infos: list[VideoInfo] = []
    for index, path in enumerate(paths, 1):
        result = scanner._inspect(path)
        width, height = parse_resolution(result.resolution)
        infos.append(VideoInfo(result.path, result.name, result.size_bytes, result.duration_seconds, result.duration_text, result.resolution, width, height, parse_bitrate(result.bitrate), result.bitrate, result.video_codec, result.audio_codec, result.fps, result.container))
        if progress:
            progress(index, len(paths))

    by_size: dict[int, list[VideoInfo]] = {}
    for info in infos:
        by_size.setdefault(info.size, []).append(info)
    for candidates in by_size.values():
        if len(candidates) > 1:
            for info in candidates:
                info.video_hash = exact_hash(info.path)

    exact_groups: dict[str, list[VideoInfo]] = {}
    for info in infos:
        if info.video_hash:
            exact_groups.setdefault(info.video_hash, []).append(info)
    groups: list[list[VideoInfo]] = []
    used: set[str] = set()
    for candidates in exact_groups.values():
        if len(candidates) > 1:
            groups.append(candidates)
            used.update(i.path for i in candidates)

    remaining = [i for i in infos if i.path not in used]
    fingerprints: dict[str, bytes] = {}
    for index, info in enumerate(remaining, 1):
        try:
            fingerprints[info.path] = visual_fingerprint(ffmpeg, info.path, info.duration)
        except (OSError, subprocess.SubprocessError):
            fingerprints[info.path] = b""
        if progress:
            progress(index, len(remaining))

    pairs: list[tuple[VideoInfo, VideoInfo, int]] = []
    for index, first in enumerate(remaining):
        for second in remaining[index + 1:]:
            if first.duration <= 0 or second.duration <= 0:
                continue
            duration_ratio = abs(first.duration - second.duration) / max(first.duration, second.duration)
            same_name = normalize_name(first.name) == normalize_name(second.name)
            if duration_ratio > 0.02 and not same_name:
                continue
            similarity = visual_similarity(fingerprints.get(first.path, b""), fingerprints.get(second.path, b""))
            if similarity >= 90 or (same_name and similarity >= 82):
                pairs.append((first, second, similarity))

    for first, second, _ in pairs:
        target = next((group for group in groups if first in group or second in group), None)
        if target is None:
            groups.append([first, second])
        else:
            if first not in target:
                target.append(first)
            if second not in target:
                target.append(second)

    results: list[DuplicateCandidate] = []
    for group_number, group in enumerate(groups, 1):
        best = max(group, key=quality_score)
        for info in group:
            scores = [100 if info.video_hash and info.video_hash == other.video_hash else visual_similarity(fingerprints.get(info.path, b""), fingerprints.get(other.path, b"")) for other in group if other is not info]
            similarity = max(scores) if scores else 100
            delete = info is not best and quality_score(info) < quality_score(best)
            reason = "Beste kwaliteit behouden" if not delete else "Lagere kwaliteit dan beste versie"
            if info.video_hash:
                reason = "Exact identiek" if delete else "Exacte originele versie"
            results.append(DuplicateCandidate(group_number, similarity, info, delete, reason))
    return results


class FinderWorker(QThread):
    result = Signal(object)
    progress = Signal(int, int)
    error = Signal(str)

    def __init__(self, folder: str, ffprobe: str | None, ffmpeg: str | None):
        super().__init__()
        self.folder, self.ffprobe, self.ffmpeg = folder, ffprobe, ffmpeg

    def run(self):
        try:
            self.result.emit(analyse_videos(self.folder, self.ffprobe, self.ffmpeg, self.progress.emit))
        except Exception as exc:
            self.error.emit(str(exc))


class VideoPreviewDialog(QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Video bekijken — {Path(path).name}")
        self.resize(1100, 700)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.video = QVideoWidget(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.audio.setVolume(1.0)
        layout = QVBoxLayout(self)
        layout.addWidget(self.video, 1)
        controls = QHBoxLayout()
        self.play_button = QPushButton("Pauze")
        self.play_button.clicked.connect(self.toggle_play)
        stop = QPushButton("Stop")
        stop.clicked.connect(self.player.stop)
        external = QPushButton("Openen in Windows")
        external.clicked.connect(lambda: open_video(path))
        controls.addWidget(self.play_button)
        controls.addWidget(stop)
        controls.addStretch(1)
        controls.addWidget(external)
        layout.addLayout(controls)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.errorOccurred.connect(self.media_error)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("Afspelen")
        else:
            self.player.play()
            self.play_button.setText("Pauze")

    def media_status(self, status):
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.play_button.setText("Niet afspeelbaar")

    def media_error(self, _error, error_string):
        if error_string:
            self.play_button.setText("Niet afspeelbaar")

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)


def open_video(path: str):
    try:
        os.startfile(path)
    except OSError as exc:
        QMessageBox.warning(None, "Video openen", f"Kan de video niet openen:\n\n{path}\n\n{exc}")


class DuplicateFinderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoAudioScanner — Dubbele video's")
        self.resize(1600, 860)
        self.worker: FinderWorker | None = None
        self.rows: list[DuplicateCandidate] = []
        self.preview_windows: list[VideoPreviewDialog] = []
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("Dubbele video's")
        title.setObjectName("title")
        credit = QLabel("Made by Kid Acid")
        credit.setObjectName("credit")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(credit)
        layout.addLayout(header)
        info = QLabel("Exacte duplicaten worden met SHA-256 herkend. Andere kandidaten worden visueel vergeleken met FFmpeg. Resolutie, bitrate, duur, codecs, FPS en container bepalen welke versie vermoedelijk het beste is. Dubbelklik op een video om hem te bekijken.")
        info.setWordWrap(True)
        info.setObjectName("subtitle")
        layout.addWidget(info)

        source = QGroupBox("Scanlocatie")
        source_layout = QHBoxLayout(source)
        self.folder = QLabel("Geen map gekozen")
        self.folder.setObjectName("path")
        choose = QPushButton("Bladeren…")
        choose.clicked.connect(self.choose_folder)
        self.scan_button = QPushButton("🔎 Dubbele video's zoeken")
        self.scan_button.setObjectName("primary")
        self.scan_button.clicked.connect(self.start_scan)
        source_layout.addWidget(self.folder, 1)
        source_layout.addWidget(choose)
        source_layout.addWidget(self.scan_button)
        layout.addWidget(source)
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m")
        layout.addWidget(self.progress)
        self.status = QLabel("Klaar om te zoeken.")
        layout.addWidget(self.status)

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(["Verwijderen", "Voorbeeld", "Groep", "Bestand", "Resolutie", "Bitrate", "Duur", "Video codec", "Audio codec", "FPS", "Container", "Overeenkomst / beoordeling"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate([95, 90, 60, 350, 105, 105, 90, 100, 100, 75, 100, 260]):
            self.table.setColumnWidth(index, width)
        self.table.cellDoubleClicked.connect(self.preview_row)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        preview = QPushButton("▶ Video bekijken")
        preview.clicked.connect(self.preview_selected)
        self.select_bad = QPushButton("Slechte versies selecteren")
        self.select_bad.clicked.connect(self.select_bad_versions)
        clear = QPushButton("Alles uitvinken")
        clear.clicked.connect(self.clear_checks)
        self.delete_button = QPushButton("🗑 Geselecteerde naar Prullenbak")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(preview)
        actions.addWidget(self.select_bad)
        actions.addWidget(clear)
        actions.addStretch(1)
        actions.addWidget(self.delete_button)
        layout.addLayout(actions)
        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background: #15171b; color: #e8eaed; font-size: 13px; }
            QMainWindow, QDialog { background: #101216; }
            QLabel#title { font-size: 28px; font-weight: 700; color: #ffffff; }
            QLabel#subtitle { color: #8f96a3; }
            QLabel#credit { color: #ffffff; font-size: 18px; font-weight: 700; padding: 7px 12px; background: #101216; border: 1px solid #2c3037; border-radius: 6px; }
            QLabel#path { color: #c8ccd3; padding: 8px; }
            QGroupBox { border: 1px solid #30343c; border-radius: 8px; margin-top: 8px; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #aeb5c0; }
            QPushButton { background: #292e36; border: 1px solid #3c424c; border-radius: 6px; padding: 9px 14px; }
            QPushButton:hover { background: #353b45; }
            QPushButton#primary { background: #315f9e; border-color: #4679bd; font-weight: 600; }
            QPushButton#danger { background: #54272b; border-color: #824047; font-weight: 600; }
            QTableWidget { background: #1e2127; border: 1px solid #353a43; gridline-color: #30343c; }
            QHeaderView::section { background: #252a31; padding: 7px; border: 0; }
            QProgressBar { background: #1e2127; border: 1px solid #353a43; border-radius: 5px; height: 18px; text-align: center; }
            QProgressBar::chunk { background: #477dcc; border-radius: 4px; }
        """)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Kies een map met video's")
        if folder:
            self.folder.setText(folder)

    def start_scan(self):
        folder = self.folder.text().strip()
        if not folder or folder == "Geen map gekozen" or not os.path.isdir(folder):
            QMessageBox.information(self, "Map kiezen", "Kies eerst een geldige map.")
            return
        if self.worker and self.worker.isRunning():
            return
        scanner = MediaScanner()
        ffprobe = scanner.ffprobe
        ffmpeg = find_ffmpeg()
        if not ffprobe or not ffmpeg:
            missing = [name for name, value in (("FFprobe", ffprobe), ("FFmpeg", ffmpeg)) if not value]
            QMessageBox.critical(self, "Benodigd programma ontbreekt", "Niet gevonden: " + ", ".join(missing))
            return
        self.rows.clear()
        self.table.setRowCount(0)
        self.scan_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText("Video's analyseren…")
        self.worker = FinderWorker(folder, ffprobe, ffmpeg)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.scan_finished)
        self.worker.error.connect(self.scan_error)
        self.worker.finished.connect(lambda: self.scan_button.setEnabled(True))
        self.worker.start()

    def update_progress(self, current: int, total: int):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(current)
        self.status.setText(f"Video {current} van {total} analyseren…")

    def scan_finished(self, rows):
        self.rows = list(rows)
        self.populate_table()
        self.status.setText(f"Klaar — {len(self.rows)} duplicaat-kandidaten gevonden.")

    def scan_error(self, message: str):
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setText("Analyse mislukt.")
        QMessageBox.critical(self, "Dubbele video's", message)

    def populate_table(self):
        self.table.setRowCount(len(self.rows))
        for row, candidate in enumerate(self.rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if candidate.recommended_delete else Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, candidate.info.path)
            self.table.setItem(row, 0, check)
            preview = QPushButton("▶ Bekijk")
            preview.clicked.connect(lambda _checked=False, r=row: self.preview_row(r))
            self.table.setCellWidget(row, 1, preview)
            values = [str(candidate.group), candidate.info.name, candidate.info.resolution, candidate.info.bitrate_text, candidate.info.duration_text, candidate.info.video_codec, candidate.info.audio_codec, candidate.info.fps, candidate.info.container, f"{candidate.similarity}% — {candidate.reason}"]
            for column, value in enumerate(values, 2):
                item = QTableWidgetItem(value)
                item.setToolTip(candidate.info.path if column == 3 else value)
                self.table.setItem(row, column, item)

    def selected_path(self, row: int) -> str | None:
        if row < 0 or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def preview_row(self, row: int, _column: int = 0):
        path = self.selected_path(row)
        if not path:
            return
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Video bekijken", "Het bestand bestaat niet meer:\n\n" + path)
            return
        dialog = VideoPreviewDialog(path, self)
        self.preview_windows.append(dialog)
        dialog.finished.connect(lambda _result, d=dialog: self._forget_preview(d))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _forget_preview(self, dialog):
        if dialog in self.preview_windows:
            self.preview_windows.remove(dialog)

    def preview_selected(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Video bekijken", "Selecteer eerst een video in de tabel.")
            return
        self.preview_row(rows[0])

    def select_bad_versions(self):
        for row, candidate in enumerate(self.rows):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked if candidate.recommended_delete else Qt.CheckState.Unchecked)

    def clear_checks(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    def delete_selected(self):
        paths = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.isfile(path):
                    paths.append(path)
        if not paths:
            QMessageBox.information(self, "Prullenbak", "Er zijn geen bestanden geselecteerd.")
            return
        names = "\n".join(Path(path).name for path in paths[:12])
        if len(paths) > 12:
            names += f"\n… en nog {len(paths) - 12} bestand(en)."
        answer = QMessageBox.warning(self, "Bevestig verwijderen", f"De volgende {len(paths)} video('s) worden naar de Windows Prullenbak verplaatst:\n\n{names}\n\nDoorgaan?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        errors = []
        for path in paths:
            try:
                send_to_recycle_bin(path)
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")
        if errors:
            QMessageBox.warning(self, "Prullenbak", "Sommige bestanden konden niet worden verplaatst:\n\n" + "\n".join(errors[:10]))
        else:
            QMessageBox.information(self, "Prullenbak", f"{len(paths)} bestand(en) naar de Windows Prullenbak verplaatst.")


def send_to_recycle_bin(path: str):
    if os.name != "nt":
        raise RuntimeError("De Windows Prullenbak is alleen beschikbaar op Windows.")
    import ctypes
    from ctypes import wintypes
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR), ("fFlags", wintypes.USHORT), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", wintypes.LPVOID), ("lpszProgressTitle", wintypes.LPCWSTR)]
    operation = SHFILEOPSTRUCTW()
    operation.wFunc = 0x0003
    operation.pFrom = str(Path(path).resolve()) + "\0\0"
    operation.fFlags = 0x0040 | 0x0010 | 0x0004
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(result or "Windows heeft de operatie afgebroken")
