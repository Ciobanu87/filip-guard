"""Prepared host-only daily backup. Disabled until explicit reviewed approval.

Stops only the two named service cgroups; rejects other runtime-user processes.
Uses the existing encrypt/upload/download/decrypt/restore verifier. No key creation,
AI calls, state initialization, remote deletion, restore/resume or mail sending.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import tempfile
import uuid

from operations_host_gate import CODE, STATE, RECOVERY, MAX_OBJECT_BYTES, host_gate, read_root_file

UNITS = ('filip-guard-ui.service', 'filip-guard-worker.service')
QUOTA = Path('/etc/filip-guard/backup-reservations.json')


def reserve_attempt(approval, now=None):
    """Conservative durable reservation: unknown/failed writes are never refunded."""
    now = now or datetime.now(timezone.utc)
    data = json.loads(read_root_file(QUOTA))
    if type(data) is not dict or set(data) != {'schema', 'attempts'} or data['schema'] != 1 or type(data['attempts']) is not list or len(data['attempts']) >= 10000:
        raise ValueError('Existing backup reservation journal required')
    current = []
    for attempt in data['attempts']:
        if type(attempt) is not dict or set(attempt) != {'at', 'bytes'} or attempt['bytes'] != MAX_OBJECT_BYTES:
            raise ValueError('Invalid reservation history')
        at = datetime.fromisoformat(attempt['at'])
        if at.tzinfo is None or at > now:
            raise ValueError('Invalid reservation time')
        if at.date() == now.date():
            raise ValueError('Daily backup attempt already reserved')
        if at >= datetime.fromisoformat(approval['reviewed_at']):
            current.append(at)
    if len(current) >= 7 or (len(current) + 1) * MAX_OBJECT_BYTES > approval['b2_free_remaining_bytes']:
        raise ValueError('Reviewed external backup allowance exhausted')
    data['attempts'].append({'at': now.isoformat(), 'bytes': MAX_OBJECT_BYTES})
    fd, temporary = tempfile.mkstemp(prefix='.backup-reservation-', dir=QUOTA.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(data, output); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, QUOTA)
        directory = os.open(QUOTA.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def control(action, unit):
    if unit not in UNITS or action not in ('status', 'stop', 'start'):
        raise ValueError('Unreviewed service command')
    if action == 'status':
        result = subprocess.run(['systemctl', 'show', unit, '--property=LoadState,ActiveState', '--no-pager'],
                                capture_output=True, text=True, timeout=15, check=True)
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if values.get('LoadState') != 'loaded' or values.get('ActiveState') not in ('active', 'inactive'):
            raise ValueError('Service absent or transitioning')
        return values['ActiveState']
    subprocess.run(['systemctl', action, unit], capture_output=True, timeout=100, check=True)


def no_other_writers():
    uid = pwd.getpwnam('filipguard').pw_uid
    for process in Path('/proc').iterdir():
        if process.name.isdecimal():
            try:
                if process.stat().st_uid == uid:
                    raise ValueError('Unexpected runtime-user process; backup remains blocked')
            except FileNotFoundError:
                pass


def backup_cycle(service_control, export, check_writers):
    previous = {unit: service_control('status', unit) for unit in UNITS}
    touched = []
    error = None
    try:
        for unit in UNITS:
            if previous[unit] == 'active':
                # Include an attempted stop: a timeout can occur after success.
                touched.append(unit)
                service_control('stop', unit)
        if any(service_control('status', unit) != 'inactive' for unit in UNITS):
            raise ValueError('Writers did not stop')
        check_writers()
        export()
    except Exception as exc:
        error = exc
    finally:
        failures = []
        for unit in reversed(touched):
            try:
                if service_control('status', unit) != 'active':
                    service_control('start', unit)
                if service_control('status', unit) != 'active':
                    raise ValueError('Service failed to resume')
            except Exception:
                failures.append(unit)
        if failures:
            raise RuntimeError('Service resume needs operator review') from None
    if error is not None:
        raise error


def run_export_command(command):
    # A subprocess timeout must not leave runuser's Python child exporting while
    # the UI resumes. The entire dedicated process group is fenced on all exits.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    try:
        process.communicate(timeout=240)
        if process.returncode:
            raise ValueError('Encrypted recovery exporter failed')
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate(timeout=15)


def run_backup():
    approval = host_gate()
    if os.geteuid() != 0 or os.environ.get('FG_STATE_BACKUP_AUTHORIZED') != '1':
        raise ValueError('Reviewed root-level backup authorization required')
    if not re.fullmatch('[0-9a-f]{32}', os.environ.get('FG_DEPLOYMENT_ID', '')):
        raise ValueError('Existing deployment identifier required')
    # Validate private state, recovery receipts, configuration and externally kept
    # keys BEFORE pausing writers. Never initialize a missing AI ledger/database.
    from application_state_backup import _root
    from runtime_state import require_existing_guard_state
    from infrastructure_configuration import configured_external_store
    from operator_secrets import configured_master_keys, private_file
    _root(STATE); _root(RECOVERY)
    if RECOVERY.is_relative_to(STATE): raise ValueError('Receipts must be outside snapshot')
    require_existing_guard_state(os.environ)
    if not (STATE / 'advisor.sqlite').is_file():
        raise ValueError('Preserved AI ledger required; no initialization permitted')
    configured_master_keys(); configured_external_store()
    # These checks construct adapters/read explicit configuration, not network.
    # The child runs as the application user and repeats private-file validation.
    manifest = RECOVERY / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex + '.json')
    def export():
        run_export_command(['runuser', '-u', 'filipguard', '--', str(CODE / '.venv/bin/python'),
                        str(CODE / 'operations_state_backup.py'), 'export',
                        '--authorized-external-access', '--writers-stopped', '--root', str(STATE),
                        '--deployment-id', os.environ['FG_DEPLOYMENT_ID'], '--manifest', str(manifest)])
        receipt = json.loads(private_file(manifest, 8192))
        from application_state_backup import _manifest
        _manifest(receipt)
        if receipt['deployment_id'] != os.environ['FG_DEPLOYMENT_ID']:
            raise ValueError('Unexpected backup receipt')
    fd = os.open('/run/filip-guard-backup.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reserve_attempt(approval)
        backup_cycle(control, export, no_other_writers)
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if not args.execute:
        print('{"status":"prepared-only","server_modified":false,"network_requests":0}')
        return 0
    try:
        run_backup()
    except Exception:
        print('{"status":"blocked-or-failed","verified":false,"operator_review_required":true}')
        return 1
    print('{"status":"verified","encrypted_readback_recovery":true,"groq_calls":0}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
