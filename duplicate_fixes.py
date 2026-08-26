from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import time
from pathlib import Path

import duplicate_finder as df

CACHE_NAME = ".videoaudioscanner_duplicates.json"
CACHE_VERSION = 4


def _visual_hashes(ffmpeg: str, path: str, duration: float) -> list[int]:
    points = [duration * fraction for fraction in (0.12, 0.36, 0.60, 0.84)] if duration > 0 else [0.0]
    hashes = []
    for point in points:
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{point:.3f}", "-i", path, "-frames:v", "1", "-vf", "scale=33:18,format=gray", "-f", "rawvideo", "pipe:1"]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except (OSError, subprocess.SubprocessError):
            return []
        if completed.returncode != 0 or len(completed.stdout) < 594:
            return []
        frame = completed.stdout[:594]
        value = 0
        for y in range(18):
            row = y * 33
            for x in range(32):
                value = (value << 1) | int(frame[row + x] > frame[row + x + 1])
        hashes.append(value)
    return hashes


def _hamming_similarity(first, second):
    if not first or not second or len(first) != len(second):
        return 0
    return int(round(sum(100 - ((a ^ b).bit_count() * 100 // 576) for a, b in zip(first, second)) / len(first)))


def _name_key(name):
    stem = Path(name).stem.casefold()
    removable = (" (1)", " (2)", " (3)", " (4)", " copy", " kopie", "_copy", "-copy")
    changed = True
    while changed:
        changed = False
        for token in removable:
            if stem.endswith(token):
                stem = stem[:-len(token)]
                changed = True
                break
    return " ".join(stem.replace("_", " ").replace("-", " ").split())


def _quality_key(info):
    return (info.width * info.height, info.bitrate, info.size, info.duration)


def _video_inventory(folder):
    items = []
    for path in Path(folder).rglob("*"):
        if not path.is_file() or path.suffix.lower() not in df.VIDEO_EXTENSIONS:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append({"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    items.sort(key=lambda x: x["path"].casefold())
    return items


def _cache_path(folder):
    return Path(folder) / CACHE_NAME


def _load_cache(folder):
    try:
        data = json.loads(_cache_path(folder).read_text(encoding="utf-8"))
        if data.get("version") != CACHE_VERSION:
            return {}
        return data.get("videos", {})
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _save_cache(folder, records):
    target = _cache_path(folder)
    temp = target.with_suffix(target.suffix + ".tmp")
    try:
        temp.write_text(json.dumps({"version": CACHE_VERSION, "videos": records}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _report(progress, current, total):
    if progress:
        progress(int(current), max(int(total), 1))


def _inspect_with_retry(scanner, path):
    result = None
    for attempt in range(3):
        try:
            result = scanner._inspect(path)
            if result.status == "OK" or not result.status.startswith("Fout"):
                return result
        except Exception:
            result = None
        if attempt < 2:
            time.sleep(0.75)
    return result


def _info_to_dict(info):
    return {"path": info.path, "name": info.name, "size": info.size, "duration": info.duration, "duration_text": info.duration_text, "resolution": info.resolution, "width": info.width, "height": info.height, "bitrate": info.bitrate, "bitrate_text": info.bitrate_text, "video_codec": info.video_codec, "audio_codec": info.audio_codec, "fps": info.fps, "container": info.container, "video_hash": info.video_hash}


def _dict_to_info(data):
    return df.VideoInfo(**data)


def _analyse_videos_incremental(folder, ffprobe, ffmpeg, progress=None):
    if not ffprobe or not ffmpeg:
        raise RuntimeError("FFprobe en FFmpeg zijn vereist.")

    inventory = _video_inventory(folder)
    previous = _load_cache(folder)
    current_paths = {x["path"] for x in inventory}
    records = {}
    scanner = df.MediaScanner(ffprobe)
    infos = []

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
            records.pop(item["path"], None)
        _report(progress, index, len(inventory))

    # Build inexpensive candidate buckets first. We deliberately do NOT create
    # visual fingerprints for all videos: that was the cause of the apparent
    # hang at the end of large scans.
    candidate_pairs = []
    seen = set()
    candidate_paths = set()

    def add_pair(a, b):
        key = tuple(sorted((a.path, b.path), key=str.casefold))
        if a.path == b.path or key in seen:
            return
        seen.add(key)
        candidate_pairs.append((a, b))
        candidate_paths.add(a.path)
        candidate_paths.add(b.path)

    name_groups = {}
    for info in infos:
        duration_bucket = int(round(info.duration / 5.0)) if info.duration > 0 else 0
        aspect = round(info.width / info.height, 2) if info.width and info.height else 0
        name_groups.setdefault((_name_key(info.name), duration_bucket, aspect), []).append(info)
    for candidates in name_groups.values():
        if len(candidates) > 60:
            continue
        for i, first in enumerate(candidates):
            for second in candidates[i + 1:]:
                add_pair(first, second)

    buckets = {}
    for info in infos:
        if info.duration <= 0 or not info.width or not info.height:
            continue
        key = (int(round(info.duration / 5.0)), round(info.width / info.height, 2), info.width, info.height)
        buckets.setdefault(key, []).append(info)
    for candidates in buckets.values():
        if len(candidates) > 60:
            continue
        for i, first in enumerate(candidates):
            for second in candidates[i + 1:]:
                if _name_key(first.name) != _name_key(second.name):
                    add_pair(first, second)

    # Exact duplicates only need hashing when a file size occurs more than once.
    by_size = {}
    for info in infos:
        by_size.setdefault(info.size, []).append(info)
    exact_groups = []
    used = set()
    for candidates in by_size.values():
        if len(candidates) < 2 or len(candidates) > 80:
            continue
        hashes = {}
        for info in candidates:
            try:
                digest = df.exact_hash(info.path)
            except (OSError, PermissionError):
                digest = ""
            if digest:
                hashes.setdefault(digest, []).append(info)
        for same in hashes.values():
            if len(same) > 1:
                exact_groups.append(same)
                used.update(x.path for x in same)

    # Fingerprint only visual candidates, reusing cache whenever possible.
    fingerprints = {}
    for path in candidate_paths:
        info = next((x for x in infos if x.path == path), None)
        if info is None:
            continue
        record = records.get(path, {})
        cached = record.get("visual_hashes")
        if cached:
            fingerprints[path] = cached
        else:
            fp = _visual_hashes(ffmpeg, path, info.duration)
            if fp:
                fingerprints[path] = fp
                record["visual_hashes"] = fp

    groups = list(exact_groups)
    for first, second in candidate_pairs:
        if first.path in used or second.path in used:
            continue
        ratio = abs(first.duration - second.duration) / max(first.duration, second.duration, 1)
        same_name = _name_key(first.name) == _name_key(second.name)
        if ratio > (0.025 if same_name else 0.012):
            continue
        similarity = _hamming_similarity(fingerprints.get(first.path, []), fingerprints.get(second.path, []))
        if similarity < (91 if same_name else 96):
            continue
        target = next((g for g in groups if first in g or second in g), None)
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

    records = {p: r for p, r in records.items() if p in current_paths and r.get("status") == "ok"}
    _save_cache(folder, records)
    return results


def analyse_videos(folder, ffprobe, ffmpeg, progress=None):
    return _analyse_videos_incremental(folder, ffprobe, ffmpeg, progress)


def send_to_recycle_bin(path):
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
        raise OSError("Windows heeft de operatie afgebroken")


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
