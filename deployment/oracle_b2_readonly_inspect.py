"""Bounded B2 metadata read; no objects, key changes, rule writes or service start."""
import base64,json,os,pwd,re,resource,runpy,stat
from pathlib import Path
import requests

PHASE="preflight"
CALLS=0
HTTP_STATUS=None
ERROR_CODE=None
ERROR_HINT=None

def main():
    global PHASE,CALLS,HTTP_STATUS,ERROR_CODE,ERROR_HINT
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    PHASE='custody-and-service-hold'
    helper=runpy.run_path('/usr/local/sbin/filip-guard-master-custody')
    if helper['status']().get('independent_owner_custody_verified') is not True:
        raise ValueError('Verified owner custody required')
    settings=helper['held_configuration']()
    PHASE='existing-private-credential-mount'
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
        global CALLS,HTTP_STATUS,ERROR_CODE,ERROR_HINT
        calls+=1;CALLS=calls
        if calls>2:raise ValueError('Bounded read-only request count exceeded')
        with session.get(url,headers={'Authorization':authorization},params=params,timeout=(5,10),allow_redirects=False,stream=True) as response:
            HTTP_STATUS=response.status_code
            raw=response.raw.read(65537)
            if len(raw)>65536:raise ValueError('Bounded response required')
            data=json.loads(raw)
            if response.status_code!=200:
                code=data.get('code','') if isinstance(data,dict) else ''
                ERROR_CODE=code if re.fullmatch('[a-z_]{1,64}',code) else 'unclassified'
                message=data.get('message','') if isinstance(data,dict) else ''
                ERROR_HINT=('bucket-parameter-missing' if 'bucketId' in message and any(x in message.lower() for x in ('missing','required')) else 'api-request-rejected')
                raise ValueError('Read-only request held')
            return data
    try:
        PHASE='native-account-authorization'
        auth=get('https://api.backblazeb2.com/b2api/v4/b2_authorize_account','Basic '+base64.b64encode((key+':'+secret).encode()).decode())
        PHASE='native-authorization-schema'
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
        PHASE='read-existing-notification-rules'
        result=get(url+'/b2api/v4/b2_get_bucket_notification_rules',auth['authorizationToken'],{'bucketId':bucket_id})
        PHASE='notification-response-schema'
        entries=result if isinstance(result,list) else [result]
        if len(entries)!=1 or not isinstance(entries[0],dict) or entries[0].get('bucketId',bucket_id)!=bucket_id:raise ValueError('Unexpected notification response')
        rules=entries[0]['eventNotificationRules']
        if not isinstance(rules,list) or any(type(r.get('isEnabled')) is not bool for r in rules):raise ValueError('Unverified rule states')
        report.update(b2_api_calls=calls,notifications_verified_disabled=not any(r['isEnabled'] for r in rules),notification_rule_count=len(rules))
        return report
    finally:session.close()


if __name__=='__main__':
    try:print(json.dumps(main(),sort_keys=True))
    except Exception:
        print(json.dumps({'status':'b2-read-only-inspection-held','phase':PHASE,'b2_api_calls':CALLS,'last_http_status':HTTP_STATUS,'error_code':ERROR_CODE,'error_hint':ERROR_HINT,'services_started':False,'secret_values_printed':False,'automatic_retries':0},sort_keys=True))
