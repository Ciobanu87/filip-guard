"""Fail-closed host activation gate. No provisioning, credential access or network."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import stat

APPROVAL = Path('/etc/filip-guard/host-approval.json')
STATE = Path('/srv/filip-guard/state')
RECOVERY = Path('/srv/filip-guard/recovery')
CODE = Path('/opt/filip-guard')
MAX_OBJECT_BYTES = 48 * 1024 * 1024


def validate_approval(data, now=None):
    now = now or datetime.now(timezone.utc)
    if type(data) is not dict:
        raise ValueError('Account-level zero-cost approval required')
    for key in ('always_free_verified', 'installation_authorized', 'image_always_free',
                'volume_performance_always_free', 'all_regions_reviewed', 'b2_zero_spend_cap_verified'):
        if data.get(key) is not True:
            raise ValueError('Unverified activation prerequisite')
    if data.get('host') != '92.5.89.125' or data.get('home_region') != 'eu-frankfurt-1':
        raise ValueError('Approval does not cover this existing host')
    if (data.get('shape') != 'VM.Standard.A1.Flex' or type(data.get('ocpus')) is not int
            or data['ocpus'] != 1 or type(data.get('memory_gib')) is not int or data['memory_gib'] != 6):
        raise ValueError('Unreviewed host allocation')
    limits = {'aggregate_a1_ocpu_hours': 1500, 'aggregate_a1_memory_gib_hours': 9000,
              'aggregate_boot_block_gib': 200, 'aggregate_volume_backups': 5, 'billable_cost': 0}
    for key, limit in limits.items():
        value = data.get(key)
        if type(value) not in (int, float) or not 0 <= value <= limit:
            raise ValueError('Missing or exceeded cumulative free allowance')
    remaining = data.get('b2_free_remaining_bytes')
    if type(remaining) is not int or remaining < MAX_OBJECT_BYTES * 8:
        raise ValueError('External backup headroom is not verified')
    if not re.fullmatch(r'[0-9a-f]{64}', data.get('evidence_sha256', '')):
        raise ValueError('Retained account evidence required')
    reviewed = datetime.fromisoformat(data['reviewed_at'])
    expires = datetime.fromisoformat(data['expires_at'])
    if reviewed.tzinfo is None or expires.tzinfo is None or not reviewed <= now < expires <= reviewed + timedelta(days=7):
        raise ValueError('Approval must be current and expire within seven days')
    return data


def read_root_file(path, limit=65536):
    path = Path(path)
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Root-controlled directory required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1 or info.st_size > limit:
            raise ValueError('Root-controlled regular approval required')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            data = source.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Oversized approval')
        return data
    finally:
        os.close(fd)


def host_gate(environ=None):
    env = os.environ if environ is None else environ
    approval = validate_approval(json.loads(read_root_file(APPROVAL)))
    expected = {'FG_CUSTOMER_AUTH_DB': STATE / 'accounts.sqlite',
                'FG_CUSTOMER_DATA_ROOT': STATE / 'sites',
                'FG_MONITOR_DB': STATE / 'monitor.sqlite',
                'FG_AI_LEDGER_DB': STATE / 'advisor.sqlite'}
    for key, value in expected.items():
        if env.get(key) != str(value):
            raise ValueError('Persistent state paths must match reviewed layout')
    if any(p.is_symlink() for p in (STATE, *STATE.parents)):
        raise ValueError('State path cannot traverse symlinks')
    if (STATE / 'FG-RESTORE-REVIEW-REQUIRED').exists():
        raise ValueError('Recovered state requires reconciliation')
    from runtime_state import require_existing_guard_state, require_existing_database
    require_existing_guard_state(env)
    require_existing_database(STATE / 'advisor.sqlite', {'advisor_requests', 'advisor_budget'})
    return approval


if __name__ == '__main__':
    try:
        host_gate()
    except Exception:
        print('{"status":"blocked","activation_authorized":false}')
        raise SystemExit(1)
    print('{"status":"gate-verified","resources_activated":false}')
