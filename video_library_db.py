from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable


class VideoLibraryDB:
    """Small persistent SQLite index for VideoAudioScanner's Video Library."""

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
                    indexed_at REAL NOT NULL DEFAULT 0
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_videos_name ON videos(name)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_videos_size ON videos(size)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_videos_modified ON videos(modified)")

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
            con.execute("""
                INSERT INTO videos(path,name,extension,size,modified,metadata_json,thumbnail_path,indexed_at)
                VALUES(?,?,?,?,?,?,?,?)
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
                thumbnail_path, float(indexed_at),
            ))

    def delete_missing(self, existing_paths: Iterable[str]):
        paths = list(existing_paths)
        with self._connect() as con:
            if not paths:
                con.execute("DELETE FROM videos")
                return
            placeholders = ",".join("?" for _ in paths)
            con.execute(f"DELETE FROM videos WHERE path NOT IN ({placeholders})", paths)

    def clear(self):
        with self._connect() as con:
            con.execute("DELETE FROM videos")

    @staticmethod
    def metadata(row) -> dict:
        try:
            return json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
