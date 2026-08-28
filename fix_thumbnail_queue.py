from pathlib import Path

path = Path("video_library.py")
text = path.read_text(encoding="utf-8")

old = '''    def _start_thumbnails(self):
        paths = list(self.card_by_path)
        self.thumbnail_total = len(paths)
        self.thumbnail_done = 0
        if not paths:
            return
        self.status.setText(f"Preview's laden: 0 / {len(paths):,}")
        self.pool.clear()
        for path in paths:
            self.pool.start(ThumbnailTask(path, self._thumb_cache_path(path), self.thumbnail_signals))
'''

new = '''    def _start_thumbnails(self):
        paths = list(self.card_by_path)
        self.thumbnail_total = len(paths)
        self.thumbnail_done = 0
        self.thumbnail_queue = paths
        self.thumbnail_queue_index = 0
        self.thumbnail_active = 0

        if not paths:
            return

        self.status.setText(
            f"Preview's laden: 0 / {len(paths):,}"
        )

        # Start slechts een kleine hoeveelheid tegelijk.
        self._start_next_thumbnails()
'''

if old not in text:
    raise SystemExit("_start_thumbnails blok niet gevonden.")

text = text.replace(old, new, 1)

old = '''    def _thumbnail_finished(self, path, data):
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

new = '''    def _start_next_thumbnails(self):
        if not hasattr(self, "thumbnail_queue"):
            return

        # Nooit meer dan twee FFmpeg-thumbnailtaken tegelijk.
        while (
            self.thumbnail_active < 2
            and self.thumbnail_queue_index < len(self.thumbnail_queue)
        ):
            path = self.thumbnail_queue[self.thumbnail_queue_index]
            self.thumbnail_queue_index += 1
            self.thumbnail_active += 1

            self.pool.start(
                ThumbnailTask(
                    path,
                    self._thumb_cache_path(path),
                    self.thumbnail_signals,
                )
            )

    def _thumbnail_finished(self, path, data):
        self.thumbnail_active = max(0, self.thumbnail_active - 1)
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

        self._start_next_thumbnails()

        if self.thumbnail_done >= self.thumbnail_total:
            self.status.setText(
                f"Klaar: {len(self.items):,} video's • previews geladen"
            )
        else:
            self.status.setText(
                f"Preview's laden: "
                f"{self.thumbnail_done:,} / {self.thumbnail_total:,}"
            )
'''

if old not in text:
    raise SystemExit("_thumbnail_finished blok niet gevonden.")

text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

print("Thumbnail-wachtrij succesvol toegevoegd.")