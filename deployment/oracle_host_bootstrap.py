"""Root host-only setup, delivered through pinned SSH after owner verification.

Uses only the existing boot disk, official OS repos and PyPI. No OCI resource
API, original-state initialization, key generation, external backup or AI calls.
"""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request

CODE = Path('/opt/filip-guard')
CONFIG = Path('/etc/filip-guard')
BASE = Path('/srv/filip-guard')
STATE = BASE / 'state'
RECOVERY = BASE / 'recovery'
CACHE = Path('/var/cache/filip-guard')
PHASE = 'authorization'


def call(args, *, timeout=90, env=None):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True, env=env)


def safe_directory(path, mode=0o755, uid=0, gid=0):
    path = Path(path)
    for parent in reversed(path.parents):
        if parent.is_symlink() or not parent.is_dir(): raise ValueError('Unsafe ancestor')
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022: raise ValueError('Untrusted ancestor')
    if path.is_symlink(): raise ValueError('Symlink directory rejected')
    if path.exists():
        info = path.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
            raise ValueError('Existing directory ownership/permissions conflict')
        if mode == 0o700 and info.st_mode & 0o077: raise ValueError('Existing private directory must be private')
    else:
        path.mkdir(mode=mode)
        os.chown(path, uid, gid)
    return path


def write_new(path, data, mode=0o600, uid=0, gid=0):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as output:
        output.write(data); output.flush(); os.fsync(output.fileno())
        os.fchown(output.fileno(), uid, gid)


def archive_entries(data):
    if len(data) > 16 * 1024 * 1024: raise ValueError('Oversized source archive')
    result = {}; total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or not path.parts or any(part in ('.', '..', '.git', '.venv') for part in path.parts)
                    or len(member.name) > 240 or not re.fullmatch(r'[A-Za-z0-9_./-]+', member.name)):
                raise ValueError('Unreviewed source path')
            if member.isdir(): continue
            if not member.isfile() or member.name in result or member.size > 2 * 1024 * 1024:
                raise ValueError('Only unique bounded regular source files allowed')
            total += member.size
            if total > 16 * 1024 * 1024 or len(result) >= 1024: raise ValueError('Source bound reached')
            result[member.name] = archive.extractfile(member).read()
    if not {'app.py', 'requirements.txt', 'operations_host_gate.py'} <= result.keys():
        raise ValueError('Incomplete source snapshot')
    return result


def private_state_digest():
    digest = hashlib.sha256()
    for path in sorted(STATE.rglob('*')):
        if path.is_symlink(): raise ValueError('Unreviewed state symlink')
        if path.is_file():
            digest.update(str(path.relative_to(STATE)).encode()); digest.update(path.read_bytes())
    return digest.hexdigest()


def runtime_env(user):
    return {'PATH': '/usr/bin:/bin', 'HOME': str(CACHE), 'LANG': 'C.UTF-8',
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(CODE),
            'FG_AI_AUTHORIZED': '0', 'FG_EMAIL_AUTHORIZED': '0',
            'FG_CUSTOMER_REGISTRATION': '0', 'FG_GUARD_TEST_UI': '0'}


def nonroot(command, user):
    env = runtime_env(user)
    return ['/usr/sbin/runuser', '-u', 'filipguard', '--', '/usr/bin/env', '-i',
            *[key + '=' + value for key, value in env.items()], *command]


def validate_runtime(user):
    python = str(CODE / '.venv/bin/python')
    call(nonroot([python, '-c', 'import requests,streamlit,bs4,cryptography,boto3'], user), timeout=60)
    appcheck = ("from streamlit.testing.v1 import AppTest; "
                "app=AppTest.from_file('/opt/filip-guard/app.py').run(timeout=45); "
                "assert not app.exception; assert any('FILIP GUARD' in item.value for item in app.title)")
    call(nonroot([python, '-c', appcheck], user), timeout=75)
    # A temporary nonroot health process only, with no account/ledger paths.
    # No service is enabled and no public socket is opened.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
    command = nonroot([python, '-m', 'streamlit', 'run', str(CODE / 'app.py'),
                        '--server.address=127.0.0.1', '--server.port=' + str(port),
                        '--server.headless=true', '--browser.gatherUsageStats=false'], user)
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                               cwd=CODE)
    healthy = False
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for unused in range(30):
            if process.poll() is not None: break
            try:
                with opener.open('http://127.0.0.1:' + str(port) + '/_stcore/health', timeout=1) as response:
                    healthy = response.status == 200 and response.read(32).strip() == b'ok'
                if healthy: break
            except Exception:
                time.sleep(1)
    finally:
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
    if not healthy: raise ValueError('Private runtime health check failed')


