
"""Persistent content snapshots for FILIP GUARD.

Snapshots are stored in SQLite.
No WordPress changes are performed here.
"""

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone


class BackupManager:
    def __init__(self, database_path):
        self.database_path = database_path
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS backups (
                    backup_id TEXT PRIMARY KEY,
                    site_url TEXT NOT NULL,
                    resource_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def _connect(self):
        return sqlite3.connect(self.database_path)

    def create_backup(self, site_url, resource_id, content):
        if not isinstance(content, str):
            raise ValueError("Content must be text.")

        if type(resource_id) is not int or resource_id <= 0:
            raise ValueError("Invalid resource ID.")

        backup_id = str(uuid.uuid4())
        content_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        created_at = datetime.now(
            timezone.utc
        ).isoformat()

        with self._connect() as db:
            db.execute(
                """
                INSERT INTO backups
                (backup_id, site_url, resource_id,
                 content, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    backup_id,
                    site_url,
                    resource_id,
                    content,
                    content_hash,
                    created_at,
                ),
            )

        return backup_id

    def get_backup(self, backup_id):
        with self._connect() as db:
            row = db.execute(
                """
                SELECT site_url, resource_id,
                       content, content_hash, created_at
                FROM backups
                WHERE backup_id = ?
                """,
                (backup_id,),
            ).fetchone()

        if row is None:
            return None

        site_url, resource_id, content, saved_hash, created_at = row

        actual_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        if actual_hash != saved_hash:
            raise ValueError("Backup integrity check failed.")

        return {
            "backup_id": backup_id,
            "site_url": site_url,
            "resource_id": resource_id,
            "content": content,
            "content_hash": saved_hash,
            "created_at": created_at,
        }
