"""Isolated SQLite fixture, NOT a WordPress REST adapter or production server.

No networking. Simulates server-side permissions, durable revisions and atomic
conditional writes for the AutoFix engine tests and local UI demonstration.
"""
from contextlib import contextmanager
import json
import sqlite3
from wordpress_revision_guard import ResourceSnapshot, verify_unchanged


class LocalWordPressFixture:
    def __init__(self, database_path):
        self.database_path = str(database_path)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS resources (
                site TEXT, kind TEXT, id INTEGER, content TEXT, revision INTEGER,
                PRIMARY KEY(site, kind, id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS editors (
                site TEXT, kind TEXT, id INTEGER, user_id INTEGER,
                PRIMARY KEY(site, kind, id, user_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS fixture_operations (
                operation_id TEXT PRIMARY KEY, request TEXT, receipt TEXT)''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self, site, kind, resource_id, content, *, user_id):
        with self._db() as db:
            db.execute('INSERT INTO resources VALUES (?, ?, ?, ?, 1)', (site, kind, resource_id, content))
            db.execute('INSERT INTO editors VALUES (?, ?, ?, ?)', (site, kind, resource_id, user_id))

    @staticmethod
    def _read(db, site, kind, resource_id, user_id):
        if not db.execute('SELECT 1 FROM editors WHERE site=? AND kind=? AND id=? AND user_id=?',
                          (site, kind, resource_id, user_id)).fetchone():
            raise PermissionError('Resource edit permission required')
        row = db.execute('SELECT content, revision FROM resources WHERE site=? AND kind=? AND id=?',
                         (site, kind, resource_id)).fetchone()
        if row is None:
            raise ValueError('Resource not found')
        return ResourceSnapshot(site, kind, resource_id, row[0], str(row[1]))

    def read_authorized(self, site, kind, resource_id, user_id):
        with self._db() as db:
            return self._read(db, site, kind, resource_id, user_id)

    def compare_and_swap(self, expected, content, user_id, *, operation_id):
        from dataclasses import asdict
        request = json.dumps([asdict(expected), content, user_id], sort_keys=True)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            observed = self._read(db, expected.site_url, expected.resource_type, expected.resource_id, user_id)
            previous = db.execute('SELECT request, receipt FROM fixture_operations WHERE operation_id=?',
                                  (operation_id,)).fetchone()
            if previous:
                if previous[0] != request:
                    raise PermissionError('Operation identifier reused with different content')
                return ResourceSnapshot(**json.loads(previous[1]))
            verify_unchanged(expected, observed)
            db.execute('UPDATE resources SET content=?, revision=revision+1 WHERE site=? AND kind=? AND id=?',
                       (content, expected.site_url, expected.resource_type, expected.resource_id))
            receipt = self._read(db, expected.site_url, expected.resource_type, expected.resource_id, user_id)
            db.execute('INSERT INTO fixture_operations VALUES (?, ?, ?)',
                       (operation_id, request, json.dumps(asdict(receipt))))
            return receipt
