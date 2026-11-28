"""Allowlisted private systemd event, with no customer text or credentials."""
import hashlib
import json
import os


def record(kind,state,reference='provider'):
    if os.environ.get('FG_OPERATOR_EVENTS')!='1':return
    if kind not in ('autofix','rollback','ai','backup') or state not in ('failed','verified'):raise ValueError('Unsupported operator event')
    # stderr/stdout are captured by systemd; no new customer-state database.
    try:print(json.dumps({'fg_operator_event':1,'kind':kind,'state':state,
        'reference':hashlib.sha256(str(reference).encode()).hexdigest()},separators=(',',':')),flush=True)
    except (OSError,ValueError):
        # Do not mask an original AutoFix failure or enable a replay. A broken
        # service journal/observer is detected by the independent heartbeat.
        return
