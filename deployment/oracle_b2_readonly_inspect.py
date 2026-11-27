"""Bounded B2 metadata read; no objects, key changes, rule writes or service start."""
import base64,json,os,pwd,re,resource,runpy,stat
from pathlib import Path
import requests


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    helper=runpy.run_path('/usr/local/sbin/filip-guard-master-custody')
    if helper['status']().get('independent_owner_custody_verified') is not True:
        raise ValueError('Verified owner custody required')
    settings=helper['held_configuration']()
    path=Path('/etc/filip-guard/secrets/s3.json')
    info=helper['private'](path,owner=pwd.getpwnam('filipguard').pw_uid)
    if stat.S_IMODE(info.st_mode)!=0o400 or info.st_size>8192:raise ValueError('Private existing credentials required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as source:credentials=json.loads(source.read(8193))
    key=credentials['access_key_id'];secret=credentials['secret_access_key']
    calls=0
    session=requests.Session();session.trust_env=False
    def get(url,authorization,params=None):
        nonlocal calls
        calls+=1
        if calls>2:raise ValueError('Bounded read-only request count exceeded')
        with session.get(url,headers={'Authorization':authorization},params=params,timeout=(5,10),allow_redirects=False,stream=True) as response:
            if response.status_code!=200:raise ValueError('Read-only permission or free cap prevents metadata read')
            raw=response.raw.read(65537)
            if len(raw)>65536:raise ValueError('Bounded response required')
            return json.loads(raw)
    try:
        auth=get('https://api.backblazeb2.com/b2api/v4/b2_authorize_account','Basic '+base64.b64encode((key+':'+secret).encode()).decode())
        storage=auth['apiInfo']['storageApi'];allowed=storage['allowed']
        capabilities=allowed['capabilities'];buckets=allowed['buckets']
        report={'status':'b2-read-only-metadata-inspected','b2_api_calls':calls,'groq_api_calls':0,'services_started':False,
                'objects_uploaded':0,'objects_downloaded':0,'notification_writes':0,'automatic_retries':0,
                'bucket_scoped_key':isinstance(buckets,list),'can_read_notifications':'readBucketNotifications' in capabilities,
                'can_write_notifications':'writeBucketNotifications' in capabilities,'notifications_verified_disabled':False,
                'account_wide_other_activity_verified':False}
        if 'readBucketNotifications' not in capabilities:
            report['remaining_evidence']='owner-console-event-notifications-required'
            return report
        matches=[b for b in (buckets or []) if b.get('name')==settings.get('FG_GUARD_S3_BUCKET')]
        if len(matches)!=1:
            report['remaining_evidence']='existing-scoped-bucket-identity-unavailable';return report
        url=storage['apiUrl']
        if not re.fullmatch(r'https://api[0-9]+\.backblazeb2\.com',url):raise ValueError('Official TLS API origin required')
        bucket_id=matches[0]['id']
        result=get(url+'/b2api/v4/b2_get_bucket_notification_rules',auth['authorizationToken'],{'bucketId':bucket_id})
        entries=result if isinstance(result,list) else [result]
        if len(entries)!=1 or entries[0].get('bucketId')!=bucket_id:raise ValueError('Unexpected notification response')
        rules=entries[0]['eventNotificationRules']
        if not isinstance(rules,list) or any(type(r.get('isEnabled')) is not bool for r in rules):raise ValueError('Unverified rule states')
        report.update(b2_api_calls=calls,notifications_verified_disabled=not any(r['isEnabled'] for r in rules),notification_rule_count=len(rules))
        return report
    finally:session.close()


if __name__=='__main__':
    try:print(json.dumps(main(),sort_keys=True))
    except Exception:
        print('{"status":"b2-read-only-inspection-held","services_started":false,"secret_values_printed":false,"automatic_retries":0}')
        raise SystemExit(1)
