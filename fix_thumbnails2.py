from pathlib import Path

path = Path("video_library.py")
text = path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# 1. ThumbnailTask vervangen
# ------------------------------------------------------------

start = text.index("class ThumbnailTask(QRunnable):")
end = text.index("\n\nclass VideoCard", start)

new_task = '''class ThumbnailTask(QRunnable):
    def __init__(self, path: str, cache_path: str, signals: WorkerSignals):
        super().__init__()
        self.path = path
        self.cache_path = cache_path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        # Worker-thread doet alleen bestand/FFmpeg werk.
        # QPixmap wordt uitsluitend in de GUI-thread gemaakt.
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

text = text[:start] + new_task + text[end:]

# ------------------------------------------------------------
# 2. make_thumbnail vervangen door bytes-versie
# ------------------------------------------------------------

start = text.index("def make_thumbnail(path: str)")
end = text.index("\n\ndef resolution_label", start)

new_thumbnail = '''def make_thumbnail_bytes(path: str) -> bytes | None:
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

text = text[:start] + new_thumbnail + text[end:]

# ------------------------------------------------------------
# 3. GUI callback aanpassen
# ------------------------------------------------------------

old = '''    def _thumbnail_finished(self, path, pixmap):
        self.thumbnail_done += 1
        card = self.card_by_path.get(path)
        if card:
            card.set_thumbnail(pixmap)
        if path == self.selected_path and pixmap and not pixmap.isNull():
            self.detail_preview.setText("")
            self.detail_preview.setPixmap(pixmap.scaled(500, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        if self.thumbnail_done >= self.thumbnail_total:
            self.status.setText(f"Klaar: {len(self.items):,} video's • previews geladen")
'''

new = '''    def _thumbnail_finished(self, path, data):
        self.thumbnail_done += 1

        pixmap = QPixmap()
        if data:
            pixmap.loadFromData(data)

        card = self.card_by_path.get(path)
        if card:
            card.set_thumbnail(pixmap)

        if path == self.selected_path and not pixmap.isNull():
            self.detail_preview.setText("")
            self.detail_preview.setPixmap(
                pixmap.scaled(
                    500,
                    220,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        if self.thumbnail_done >= self.thumbnail_total:
            self.status.setText(
                f"Klaar: {len(self.items):,} video's • previews geladen"
            )
'''

if old not in text:
    raise SystemExit("_thumbnail_finished blok niet gevonden.")

text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Thumbnail-systeem succesvol aangepast.")