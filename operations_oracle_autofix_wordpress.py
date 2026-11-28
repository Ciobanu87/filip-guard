"""Execute approved isolated dependency installation and real WordPress pilot."""
import base64
import json
from pathlib import Path
import shlex
import subprocess
from operations_oracle_ssh_probe import run_pinned_command


def main():
    try:
        archive=subprocess.run(['git','archive','--format=tar','ee593326f89b5db8a1f0700c6a9f18424a36e0e6'],capture_output=True,check=True,timeout=20).stdout
        root=Path(__file__).with_name('deployment')
        helper=(root/'oracle_autofix_native_pilot.py').read_text()
        source=(root/'oracle_autofix_wordpress_pilot.py').read_text()
        program=source+'\nmain('+repr(helper)+')\n'
        command='sudo -n python3 -c '+shlex.quote("import base64;exec(base64.b64decode('"+base64.b64encode(program.encode()).decode()+"'))")
        report=json.loads(run_pinned_command(command,operation='host-setup',input_data=archive,timeout=900))
        if type(report) is not dict or report.get('status') not in ('private-wordpress-pilot-passed','private-wordpress-pilot-failed','private-wordpress-pilot-held-or-failed'):raise ValueError('Unexpected pilot result')
    except Exception:
        print(json.dumps({'status':'private-wordpress-pilot-unverified','production_autofix_activated':False}));return 1
    print(json.dumps(report,sort_keys=True))
    return 0 if report['status']=='private-wordpress-pilot-passed' else 1


if __name__=='__main__':raise SystemExit(main())
