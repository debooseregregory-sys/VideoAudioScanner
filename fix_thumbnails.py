from pathlib import Path

path = Path("video_library.py")
text = path.read_text(encoding="utf-8")

old = '''    def run(self):
        pixmap = None
        if os.path.isfile(self.cache_path):
            cached = QPixmap(self.cache_path)
            if not cached.isNull():
                pixmap = cached
        if pixmap is None:
            pixmap = make_thumbnail(self.path)
            if pixmap and not pixmap.isNull():
                try:
                    pixmap.save(self.cache_path, "JPG", 88)
                except Exception:
                    pass
        self.signals.finished.emit(self.path, pixmap)
'''

new = '''    def run(self):
        # QPixmap mag niet in een worker-thread worden aangemaakt.
        # De worker levert alleen de afbeeldingsbytes terug.
        data = None

        if os.path.isfile(self.cache_path):
            try:
                data = Path(self.cache_path).read_bytes()
            except OSError:
                data = None

        if data is None:
            data = make_thumbnail_bytes(self.path)

            if data:
                try:
                    Path(self.cache_path).write_bytes(data)
                except OSError:
                    pass

        self.signals.finished.emit(self.path, data)
'''

if old not in text:
    raise SystemExit("ThumbnailTask.run niet gevonden.")

text = text.replace(old, new, 1)

marker = '''def make_thumbnail(path: str) -> QPixmap | None:
'''

if marker in text:
    start = text.index(marker)
    end = text.index("\\n\\ndef resolution_label", start)

    replacement = '''def make_thumbnail_bytes(path: str) -> bytes | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None

    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel", "error",
                "-ss", "00:00:03",
                "-i", path,
                "-frames:v", "1",
                "-vf", "scale=640:-2",
                "-f", "image2",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )

        if result.returncode != 0 or not result.stdout:
            return None

        return result.stdout

    except (OSError, subprocess.SubprocessError):
        return None
'''

    text = text[:start] + replacement + text[end:]
else:
    raise SystemExit("make_thumbnail functie niet gevonden.")

path.write_text(text, encoding="utf-8")
print("Thumbnail worker aangepast.")