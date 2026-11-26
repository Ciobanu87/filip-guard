"""Transfer existing B2 credentials only through pinned SSH stdin; no B2 calls."""
import json
import os
from pathlib import Path
import re
import shlex
from urllib.parse import urlsplit
from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command

ROOT = Path(__file__).parent


def payload(env, evidence_hash):
    endpoint = env['FG_B2_ENDPOINT']
    parts = urlsplit(endpoint)
    match = re.fullmatch(r's3\.([a-z0-9-]+)\.backblazeb2\.com', parts.hostname or '')
    if parts.scheme != 'https' or not match or parts.username or parts.password or parts.port not in (None, 443) or parts.path not in ('', '/') or parts.query or parts.fragment:
        raise ValueError('Existing verified B2 HTTPS endpoint required')
    bucket = env['FG_B2_BUCKET']
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', bucket):
        raise ValueError('Existing bucket required')
    credentials = {'access_key_id': env['FG_B2_KEY_ID'], 'secret_access_key': env['FG_B2_APPLICATION_KEY']}
    if any(not 1 <= len(value) <= 4096 or not value.isascii() or value.strip() != value or '\n' in value or '\r' in value for value in credentials.values()):
        raise ValueError('Existing private credentials required')
    result = {'endpoint': endpoint.rstrip('/'), 'region': match.group(1), 'bucket': bucket,
              'credentials': credentials, 'evidence_sha256': evidence_hash}
    encoded = json.dumps(result).encode()
    if len(encoded) > 8192: raise ValueError('Private payload too large')
    return encoded


def main():
    try:
        evidence = (ROOT / 'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
        authorization = validate_authorization(json.loads((ROOT / 'deployment/oracle-host-setup-request.json').read_text()), evidence, os.environ)
        data = payload(os.environ, authorization['evidence_sha256'])
        source = (ROOT / 'deployment/oracle_b2_mount.py').read_text()
        report = json.loads(run_pinned_command('sudo -n -- /usr/bin/python3 -c ' + shlex.quote(source),
                                             operation='host-setup', input_data=data, timeout=90))
        expected = {'status': 'existing-b2-config-mounted-inactive', 'credential_mode_0400': True,
                    'credential_owner_is_app': True, 'nonroot_adapter_constructed': True,
                    'network_requests': 0, 'uploads': 0, 'backup_timer_enabled': False,
                    'master_key_generated': False, 'ai_ledger_initialized': False, 'groq_calls': 0}
        if report != expected or any(type(report[k]) is not type(value) for k, value in expected.items()):
            raise ValueError('B2 host configuration incomplete')
    except Exception:
        print('{"status":"b2-host-config-blocked-or-failed","server_may_be_modified":true,"uploads":0,"groq_calls":0}')
        return 1
    print(json.dumps(report, sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
