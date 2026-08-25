from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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
    candidates = [
        here / "ffmpeg.exe",
        here / "ffmpeg" / "bin" / "ffmpeg.exe",
        here / "tools" / "ffmpeg.exe",
    ]
    for candidate in candidates:
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
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def visual_fingerprint(ffmpeg: str, path: str, duration: float) -> bytes:
    """Extract four small grayscale frames used for visual similarity scoring."""
    points = [0.0] if duration <= 0 else [duration * fraction for fraction in (0.10, 0.35, 0.60, 0.85)]
    result = bytearray()
    for point in points:
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-ss", f"{point:.3f}", "-i", path,
            "-frames:v", "1", "-vf", "scale=32:18,format=gray",
            "-f", "rawvideo", "pipe:1",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
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
    return max(0, min(100, int(round(100 - (difference / 255 * 100)))))


def quality_score(info: VideoInfo) -> float:
    pixels = info.width * info.height
    bitrate = info.bitrate or 0
    duration = max(info.duration, 1.0)
    # Resolution is strongest, bitrate is second, and the encoded data rate per second
    # helps distinguish otherwise equal resolutions without blindly preferring huge files.
    return pixels * 1000 + bitrate + info.size / duration


def analyse_videos(folder: str, ffprobe: str | None, ffmpeg: str | None, progress=None) -> list[DuplicateCandidate]:
    if not ffprobe:
        raise RuntimeError("FFprobe is niet gevonden.")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is niet gevonden. FFmpeg is nodig om de videobeelden te vergelijken.")

    scanner = MediaScanner(ffprobe)
    root = Path(folder)
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS),
        key=lambda p: str(p).casefold(),
    )

    infos: list[VideoInfo] = []
    total = len(paths)
    for index, path in enumerate(paths, 1):
        result = scanner._inspect(path)
        width, height = parse_resolution(result.resolution)
        infos.append(VideoInfo(
            path=result.path,
            name=result.name,
            size=result.size_bytes,
            duration=result.duration_seconds,
            duration_text=result.duration_text,
            resolution=result.resolution,
            width=width,
            height=height,
            bitrate=parse_bitrate(result.bitrate),
            bitrate_text=result.bitrate,
            video_codec=result.video_codec,
            audio_codec=result.audio_codec,
            fps=result.fps,
            container=result.container,
        ))
        if progress:
            progress(index, total)

    # Exact duplicates are detected with SHA-256, but only files with equal byte size
    # are hashed so a large collection does not require hashing every video twice.
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
            used.update(info.path for info in candidates)

    # Visual pass for files that are not byte-for-byte identical. Duration/name are
    # used as inexpensive gates before FFmpeg frame comparison.
    remaining = [info for info in infos if info.path not in used]
    fingerprints: dict[str, bytes] = {}
    for index, info in enumerate(remaining, 1):
        try:
            fingerprints[info.path] = visual_fingerprint(ffmpeg, info.path, info.duration)
        except (OSError, subprocess.SubprocessError):
            fingerprints[info.path] = b""
        if progress:
            progress(index, len(remaining))

    candidate_pairs: list[tuple[VideoInfo, VideoInfo, int]] = []
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
                candidate_pairs.append((first, second, similarity))

    for first, second, _similarity in candidate_pairs:
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
            similarity = 100 if info.video_hash else 95
            if info is not best:
                scores = []
                for other in group:
                    if other is info:
                        continue
                    if info.video_hash and info.video_hash == other.video_hash:
                        scores.append(100)
                    else:
                        scores.append(visual_similarity(fingerprints.get(info.path, b""), fingerprints.get(other.path, b"")))
                if scores:
                    similarity = max(scores)
            delete = info is not best and quality_score(info) < quality_score(best)
            reason = "Beste kwaliteit behouden" if not delete else "Lagere kwaliteit dan beste versie"
            if info.video_hash and group[0].video_hash == info.video_hash:
                reason = "Exact identiek" if delete else "Exacte originele versie"
            results.append(DuplicateCandidate(group_number, similarity, info, delete, reason))

    return results


class FinderWorker(QThread):
    result = Signal(object)
    progress = Signal(int, int)
    error = Signal(str)

    def __init__(self, folder: str, ffprobe: str | None, ffmpeg: str | None):
        super().__init__()
        self.folder = folder
        self.ffprobe = ffprobe
        self.ffmpeg = ffmpeg

    def run(self):
        try:
            self.result.emit(analyse_videos(self.folder, self.ffprobe, self.ffmpeg, self.progress.emit))
        except Exception as exc:
            self.error.emit(str(exc))


class DuplicateFinderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoAudioScanner — Dubbele video's")
        self.resize(1600, 860)
        self.worker: FinderWorker | None = None
        self.rows: list[DuplicateCandidate] = []
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
        header.addWidget(title)
        header.addStretch(1)
        credit = QLabel("Made by Kid Acid")
        credit.setObjectName("credit")
        header.addWidget(credit)
        layout.addLayout(header)

        info = QLabel(
            "Exacte duplicaten worden met SHA-256 herkend. Andere kandidaten worden visueel vergeleken met FFmpeg. "
            "Resolutie, bitrate, duur, codecs, FPS en container bepalen welke versie vermoedelijk het beste is."
        )
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

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "Verwijderen", "Groep", "Bestand", "Resolutie", "Bitrate", "Duur",
            "Video codec", "Audio codec", "FPS", "Container", "Overeenkomst / beoordeling",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        widths = [95, 60, 350, 105, 105, 90, 100, 100, 75, 100, 260]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.select_bad = QPushButton("Slechte versies selecteren")
        self.select_bad.clicked.connect(self.select_bad_versions)
        self.clear_selection = QPushButton("Alles uitvinken")
        self.clear_selection.clicked.connect(self.clear_checks)
        self.delete_button = QPushButton("🗑 Geselecteerde naar Prullenbak")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(self.select_bad)
        actions.addWidget(self.clear_selection)
        actions.addStretch(1)
        actions.addWidget(self.delete_button)
        layout.addLayout(actions)

        self.setCentralWidget(root)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background: #15171b; color: #e8eaed; font-size: 13px; }
            QMainWindow { background: #101216; }
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
            QMessageBox.warning(self, "FFmpeg/FFprobe ontbreekt", "Voor visuele duplicaatcontrole zijn zowel FFprobe als FFmpeg nodig.")
            return
        self.table.setRowCount(0)
        self.rows.clear()
        self.progress.setValue(0)
        self.status.setText("Video's analyseren…")
        self.scan_button.setEnabled(False)
        self.worker = FinderWorker(folder, ffprobe, ffmpeg)
        self.worker.progress.connect(self._update_progress)
        self.worker.result.connect(self.show_results)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(lambda: self.scan_button.setEnabled(True))
        self.worker.start()

    def _update_progress(self, value: int, total: int):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(value)

    def show_results(self, rows: list[DuplicateCandidate]):
        self.rows = rows
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Checked if row.recommended_delete else Qt.CheckState.Unchecked)
            self.table.setItem(row_index, 0, check)
            self.table.setItem(row_index, 1, QTableWidgetItem(str(row.group)))
            name = QTableWidgetItem(row.info.name)
            name.setToolTip(row.info.path)
            self.table.setItem(row_index, 2, name)
            self.table.setItem(row_index, 3, QTableWidgetItem(row.info.resolution))
            self.table.setItem(row_index, 4, QTableWidgetItem(row.info.bitrate_text))
            self.table.setItem(row_index, 5, QTableWidgetItem(row.info.duration_text))
            self.table.setItem(row_index, 6, QTableWidgetItem(row.info.video_codec))
            self.table.setItem(row_index, 7, QTableWidgetItem(row.info.audio_codec))
            self.table.setItem(row_index, 8, QTableWidgetItem(row.info.fps))
            self.table.setItem(row_index, 9, QTableWidgetItem(row.info.container))
            self.table.setItem(row_index, 10, QTableWidgetItem(f"{row.similarity}% • {row.reason}"))

        groups = len({row.group for row in rows})
        checked = sum(1 for row in rows if row.recommended_delete)
        if rows:
            self.status.setText(f"{groups} dubbele groep(en) gevonden • {len(rows)} bestanden • {checked} automatisch aangevinkt")
        else:
            self.status.setText("Geen dubbele video's gevonden.")

    def show_error(self, message: str):
        self.status.setText("Fout tijdens duplicaatcontrole.")
        QMessageBox.critical(self, "Duplicaatcontrole", message)

    def select_bad_versions(self):
        for index, row in enumerate(self.rows):
            item = self.table.item(index, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked if row.recommended_delete else Qt.CheckState.Unchecked)

    def clear_checks(self):
        for index in range(self.table.rowCount()):
            item = self.table.item(index, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    def delete_selected(self):
        paths = []
        for index in range(self.table.rowCount()):
            item = self.table.item(index, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                paths.append(self.rows[index].info.path)
        if not paths:
            QMessageBox.information(self, "Geen selectie", "Er zijn geen bestanden aangevinkt.")
            return
        answer = QMessageBox.question(
            self,
            "Naar Prullenbak",
            f"Wil je {len(paths)} bestand(en) naar de Windows Prullenbak verplaatsen?\n\nZe worden niet definitief verwijderd.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._recycle(paths)

    def _recycle(self, paths: list[str]):
        if os.name != "nt":
            QMessageBox.warning(self, "Windows", "De Prullenbak-functie is alleen beschikbaar op Windows.")
            return
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR), ("fFlags", wintypes.UINT),
                ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        existing = [path for path in paths if Path(path).is_file()]
        if not existing:
            QMessageBox.warning(self, "Prullenbak", "De geselecteerde bestanden bestaan niet meer.")
            return
        source = "".join(path + "\0" for path in existing) + "\0"
        operation = SHFILEOPSTRUCTW(None, 0x0003, source, None, 0x0004 | 0x0010 | 0x0040 | 0x0400, False, None, None)
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
        if result != 0 or operation.fAnyOperationsAborted:
            QMessageBox.warning(self, "Prullenbak", "Niet alle bestanden konden naar de Prullenbak worden verplaatst.")
            return
        self.status.setText(f"{len(existing)} bestand(en) naar de Prullenbak verplaatst.")
        self.start_scan()


def main():
    app = QApplication([])
    window = DuplicateFinderWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
