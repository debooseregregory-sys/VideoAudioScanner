from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable


class VideoLibraryDB:
    """Persistent SQLite index used by the Video Library."""

    def __init__(self, base_dir: str | Path | None = None):
        root = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.path = root / "data" / "video_library.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self):
        con = sqlite3.connect(str(self.path))
        con.row_factory = sqlite3.Row
        return con

    def _init(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    path TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size INTEGER NOT NULL DEFAULT 0,
                    modified REAL NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    thumbnail_path TEXT NOT NULL DEFAULT '',
                    indexed_at REAL NOT NULL DEFAULT 0,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    watched INTEGER NOT NULL DEFAULT 0,
                    watched_at REAL NOT NULL DEFAULT 0
                )
            """)
            self._ensure_column(con, "favorite", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(con, "watched", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(con, "watched_at", "REAL NOT NULL DEFAULT 0")
            con.execute("CREATE INDEX IF NOT EXISTS idx_videos_name ON videos(name)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_videos_size ON videos(size)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_videos_modified ON videos(modified)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_videos_favorite ON videos(favorite)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_videos_watched ON videos(watched)")

    @staticmethod
    def _ensure_column(con, name: str, definition: str):
        columns = {row[1] for row in con.execute("PRAGMA table_info(videos)").fetchall()}
        if name not in columns:
            con.execute(f"ALTER TABLE videos ADD COLUMN {name} {definition}")

    def get(self, path: str):
        with self._connect() as con:
            return con.execute("SELECT * FROM videos WHERE path = ?", (path,)).fetchone()

    def all(self) -> list[sqlite3.Row]:
        with self._connect() as con:
            return con.execute("SELECT * FROM videos ORDER BY name COLLATE NOCASE").fetchall()

    def save(self, *, path: str, name: str, extension: str, size: int,
             modified: float, metadata: dict | None = None,
             thumbnail_path: str = "", indexed_at: float = 0):
        with self._connect() as con:
            old = con.execute("SELECT favorite, watched, watched_at FROM videos WHERE path = ?", (path,)).fetchone()
            favorite = int(old["favorite"]) if old else 0
            watched = int(old["watched"]) if old else 0
            watched_at = float(old["watched_at"]) if old else 0
            con.execute("""
                INSERT INTO videos(path,name,extension,size,modified,metadata_json,thumbnail_path,indexed_at,favorite,watched,watched_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                    name=excluded.name,
                    extension=excluded.extension,
                    size=excluded.size,
                    modified=excluded.modified,
                    metadata_json=excluded.metadata_json,
                    thumbnail_path=excluded.thumbnail_path,
                    indexed_at=excluded.indexed_at
            """, (
                path, name, extension, int(size), float(modified),
                json.dumps(metadata or {}, ensure_ascii=False),
                thumbnail_path, float(indexed_at), favorite, watched, watched_at,
            ))

    def set_favorite(self, path: str, value: bool):
        with self._connect() as con:
            con.execute("UPDATE videos SET favorite = ? WHERE path = ?", (1 if value else 0, path))

    def set_watched(self, path: str, value: bool):
        import time
        with self._connect() as con:
            con.execute(
                "UPDATE videos SET watched = ?, watched_at = ? WHERE path = ?",
                (1 if value else 0, time.time() if value else 0, path),
            )

    def delete_missing_under_root(self, root: str | Path, existing_paths: Iterable[str]):
        root_path = Path(root).resolve()
        existing = {str(Path(p).resolve()) for p in existing_paths}
        with self._connect() as con:
            rows = con.execute("SELECT path FROM videos").fetchall()
            for row in rows:
                stored = Path(row["path"])
                try:
                    inside = stored == root_path or root_path in stored.parents
                    normalized = str(stored.resolve())
                except (OSError, ValueError):
                    inside = False
                    normalized = str(stored)
                if inside and normalized not in existing:
                    con.execute("DELETE FROM videos WHERE path = ?", (row["path"],))

    def clear(self):
        with self._connect() as con:
            con.execute("DELETE FROM videos")

    @staticmethod
    def metadata(row) -> dict:
        try:
            return json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
