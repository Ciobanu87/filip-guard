"""Explicit operator bootstrap of fresh read-only guard storage. No network/keys.

Never run automatically on restart: missing nonempty site storage is not replaced.
This supports accounts/API/domain guards without WordPress or backup credentials.
"""
import argparse
import json
import os
from pathlib import Path
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from guard_assets import GuardAssetDirectory
from monitoring_service import MonitoringService


def initialize_read_only(environ=None):
    env=os.environ if environ is None else environ
    auth_path=Path(env['FG_CUSTOMER_AUTH_DB']);root=Path(env['FG_CUSTOMER_DATA_ROOT']);monitor_path=Path(env['FG_MONITOR_DB'])
    if root.is_symlink() or (root.exists() and not (root/'sites.sqlite').is_file() and any(root.iterdir())):
        raise ValueError('Nonempty or ambiguous site state cannot be initialized')
    auth=CustomerAuth(auth_path);directory=CustomerSites(auth,root,None)
    MonitoringService(GuardAssetDirectory(directory),monitor_path)
    return {'status':'initialized','scope':'read-only-monitoring','accounts_created':0,
            'keys_generated':False,'network_requests':0,'repairs_enabled':False,'worker_started':False}


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--initialize-read-only',action='store_true');args=parser.parse_args(argv)
    if not args.initialize_read_only:
        print(json.dumps({'status':'blocked','reason':'Explicit operator initialization required'}));return 2
    try:result=initialize_read_only()
    except Exception:
        print(json.dumps({'status':'blocked','reason':'Private monitoring storage could not be initialized safely'}));return 1
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
