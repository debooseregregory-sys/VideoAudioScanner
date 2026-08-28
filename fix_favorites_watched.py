from pathlib import Path

path = Path("video_library.py")
text = path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# 1. VideoItem uitbreiden
# ------------------------------------------------------------

old = '''class VideoItem:
    path: str
    name: str
    size: int
    extension: str
    modified: float = 0.0
    metadata: dict | None = None
'''

new = '''class VideoItem:
    path: str
    name: str
    size: int
    extension: str
    modified: float = 0.0
    metadata: dict | None = None
    favorite: bool = False
    watched: bool = False
'''

if old not in text:
    raise SystemExit("VideoItem blok niet gevonden.")

text = text.replace(old, new, 1)

# ------------------------------------------------------------
# 2. DB gegevens laden in load_index_for_folder
# ------------------------------------------------------------

old = '''                    float(row["modified"]), self.db.metadata(row),
                ))
'''

new = '''                    float(row["modified"]),
                    self.db.metadata(row),
                    bool(row["favorite"]),
                    bool(row["watched"]),
                ))
'''

if old not in text:
    raise SystemExit("load_index_for_folder VideoItem blok niet gevonden.")

text = text.replace(old, new, 1)

# ------------------------------------------------------------
# 3. Scan bestaande VideoItem aanpassen
# ------------------------------------------------------------

old = '''                found.append(VideoItem(p, path.name, stat.st_size, path.suffix.lower(), stat.st_mtime, metadata if unchanged else {}))
'''

new = '''                found.append(
                    VideoItem(
                        p,
                        path.name,
                        stat.st_size,
                        path.suffix.lower(),
                        stat.st_mtime,
                        metadata if unchanged else {},
                        bool(row["favorite"]) if row else False,
                        bool(row["watched"]) if row else False,
                    )
                )
'''

if old not in text:
    raise SystemExit("scan VideoItem blok niet gevonden.")

text = text.replace(old, new, 1)

# ------------------------------------------------------------
# 4. Filterbox toevoegen na codec filter
# ------------------------------------------------------------

marker = '''        self.codec_box = QComboBox()
'''

if marker not in text:
    raise SystemExit("codec_box niet gevonden.")

# Alleen toevoegen als hij nog niet bestaat.
if "self.status_filter" not in text:
    insert = '''        self.status_filter = QComboBox()
        self.status_filter.addItems([
            "Alle video's",
            "⭐ Favorieten",
            "✓ Bekeken",
            "○ Onbekeken",
        ])
        self.status_filter.currentIndexChanged.connect(self.refresh_cards)

'''
    text = text.replace(marker, insert + marker, 1)

# ------------------------------------------------------------
# 5. Filter in _visible_items
# ------------------------------------------------------------

marker = '''        for item in self.items:
            if query and query not in item.name.casefold() and query not in item.path.casefold():
'''

replacement = '''        status_filter = self.status_filter.currentIndex()

        for item in self.items:
            if status_filter == 1 and not item.favorite:
                continue
            if status_filter == 2 and not item.watched:
                continue
            if status_filter == 3 and item.watched:
                continue

            if query and query not in item.name.casefold() and query not in item.path.casefold():
'''

if marker not in text:
    raise SystemExit("_visible_items loop niet gevonden.")

text = text.replace(marker, replacement, 1)

# ------------------------------------------------------------
# 6. VideoCard status-labels
# ------------------------------------------------------------

old = '''        meta = QLabel(f"{item.extension.upper().lstrip('.')}  •  {format_size(item.size)}")
        meta.setObjectName("libraryMeta")
        layout.addWidget(meta)
'''

new = '''        meta = QLabel(f"{item.extension.upper().lstrip('.')}  •  {format_size(item.size)}")
        meta.setObjectName("libraryMeta")
        layout.addWidget(meta)

        self.status_label = QLabel()
        self.status_label.setObjectName("libraryStatusBadge")
        self.update_status()

        layout.addWidget(self.status_label)
'''

if old not in text:
    raise SystemExit("VideoCard metadata-blok niet gevonden.")

text = text.replace(old, new, 1)

# Voeg statusmethodes toe vóór set_thumbnail.
marker = '''    def set_thumbnail(self, pixmap):
'''

methods = '''    def update_status(self):
        parts = []

        if self.item.favorite:
            parts.append("⭐ Favoriet")

        if self.item.watched:
            parts.append("✓ Bekeken")
        else:
            parts.append("○ Onbekeken")

        self.status_label.setText("   ".join(parts))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.select_callback(self.item.path)

        super().mousePressEvent(event)

'''

if marker not in text:
    raise SystemExit("VideoCard set_thumbnail marker niet gevonden.")

text = text.replace(marker, methods + marker, 1)

# ------------------------------------------------------------
# 7. Klikbare acties toevoegen aan detailpaneel
# ------------------------------------------------------------

marker = '''        self.play_button = QPushButton("▶  Afspelen in Video Suite Player")
'''

if marker not in text:
    raise SystemExit("play_button niet gevonden.")

buttons = '''        self.favorite_button = QPushButton("⭐  Favoriet")
        self.favorite_button.setCheckable(True)
        self.favorite_button.clicked.connect(self.toggle_favorite)
        dl.addWidget(self.favorite_button)

        self.watched_button = QPushButton("✓  Bekeken")
        self.watched_button.setCheckable(True)
        self.watched_button.clicked.connect(self.toggle_watched)
        dl.addWidget(self.watched_button)

'''

text = text.replace(marker, buttons + marker, 1)

# ------------------------------------------------------------
# 8. show_details knoppen synchroniseren
# ------------------------------------------------------------

old = '''        self.play_button.setEnabled(True)
        self.folder_button.setEnabled(True)
        self.analyze_button.setEnabled(True)
'''

new = '''        self.favorite_button.setChecked(item.favorite)
        self.watched_button.setChecked(item.watched)

        self.play_button.setEnabled(True)
        self.folder_button.setEnabled(True)
        self.analyze_button.setEnabled(True)
'''

if old not in text:
    raise SystemExit("show_details button-blok niet gevonden.")

text = text.replace(old, new, 1)

# ------------------------------------------------------------
# 9. Toggle-methodes toevoegen
# ------------------------------------------------------------

marker = '''    def _fill_details(self, data, path):
'''

methods = '''    def toggle_favorite(self, checked):
        if not self.selected_path:
            return

        item = next(
            (x for x in self.items if x.path == self.selected_path),
            None,
        )
        if not item:
            return

        item.favorite = bool(checked)
        self.db.set_favorite(item.path, item.favorite)

        card = self.card_by_path.get(item.path)
        if card:
            card.update_status()

        self.refresh_cards()

    def toggle_watched(self, checked):
        if not self.selected_path:
            return

        item = next(
            (x for x in self.items if x.path == self.selected_path),
            None,
        )
        if not item:
            return

        item.watched = bool(checked)
        self.db.set_watched(item.path, item.watched)

        card = self.card_by_path.get(item.path)
        if card:
            card.update_status()

        self.refresh_cards()

'''

if marker not in text:
    raise SystemExit("_fill_details marker niet gevonden.")

text = text.replace(marker, methods + marker, 1)

# ------------------------------------------------------------
# 10. Styling
# ------------------------------------------------------------

old = '''            QLabel#libraryPath { color:#777f8c; font-size:11px; }
'''

new = '''            QLabel#libraryPath { color:#777f8c; font-size:11px; }
            QLabel#libraryStatusBadge { color:#d9b85a; font-weight:700; padding:3px 0; }
'''

if old in text:
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

print("Favorieten + Bekeken toegevoegd.")