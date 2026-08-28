from pathlib import Path

p = Path("video_library.py")
s = p.read_text(encoding="utf-8")

old = '''                if not unchanged:
                    self.pool.start(MetadataTask(p, self.metadata_signals))
'''

new = '''                # Metadata wordt pas na het verzamelen van alle bestanden
                # verwerkt. Zo starten we niet honderden FFprobe-processen
                # tijdens het scannen.
'''

if old not in s:
    raise SystemExit("Metadata-blok niet gevonden.")

s = s.replace(old, new, 1)

old = '''        self._start_thumbnails()
'''

new = '''        # Eerst de lijst tonen. Zware preview/metadata-verwerking
        # gebeurt daarna gecontroleerd.
        self._start_thumbnails()
        self._start_metadata_queue()
'''

if old not in s:
    raise SystemExit("_start_thumbnails-aanroep niet gevonden.")

s = s.replace(old, new, 1)

# Voeg een gecontroleerde metadata-startfunctie toe vlak voor _visible_items.
marker = '''    def _visible_items(self):
'''

method = '''    def _start_metadata_queue(self):
        """Verwerk metadata gecontroleerd nadat de scan zichtbaar is."""
        pending = [
            item.path
            for item in self.items
            if not item.metadata or item.metadata.get("error")
        ]

        if not pending:
            return

        self.metadata_queue = pending
        self.metadata_queue_index = 0
        self.status.setText(
            f"Video's gevonden. Metadata wordt verwerkt: "
            f"0 / {len(pending):,}"
        )
        self._start_next_metadata()

    def _start_next_metadata(self):
        if not hasattr(self, "metadata_queue"):
            return

        # Houd maximaal twee metadata-processen tegelijk actief.
        active = getattr(self, "_metadata_active", 0)

        while active < 2 and self.metadata_queue_index < len(self.metadata_queue):
            path = self.metadata_queue[self.metadata_queue_index]
            self.metadata_queue_index += 1
            active += 1
            self.pool.start(MetadataTask(path, self.metadata_signals))

        self._metadata_active = active

'''
if marker not in s:
    raise SystemExit("Marker voor metadata-functie niet gevonden.")

s = s.replace(marker, method + marker, 1)

# Zorg dat de bestaande metadata callback de queue verder laat lopen.
old = '''    def _metadata_finished(self, path, data):
        item = next((x for x in self.items if x.path == path), None)
'''

new = '''    def _metadata_finished(self, path, data):
        self._metadata_active = max(0, getattr(self, "_metadata_active", 1) - 1)

        item = next((x for x in self.items if x.path == path), None)
'''

if old not in s:
    raise SystemExit("_metadata_finished niet gevonden.")

s = s.replace(old, new, 1)

# Na metadata-update opnieuw kaarten verversen en volgende jobs starten.
old = '''        item.metadata = data
'''

new = '''        item.metadata = data
        self._metadata_active = max(0, getattr(self, "_metadata_active", 1) - 1)

        try:
            self.db.upsert(
                path,
                item.name,
                item.size,
                item.extension,
                item.modified,
            )
        except Exception:
            pass

        self._start_next_metadata()
'''

if old not in s:
    raise SystemExit("Metadata-toewijzing niet gevonden.")

s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("Scan-aanpassing toegepast.")