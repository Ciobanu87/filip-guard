"""Run only the approved private native subset using existing runtime/isolation."""
import base64
import json
from pathlib import Path
import shlex
import subprocess
from operations_oracle_ssh_probe import run_pinned_command

CANDIDATE='ee593326f89b5db8a1f0700c6a9f18424a36e0e6'


def main():
    try:
        archive=subprocess.run(['git','archive','--format=tar',CANDIDATE],capture_output=True,check=True,timeout=20).stdout
        source=Path(__file__).with_name('deployment').joinpath('oracle_autofix_native_pilot.py').read_bytes()
        command='sudo -n python3 -c '+shlex.quote("import base64;exec(base64.b64decode('"+base64.b64encode(source).decode()+"'))")
        report=json.loads(run_pinned_command(command,operation='host-setup',input_data=archive,timeout=900))
        if type(report) is not dict or report.get('status') not in ('native-python-pilot-passed','native-python-pilot-failed','native-python-pilot-held-or-failed'):
            raise ValueError('Invalid native pilot result')
    except Exception:
        print(json.dumps({'status':'native-python-pilot-unverified','production_autofix_activated':False}));return 1
    print(json.dumps(report,sort_keys=True))
    return 0 if report['status']=='native-python-pilot-passed' else 1


if __name__=='__main__':raise SystemExit(main())
