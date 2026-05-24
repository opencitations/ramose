# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class ResultCache:
    def __init__(self, directory: str) -> None:
        db_dir = Path(directory)
        db_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_dir / "cache.db"), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)",
        )
        self._conn.commit()

    def get(self, key: str) -> object:
        row = self._conn.execute(
            "SELECT value FROM cache WHERE key = ? AND expires_at > ?",
            (key, time.time()),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key: str, value: object, expire: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time() + expire),
        )
        self._conn.commit()
