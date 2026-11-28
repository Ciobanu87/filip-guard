"""Root-only explicit confirmation. Does not restore, restart or modify WordPress."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from operations_alerting import Incidents
from operations_healthchecks import private_json


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--receipt',required=True)
    args=parser.parse_args(argv)
    try:
        if os.geteuid()!=0:raise ValueError('Operator confirmation required')
        receipt=Path(args.receipt)
        if receipt.parent!=Path('/srv/filip-guard/operations/reviewed-recovery'):raise ValueError('Reviewed evidence directory required')
        data=private_json(receipt)
        if set(data)!={'incident','recovery_verified','verified_at','evidence_sha256'} or data['recovery_verified'] is not True:raise ValueError('Explicit independent recovery evidence required')
        import time
        if type(data['verified_at']) not in (int,float) or not 0<=time.time()-data['verified_at']<=3600:raise ValueError('Recent verification required')
        journal=Incidents('/srv/filip-guard/operations')
        journal.confirm(data['incident'],data['evidence_sha256'],data['verified_at'])
    except Exception:
        print('{"status":"recovery-confirmation-held"}');return 1
    print('{"status":"operator-recovery-confirmed","wordpress_mutations":0}');return 0


if __name__=='__main__':raise SystemExit(main())
