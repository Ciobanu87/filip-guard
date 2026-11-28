"""No secrets in request or output: tokens stay in the existing server file."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
from operations_oracle_ssh_probe import run_pinned_command


def main():
    try:
        root=Path(__file__).parent
        from deployment.oracle_operator_prepare import FILES
        request=json.loads((root/'deployment/oracle-operator-control-request.json').read_text())
        request.pop('revision',None)
        request['hashes']={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in FILES}
        source=(root/'deployment/oracle_operator_control.py').read_bytes()
        command='sudo -n python3 -c '+shlex.quote("import base64;exec(base64.b64decode('"+base64.b64encode(source).decode()+"'))")
        report=json.loads(run_pinned_command(command,operation='host-setup',input_data=json.dumps(request).encode(),timeout=180))
        if report.get('status') not in ('operator-inspected','operator-action-completed','operator-held-missing-private-config','operator-control-held-or-failed'):raise ValueError('Unknown result')
    except Exception:
        print('{"status":"operator-control-unverified","production_active":false}');return 1
    print(json.dumps(report,sort_keys=True));return 1 if report['status']=='operator-control-held-or-failed' else 0


if __name__=='__main__':raise SystemExit(main())