def bootstrap(commit, archive_digest, evidence_digest, source):
    global PHASE
    if os.geteuid() != 0 or not re.fullmatch('[0-9a-f]{40}', commit): raise ValueError('Explicit root source snapshot required')
    if not all(re.fullmatch('[0-9a-f]{64}', value) for value in (archive_digest, evidence_digest)):
        raise ValueError('Source/evidence digest required')
    if hashlib.sha256(source).hexdigest() != archive_digest: raise ValueError('Source integrity mismatch')
    entries = archive_entries(source)
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if os.uname().machine != 'aarch64' or release.get('ID', '').strip('"') != 'ol':
        raise ValueError('Unexpected existing host')
    fs = os.statvfs('/opt')
    if fs.f_bavail * fs.f_frsize < 4 * 1024**3: raise ValueError('Insufficient existing disk headroom')
    marker = CODE / '.fg-bootstrap-source.json'
    receipt = {'commit': commit, 'archive_sha256': archive_digest, 'evidence_sha256': evidence_digest}
    PHASE = 'source-layout'
    if CODE.exists():
        safe_directory(CODE)
        if marker.is_symlink() or not marker.is_file() or json.loads(marker.read_text()) != receipt:
            raise ValueError('Unmanaged or different source deployment; no overwrite authorized')
    else:
        safe_directory(CODE)
        write_new(marker, json.dumps(receipt, sort_keys=True).encode())
    for name, data in entries.items():
        path = CODE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if any(parent.is_symlink() for parent in (path, *path.parents)): raise ValueError('Unsafe source ancestor')
        if path.exists():
            if path.read_bytes() != data: raise ValueError('Existing source changed; do not overwrite')
        else:
            write_new(path, data, mode=0o644)
    PHASE = 'official-python-packages'
    call(['/usr/bin/dnf', '-y', '--disablerepo=*', '--enablerepo=ol9_baseos_latest',
          '--enablerepo=ol9_appstream', '--setopt=gpgcheck=1', 'install', 'python3.11', 'python3.11-pip'], timeout=360)
    PHASE = 'isolated-python-environment'
    if (CODE / '.venv').is_symlink(): raise ValueError('Unreviewed virtual environment')
    call(['/usr/bin/python3.11', '-m', 'venv', str(CODE / '.venv')])
    pip_env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PIP_CONFIG_FILE': '/dev/null',
               'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PIP_NO_CACHE_DIR': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    call([str(CODE / '.venv/bin/python'), '-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple',
          '-r', str(CODE / 'requirements.txt')], timeout=360, env=pip_env)
    PHASE = 'private-system-user-and-storage'
    try:
        user = pwd.getpwnam('filipguard')
        if user.pw_shell != '/usr/sbin/nologin' or user.pw_uid == 0: raise ValueError('Existing user conflicts')
    except KeyError:
        call(['/usr/sbin/useradd', '--system', '--user-group', '--home-dir', '/nonexistent',
              '--no-create-home', '--shell', '/usr/sbin/nologin', 'filipguard'])
        user = pwd.getpwnam('filipguard')
    safe_directory(CONFIG); safe_directory(BASE)
    safe_directory(STATE, 0o700, user.pw_uid, user.pw_gid)
    safe_directory(RECOVERY, 0o700, user.pw_uid, user.pw_gid)
    safe_directory(CACHE, 0o700, user.pw_uid, user.pw_gid)
    existing_state = private_state_digest()
    config_file = CONFIG / 'runtime.env'
    data = entries['deployment/oracle-prepared/runtime.env.example']
    if config_file.exists():
        if config_file.is_symlink() or config_file.read_bytes() != data: raise ValueError('Existing config not overwritten')
    else: write_new(config_file, data)
    PHASE = 'inactive-systemd-units'
    units = []
    for name in ('filip-guard-ui.service', 'filip-guard-worker.service', 'filip-guard-state-backup.service', 'filip-guard-state-backup.timer'):
        path = Path('/etc/systemd/system') / name
        data = entries['deployment/oracle-prepared/' + name + '.example']
        if path.exists() or path.is_symlink():
            if path.is_symlink() or path.read_bytes() != data: raise ValueError('Existing unit not overwritten')
        else: write_new(path, data, mode=0o644)
        units.append(str(path))
    call(['/usr/bin/systemd-analyze', 'verify', *units])
    call(['/usr/bin/systemctl', 'daemon-reload'])
    for path in units:
        state = subprocess.run(['/usr/bin/systemctl', 'is-enabled', Path(path).name], capture_output=True, text=True, timeout=10)
        if state.stdout.strip() not in ('disabled', 'static'): raise ValueError('Unexpected enabled service')
    PHASE = 'nonroot-render-and-loopback-health'
    validate_runtime(user)
    if private_state_digest() != existing_state: raise ValueError('Persistent application state changed during host probe')
    PHASE = 'durable-host-receipt'
    proof = RECOVERY / 'host-durability-proof.json'
    proof_data = json.dumps({'scope': 'host-durability-probe', 'source': commit, 'evidence_sha256': evidence_digest}, sort_keys=True).encode()
    if proof.exists():
        if proof.is_symlink() or proof.read_bytes() != proof_data: raise ValueError('Existing durability proof conflicts')
    else: write_new(proof, proof_data, uid=user.pw_uid, gid=user.pw_gid)
    final = {**receipt, 'boot_id_sha256': hashlib.sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest(),
             'state_digest': existing_state, 'proof_sha256': hashlib.sha256(proof_data).hexdigest()}
    final_path = CONFIG / 'host-install-receipt.json'
    if not final_path.exists(): write_new(final_path, json.dumps(final, sort_keys=True).encode())
    return {'status': 'host-runtime-prepared', 'server_modified': True, 'source_snapshot_verified': True,
            'python311_installed': True, 'dependencies_imported_as_nonroot': True,
            'public_scanner_ui_render_verified': True, 'loopback_health_verified': True,
            'persistent_state_unchanged': True, 'services_enabled': False, 'external_backup_enabled': False,
            'customer_state_initialized': False, 'ai_ledger_initialized': False, 'new_cloud_resources': 0, 'groq_calls': 0}


if __name__ == '__main__':
    try:
        source = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        report = bootstrap(sys.argv[1], sys.argv[2], sys.argv[3], source)
    except Exception:
        print(json.dumps({'status': 'host-setup-blocked-or-failed', 'phase': PHASE,
                          'server_may_be_modified': True, 'groq_calls': 0})); raise SystemExit(1)
    print(json.dumps(report, sort_keys=True))
