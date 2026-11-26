"""Existing-host SSH hardening with timed rollback and controlled reboot proof.

Fixed root operations only; no key changes, public access, IAM, cloud resources,
application state initialization, external backup calls or AI inference.
"""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile

CONFIG = Path('/etc/ssh/sshd_config')
RECOVERY = Path('/etc/filip-guard/ssh-recovery')
RECEIPT = Path('/etc/filip-guard/host-install-receipt.json')
PROOF = Path('/srv/filip-guard/recovery/host-durability-proof.json')
TIMER = 'filip-guard-ssh-rollback.timer'
PREFIX = b'# FILIP GUARD verified host SSH policy\nPermitRootLogin no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPubkeyAuthentication yes\n'
ROLLBACK = '''import hashlib,json,os,subprocess,tempfile
from pathlib import Path
root=Path('/etc/filip-guard/ssh-recovery'); target=Path('/etc/ssh/sshd_config')
record=json.loads((root/'pending.json').read_text())
if record['status']=='pending' and hashlib.sha256(target.read_bytes()).hexdigest()==record['hardened_sha256']:
 data=(root/'sshd_config.before').read_bytes()
 if hashlib.sha256(data).hexdigest()!=record['original_sha256']:raise SystemExit(1)
 fd,name=tempfile.mkstemp(prefix='.fg-ssh-restore-',dir=target.parent)
 with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
 os.chmod(name,record['mode']);os.replace(name,target)
 subprocess.run(['/usr/sbin/restorecon','-F',str(target)],check=True,capture_output=True)
 subprocess.run(['/usr/sbin/sshd','-t'],check=True,capture_output=True)
 subprocess.run(['/usr/bin/systemctl','reload','sshd.service'],check=True,capture_output=True)
 record['status']='rolled-back'
 fd,name=tempfile.mkstemp(prefix='.fg-ssh-status-',dir=root)
 with os.fdopen(fd,'w') as out:json.dump(record,out);out.flush();os.fsync(out.fileno())
 os.chmod(name,0o600);os.replace(name,root/'pending.json')
'''


def call(args):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=25)


def private_regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1:
        raise ValueError('Root-controlled regular file required')
    return info


