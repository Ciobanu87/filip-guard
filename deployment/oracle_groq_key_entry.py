#!/usr/bin/python3.11
"""Owner-only interactive Groq credential entry. No network, inference or activation."""
import fcntl
import getpass
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import resource
import stat
import subprocess
import sys
import tempfile
import warnings

CONFIG = Path('/etc/filip-guard')
KEY = CONFIG / 'secrets/groq-api-key'


def private_root(path, directory=False):
    info = path.lstat()
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or info.st_uid != 0 or info.st_mode & (0o022 if directory else 0o077)):
        raise ValueError('Unsafe operator configuration')
    if not directory and info.st_nlink != 1: raise ValueError('Unsafe configuration link')


def proposed_configuration(original):
    lines = original.splitlines()
    entries = [line.split('=', 1) for line in lines if line and not line.startswith('#') and '=' in line]
    names = [pair[0] for pair in entries]
    if len(names) != len(set(names)): raise ValueError('Duplicate runtime configuration')
    values = dict(entries)
    if values.get('FG_AI_AUTHORIZED') != '0' or values.get('FG_STATE_BACKUP_AUTHORIZED') != '0':
        raise ValueError('AI and backup must remain held')
    target = str(KEY)
    if 'FG_GROQ_API_KEY_FILE' in values and values['FG_GROQ_API_KEY_FILE'] != target:
        raise ValueError('Different existing credential reference')
    if any(values.get(name) for name in ('GROQ_API_KEY', 'FG_GROQ_API_KEY')):
        raise ValueError('Existing inline credential requires separate review')
    return original + ('' if original.endswith('\n') else '\n') + ('' if 'FG_GROQ_API_KEY_FILE' in values else 'FG_GROQ_API_KEY_FILE=' + target + '\n')


def validate_candidate(first, second):
    if not isinstance(first, str) or len(first) > 256 or not re.fullmatch(r'gsk_[A-Za-z0-9_-]{20,240}', first):
        raise ValueError('Unexpected key format; nothing installed')
    if not hmac.compare_digest(first.encode(), second.encode()):
        raise ValueError('Entries did not match; nothing installed')
    return first.encode('ascii')


def install_candidate(encoded, text, uid, gid, *, key_path=KEY, env_path=CONFIG / 'runtime.env'):
    # Exclusive creation: no key overwrite or rotation. Environment contains
    # only the file path; no secret is written to it, output or a subprocess.
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    temporary = None
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(encoded); output.flush(); os.fsync(output.fileno())
            os.fchown(output.fileno(), uid, gid); os.fchmod(output.fileno(), 0o400)
        fd, temporary = tempfile.mkstemp(prefix='.fg-groq-reference-', dir=env_path.parent)
        with os.fdopen(fd, 'w') as output:
            output.write(text); output.flush(); os.fsync(output.fileno()); os.fchmod(output.fileno(), 0o600)
        os.replace(temporary, env_path); temporary = None
        directory = os.open(key_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except Exception:
        key_path.unlink(missing_ok=True)
        raise
    finally:
        if temporary: Path(temporary).unlink(missing_ok=True)


def main():
    if os.geteuid() != 0 or len(sys.argv) != 1 or not os.isatty(0) or not os.isatty(2):
        raise ValueError('Run with sudo from your private interactive SSH terminal; no arguments or redirected input')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); os.umask(0o077)
    private_root(CONFIG, directory=True); private_root(CONFIG / 'secrets', directory=True)
    private_root(CONFIG / 'runtime.env')
    # Hold the root-owned runtime inode while checking/inserting. Other
    # configuration operations remain operator-only and must be serialized.
    with open(CONFIG / 'runtime.env', 'r') as locked:
        fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
        text = proposed_configuration(locked.read())
        if KEY.exists() or KEY.is_symlink(): raise ValueError('Existing key is never overwritten')
        for unit in ('filip-guard-ui.service', 'filip-guard-worker.service', 'filip-guard-state-backup.timer'):
            result = subprocess.run(['/usr/bin/systemctl', 'is-active', unit], capture_output=True, text=True, timeout=10)
            if result.stdout.strip() != 'inactive': raise ValueError('Services must remain inactive')
        user = pwd.getpwnam('filipguard')
        print('Introdu cheia existenta de doua ori. Caracterele nu vor fi afisate. Nu se apeleaza Groq.', file=sys.stderr)
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            first = getpass.getpass('Cheie Groq: ')
            second = getpass.getpass('Repeta cheia: ')
        encoded = validate_candidate(first, second)
        del first, second
        install_candidate(encoded, text, user.pw_uid, user.pw_gid)
        del encoded
    print(json.dumps({'status': 'groq-candidate-installed-not-api-validated', 'file_mode': '0400',
                      'ai_enabled': False, 'groq_api_calls': 0, 'services_started': False}))


if __name__ == '__main__':
    try: main()
    except (Exception, KeyboardInterrupt):
        print('Introducere oprita; nicio activare. Nu transmite cheia in conversatie sau loguri.', file=sys.stderr)
        raise SystemExit(1)
