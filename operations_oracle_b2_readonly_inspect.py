"""Execute the bounded metadata inspection on the existing host; sanitized output only."""
import hashlib,json,os,shlex,sys
from pathlib import Path
from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command


def main():
    root=Path(__file__).parent
    evidence=(root/'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
    validate_authorization(json.loads((root/'deployment/oracle-host-setup-request.json').read_text()),evidence,os.environ)
    if sys.argv[1:] not in ([],['--validate-backup']):raise ValueError('Explicit reviewed operation required')
    validate_backup=sys.argv[1:]==['--validate-backup']
    if validate_backup:
        expected={'manual_validation_only':True,'saved_zero_spend_caps_owner_confirmed':True,'max_native_metadata_calls':4,'max_encrypted_state_puts':1,'max_state_gets':2,'retry_failed_backup':False,'service_activation_authorized':False,'notification_writes':0}
        request=json.loads((root/'deployment/oracle-b2-backup-validation-request.json').read_text())
        if request!=expected or any(type(request[k]) is not type(v) for k,v in expected.items()):raise ValueError('Exact single manual backup authorization required')
    source=(root/'deployment/oracle_b2_readonly_inspect.py').read_text()
    compile(source,'b2-readonly-inspection','exec')
    result=json.loads(run_pinned_command('sudo -n -- /opt/filip-guard/.venv/bin/python -c '+shlex.quote(source)+(' --validate-backup' if validate_backup else ''),operation='host-setup',timeout=180))
    if result.get('status') not in ('b2-read-only-metadata-inspected','b2-read-only-inspection-held','real-state-encrypted-backup-and-fresh-restore-verified'):raise ValueError('Read-only metadata unavailable')
    allowed={'status','b2_api_calls','groq_api_calls','services_started','objects_uploaded','objects_downloaded','notification_writes','automatic_retries','bucket_scoped_key','can_read_notifications','can_write_notifications','notifications_verified_disabled','account_wide_other_activity_verified','remaining_evidence','notification_rule_count','phase','last_http_status','secret_values_printed','error_code','error_hint','error_vocabulary','notification_api_disabled_by_provider','notification_cost_guard_verified','s3_puts','s3_gets','database_count','source_state_unchanged','restored_state_resume_blocked','owner_custody_verified','full_wordpress_backup','manual_validation_only','bucket_all_versions_bytes','unfinished_upload_count'}
    if set(result)-allowed:raise ValueError('Unreviewed metadata is never published')
    result.pop('bucket_all_versions_bytes',None)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception:
        print('{"status":"b2-read-only-inspection-held","services_started":false,"secret_values_printed":false}')
        raise SystemExit(1)
