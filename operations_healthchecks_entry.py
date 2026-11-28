"""Owner enters two existing ingestion URLs directly on Oracle, hidden.

No management API key, email address or token is sent to GitHub/ChatGPT. Does not
start the timer or send network traffic. Existing config is never overwritten.
"""
import getpass
import json
import os
from pathlib import Path
from operations_alerting import endpoint


def main():
    try:
        if os.geteuid()!=0 or not os.isatty(0):raise ValueError('Private interactive terminal required')
        path=Path('/etc/filip-guard/healthchecks.json')
        if path.exists() or path.is_symlink():raise ValueError('Existing configuration requires review')
        host=endpoint(getpass.getpass('Healthchecks host ping URL (hidden): '))
        incident=endpoint(getpass.getpass('Healthchecks incident ping URL (hidden): '))
        if host==incident:raise ValueError('Two separate checks required')
        config=dict(schema=1,authorized=True,host_url=host,incident_url=incident,
                    expected_ui=False,expected_worker=False,expected_ai=False,expected_backup=False,recover_worker=False)
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as output:json.dump(config,output);output.flush();os.fsync(output.fileno())
    except Exception:
        print('{"status":"healthchecks-entry-held","secrets_logged":false}');return 1
    print('{"status":"healthchecks-private-config-installed-not-live-validated","production_active":false}');return 0


if __name__=='__main__':raise SystemExit(main())
