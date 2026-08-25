from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".ts", ".mts", ".m2ts", ".wmv", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".alac"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


@dataclass
class MediaResult:
    path: str
    name: str
    media_type: str
    duration_seconds: float
    duration_text: str
    resolution: str
    video_codec: str
    audio_codec: str
    size_bytes: int
    size_text: str
    status: str


class MediaScanner:
    def __init__(self):
        self.ffprobe = self._find_ffprobe()
        self.last_total = 0

    @staticmethod
    def _find_ffprobe() -> str | None:
        names = ["ffprobe.exe", "ffprobe"] if os.name == "nt" else ["ffprobe"]
        for name in names:
            found = shutil.which(name)
            if found:
                return found
        candidates = []
        if os.name == "nt":
            candidates += [
                Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "ffmpeg" / "bin" / "ffprobe.exe",
                Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "FFmpeg" / "bin" / "ffprobe.exe",
            ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return None

    def scan(self, folder: str) -> Iterator[MediaResult]:
        root = Path(folder)
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS]
        self.last_total = len(files)
        for path in files:
            yield self._inspect(path)

    def _inspect(self, path: Path) -> MediaResult:
        size = 0
        try:
            size = path.stat().st_size
        except OSError:
            pass
        media_type = "Video" if path.suffix.lower() in VIDEO_EXTENSIONS else "Audio"
        base = dict(path=str(path), name=path.name, media_type=media_type,
                    duration_seconds=0.0, duration_text="—", resolution="—",
                    video_codec="—", audio_codec="—", size_bytes=size,
                    size_text=format_size(size), status="OK")
        if not self.ffprobe:
            base["status"] = "FFprobe niet gevonden"
            return MediaResult(**base)
        try:
            probe = self._run_ffprobe(path)
            fmt = probe.get("format", {})
            streams = probe.get("streams", [])
            duration = float(fmt.get("duration") or 0)
            video = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
            base["duration_seconds"] = duration
            base["duration_text"] = format_duration(duration)
            if video:
                width, height = video.get("width"), video.get("height")
                if width and height:
                    base["resolution"] = f"{width} × {height}"
                base["video_codec"] = video.get("codec_name") or "—"
            if audio:
                base["audio_codec"] = audio.get("codec_name") or "—"
        except Exception as exc:
            base["status"] = f"Fout: {str(exc)[:120]}"
        return MediaResult(**base)

    def _run_ffprobe(self, path: Path) -> dict:
        completed = subprocess.run(
            [self.ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or "FFprobe kon het bestand niet lezen."
            raise RuntimeError(message)
        import json
        return json.loads(completed.stdout)


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def format_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"
