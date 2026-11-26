"""Pinned SSH transport and read-only preflight for an existing Oracle VM.

The trusted host fingerprint must come from the operator's out-of-band console.
No credential, IP, host key or raw remote output is printed or archived.
"""
import base64
from hashlib import sha256
from hmac import compare_digest
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

class HostSetupError(ConnectionError):
    def __init__(self, phase):
        self.phase = phase
        super().__init__('Authorized host setup did not complete')


REMOTE_COMMAND = """python3 - <<'PYREMOTE'
import json,os,platform,subprocess
settings={}
try:
    probe=subprocess.run(['sudo','-n','/usr/sbin/sshd','-T'],capture_output=True,text=True,timeout=10)
    if probe.returncode==0:
        settings=dict(line.split(None,1) for line in probe.stdout.splitlines() if ' ' in line)
except Exception:pass
print(json.dumps({'arm64':platform.machine()=='aarch64',
    'sudo_read_check_available':bool(settings),
    'password_authentication_disabled':settings.get('passwordauthentication')=='no',
    'public_key_authentication_enabled':settings.get('pubkeyauthentication')=='yes',
    'root_login_disabled':settings.get('permitrootlogin')=='no'}))
PYREMOTE"""


def pinned_known_host(host, expected_fingerprint, scan):
    address=ipaddress.ip_address(host)
    if not address.is_global:raise ValueError('Public operator-supplied IP required')
    if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}',expected_fingerprint):raise ValueError('Trusted SHA256 fingerprint required')
    keys=set()
    for line in scan.splitlines():
        if line.startswith('#') or not line.strip():continue
        parts=line.split()
        if len(parts)!=3 or parts[1]!='ssh-ed25519':raise ValueError('Unexpected SSH host key')
        blob=base64.b64decode(parts[2],validate=True)
        if len(blob)!=51 or not blob.startswith(b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20'):
            raise ValueError('Invalid ED25519 public host key')
        actual='SHA256:'+base64.b64encode(sha256(blob).digest()).decode().rstrip('=')
        if not compare_digest(actual,expected_fingerprint):raise ValueError('SSH host identity mismatch')
        keys.add(parts[2])
    if len(keys)!=1:raise ValueError('Unique matching SSH host key required')
    return str(address)+' ssh-ed25519 '+next(iter(keys))+'\n'


def run_pinned_command(remote_command,env=None,runner=None,*,operation="read-only",input_data=None,timeout=40):
    env=os.environ if env is None else env;runner=subprocess.run if runner is None else runner
    if operation == 'read-only':
        if env.get('FG_OCI_SSH_PROBE_AUTHORIZED') != '1' or input_data is not None or timeout != 40:
            raise ValueError('Explicit read-only SSH authorization required')
    elif operation == 'host-setup':
        if env.get('FG_OCI_HOST_SETUP_AUTHORIZED') != '1' or type(timeout) is not int or not 40 <= timeout <= 900:
            raise ValueError('Explicit host setup authorization required')
        if input_data is not None and (type(input_data) is not bytes or len(input_data) > 16 * 1024 * 1024):
            raise ValueError('Bounded source archive required')
    else:
        raise ValueError('Unreviewed SSH operation')
    host=env['FG_OCI_HOST'];expected=env['FG_OCI_HOST_ED25519_SHA256'];private=env['FG_OCI_SSH_PRIVATE_KEY']
    if not ipaddress.ip_address(host).is_global:raise ValueError('Public IP required')
    if not 100<len(private)<=32768 or not private.startswith('-----BEGIN ') or 'PRIVATE KEY-----' not in private[:80]:
        raise ValueError('Existing private key required')
    child_env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C'}
    scan=runner(['ssh-keyscan','-T','8','-t','ed25519',host],capture_output=True,text=True,timeout=15,check=False,env=child_env)
    if scan.returncode!=0:raise ConnectionError('SSH host key unavailable')
    known=pinned_known_host(host,expected,scan.stdout)  # before key is used
    with tempfile.TemporaryDirectory(prefix='fg-oracle-ssh-') as directory:
        root=Path(directory);key=root/'identity';hosts=root/'known_hosts'
        for path,value in ((key,private.rstrip()+'\n'),(hosts,known)):
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as output:output.write(value)
        command=['ssh','-i',str(key),'-o','BatchMode=yes','-o','IdentitiesOnly=yes',
            '-o','IdentityAgent=none','-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ssh-ed25519',
            '-o','UserKnownHostsFile='+str(hosts),'-o','GlobalKnownHostsFile=/dev/null',
            '-o','PasswordAuthentication=no','-o','KbdInteractiveAuthentication=no',
            '-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-o','LogLevel=ERROR',
            'opc@'+host,remote_command]
        options = dict(capture_output=True, text=input_data is None, timeout=timeout, check=False, env=child_env)
        if input_data is not None: options['input'] = input_data
        result=runner(command, **options)
        if result.returncode != 0:
            if operation == 'host-setup':
                phase = 'unknown'
                try:
                    data = json.loads(result.stdout)
                    allowed = {'authorization', 'source-layout', 'official-python-packages', 'isolated-python-environment',
                               'private-system-user-and-storage', 'inactive-systemd-units', 'nonroot-render-and-loopback-health',
                               'durable-host-receipt', 'security-configuration', 'reboot-validation'}
                    if type(data) is dict and data.get('phase') in allowed: phase = data['phase']
                except Exception: pass
                raise HostSetupError(phase)
            raise ConnectionError('Pinned SSH authentication or read-only check failed')
        if len(result.stdout)>4096:raise ValueError('Unexpected remote response')
        return result.stdout.decode('utf-8') if isinstance(result.stdout, bytes) else result.stdout


def run_probe(env=None,runner=None):
    checks=json.loads(run_pinned_command(REMOTE_COMMAND,env,runner))
    allowed={'arm64','sudo_read_check_available','password_authentication_disabled',
             'public_key_authentication_enabled','root_login_disabled'}
    if type(checks) is not dict or set(checks)!=allowed or any(type(x) is not bool for x in checks.values()):
        raise ValueError('Invalid read-only check')
    return {'status':'authenticated-read-only','host_identity_verified':True,**checks,
        'server_modified':False,'always_free_billing_verified':False,'groq_calls':0}


def main():
    try:result=run_probe()
    except Exception:
        print(json.dumps({'status':'blocked-or-failed','host_or_auth_not_verified':True,
            'server_modified':False,'always_free_billing_verified':False}));return 1
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
