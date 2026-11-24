"""Authenticated, non-network credential key rotation. No key generation/deletion."""
import argparse
import getpass
import json
import os
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from operator_secrets import configured_master_keys


def main(argv=None):
    parser=argparse.ArgumentParser(description='Re-encrypt owned WordPress credentials under mounted active key version')
    parser.add_argument('--account',required=True);parser.add_argument('--site-id',required=True)
    args=parser.parse_args(argv)
    auth=None;session=None
    try:
        auth=CustomerAuth(os.environ['FG_CUSTOMER_AUTH_DB'])
        session=auth.login(args.account,getpass.getpass('FILIP GUARD account password: '))
        sites=CustomerSites(auth,os.environ['FG_CUSTOMER_DATA_ROOT'],configured_master_keys(),
            active_key_id=os.environ['FG_GUARD_KEY_ID'])
        result=sites.rotate_credentials(session,args.site_id)
    except Exception:
        print(json.dumps({'status':'blocked','reason':'Owner authentication or key rotation could not be verified'}));return 1
    finally:
        if auth is not None and session is not None:auth.logout(session)
    print(json.dumps(result));return 0

if __name__=='__main__':raise SystemExit(main())
