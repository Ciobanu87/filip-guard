"""Existing B2 mount only. Input values never appear in argv/stdout/artifacts."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tempfile

CONFIG = Path('/etc/filip-guard')


def main():
    if os.geteuid() != 0: raise ValueError('Explicit host setup requires root')
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192: raise ValueError('Bounded private input required')
    data = json.loads(raw)
    installed = json.loads((CONFIG / 'host-install-receipt.json').read_text())
    if installed['evidence_sha256'] != data['evidence_sha256']: raise ValueError('Wrong verified deployment')
    if json.loads((CONFIG / 'ssh-recovery/pending.json').read_text())['status'] != 'confirmed':
        raise ValueError('Verified SSH hardening required')
    # This is configuration only; persistent/customer/AI state is never opened.
    user = pwd.getpwnam('filipguard')
    directory = CONFIG / 'secrets'
    if directory.is_symlink(): raise ValueError('Unsafe credential directory')
    if directory.exists():
        info = directory.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Root-controlled credential directory required')
    else:
        directory.mkdir(mode=0o711); os.chmod(directory, 0o711)
    path = directory / 's3.json'
    encoded = json.dumps(data['credentials'], sort_keys=True).encode()
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != user.pw_uid
                or stat.S_IMODE(info.st_mode) != 0o400 or not hmac.compare_digest(path.read_bytes(), encoded)):
            raise ValueError('Existing credentials are not replaced')
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, 'wb') as output:
            output.write(encoded); output.flush(); os.fsync(output.fileno())
            os.fchown(output.fileno(), user.pw_uid, user.pw_gid)
    env_path = CONFIG / 'runtime.env'
    info = env_path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('Private root configuration required')
    original = env_path.read_text()
    additions = {'FG_GUARD_S3_ENDPOINT': data['endpoint'], 'FG_GUARD_S3_BUCKET': data['bucket'],
                 'FG_GUARD_S3_REGION': data['region']}
    existing = dict(line.split('=', 1) for line in original.splitlines() if '=' in line and not line.startswith('#'))
    if existing.get('FG_STATE_BACKUP_AUTHORIZED') != '0': raise ValueError('Backup authorization must remain off')
    for key, value in additions.items():
        if key in existing and existing[key] != value: raise ValueError('Existing provider settings are not replaced')
    text = original + ''.join(key + '=' + value + '\n' for key, value in additions.items() if key not in existing)
    if text != original:
        fd, temporary = tempfile.mkstemp(prefix='.fg-provider-config-', dir=CONFIG)
        with os.fdopen(fd, 'w') as output:
            output.write(text); output.flush(); os.fsync(output.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, env_path)
    # Construct the existing explicit-credential SDK adapter as the app user.
    # Its constructor does NOT issue a network request or discover ambient keys.
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/var/cache/filip-guard',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/opt/filip-guard',
           'FG_GUARD_S3_SECRET_SOURCE': 'file', 'FG_GUARD_S3_CREDENTIALS_FILE': str(path), **additions}
    command = ['/usr/sbin/runuser', '-u', 'filipguard', '--', '/usr/bin/env', '-i',
               *[key + '=' + value for key, value in env.items()], '/opt/filip-guard/.venv/bin/python', '-c',
               'from infrastructure_configuration import configured_external_store; configured_external_store()']
    subprocess.run(command, capture_output=True, timeout=40, check=True)
    for unit in ('filip-guard-state-backup.timer', 'filip-guard-state-backup.service'):
        result = subprocess.run(['/usr/bin/systemctl', 'is-enabled', unit], capture_output=True, text=True, timeout=10)
        if result.stdout.strip() not in ('disabled', 'static'): raise ValueError('Unreviewed timer activation')
    return {'status': 'existing-b2-config-mounted-inactive', 'credential_mode_0400': True,
            'credential_owner_is_app': True, 'nonroot_adapter_constructed': True,
            'network_requests': 0, 'uploads': 0, 'backup_timer_enabled': False,
            'master_key_generated': False, 'ai_ledger_initialized': False, 'groq_calls': 0}


if __name__ == '__main__':
    try: report = main()
    except Exception:
        print('{"status":"host-b2-mount-unverified","phase":"security-configuration"}'); raise SystemExit(1)
    print(json.dumps(report, sort_keys=True))
