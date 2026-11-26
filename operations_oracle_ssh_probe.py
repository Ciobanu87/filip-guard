"""Read-only SSH preflight for an existing Oracle VM; no provisioning or install.

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


def run_probe(env=None,runner=None):
    env=os.environ if env is None else env;runner=subprocess.run if runner is None else runner
    if env.get('FG_OCI_SSH_PROBE_AUTHORIZED')!='1':raise ValueError('Explicit read-only SSH authorization required')
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
            'opc@'+host,REMOTE_COMMAND]
        result=runner(command,capture_output=True,text=True,timeout=40,check=False,env=child_env)
        if result.returncode!=0:raise ConnectionError('Pinned SSH authentication or read-only check failed')
        if len(result.stdout)>4096:raise ValueError('Unexpected remote response')
        checks=json.loads(result.stdout)
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
