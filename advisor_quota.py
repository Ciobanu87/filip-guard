"""Safe provider cooldown metadata; no keys, raw headers or error messages saved."""
import json
import math
import re
from email.utils import parsedate_to_datetime


def duration(value):
    if type(value) is not str or len(value)>64:return None
    if re.fullmatch(r'\d{1,8}(?:\.\d+)?',value):result=float(value)
    elif re.fullmatch(r'(?:\d+(?:\.\d+)?[dhms])+',value):
        result=sum(float(n)*{'d':86400,'h':3600,'m':60,'s':1}[unit] for n,unit in re.findall(r'(\d+(?:\.\d+)?)([dhms])',value))
    else:return None
    return result if math.isfinite(result) and 0<=result<=31*86400 else None


def quota_metadata(headers,error=None,*,now=0):
    values=dict(headers);info={};message=(error or {}).get('message','')
    if type(message) is not str:message=''
    message=message[:4096]
    kinds={'TPM':'tokens_per_minute','TPD':'tokens_per_day','RPM':'requests_per_minute','RPD':'requests_per_day'}
    match=re.search(r'\b(TPM|TPD|RPM|RPD)\b',message,re.I)
    info['quota_kind']=kinds[match[0].upper()] if match else 'unknown'
    delay=duration(values.get('retry-after'))
    if delay is None and values.get('retry-after'):
        try:delay=max(0,parsedate_to_datetime(values['retry-after']).timestamp()-now)
        except (ValueError,TypeError,OverflowError):pass
    if delay is None:
        match=re.search(r'try again in\s+(\d+(?:\.\d+)?[dhms](?:\d+(?:\.\d+)?[dhms])*)',message,re.I)
        if match:delay=duration(match[1].lower())
    if delay is not None and math.isfinite(delay) and 0<=delay<=31*86400:info['retry_after_seconds']=delay
    for header,key in [('x-ratelimit-limit-tokens','tokens_per_minute_limit'),('x-ratelimit-remaining-tokens','tokens_per_minute_remaining'),
                       ('x-ratelimit-limit-requests','requests_per_day_limit'),('x-ratelimit-remaining-requests','requests_per_day_remaining')]:
        value=values.get(header)
        if type(value) is str and re.fullmatch(r'\d{1,10}',value):info[key]=int(value)
    for header,key in [('x-ratelimit-reset-tokens','tokens_per_minute_reset_seconds'),('x-ratelimit-reset-requests','requests_per_day_reset_seconds')]:
        value=duration(values.get(header))
        if value is not None:info[key]=value
    # A TPM reset must never be used as proof that a TPD/unknown limit expired.
    if 'retry_after_seconds' not in info and info['quota_kind']=='tokens_per_minute' and 'tokens_per_minute_reset_seconds' in info:
        info['retry_after_seconds']=info['tokens_per_minute_reset_seconds']
    return info


def install(db):
    db.execute('''CREATE TABLE IF NOT EXISTS advisor_provider_cooldown (
        provider TEXT PRIMARY KEY,observed REAL NOT NULL,blocked_until REAL NOT NULL,
        source TEXT NOT NULL,diagnostic TEXT NOT NULL)''')


def is_quota(diagnostic):return type(diagnostic) is dict and diagnostic.get('http_status')==429


def record(db,provider,observed,diagnostic):
    delay=diagnostic.get('retry_after_seconds')
    known=type(delay) in (int,float) and math.isfinite(delay) and 0<=delay<=31*86400
    # An old 429 without a retained expiry cannot be assumed to clear in 10 min.
    # 24h is conservative local backoff, explicitly NOT a confirmed provider reset.
    until=observed+(max(61,float(delay)) if known else 86400)
    source='provider' if known else 'conservative-unknown-expiry'
    db.execute('''INSERT INTO advisor_provider_cooldown VALUES (?,?,?,?,?)
        ON CONFLICT(provider) DO UPDATE SET observed=excluded.observed,blocked_until=excluded.blocked_until,
        source=excluded.source,diagnostic=excluded.diagnostic
        WHERE excluded.blocked_until>advisor_provider_cooldown.blocked_until''',
        (provider,observed,until,source,json.dumps(diagnostic)))


def migrate_legacy(db,provider):
    for started,result in db.execute("SELECT started,result FROM advisor_requests WHERE state='failed' AND result IS NOT NULL"):
        try:diagnostic=json.loads(result).get('diagnostic')
        except (ValueError,AttributeError):continue
        if is_quota(diagnostic):record(db,provider,started,diagnostic)


def active(db,provider,now):
    row=db.execute('SELECT observed,blocked_until,source,diagnostic FROM advisor_provider_cooldown WHERE provider=?',(provider,)).fetchone()
    if not row or row[1]<=now:return None
    return {'observed_at':row[0],'eligible_at':row[1],'wait_seconds':math.ceil(row[1]-now),
            'expiry_source':row[2],'provider_expiry_confirmed':row[2]=='provider','diagnostic':json.loads(row[3])}
