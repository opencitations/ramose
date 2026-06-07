# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from pathlib import Path


class TokenStore:
    def __init__(self, directory: str) -> None:
        db_dir = Path(directory)
        db_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_dir / "auth.db"), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS tokens "
            "(token_hash TEXT PRIMARY KEY, label TEXT, created_at REAL NOT NULL, "
            "expires_at REAL, revoked INTEGER NOT NULL DEFAULT 0)",
        )
        self._conn.commit()

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create(self, label: str, ttl: int | None = None) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        expires_at = now + ttl if ttl is not None else None
        self._conn.execute(
            "INSERT INTO tokens (token_hash, label, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (TokenStore._hash(token), label, now, expires_at),
        )
        self._conn.commit()
        return token

    def validate(self, token: str) -> bool:
        row = self._conn.execute(
            "SELECT expires_at FROM tokens WHERE token_hash = ? AND revoked = 0",
            (TokenStore._hash(token),),
        ).fetchone()
        if row is None:
            return False
        expires_at = row[0]
        return expires_at is None or expires_at > time.time()

    def revoke(self, token: str) -> bool:
        cursor = self._conn.execute(
            "UPDATE tokens SET revoked = 1 WHERE token_hash = ?",
            (TokenStore._hash(token),),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_tokens(self) -> list[tuple[str, float, float | None, int]]:
        return self._conn.execute(
            "SELECT label, created_at, expires_at, revoked FROM tokens ORDER BY created_at",
        ).fetchall()