def atomic(path, data, mode=0o600):
    fd, name = tempfile.mkstemp(prefix='.fg-managed-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data); output.flush(); os.fsync(output.fileno())
        os.chmod(name, mode); os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


def settings(connection, user):
    values = connection.split()
    if len(values) != 4: raise ValueError('Actual SSH connection context required')
    client, unused, local, port = values
    ipaddress.ip_address(client); ipaddress.ip_address(local)
    if not port.isdecimal(): raise ValueError('Invalid SSH context')
    raw = call(['/usr/sbin/sshd', '-T', '-C', f'user={user},host={client},addr={client},laddr={local},lport={port}']).stdout
    return dict(line.split(None, 1) for line in raw.splitlines() if ' ' in line)


def verified(connection):
    root = settings(connection, 'root'); opc = settings(connection, 'opc')
    return (root.get('permitrootlogin') == 'no' and opc.get('pubkeyauthentication') == 'yes'
            and all(config.get('passwordauthentication') == 'no' and config.get('kbdinteractiveauthentication') == 'no'
                    for config in (root, opc)))


def apply(connection):
    private_regular(RECEIPT); private_regular(CONFIG)
    if RECOVERY.exists():
        info = RECOVERY.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('Untrusted recovery directory')
    else: RECOVERY.mkdir(mode=0o700)
    pending = RECOVERY / 'pending.json'
    if pending.exists():
        private_regular(pending); record = json.loads(pending.read_text())
        if record['status'] == 'confirmed' and verified(connection):
            return {'status': 'ssh-already-confirmed', 'root_login_disabled': True, 'server_modified': False}
        raise ValueError('Existing SSH recovery operation needs review')
    call(['/usr/sbin/sshd', '-t'])
    original = CONFIG.read_bytes(); mode = stat.S_IMODE(CONFIG.stat().st_mode)
    if len(original) > 256 * 1024: raise ValueError('Unexpected SSH configuration')
    hardened = PREFIX + original
    atomic(RECOVERY / 'sshd_config.before', original)
    atomic(RECOVERY / 'rollback.py', ROLLBACK.encode())
    record = {'status': 'pending', 'original_sha256': hashlib.sha256(original).hexdigest(),
              'hardened_sha256': hashlib.sha256(hardened).hexdigest(), 'mode': mode}
    atomic(pending, json.dumps(record).encode())
    # A fresh independent connection must cancel this root-controlled rollback.
    call(['/usr/bin/systemd-run', '--unit=filip-guard-ssh-rollback', '--on-active=5m',
          '--timer-property=AccuracySec=1s', '/usr/bin/python3', str(RECOVERY / 'rollback.py')])
    call(['/usr/bin/systemctl', 'is-active', TIMER])
    try:
        atomic(CONFIG, hardened, mode)
        call(['/usr/sbin/restorecon', '-F', str(CONFIG)])
        call(['/usr/sbin/sshd', '-t'])
        if not verified(connection): raise ValueError('Effective SSH policy did not match')
        call(['/usr/bin/systemctl', 'reload', 'sshd.service'])
    except Exception:
        # Restore locally while the original root operation/session is alive.
        atomic(CONFIG, original, mode); call(['/usr/sbin/restorecon', '-F', str(CONFIG)])
        call(['/usr/sbin/sshd', '-t']); call(['/usr/bin/systemctl', 'reload', 'sshd.service'])
        call(['/usr/bin/systemctl', 'stop', TIMER])
        record['status'] = 'rolled-back'; atomic(pending, json.dumps(record).encode())
        raise
    return {'status': 'ssh-hardened-pending-second-connection', 'root_login_disabled': True,
            'rollback_timer_active': True, 'server_modified': True}


def confirm(connection):
    private_regular(RECEIPT)
    pending = RECOVERY / 'pending.json'; private_regular(pending)
    record = json.loads(pending.read_text())
    if record['status'] not in ('pending', 'confirmed') or not verified(connection):
        raise ValueError('Independent pinned SSH policy verification failed')
    if hashlib.sha256(CONFIG.read_bytes()).hexdigest() != record['hardened_sha256']:
        raise ValueError('SSH configuration changed concurrently')
    if record['status'] == 'pending':
        call(['/usr/bin/systemctl', 'stop', TIMER])
        # Detect a rollback which raced with confirmation, never assert success.
        if not verified(connection) or hashlib.sha256(CONFIG.read_bytes()).hexdigest() != record['hardened_sha256']:
            raise ValueError('Rollback raced with verification')
        record['status'] = 'confirmed'; atomic(pending, json.dumps(record).encode())
    return {'status': 'ssh-hardening-confirmed', 'second_pinned_connection_verified': True,
            'root_login_disabled': True, 'password_authentication_disabled': True,
            'public_key_authentication_enabled': True, 'rollback_timer_cancelled': True}


def reboot(connection):
    confirm(connection); private_regular(RECEIPT)
    receipt = json.loads(RECEIPT.read_text())
    boot = hashlib.sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest()
    if boot != receipt['boot_id_sha256']:
        return {'status': 'reboot-already-observed', 'reboot_scheduled': False}
    # Record and honor an existing pending reboot; never reboot repeatedly.
    request = Path('/etc/filip-guard/reboot-request.json')
    if not request.exists():
        atomic(request, json.dumps({'boot_id_sha256': boot, 'source': receipt['commit']}).encode())
        call(['/usr/bin/systemd-run', '--unit=filip-guard-validation-reboot', '--on-active=5s',
              '--timer-property=AccuracySec=1s', '/usr/bin/systemctl', 'reboot'])
    return {'status': 'reboot-requested', 'reboot_scheduled': True}


def validate(connection):
    confirm(connection); private_regular(RECEIPT)
    receipt = json.loads(RECEIPT.read_text())
    rebooted = hashlib.sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest() != receipt['boot_id_sha256']
    if not rebooted or PROOF.is_symlink() or hashlib.sha256(PROOF.read_bytes()).hexdigest() != receipt['proof_sha256']:
        raise ValueError('Host reboot/durable proof not verified')
    # Validate original SQLite/ledger bytes without creating or opening any DB.
    state = Path('/srv/filip-guard/state'); digest = hashlib.sha256()
    for path in sorted(state.rglob('*')):
        if path.is_symlink(): raise ValueError('State symlink rejected')
        if path.is_file(): digest.update(str(path.relative_to(state)).encode()); digest.update(path.read_bytes())
    if digest.hexdigest() != receipt['state_digest']: raise ValueError('Original state changed')
    user = __import__('pwd').getpwnam('filipguard')
    for directory in (state, PROOF.parent):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != user.pw_uid or info.st_mode & 0o077:
            raise ValueError('Private persistent directory verification failed')
    for unit in ('filip-guard-ui.service', 'filip-guard-worker.service', 'filip-guard-state-backup.timer'):
        outcome = subprocess.run(['/usr/bin/systemctl', 'is-enabled', unit], capture_output=True, text=True, timeout=10)
        if outcome.stdout.strip() != 'disabled': raise ValueError('Unreviewed service activation')
    if call(['/usr/sbin/getenforce']).stdout.strip() != 'Enforcing': raise ValueError('SELinux must remain enforcing')
    call(['/usr/bin/systemctl', 'is-active', 'firewalld.service'])
    call(['/opt/filip-guard/.venv/bin/python', '-c', 'import requests,streamlit,bs4,cryptography,boto3'])
    return {'status': 'reboot-and-private-persistence-verified', 'reboot_observed': True,
            'root_login_disabled': True, 'second_pinned_connection_verified': True,
            'private_state_unchanged': True, 'durability_proof_survived': True,
            'selinux_enforcing': True, 'firewalld_active': True,
            'services_enabled': False, 'external_backup_enabled': False,
            'new_cloud_resources': 0, 'groq_calls': 0}


if __name__ == '__main__':
    try:
        if os.geteuid() != 0: raise ValueError('Authorized root operation required')
        operations = {'apply': apply, 'confirm': confirm, 'reboot': reboot, 'validate': validate}
        report = operations[sys.argv[1]](sys.argv[2])
    except Exception:
        print('{"status":"host-security-blocked-or-failed","phase":"security-configuration","server_may_be_modified":true}')
        raise SystemExit(1)
    print(json.dumps(report, sort_keys=True))
