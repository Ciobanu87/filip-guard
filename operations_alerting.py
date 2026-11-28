"""Private operator incident latch and bounded Healthchecks-only transport.

No inference, customer notification, WordPress write or backup upload is performed.
No exception, customer identifier, URL token or response body is logged/exported.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

KINDS={'autofix','rollback','ai','backup','worker','service','observer'}


def private_directory(path):
    path=Path(path)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode&0o077:raise ValueError('Private operations directory required')
    return path


class Incidents:
    def __init__(self,directory):
        self.path=private_directory(directory)/'incidents.sqlite'
        if self.path.is_symlink():raise ValueError('Unsafe journal')
        old=os.umask(0o077)
        try:
            with self.db() as db:
                db.executescript('''CREATE TABLE IF NOT EXISTS incidents (
                  source TEXT PRIMARY KEY,kind TEXT NOT NULL,observed REAL NOT NULL,
                  active INTEGER NOT NULL,confirmed REAL,evidence TEXT);
                  CREATE TABLE IF NOT EXISTS restarts (unit TEXT,at REAL NOT NULL);
                  CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY,value TEXT);''')
        finally:os.umask(old)
        if self.path.stat().st_mode&0o077:raise ValueError('Unsafe journal permissions')

    def db(self):return sqlite3.connect(self.path,timeout=3)

    def fail(self,kind,source,observed):
        if kind not in KINDS or type(source) is not str or not re.fullmatch('[0-9a-f]{64}',source) or not 0<=observed<1e12:raise ValueError('Invalid incident')
        with self.db() as db:
            db.execute('''INSERT INTO incidents VALUES (?,?,?,1,NULL,NULL)
             ON CONFLICT(source) DO UPDATE SET observed=max(observed,excluded.observed),
             active=CASE WHEN excluded.observed>coalesce(confirmed,-1) THEN 1 ELSE active END''',(source,kind,observed))

    def confirm(self,source,evidence,now):
        if not re.fullmatch('[0-9a-f]{64}',source) or not re.fullmatch('[0-9a-f]{64}',evidence):raise ValueError('Verified evidence digest required')
        with self.db() as db:
            row=db.execute('SELECT observed FROM incidents WHERE source=?',(source,)).fetchone()
            if not row or now<row[0]:raise ValueError('Recovery must follow incident')
            db.execute('UPDATE incidents SET active=0,confirmed=?,evidence=? WHERE source=?',(now,evidence,source))

    def active(self):
        with self.db() as db:return db.execute('SELECT source,kind,observed FROM incidents WHERE active=1 ORDER BY observed,source').fetchall()

    def reserve_restart(self,unit,now):
        if unit!='filip-guard-worker.service':raise ValueError('Only read-only worker recovery is allowed')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM restarts WHERE at>?',(now-3600,)).fetchone()[0]>=2:return False
            db.execute('INSERT INTO restarts VALUES (?,?)',(unit,now));return True


def opaque(*parts):return hashlib.sha256('\0'.join(map(str,parts)).encode()).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def endpoint(value):
    # Exact official ingestion host only; no ports, query strings or redirects.
    if not isinstance(value,str) or not re.fullmatch(r'https://hc-ping\.com/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',value):
        raise ValueError('Private Healthchecks UUID endpoint required')
    return value


def ping(url,failed=False,*,opener=None,sleep=time.sleep):
    url=endpoint(url)+('/fail' if failed else '')
    opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    # Empty payload: no customer details, event identifiers, traces or secrets.
    request=urllib.request.Request(url,data=b'',method='POST',headers={'User-Agent':'FILIP-GUARD-operator-monitor/1'})
    for attempt in range(2):
        try:
            with opener.open(request,timeout=5) as response:
                if response.status!=200 or response.read(32)!=b'OK':raise ValueError('Ingestion not confirmed')
            return True
        except urllib.error.HTTPError as error:
            if error.code not in (429,500,502,503,504):return False
        except (OSError,ValueError):pass
        if attempt==0:sleep(1)
    return False


def emit(journal,host_url,incident_url,*,send=ping):
    # Aggregate incident success is impossible while ANY source remains active.
    failed=bool(journal.active())
    incident_ok=send(incident_url,failed)
    # Heartbeat is last: observer/collector/delivery failure becomes dead-man loss.
    host_ok=send(host_url,False) if incident_ok else False
    return dict(incident_delivery_confirmed=incident_ok,heartbeat_confirmed=host_ok,active_incidents=len(journal.active()))
