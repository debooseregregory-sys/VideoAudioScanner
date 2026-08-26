from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import duplicate_finder as df

CACHE_NAME = ".videoaudioscanner_duplicates.json"
CACHE_VERSION = 2


def _visual_hashes(ffmpeg: str, path: str, duration: float) -> list[int]:
    points = [duration * fraction for fraction in (0.12, 0.36, 0.60, 0.84)] if duration > 0 else [0.0]
    hashes: list[int] = []
    for point in points:
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{point:.3f}", "-i", path, "-frames:v", "1", "-vf", "scale=33:18,format=gray", "-f", "rawvideo", "pipe:1"]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except (OSError, subprocess.SubprocessError):
            return []
        if completed.returncode != 0 or len(completed.stdout) < 33 * 18:
            return []
        frame = completed.stdout[:33 * 18]
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
    return int(round(sum(100 - ((a ^ b).bit_count() * 100 // 576) for a, b in zip(first, second)) / len(first)))


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
    return (info.width * info.height, info.bitrate, info.size, info.duration)


def _video_inventory(folder: str) -> list[dict]:
    root = Path(folder)
    items = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in df.VIDEO_EXTENSIONS:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append({"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    items.sort(key=lambda item: item["path"].casefold())
    return items


def _cache_path(folder: str) -> Path:
    return Path(folder) / CACHE_NAME


def _load_cache(folder: str) -> dict:
    try:
        data = json.loads(_cache_path(folder).read_text(encoding="utf-8"))
        if data.get("version") != CACHE_VERSION:
            return {}
        return data.get("videos", {}) if isinstance(data.get("videos", {}), dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _save_cache(folder: str, records: dict):
    payload = {"version": CACHE_VERSION, "videos": records}
    target = _cache_path(folder)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _report(progress, current, total):
    if progress:
        progress(int(current), max(int(total), 1))


def _inspect_with_retry(scanner, path: Path):
    last = None
    for attempt in range(3):
        try:
            result = scanner._inspect(path)
            last = result
            if result.status == "OK" or not result.status.startswith("Fout"):
                return result
        except Exception:
            last = None
        if attempt < 2:
            time.sleep(0.75)
    return last


def _info_to_dict(info: df.VideoInfo) -> dict:
    return {
        "path": info.path, "name": info.name, "size": info.size, "duration": info.duration,
        "duration_text": info.duration_text, "resolution": info.resolution, "width": info.width,
        "height": info.height, "bitrate": info.bitrate, "bitrate_text": info.bitrate_text,
        "video_codec": info.video_codec, "audio_codec": info.audio_codec, "fps": info.fps,
        "container": info.container, "video_hash": info.video_hash,
    }


def _dict_to_info(data: dict) -> df.VideoInfo:
    return df.VideoInfo(**data)


def _analyse_videos_incremental(folder: str, ffprobe: str | None, ffmpeg: str | None, progress=None):
    if not ffprobe or not ffmpeg:
        raise RuntimeError("FFprobe en FFmpeg zijn vereist.")

    inventory = _video_inventory(folder)
    previous = _load_cache(folder)
    current_paths = {item["path"] for item in inventory}
    records: dict = {}
    scanner = df.MediaScanner(ffprobe)
    infos: list[df.VideoInfo] = []

    for index, item in enumerate(inventory, 1):
        old = previous.get(item["path"])
        if old and old.get("size") == item["size"] and old.get("mtime_ns") == item["mtime_ns"] and old.get("status") == "ok":
            try:
                info = _dict_to_info(old["info"])
                if Path(info.path).is_file():
                    infos.append(info)
                    records[item["path"]] = old
                    _report(progress, index, len(inventory))
                    continue
            except (TypeError, KeyError):
                pass

        result = _inspect_with_retry(scanner, Path(item["path"]))
        if result is not None and (result.status == "OK" or not result.status.startswith("Fout")):
            width, height = df.parse_resolution(result.resolution)
            info = df.VideoInfo(result.path, result.name, result.size_bytes, result.duration_seconds, result.duration_text, result.resolution, width, height, df.parse_bitrate(result.bitrate), result.bitrate, result.video_codec, result.audio_codec, result.fps, result.container)
            infos.append(info)
            records[item["path"]] = {"size": item["size"], "mtime_ns": item["mtime_ns"], "status": "ok", "info": _info_to_dict(info)}
        else:
            # Never cache a failed/locked file as successful. It will be retried next run.
            records.pop(item["path"], None)
        _report(progress, index, len(inventory))

    # Rebuild duplicate relationships from cached metadata, but only fingerprint
    # videos that have no stored visual fingerprint or whose file changed.
    changed_paths = {item["path"] for item in inventory if item["path"] not in previous or previous[item["path"]].get("size") != item["size"] or previous[item["path"]].get("mtime_ns") != item["mtime_ns"]}
    fingerprints = {}
    for info in infos:
        record = records.get(info.path, {})
        cached_fp = record.get("visual_hashes")
        if info.path not in changed_paths and cached_fp:
            fingerprints[info.path] = cached_fp
        else:
            fingerprints[info.path] = _visual_hashes(ffmpeg, info.path, info.duration)
            if fingerprints[info.path]:
                records[info.path]["visual_hashes"] = fingerprints[info.path]

    by_size: dict[int, list[df.VideoInfo]] = {}
    for info in infos:
        by_size.setdefault(info.size, []).append(info)
    groups: list[list[df.VideoInfo]] = []
    used: set[str] = set()
    for candidates in by_size.values():
        if len(candidates) < 2:
            continue
        hashes = {}
        for info in candidates:
            try:
                info.video_hash = df.exact_hash(info.path)
            except (OSError, PermissionError):
                info.video_hash = ""
            hashes.setdefault(info.video_hash, []).append(info)
        for same in hashes.values():
            if same[0].video_hash and len(same) > 1:
                groups.append(same)
                used.update(i.path for i in same)

    remaining = [i for i in infos if i.path not in used]
    pairs = []
    seen_pairs = set()

    def consider(first, second):
        key = tuple(sorted((first.path, second.path), key=str.casefold))
        if first.path == second.path or key in seen_pairs or first.duration <= 0 or second.duration <= 0:
            return
        seen_pairs.add(key)
        ratio = abs(first.duration - second.duration) / max(first.duration, second.duration)
        same_name = _name_key(first.name) == _name_key(second.name)
        if ratio > (0.025 if same_name else 0.012):
            return
        similarity = _hamming_similarity(fingerprints.get(first.path, []), fingerprints.get(second.path, []))
        if similarity >= (91 if same_name else 96):
            pairs.append((first, second))

    name_groups: dict[str, list[df.VideoInfo]] = {}
    for info in remaining:
        name_groups.setdefault(_name_key(info.name), []).append(info)
    for candidates in name_groups.values():
        for index, first in enumerate(candidates):
            for second in candidates[index + 1:]:
                consider(first, second)

    buckets: dict[tuple, list[df.VideoInfo]] = {}
    for info in remaining:
        if info.duration <= 0:
            continue
        aspect_bucket = round((info.width / info.height), 2) if info.width and info.height else 0
        key = (int(round(info.duration / 5.0)), aspect_bucket, info.width, info.height)
        buckets.setdefault(key, []).append(info)
    for candidates in buckets.values():
        if len(candidates) <= 60:
            for index, first in enumerate(candidates):
                for second in candidates[index + 1:]:
                    if _name_key(first.name) != _name_key(second.name):
                        consider(first, second)

    for first, second in pairs:
        target = next((group for group in groups if first in group or second in group), None)
        if target is None:
            groups.append([first, second])
        else:
            if first not in target:
                target.append(first)
            if second not in target:
                target.append(second)

    results = []
    for group_number, group in enumerate(groups, 1):
        best = max(group, key=_quality_key)
        for info in group:
            if info.video_hash:
                similarity = 100
                reason = "Exact identiek — " + ("beste versie behouden" if info is best else "kopie")
            else:
                scores = [_hamming_similarity(fingerprints.get(info.path, []), fingerprints.get(other.path, [])) for other in group if other is not info]
                similarity = max(scores) if scores else 0
                reason = "Beste kwaliteit behouden" if info is best else "Vermoedelijk lagere kwaliteit"
            results.append(df.DuplicateCandidate(group_number, similarity, info, info is not best, reason))

    # Remove stale cache entries and save successful analyses only.
    records = {path: record for path, record in records.items() if path in current_paths and record.get("status") == "ok"}
    _save_cache(folder, records)
    return results


def analyse_videos(folder: str, ffprobe: str | None, ffmpeg: str | None, progress=None):
    return _analyse_videos_incremental(folder, ffprobe, ffmpeg, progress)


def send_to_recycle_bin(path: str):
    if os.name != "nt":
        raise RuntimeError("De Windows Prullenbak is alleen beschikbaar op Windows.")
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR), ("fFlags", wintypes.UINT), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", wintypes.LPVOID), ("lpszProgressTitle", wintypes.LPCWSTR)]

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = 0x0003
    operation.pFrom = str(resolved) + "\0\0"
    operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError(f"Windows SHFileOperation foutcode {result}")
    if operation.fAnyOperationsAborted:
        raise OSError("Windows heeft het verplaatsen afgebroken")


def _delete_selected(self):
    paths = []
    for row in range(self.table.rowCount()):
        item = self.table.item(row, 0)
        if item and item.checkState() == df.Qt.CheckState.Checked:
            path = item.data(df.Qt.ItemDataRole.UserRole)
            if path and Path(path).is_file():
                paths.append(str(path))
    if not paths:
        df.QMessageBox.information(self, "Prullenbak", "Er zijn geen bestanden geselecteerd.")
        return
    names = "\n".join(Path(p).name for p in paths[:12])
    if len(paths) > 12:
        names += f"\n… en nog {len(paths) - 12} bestand(en)."
    answer = df.QMessageBox.warning(self, "Bevestig verwijderen", f"De volgende {len(paths)} video('s) worden naar de Windows Prullenbak verplaatst:\n\n{names}\n\nDoorgaan?", df.QMessageBox.StandardButton.Yes | df.QMessageBox.StandardButton.No, df.QMessageBox.StandardButton.No)
    if answer != df.QMessageBox.StandardButton.Yes:
        return
    errors = []
    moved = 0
    for path in paths:
        try:
            send_to_recycle_bin(path)
            moved += 1
        except Exception as exc:
            errors.append(f"{Path(path).name}: {exc}")
    if errors:
        df.QMessageBox.warning(self, "Prullenbak", f"{moved} bestand(en) verplaatst.\n\nNiet gelukt:\n" + "\n".join(errors[:12]))
    else:
        df.QMessageBox.information(self, "Prullenbak", f"{moved} bestand(en) naar de Windows Prullenbak verplaatst.")


def install_fixes():
    df.analyse_videos = analyse_videos
    df.send_to_recycle_bin = send_to_recycle_bin
    df.DuplicateFinderWindow.delete_selected = _delete_selected
