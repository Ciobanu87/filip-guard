"""Explicitly close SQLite test connections, including after failures."""
from contextlib import contextmanager
import sqlite3


@contextmanager
def test_db(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()
