"""Bounded B2 metadata read; no objects, key changes, rule writes or service start."""
import base64,json,os,pwd,re,resource,runpy,stat,sys,hashlib,subprocess
from datetime import datetime,timezone
from pathlib import Path

PHASE="preflight"
CALLS=0
HTTP_STATUS=None
ERROR_CODE=None
ERROR_HINT=None
ERROR_WORDS=[]
NOTIFICATION_API_DISABLED=False

def provider_notification_disabled(status,code,message):
    return (status==400 and code=='bad_request' and isinstance(message,str)
            and re.fullmatch(r'(?:this )?api (?:is )?not enabled[.!]?',message.strip(),re.IGNORECASE) is not None)

def main(validate_backup=False):
    import requests
    global PHASE,CALLS,HTTP_STATUS,ERROR_CODE,ERROR_HINT,ERROR_WORDS,NOTIFICATION_API_DISABLED
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
    def get(url,authorization,params=None,*,body=None):
        nonlocal calls
        global CALLS,HTTP_STATUS,ERROR_CODE,ERROR_HINT,ERROR_WORDS,NOTIFICATION_API_DISABLED
        calls+=1;CALLS=calls
        if calls>(4 if validate_backup else 2):raise ValueError('Bounded read-only request count exceeded')
        method='GET' if body is None else 'POST'
        with session.request(method,url,headers={'Authorization':authorization,'Accept':'application/json'},params=params,json=body,timeout=(5,10),allow_redirects=False,stream=True) as response:
            HTTP_STATUS=response.status_code
            raw=response.raw.read(65537)
            if len(raw)>65536:raise ValueError('Bounded response required')
            data=json.loads(raw)
            if response.status_code!=200:
                code=data.get('code','') if isinstance(data,dict) else ''
                ERROR_CODE=code if re.fullmatch('[a-z_]{1,64}',code) else 'unclassified'
                message=data.get('message','') if isinstance(data,dict) else ''
                ERROR_HINT=('bucket-parameter-missing' if 'bucketId' in message and any(x in message.lower() for x in ('missing','required')) else 'api-request-rejected')
                vocabulary={'api','version','unsupported','support','supported','v3','v4','get','post','method','must','body','request','json','parse','parameter','query','unexpected','missing','bucketid','account','enabled','allowed','notifications','not','cannot','found','invalid','content','type','token','authorization','forbidden','requires','required','disabled','operation','endpoint','notification','empty','path','url','protocol','authentication','insufficient','malformed','argument','capability','bucket','prefix','restriction','restricted','file','key','application','permissions','read','write','list','with','without','call','id'}
                ERROR_WORDS=sorted(set(re.findall('[a-z0-9]+',message.lower())) & vocabulary)
                if 'prefix' in ERROR_WORDS and 'key' in ERROR_WORDS:ERROR_HINT='existing-key-prefix-restriction'
                if (PHASE=='read-existing-notification-rules' and provider_notification_disabled(response.status_code,code,message)):
                    NOTIFICATION_API_DISABLED=True
                    return {}
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
        # Official Backblaze b2-sdk-python v2.8.1 uses this compatible read-only route.
        result=get(url+'/b2api/v3/b2_get_bucket_notification_rules',auth['authorizationToken'],{'bucketId':bucket_id})
        if NOTIFICATION_API_DISABLED:
            report.update(notification_api_disabled_by_provider=True,notification_cost_guard_verified=True,b2_api_calls=calls)
            if validate_backup:return validate_existing_backup(settings,helper,session,get,auth,storage,matches[0],report)
            return report
        PHASE='notification-response-schema'
        entries=result if isinstance(result,list) else [result]
        if len(entries)!=1 or not isinstance(entries[0],dict) or entries[0].get('bucketId',bucket_id)!=bucket_id:raise ValueError('Unexpected notification response')
        rules=entries[0]['eventNotificationRules']
        if not isinstance(rules,list) or any(type(r.get('isEnabled')) is not bool for r in rules):raise ValueError('Unverified rule states')
        report.update(b2_api_calls=calls,notifications_verified_disabled=not any(r['isEnabled'] for r in rules),notification_rule_count=len(rules))
        report['notification_cost_guard_verified']=report['notifications_verified_disabled']
        if validate_backup:return validate_existing_backup(settings,helper,session,get,auth,storage,matches[0],report)
        return report
    finally:session.close()


