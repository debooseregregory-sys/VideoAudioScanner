from pathlib import Path

path = Path("video_library.py")
text = path.read_text(encoding="utf-8")

# Beperk de achtergrondpool zodat een grote videomap
# de computer niet laat vastlopen.
old = "self.pool = QThreadPool(self)"
new = "self.pool = QThreadPool(self)\n        self.pool.setMaxThreadCount(2)"

if old in text and "self.pool.setMaxThreadCount(2)" not in text:
    text = text.replace(old, new, 1)
    print("OK: threadpool beperkt tot 2 workers.")
else:
    print("Threadpool-regel niet gewijzigd.")

path.write_text(text, encoding="utf-8")
print("video_library.py opgeslagen.")