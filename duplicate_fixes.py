from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import duplicate_finder as df


def _visual_hashes(ffmpeg: str, path: str, duration: float) -> list[int]:
    points = [duration * fraction for fraction in (0.12, 0.36, 0.60, 0.84)] if duration > 0 else [0.0]
    hashes: list[int] = []
    for point in points:
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-ss", f"{point:.3f}", "-i", path,
            "-frames:v", "1", "-vf", "scale=33:18,format=gray",
            "-f", "rawvideo", "pipe:1",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=45,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if completed.returncode != 0 or not completed.stdout:
            return []
        frame = completed.stdout
        expected = 33 * 18
        if len(frame) < expected:
            return []
        frame = frame[:expected]
        value = 0
        for y in range(18):
            row = y * 33
            for x in range(32):
                value = (value << 1) | int(frame[row + x] > frame[row + x + 1])
        hashes.append(value)
    return hashes


def _hamming_similarity(first: list[int], second: list[int]) -> int:
    if not first or not second or len(first) != len(second):
        return 0
    scores = []
    for a, b in zip(first, second):
        distance = (a ^ b).bit_count()
        scores.append(100 - (distance * 100 // 576))
    return int(round(sum(scores) / len(scores)))


def _name_key(name: str) -> str:
    stem = Path(name).stem.casefold()
    removable = (" (1)", " (2)", " (3)", " (4)", " copy", " kopie", "_copy", "-copy")
    changed = True
    while changed:
        changed = False
        for token in removable:
            if stem.endswith(token):
                stem = stem[: -len(token)]
                changed = True
                break
    return " ".join(stem.replace("_", " ").replace("-", " ").split())


def _quality_key(info: df.VideoInfo):
    return (
        info.width * info.height,
        info.bitrate,
        info.size,
        info.duration,
    )


def analyse_videos(folder: str, ffprobe: str | None, ffmpeg: str | None, progress=None):
    if not ffprobe:
        raise RuntimeError("FFprobe is niet gevonden.")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is niet gevonden.")

    scanner = df.MediaScanner(ffprobe)
    root = Path(folder)
    paths = sorted(
        (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in df.VIDEO_EXTENSIONS),
        key=lambda p: str(p).casefold(),
    )
    infos: list[df.VideoInfo] = []
    total = len(paths)
    for index, path in enumerate(paths, 1):
        result = scanner._inspect(path)
        width, height = df.parse_resolution(result.resolution)
        info = df.VideoInfo(
            result.path, result.name, result.size_bytes, result.duration_seconds,
            result.duration_text, result.resolution, width, height,
            df.parse_bitrate(result.bitrate), result.bitrate,
            result.video_codec, result.audio_codec, result.fps, result.container,
        )
        infos.append(info)
        if progress:
            progress(index, total)

    # SHA-256 is the only automatic match that is called "exact".
    by_size: dict[int, list[df.VideoInfo]] = {}
    for info in infos:
        by_size.setdefault(info.size, []).append(info)
    groups: list[list[df.VideoInfo]] = []
    used: set[str] = set()
    for candidates in by_size.values():
        if len(candidates) < 2:
            continue
        hashes: dict[str, list[df.VideoInfo]] = {}
        for info in candidates:
            info.video_hash = df.exact_hash(info.path)
            hashes.setdefault(info.video_hash, []).append(info)
        for same in hashes.values():
            if len(same) > 1:
                groups.append(same)
                used.update(i.path for i in same)

    remaining = [i for i in infos if i.path not in used]
    fingerprints: dict[str, list[int]] = {}
    for index, info in enumerate(remaining, 1):
        fingerprints[info.path] = _visual_hashes(ffmpeg, info.path, info.duration)
        if progress:
            progress(index, len(remaining))

    # Conservative candidate generation: similar duration is required unless the
    # filenames are clearly copies of the same name. This prevents unrelated dark
    # or low-detail videos from being grouped merely because their pixels are similar.
    name_groups: dict[str, list[df.VideoInfo]] = {}
    for info in remaining:
        name_groups.setdefault(_name_key(info.name), []).append(info)

    pairs: list[tuple[df.VideoInfo, df.VideoInfo, int]] = []
    seen_pairs: set[tuple[str, str]] = set()

    def consider(first: df.VideoInfo, second: df.VideoInfo):
        if first.path == second.path:
            return
        key = tuple(sorted((first.path, second.path), key=str.casefold))
        if key in seen_pairs:
            return
        seen_pairs.add(key)
        if first.duration <= 0 or second.duration <= 0:
            return
        duration_ratio = abs(first.duration - second.duration) / max(first.duration, second.duration)
        same_name = _name_key(first.name) == _name_key(second.name)
        # A filename match may tolerate a little editing; unnamed matches must be very strong.
        if duration_ratio > (0.025 if same_name else 0.012):
            return
        similarity = _hamming_similarity(fingerprints.get(first.path, []), fingerprints.get(second.path, []))
        threshold = 91 if same_name else 96
        if similarity >= threshold:
            pairs.append((first, second, similarity))

    for candidates in name_groups.values():
        if len(candidates) > 1:
            for index, first in enumerate(candidates):
                for second in candidates[index + 1:]:
                    consider(first, second)

    # For different filenames, only compare videos with a close duration bucket.
    duration_buckets: dict[int, list[df.VideoInfo]] = {}
    for info in remaining:
        duration_buckets.setdefault(round(info.duration / 10), []).append(info)
    for bucket, candidates in duration_buckets.items():
        nearby = candidates + duration_buckets.get(bucket - 1, []) + duration_buckets.get(bucket + 1, [])
        unique = {i.path: i for i in nearby}
        values = list(unique.values())
        for index, first in enumerate(values):
            for second in values[index + 1:]:
                if _name_key(first.name) != _name_key(second.name):
                    consider(first, second)

    # Merge connected candidate pairs into groups.
    for first, second, _similarity in pairs:
        target = next((group for group in groups if first in group or second in group), None)
        if target is None:
            groups.append([first, second])
        else:
            if first not in target:
                target.append(first)
            if second not in target:
                target.append(second)

    results: list[df.DuplicateCandidate] = []
    for group_number, group in enumerate(groups, 1):
        best = max(group, key=_quality_key)
        for info in group:
            if info.video_hash:
                similarity = 100
            else:
                scores = [_hamming_similarity(fingerprints.get(info.path, []), fingerprints.get(other.path, [])) for other in group if other is not info]
                similarity = max(scores) if scores else 0
            delete = info is not best
            if info.video_hash:
                reason = "Exact identiek — beste versie behouden" if not delete else "Exact identiek — kopie"
            else:
                reason = "Beste kwaliteit behouden" if not delete else "Vermoedelijk lagere kwaliteit"
            results.append(df.DuplicateCandidate(group_number, similarity, info, delete, reason))
    return results


def send_to_recycle_bin(path: str):
    if os.name != "nt":
        raise RuntimeError("De Windows Prullenbak is alleen beschikbaar op Windows.")
    if not Path(path).is_file():
        raise FileNotFoundError(path)

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.wintypes.HWND),
            ("wFunc", ctypes.wintypes.UINT),
            ("pFrom", ctypes.wintypes.LPCWSTR),
            ("pTo", ctypes.wintypes.LPCWSTR),
            ("fFlags", ctypes.wintypes.UINT),
            ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
            ("hNameMappings", ctypes.wintypes.LPVOID),
            ("lpszProgressTitle", ctypes.wintypes.LPCWSTR),
        ]

    source = str(Path(path).resolve()) + "\0\0"
    operation = SHFILEOPSTRUCTW()
    operation.wFunc = 0x0003
    operation.pFrom = source
    operation.fFlags = 0x0004 | 0x0010 | 0x0040 | 0x0400
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError(f"Windows SHFileOperation foutcode {result}")
    if operation.fAnyOperationsAborted:
        raise OSError("Windows heeft het verplaatsen afgebroken")


