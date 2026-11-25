"""Read-only checks before opening existing deployment state.

Runtime startup must not bootstrap a missing/partial volume. Explicit first-time
provisioning remains in operations_guard_setup; these checks create no files.
"""
import os
from pathlib import Path
import sqlite3
import stat


AUTH_TABLES = {'customers', 'customer_sessions', 'login_attempts'}
SITE_TABLES = {'customer_sites'}
MONITOR_TABLES = {'monitor_schedules', 'monitor_runs', 'monitor_findings',
                  'monitor_notifications', 'monitor_email_outbox'}


def require_existing_database(path, tables):
    path = Path(path)
    try:
        if path.is_symlink():
            raise ValueError('Existing private application state required')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size == 0:
            raise ValueError('Existing private application state required')
        if any((parent / 'FG-RESTORE-REVIEW-REQUIRED').exists() for parent in path.absolute().parents):
            raise ValueError('Recovered state requires operator reconciliation')
        # mode=ro is essential: SQLite's default mode can create a missing DB.
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as db:
            present = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not set(tables).issubset(present):
                raise ValueError('Existing application state is incomplete')
            if db.execute('PRAGMA quick_check(1)').fetchone() != ('ok',):
                raise ValueError('Existing application state is corrupt')
    except (OSError, sqlite3.Error):
        raise ValueError('Existing private application state unavailable; restore before startup') from None
    return str(path)


def require_existing_guard_state(environ=None):
    env = os.environ if environ is None else environ
    paths = (env['FG_CUSTOMER_AUTH_DB'], str(Path(env['FG_CUSTOMER_DATA_ROOT']) / 'sites.sqlite'),
             env['FG_MONITOR_DB'])
    if len({Path(path).resolve() for path in paths}) != len(paths):
        raise ValueError('Separate account, ownership and monitoring databases required')
    for path, tables in zip(paths, (AUTH_TABLES, SITE_TABLES, MONITOR_TABLES)):
        require_existing_database(path, tables)
    return paths
