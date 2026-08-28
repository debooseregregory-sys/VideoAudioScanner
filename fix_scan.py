from pathlib import Path

path = Path("video_library.py")
text = path.read_text(encoding="utf-8")

old = '''        self.status.setText("Video's zoeken…")
        self.scan_button.setEnabled(False)
        QApplication.processEvents()
        items: list[VideoItem] = []
'''

new = '''        self.status.setText("Video's zoeken…")
        self.scan_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        QApplication.processEvents()

        # Zoek alleen bestanden. Zware metadata- en thumbnailtaken
        # worden pas uitgevoerd nadat de lijst zichtbaar is.
        items: list[VideoItem] = []
'''

if old not in text:
    raise SystemExit("Kon het scanblok niet vinden; bestand is niet gewijzigd.")

text = text.replace(old, new, 1)

old2 = '''        self.items = items
        self.scan_button.setEnabled(True)
        self.refresh_cards()
        total = sum(i.size for i in items)
'''

new2 = '''        self.items = items

        # Toon de video's onmiddellijk. De GUI blijft hierdoor
        # bruikbaar terwijl verdere verwerking later kan gebeuren.
        self.refresh_cards()

        self.scan_button.setEnabled(True)
        self.refresh_button.setEnabled(True)

        total = sum(i.size for i in items)
'''

if old2 not in text:
    raise SystemExit("Kon het tweede scanblok niet vinden; bestand is niet gewijzigd.")

text = text.replace(old2, new2, 1)

path.write_text(text, encoding="utf-8")
print("Scan-flow aangepast.")