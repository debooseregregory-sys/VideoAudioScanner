from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
    bitrate: str
    sample_rate: str
    channels: str
    fps: str
    container: str
    size_bytes: int
    size_text: str
    status: str


class MediaScanner:
    """Recursively scan media files and read metadata with FFprobe."""

    def __init__(self, ffprobe_path: str | None = None):
        self.ffprobe = self._find_ffprobe(ffprobe_path)
        self.last_total = 0

    @staticmethod
    def _find_ffprobe(explicit: str | None = None) -> str | None:
        candidates: list[Path] = []
        if explicit:
            candidates.append(Path(explicit).expanduser())
        env_path = os.environ.get("VIDEOAUDIOSCANNER_FFPROBE", "").strip()
        if env_path:
            candidates.append(Path(env_path).expanduser())
        found = shutil.which("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if found:
            candidates.append(Path(found))
        app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        candidates.extend([app_dir / "ffprobe.exe", app_dir / "ffmpeg" / "bin" / "ffprobe.exe", app_dir / "tools" / "ffprobe.exe", Path.cwd() / "tools" / "ffprobe.exe"])
        if os.name == "nt":
            pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            pfx86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            lad = Path(os.environ.get("LOCALAPPDATA", ""))
            candidates.extend([pf / "ffmpeg" / "bin" / "ffprobe.exe", pf / "FFmpeg" / "bin" / "ffprobe.exe", pfx86 / "ffmpeg" / "bin" / "ffprobe.exe", lad / "ffmpeg" / "bin" / "ffprobe.exe"])
        seen: set[str] = set()
        for candidate in candidates:
            try:
                key = str(candidate.resolve()).casefold()
            except OSError:
                key = str(candidate).casefold()
            if key in seen:
                continue
            seen.add(key)
            try:
                if candidate.is_file():
                    return str(candidate)
            except OSError:
                continue
        return None

    def scan(self, folder: str) -> Iterator[MediaResult]:
        root = Path(folder)
        try:
            files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS]
        except (OSError, PermissionError) as exc:
            raise RuntimeError(f"Kan de map niet lezen: {exc}") from exc
        files.sort(key=lambda p: str(p).casefold())
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
        base = dict(path=str(path), name=path.name, media_type=media_type, duration_seconds=0.0, duration_text="—", resolution="—", video_codec="—", audio_codec="—", bitrate="—", sample_rate="—", channels="—", fps="—", container="—", size_bytes=size, size_text=format_size(size), status="OK")
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
            base["container"] = fmt.get("format_name") or "—"
            bitrate = fmt.get("bit_rate")
            if bitrate:
                base["bitrate"] = format_bitrate(bitrate)
            if video:
                width, height = video.get("width"), video.get("height")
                if width and height:
                    base["resolution"] = f"{width} × {height}"
                base["video_codec"] = video.get("codec_name") or "—"
                base["fps"] = format_fps(video.get("avg_frame_rate") or video.get("r_frame_rate"))
            if audio:
                base["audio_codec"] = audio.get("codec_name") or "—"
                rate = audio.get("sample_rate")
                if rate:
                    base["sample_rate"] = f"{int(float(rate)):,} Hz".replace(",", ".")
                channels = audio.get("channel_layout") or audio.get("channels")
                base["channels"] = str(channels) if channels else "—"
            if not video and not audio:
                base["status"] = "Geen media-stream gevonden"
        except subprocess.TimeoutExpired:
            base["status"] = "Fout: FFprobe timeout (>60 s)"
        except FileNotFoundError:
            base["status"] = "Fout: FFprobe kon niet worden gestart"
        except PermissionError:
            base["status"] = "Fout: geen toegang"
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            base["status"] = f"Fout: {(str(exc).strip() or 'FFprobe kon het bestand niet lezen.')[:120]}"
        except Exception as exc:
            base["status"] = f"Fout: {str(exc)[:120]}"
        return MediaResult(**base)

    def _run_ffprobe(self, path: Path) -> dict:
        completed = subprocess.run([self.ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "FFprobe kon het bestand niet lezen.")
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


def format_bitrate(value: str | int | float) -> str:
    try:
        kbps = float(value) / 1000
        return f"{kbps:.0f} kb/s"
    except (TypeError, ValueError):
        return "—"


def format_fps(value: str | None) -> str:
    if not value or value in {"0/0", "N/A"}:
        return "—"
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            fps = float(numerator) / float(denominator)
        else:
            fps = float(value)
        return f"{fps:.3f}".rstrip("0").rstrip(".") + " fps"
    except (TypeError, ValueError, ZeroDivisionError):
        return "—"
