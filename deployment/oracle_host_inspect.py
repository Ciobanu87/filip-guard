"""Fixed, read-only, stdlib-only host inventory. Run through pinned SSH stdin.

No package installation, service changes, metadata credentials or private file
contents. Capacities observed inside Linux do not establish OCI billing.
"""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8)
        return result.stdout.strip()[:4096] if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def inspect():
    release = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            release[key] = value.strip('"')
    ssh = command(['sudo', '-n', '/usr/sbin/sshd', '-T'])
    settings = dict(line.split(None, 1) for line in ssh.splitlines() if ' ' in line)
    root_login = settings.get('permitrootlogin', 'unknown')
    if root_login not in ('yes', 'no', 'prohibit-password', 'without-password', 'forced-commands-only'):
        root_login = 'unknown'
    existing = Path('/srv/filip-guard')
    while not existing.exists():
        existing = existing.parent
    mount = command(['findmnt', '-n', '-o', 'FSTYPE', '--target', str(existing)])
    fs = os.statvfs(existing)
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return {
        'schema': 1,
        'oracle_linux_9': release.get('ID') == 'ol' and release.get('VERSION_ID', '').split('.')[0] == '9',
        'arm64': platform.machine() == 'aarch64',
        'logical_cpus': os.cpu_count() or 0,
        'memory_mib': int(memory['MemTotal'].split()[0]) // 1024,
        'systemd_available': bool(shutil.which('systemctl')),
        'python311_available': bool(shutil.which('python3.11')),
        'podman_available': bool(shutil.which('podman')),
        'docker_available': bool(shutil.which('docker')),
        'root_login': root_login,
        'password_authentication_disabled': settings.get('passwordauthentication') == 'no',
        'public_key_authentication_enabled': settings.get('pubkeyauthentication') == 'yes',
        'selinux_enforcing': command(['getenforce']) == 'Enforcing',
        'firewalld_active': command(['systemctl', 'is-active', 'firewalld.service']) == 'active',
        'state_filesystem': mount if mount in ('xfs', 'ext4', 'btrfs', 'tmpfs', 'overlay', 'nfs', 'nfs4') else 'other',
        'state_filesystem_total_gib': fs.f_blocks * fs.f_frsize // (1024 ** 3),
        'state_filesystem_available_gib': fs.f_bavail * fs.f_frsize // (1024 ** 3),
        'state_directory_exists': Path('/srv/filip-guard/state').is_dir(),
        'state_directory_symlink': Path('/srv/filip-guard/state').is_symlink(),
        'existing_guard_ui_active': command(['systemctl', 'is-active', 'filip-guard-ui.service']) == 'active',
        'existing_guard_worker_active': command(['systemctl', 'is-active', 'filip-guard-worker.service']) == 'active',
        'always_free_billing_verified': False,
        'server_modified': False,
        'groq_calls': 0,
    }


if __name__ == '__main__':
    print(json.dumps(inspect(), sort_keys=True))
