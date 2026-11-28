"""Pinned SSH preparation of independent operator files only, without secrets."""
import base64
import json
from pathlib import Path
import shlex
from operations_oracle_ssh_probe import run_pinned_command


def main():
    try:
        from deployment.oracle_operator_prepare import FILES
        base=Path(__file__).parent
        payload={'files':{name:(base/name).read_text() for name in sorted(FILES)},'units':{name:(base/'deployment/oracle-prepared'/(name+'.example')).read_text() for name in ('filip-guard-operator-monitor.service','filip-guard-operator-monitor.timer')}}
        source=(base/'deployment/oracle_operator_prepare.py').read_bytes()
        command='sudo -n python3 -c '+shlex.quote("import base64;exec(base64.b64decode('"+base64.b64encode(source).decode()+"'))")
        report=json.loads(run_pinned_command(command,operation='host-setup',input_data=json.dumps(payload).encode(),timeout=180))
        if report.get('status') not in ('operator-prepared-held','operator-preparation-held-or-failed'):raise ValueError('Unexpected result')
    except Exception:
        print('{"status":"operator-preparation-unverified","production_active":false}');return 1
    print(json.dumps(report,sort_keys=True));return 0 if report['status']=='operator-prepared-held' else 1


if __name__=='__main__':raise SystemExit(main())
