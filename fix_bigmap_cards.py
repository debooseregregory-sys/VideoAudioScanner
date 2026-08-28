from pathlib import Path

path = Path("video_library.py")
text = path.read_text(encoding="utf-8")

old = '''    def refresh_cards(self):
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()
        self.card_by_path.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        items = self._visible_items()
        for index, item in enumerate(items):
            card = VideoCard(item, self.select_video, self.open_video, self.container)
            card.set_selected(item.path == self.selected_path)
            self.cards.append(card)
            self.card_by_path[item.path] = card
            self.grid.addWidget(card, index // 3, index % 3)
        self.grid.setRowStretch(max(1, (len(items) + 2) // 3), 1)
        self.status.setText(f"Weergave: {len(items):,} van {len(self.items):,} video's")
'''

new = '''    def refresh_cards(self):
        # Nooit duizenden Qt-widgets tegelijk aanmaken.
        # De database/lijst mag groot zijn, maar de GUI toont slechts
        # een beperkt aantal kaarten tegelijk.
        for card in self.cards:
            card.deleteLater()

        self.cards.clear()
        self.card_by_path.clear()

        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        items = self._visible_items()

        # Maximaal 60 kaarten tegelijk.
        # Dit voorkomt dat een bibliotheek van 10.000+ video's
        # de GUI laat vastlopen.
        display_items = items[:60]

        for index, item in enumerate(display_items):
            card = VideoCard(
                item,
                self.select_video,
                self.open_video,
                self.container,
            )
            card.set_selected(item.path == self.selected_path)

            self.cards.append(card)
            self.card_by_path[item.path] = card

            self.grid.addWidget(
                card,
                index // 3,
                index % 3,
            )

        rows = max(1, (len(display_items) + 2) // 3)
        self.grid.setRowStretch(rows, 1)

        if len(items) > 60:
            self.status.setText(
                f"Weergave: eerste 60 van {len(items):,} video's "
                f"(totaal geïndexeerd: {len(self.items):,})"
            )
        else:
            self.status.setText(
                f"Weergave: {len(items):,} van {len(self.items):,} video's"
            )

        # Alleen voor de kaarten die daadwerkelijk op het scherm staan
        # worden previews gestart.
        self._start_thumbnails()
'''

if old not in text:
    raise SystemExit(
        "Het huidige refresh_cards-blok werd niet exact gevonden. "
        "Er is niets gewijzigd."
    )

text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

print("Grote-bibliotheek kaartbeperking toegevoegd.")