def install_fixes():
    df.analyse_videos = analyse_videos
    df.send_to_recycle_bin = send_to_recycle_bin
    df.DuplicateFinderWindow.delete_selected = _delete_selected


def _delete_selected(self):
    paths = []
    for row in range(self.table.rowCount()):
        item = self.table.item(row, 0)
        if item and item.checkState() == df.Qt.CheckState.Checked:
            path = item.data(df.Qt.ItemDataRole.UserRole)
            if path and Path(path).is_file():
                paths.append(path)
    if not paths:
        df.QMessageBox.information(self, "Prullenbak", "Er zijn geen bestanden geselecteerd.")
        return
    names = "\n".join(Path(path).name for path in paths[:12])
    if len(paths) > 12:
        names += f"\n… en nog {len(paths) - 12} bestand(en)."
    answer = df.QMessageBox.warning(
        self, "Bevestig verwijderen",
        f"De volgende {len(paths)} video('s) worden naar de Windows Prullenbak verplaatst:\n\n{names}\n\nDoorgaan?",
        df.QMessageBox.StandardButton.Yes | df.QMessageBox.StandardButton.No,
        df.QMessageBox.StandardButton.No,
    )
    if answer != df.QMessageBox.StandardButton.Yes:
        return
    errors = []
    for path in paths:
        try:
            send_to_recycle_bin(path)
        except Exception as exc:
            errors.append(f"{Path(path).name}: {exc}")
    if errors:
        df.QMessageBox.warning(self, "Prullenbak", "Sommige bestanden konden niet worden verplaatst:\n\n" + "\n".join(errors[:10]))
    else:
        df.QMessageBox.information(self, "Prullenbak", f"{len(paths)} bestand(en) naar de Windows Prullenbak verplaatst.")
