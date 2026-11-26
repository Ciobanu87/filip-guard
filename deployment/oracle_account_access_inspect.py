"""Read-only probe of EXISTING OCI account tooling/identity. No installation.

No config-file credentials, IAM writes, grants, debug logs or raw identifiers.
SDK/CLI must already be available. A successful IAM read is not a billing audit.
"""
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import urllib.request


def result():
    return dict(schema=1, sdk_available=False, cli_available=False,
                existing_identity_read_authorized=False, home_region_frankfurt_verified=False,
                region_subscription_count=0, region_list_complete=False,
                account_resource_inventory_verified=False, cumulative_usage_verified=False,
                server_modified=False, iam_permissions_changed=False, groq_calls=0,
                status='no-existing-account-tooling')


def read_home(rows, complete, report, sdk=False):
    if not complete or type(rows) is not list or not 1 <= len(rows) <= 100:
        report['status'] = 'account-region-list-incomplete'
        return report
    homes = [row.region_name if sdk else row.get('region-name') for row in rows
             if (row.is_home_region if sdk else row.get('is-home-region')) is True]
    if len(homes) != 1:
        report['status'] = 'account-home-region-unverified'
        return report
    report.update(existing_identity_read_authorized=True, region_list_complete=True,
                  region_subscription_count=len(rows), home_region_frankfurt_verified=homes == ['eu-frankfurt-1'],
                  status='existing-identity-region-read-succeeded')
    return report


def inspect():
    report = result()
    report['sdk_available'] = importlib.util.find_spec('oci') is not None
    report['cli_available'] = shutil.which('oci') is not None
    if not report['sdk_available'] and not report['cli_available']:
        return report
    # Bound preinstalled SDK metadata/auth retries too; never grant a new policy.
    def timeout(*unused):
        raise TimeoutError('Existing identity probe timeout')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(24)
    try:
        os.environ['OCI_METADATA_BASE_URL'] = 'http://169.254.169.254/opc/v2'
        if report['sdk_available']:
            import oci
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner(
                federation_client_retry_strategy=oci.retry.NoneRetryStrategy())
            client = oci.identity.IdentityClient({'region': 'eu-frankfurt-1'}, signer=signer,
                                                timeout=(3, 5), retry_strategy=oci.retry.NoneRetryStrategy())
            response = client.list_region_subscriptions(signer.tenancy_id)
            return read_home(response.data, not response.has_next_page, report, sdk=True)
        # CLI may have its SDK in its own venv. Read only the nonsecret instance
        # compartment ID from IMDS, never identity private-key/certificate paths.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request('http://169.254.169.254/opc/v2/instance/',
                                         headers={'Authorization': 'Bearer Oracle'})
        with opener.open(request, timeout=3) as response:
            raw = response.read(65537)
        if len(raw) > 65536: raise ValueError('Unexpected metadata')
        tenancy = json.loads(raw)['compartmentId']
        if not isinstance(tenancy, str) or not tenancy.startswith('ocid1.tenancy.'):
            report['status'] = 'existing-cli-needs-tenancy-scope'
            return report
        child_env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C',
                     'OCI_METADATA_BASE_URL': 'http://169.254.169.254/opc/v2'}
        process = subprocess.run([shutil.which('oci'), '--auth', 'instance_principal',
                                  '--config-file', '/dev/null', '--region', 'eu-frankfurt-1',
                                  'iam', 'region-subscription', 'list', '--tenancy-id', tenancy, '--all'],
                                 capture_output=True, text=True, timeout=18, env=child_env)
        if process.returncode != 0 or len(process.stdout) > 65536:
            report['status'] = 'existing-identity-read-unavailable'
            return report
        return read_home(json.loads(process.stdout)['data'], True, report)
    except Exception:
        report['status'] = 'existing-identity-read-unavailable'
        return report
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    print(json.dumps(inspect(), sort_keys=True))
