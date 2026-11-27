"""Execute the bounded metadata inspection on the existing host; sanitized output only."""
import hashlib,json,os,shlex
from pathlib import Path
from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command


def main():
    root=Path(__file__).parent
    evidence=(root/'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
    validate_authorization(json.loads((root/'deployment/oracle-host-setup-request.json').read_text()),evidence,os.environ)
    source=(root/'deployment/oracle_b2_readonly_inspect.py').read_text()
    compile(source,'b2-readonly-inspection','exec')
    result=json.loads(run_pinned_command('sudo -n -- /opt/filip-guard/.venv/bin/python -c '+shlex.quote(source),operation='host-setup',timeout=90))
    if result.get('status') not in ('b2-read-only-metadata-inspected','b2-read-only-inspection-held'):raise ValueError('Read-only metadata unavailable')
    allowed={'status','b2_api_calls','groq_api_calls','services_started','objects_uploaded','objects_downloaded','notification_writes','automatic_retries','bucket_scoped_key','can_read_notifications','can_write_notifications','notifications_verified_disabled','account_wide_other_activity_verified','remaining_evidence','notification_rule_count','phase','last_http_status','secret_values_printed'}
    if set(result)-allowed:raise ValueError('Unreviewed metadata is never published')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception:
        print('{"status":"b2-read-only-inspection-held","services_started":false,"secret_values_printed":false}')
        raise SystemExit(1)
