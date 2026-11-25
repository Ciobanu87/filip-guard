"""Explicit offline application-state backup/recovery. Prints no private paths/data."""
import argparse
import json
import os
from pathlib import Path

from application_state_backup import export_application_state, recover_application_state
from infrastructure_configuration import configured_external_store
from operator_secrets import configured_master_keys, private_file


def main(argv=None):
    parser = argparse.ArgumentParser(description='Stopped application SQLite-state encrypted recovery')
    parser.add_argument('operation', choices=['export', 'recover'])
    parser.add_argument('--authorized-external-access', action='store_true')
    parser.add_argument('--writers-stopped', action='store_true')
    parser.add_argument('--root'); parser.add_argument('--deployment-id')
    parser.add_argument('--manifest', required=True); parser.add_argument('--destination')
    args = parser.parse_args(argv)
    if not args.authorized_external_access or (args.operation == 'export' and not args.writers_stopped):
        print(json.dumps({'status': 'blocked', 'reason': 'External authorization and stopped writers required'}))
        return 2
    try:
        if args.operation == 'export':
            if not args.root or not args.deployment_id: raise ValueError()
            # Reserve a NEW receipt before any upload. No overwrite or secret persistence.
            receipt = Path(args.manifest).absolute()
            from application_state_backup import _root
            _root(receipt.parent)
            if receipt.is_relative_to(Path(args.root).absolute()): raise ValueError()
            fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as output:
                output.write('{"status":"incomplete"}'); output.flush(); os.fsync(output.fileno())
                manifest = export_application_state(args.root, configured_external_store(), configured_master_keys(),
                    deployment_id=args.deployment_id, key_id=os.environ['FG_GUARD_KEY_ID'], quiesced=True)
                output.seek(0); json.dump(manifest, output); output.truncate(); output.flush(); os.fsync(output.fileno())
            result = {'verified': True, 'scope': manifest['scope'], 'readback_recovery': True}
        else:
            if not args.destination or Path(args.destination).exists() or Path(args.destination).is_symlink(): raise ValueError()
            manifest = json.loads(private_file(args.manifest, 8192))
            result = recover_application_state(configured_external_store(), configured_master_keys(), manifest, args.destination)
    except Exception:
        print(json.dumps({'status': 'failed', 'reason': 'Application-state backup/recovery could not be verified; retain incomplete evidence'}))
        return 1
    print(json.dumps({'status': 'verified', **result})); return 0


if __name__ == '__main__': raise SystemExit(main())
