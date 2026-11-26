"""Prepare inactive units and run a native unprivileged synthetic host drill.

No service start/enable, reboot, provider API, original state/key or AI mutation.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import signal
import stat
import subprocess
import sys
import tempfile
import time

CONFIG = Path('/etc/filip-guard')
STATE = Path('/srv/filip-guard/state')
UNITS = {'filip-guard-ui.service', 'filip-guard-worker.service'}
PHASE = 'authorization'


def call(args, timeout=30, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True, **kwargs)


def current_unit(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1:
        raise ValueError('Root-controlled installed unit required')
    return path.read_bytes()


def unchanged_state():
    digest = hashlib.sha256()
    for path in sorted(STATE.rglob('*')):
        if path.is_symlink(): raise ValueError('Unreviewed state symlink')
        if path.is_file():
            digest.update(str(path.relative_to(STATE)).encode()); digest.update(path.read_bytes())
    return digest.digest()


def state_of_units():
    for unit in sorted(UNITS | {'filip-guard-state-backup.service', 'filip-guard-state-backup.timer'}):
        enabled = subprocess.run(['/usr/bin/systemctl', 'is-enabled', unit], capture_output=True, text=True, timeout=10)
        active = subprocess.run(['/usr/bin/systemctl', 'is-active', unit], capture_output=True, text=True, timeout=10)
        if enabled.stdout.strip() not in ('disabled', 'static') or active.stdout.strip() != 'inactive':
            raise ValueError('All gated services must remain disabled and inactive')


def app_pids(uid):
    result = []
    for path in Path('/proc').iterdir():
        if path.name.isdecimal():
            try:
                if path.stat().st_uid == uid: result.append(int(path.name))
            except FileNotFoundError: pass
    return result


def atomic(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.fg-unit-preparation-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data); output.flush(); os.fsync(output.fileno())
        os.chmod(temporary, 0o644); os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def prepare_units(data):
    if set(data['units']) != UNITS or set(data['previous_sha256']) != UNITS:
        raise ValueError('Only the two fixed inactive runtime units may change')
    originals = {}
    for name, text in data['units'].items():
        path = Path('/etc/systemd/system') / name
        original = current_unit(path); desired = text.encode()
        if hashlib.sha256(original).hexdigest() != data['previous_sha256'][name] and original != desired:
            raise ValueError('Installed unit changed; no overwrite')
        required = ('ConditionPathExists=/etc/filip-guard/host-approval.json',
                    'ExecCondition=/opt/filip-guard/.venv/bin/python /opt/filip-guard/operations_host_gate.py',
                    'NoNewPrivileges=true', 'ProtectSystem=strict', 'ProtectHome=true', 'KillMode=control-group',
                    'StartLimitIntervalSec=300', 'StartLimitBurst=3', 'CapabilityBoundingSet=',
                    'Environment=HOME=/var/cache/filip-guard')
        if any(value not in text for value in required): raise ValueError('Existing protections must be preserved')
        originals[path] = original
    try:
        for path in originals:
            atomic(path, data['units'][path.name].encode())
        call(['/usr/bin/systemd-analyze', 'verify', *map(str, originals)])
        call(['/usr/bin/systemctl', 'daemon-reload'])
    except Exception:
        for path, original in originals.items(): atomic(path, original)
        call(['/usr/bin/systemctl', 'daemon-reload'])
        raise


def run_disposable_harness(source, uid):
    if len(source) > 65536 or app_pids(uid): raise ValueError('No unrelated app-user processes may run')
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/var/cache/filip-guard',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/opt/filip-guard',
           'FG_DISPOSABLE_HOST_VALIDATION': '1', 'FG_VALIDATION_CODE_ROOT': '/opt/filip-guard',
           'FG_AI_AUTHORIZED': '0', 'FG_EMAIL_AUTHORIZED': '0', 'FG_STATE_BACKUP_AUTHORIZED': '0'}
    command = ['/usr/sbin/runuser', '-u', 'filipguard', '--', '/usr/bin/env', '-i',
               *[key + '=' + value for key, value in env.items()], '/opt/filip-guard/.venv/bin/python', '-c', source]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        output, errors = process.communicate(timeout=150)
        if process.returncode or len(output) > 4096: raise ValueError('Isolated native validation failed')
        return json.loads(output)
    finally:
        if process.poll() is None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=10)
        # Before the drill this dedicated uid had no processes, so leftovers can
        # only belong to this authorized disposable process tree. Fence them.
        for pid in app_pids(uid):
            try: os.kill(pid, signal.SIGTERM)
            except ProcessLookupError: pass
        for unused in range(10):
            if not app_pids(uid): break
            time.sleep(0.2)
        for pid in app_pids(uid):
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass


def main():
    global PHASE
    if os.geteuid() != 0: raise ValueError('Authorized host preparation requires root')
    raw = sys.stdin.buffer.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024: raise ValueError('Preparation payload too large')
    data = json.loads(raw)
    receipt = json.loads((CONFIG / 'host-install-receipt.json').read_text())
    if receipt['evidence_sha256'] != data['evidence_sha256']: raise ValueError('Different approved host')
    if json.loads((CONFIG / 'ssh-recovery/pending.json').read_text())['status'] != 'confirmed':
        raise ValueError('Existing hardening must remain confirmed')
    state_of_units(); before = unchanged_state()
    user = pwd.getpwnam('filipguard')
    if app_pids(user.pw_uid): raise ValueError('Unexpected active app-user process')
    PHASE = 'inactive-systemd-units'; prepare_units(data)
    PHASE = 'nonroot-render-and-loopback-health'
    checks = run_disposable_harness(data['harness'], user.pw_uid)
    required = {'tenant_boundaries_verified', 'state_reopened_in_fresh_process', 'single_multiprocess_claim',
                'stale_lease_rejected', 'sqlite_sigkill_recovery_verified', 'idle_worker_heartbeat_advanced',
                'worker_sigterm_exit_clean', 'restore_hold_enforced', 'missing_state_not_recreated',
                'fixture_permissions_private'}
    if checks.get('status') != 'native-host-isolated-readiness-verified' or any(checks.get(key) is not True for key in required):
        raise ValueError('Native host isolation/stability proof incomplete')
    if any(checks.get(key) != 0 for key in ('provider_requests', 'groq_calls', 'master_key_operations')) or checks.get('production_state_accessed') is not False:
        raise ValueError('Unexpected live action')
    if unchanged_state() != before: raise ValueError('Persistent production state changed')
    state_of_units()
    if app_pids(user.pw_uid): raise ValueError('Disposable child process remains')
    # Verify the installed activation gate still refuses the held environment.
    gate = subprocess.run(['/opt/filip-guard/.venv/bin/python', '/opt/filip-guard/operations_host_gate.py'],
                          capture_output=True, text=True, timeout=15, env={'PATH': '/usr/bin:/bin'})
    if gate.returncode != 1 or json.loads(gate.stdout).get('activation_authorized') is not False:
        raise ValueError('Activation hold was not enforced')
    result = {**checks, 'inactive_units_prepared': True, 'original_state_unchanged': True,
              'activation_gate_still_blocks': True, 'services_enabled': False, 'temporary_processes_cleaned': True}
    record = CONFIG / 'operations-readiness-receipt.json'
    fd, temporary = tempfile.mkstemp(prefix='.fg-readiness-receipt-', dir=CONFIG)
    with os.fdopen(fd, 'w') as output:
        json.dump({'validation_source_sha256': hashlib.sha256(data['harness'].encode()).hexdigest(), **result}, output, sort_keys=True)
        output.flush(); os.fsync(output.fileno())
    os.chmod(temporary, 0o600); os.replace(temporary, record)
    return result


if __name__ == '__main__':
    try: report = main()
    except Exception:
        print(json.dumps({'status': 'operations-readiness-unverified', 'phase': PHASE,
                          'services_enabled': False, 'provider_requests': 0, 'groq_calls': 0})); raise SystemExit(1)
    print(json.dumps(report, sort_keys=True))