def validate_existing_backup(settings,helper,session,get,auth,storage,bucket,report):
    global PHASE
    if report.get('notification_cost_guard_verified') is not True:raise ValueError('Notification cost guard required')
    if storage['allowed'].get('namePrefix'):raise ValueError('Complete bucket inventory requires existing unrestricted-prefix read scope')
    PHASE='bounded-existing-bucket-inventory'
    api=storage['apiUrl'];token=auth['authorizationToken']
    versions=get(api+'/b2api/v3/b2_list_file_versions',token,body={'bucketId':bucket['id'],'maxFileCount':100})
    if versions.get('nextFileName') or versions.get('nextFileId'):raise ValueError('Bounded inventory incomplete')
    files=versions['files']
    if not isinstance(files,list) or len(files)>100:raise ValueError('Bounded inventory required')
    total=0
    for entry in files:
        size=entry.get('contentLength')
        if type(size) is not int or size<0:raise ValueError('Storage size not verified')
        total+=size
    unfinished=get(api+'/b2api/v3/b2_list_unfinished_large_files',token,body={'bucketId':bucket['id'],'maxFileCount':100})
    if unfinished.get('nextFileId') or unfinished.get('files')!=[]:raise ValueError('Unfinished upload storage not verified')
    if 10_000_000_000-total<48*1024*1024*8:raise ValueError('Conservative free storage headroom required')
    from application_state_backup import MAX_ENVELOPE,_inventory,_root,export_application_state,recover_application_state
    if MAX_ENVELOPE!=48*1024*1024:raise ValueError('Unreviewed archive size bound')
    PHASE='stopped-writers-and-source-inventory'
    uid=pwd.getpwnam('filipguard').pw_uid
    for process in Path('/proc').iterdir():
        if process.name.isdecimal():
            try:
                if process.stat().st_uid==uid:raise ValueError('No application writer may run')
            except FileNotFoundError:pass
    source=_root('/srv/filip-guard/state');inventory=_inventory(source)
    if sum((source/name).stat().st_size for name in inventory[1])>32*1024*1024:raise ValueError('Bounded existing state required')
    before={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in inventory[1]}
    if not before:raise ValueError('Existing state required; no initialization')
    recovery=_root('/srv/filip-guard/recovery')
    destination=recovery/'external-validation-v1'
    if destination.exists() or destination.is_symlink():raise ValueError('Existing backup attempt is never repeated or overwritten')
    destination.mkdir(mode=0o700)
    helper['exclusive'](destination/'attempt.json',json.dumps({'status':'reserved-before-external-write','at':datetime.now(timezone.utc).isoformat(),'max_ciphertext_bytes':MAX_ENVELOPE,'max_puts':1,'max_gets':2}).encode())
    os.environ.update(settings)
    from infrastructure_configuration import configured_external_store
    from operator_secrets import configured_master_keys
    class BoundedStore:
        def __init__(self):self.store=configured_external_store();self.puts=0;self.gets=0
        def put(self,key,data):
            self.puts+=1
            if self.puts>1 or len(data)>MAX_ENVELOPE:raise ValueError('Single bounded encrypted write only')
            return self.store.put(key,data)
        def get(self,key):
            self.gets+=1
            if self.gets>2:raise ValueError('Two bounded recovery reads only')
            return self.store.get(key)
    store=BoundedStore();keys=configured_master_keys()
    PHASE='encrypt-upload-and-readback'
    manifest=export_application_state(source,store,keys,deployment_id=settings['FG_DEPLOYMENT_ID'],key_id=settings['FG_GUARD_KEY_ID'],quiesced=True)
    helper['exclusive'](destination/'manifest.json',json.dumps(manifest,sort_keys=True).encode())
    PHASE='separate-directory-recovery'
    restored=destination/'restored'
    result=recover_application_state(store,keys,manifest,restored)
    recovered={name:hashlib.sha256((restored/name).read_bytes()).hexdigest() for name in inventory[1]}
    after={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in inventory[1]}
    if recovered!=before or after!=before or _inventory(source)!=inventory:raise ValueError('Source must stay byte-for-byte unchanged')
    helper['held_configuration']()
    report.update(status='real-state-encrypted-backup-and-fresh-restore-verified',b2_api_calls=CALLS,
                  s3_puts=store.puts,s3_gets=store.gets,objects_uploaded=store.puts,objects_downloaded=store.gets,database_count=result['database_count'],
                  source_state_unchanged=True,restored_state_resume_blocked=result['resume_blocked'],
                  owner_custody_verified=True,full_wordpress_backup=False,manual_validation_only=True,
                  bucket_all_versions_bytes=total,unfinished_upload_count=0)
    helper['exclusive'](destination/'completed.json',json.dumps(report,sort_keys=True).encode())
    return report


if __name__=='__main__':
    try:print(json.dumps(main(validate_backup=sys.argv[1:]==['--validate-backup']),sort_keys=True))
    except Exception:
        print(json.dumps({'status':'b2-read-only-inspection-held','phase':PHASE,'b2_api_calls':CALLS,'last_http_status':HTTP_STATUS,'error_code':ERROR_CODE,'error_hint':ERROR_HINT,'error_vocabulary':ERROR_WORDS,'services_started':False,'secret_values_printed':False,'automatic_retries':0},sort_keys=True))
