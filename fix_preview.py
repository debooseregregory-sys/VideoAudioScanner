from pathlib import Path

path = Path("video_library.py")
text = path.read_text(encoding="utf-8")

old = '''        result = subprocess.run(
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
'''

new = '''        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel", "error",
                "-threads", "1",
                "-i", path,
                "-frames:v", "1",
                "-vf", "scale=640:-2",
                "-q:v", "5",
                "-f", "image2",
                "pipe:1",
            ],
'''

if old not in text:
    raise SystemExit("FFmpeg thumbnail-blok niet gevonden.")

text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Preview FFmpeg-instellingen aangepast.")