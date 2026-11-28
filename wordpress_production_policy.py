"""Private operator admission for a bounded production candidate; never activation.

No policy/validation receipt is generated here. Both must be explicitly installed
by the operator after the authorized live trial. No client field is authority.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import time
from pathlib import Path
from operator_secrets import private_file
from wordpress_execution_gate import _origin
from wordpress_compatibility import PROFILE,assess_compatibility

CHECKS={'identity','compatibility','backup_restore','conditional_write','independent_verification','rollback','recovery','tenant_isolation'}
FIELDS={'protocol','profile','site_url','source_commit','wp_version','theme_sha256','companion_sha256',
        'content_selector','resources','approved_at','expires_at','validation_sha256'}


def strict_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate policy field')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Invalid policy number')))


@dataclass(frozen=True)
class ProductionPolicy:
    raw:bytes
    document:dict

    @property
    def origin(self):return self.document['site_url']
    @property
    def digest(self):return sha256(self.raw).hexdigest()
    def permits(self,kind,identifier):
        return {'kind':kind,'id':identifier} in self.document['resources']
    def check_evidence(self,snapshot,evidence,*,now=None):
        doc=self.document
        result=assess_compatibility(snapshot,evidence,reviewed_theme_sha256=doc['theme_sha256'],now=now,expected_environment='production')
        if (result['blockers'] or snapshot.site_url!=self.origin or not self.permits(snapshot.resource_type,snapshot.resource_id)
            or evidence.get('wp_version')!=doc['wp_version'] or evidence.get('companion_sha256')!=doc['companion_sha256']
            or evidence.get('production_policy_sha256')!=self.digest):
            raise PermissionError('Production environment does not match reviewed policy')


def read_production_policy(policy_path,receipt_path,release_commit,*,now=None,for_history=False):
    raw=private_file(policy_path,32768);receipt_raw=private_file(receipt_path,32768)
    doc=strict_json(raw);receipt=strict_json(receipt_raw);timestamp=time.time() if now is None else now
    if type(doc) is not dict or set(doc)!=FIELDS or raw!=json.dumps(doc,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode():
        raise ValueError('Canonical private production policy required')
    if (doc['protocol']!='filip-guard-production-v1' or doc['profile']!=PROFILE
        or doc['site_url']!='https://'+_origin(doc['site_url'])
        or type(doc['source_commit']) is not str or not re.fullmatch('[0-9a-f]{40}',doc['source_commit'])
        or doc['source_commit']!=release_commit or type(doc['wp_version']) is not str or not re.fullmatch(r'6\.\d+(?:\.\d+)?',doc['wp_version'])):
        raise ValueError('Reviewed release and canonical origin required')
    for key in ('theme_sha256','companion_sha256','validation_sha256'):
        if type(doc[key]) is not str or not re.fullmatch('[0-9a-f]{64}',doc[key]) or doc[key]=='0'*64:raise ValueError('Reviewed artifact digest required')
    if (type(doc['approved_at']) is not int or type(doc['expires_at']) is not int
        or not doc['approved_at']<=timestamp or (not for_history and timestamp>=doc['expires_at']) or not 0<doc['expires_at']-doc['approved_at']<=3600):
        raise PermissionError('Production admission expired or unavailable')
    if type(doc['content_selector']) is not str or not re.fullmatch(r'[a-z][a-z0-9-]*#post-\{resource_id\}',doc['content_selector']):
        raise ValueError('Reviewed per-resource public content selector required')
    resources=doc['resources']
    if (type(resources) is not list or not 1<=len(resources)<=10 or any(type(r) is not dict or set(r)!={'kind','id'} or r['kind'] not in ('post','page')
        or type(r['id']) is not int or not 0<r['id']<=2147483647 for r in resources)
        or len({(r['kind'],r['id']) for r in resources})!=len(resources)):
        raise ValueError('Bounded exact resource admission required')
    if sha256(receipt_raw).hexdigest()!=doc['validation_sha256'] or type(receipt) is not dict:
        raise PermissionError('Independent validation receipt mismatch')
    required={'protocol','target_origin','validation_origin','environment','source_commit','wp_version','theme_sha256','companion_sha256','content_selector','validated_at','checks'}
    if set(receipt)!=required or receipt['protocol']!='filip-guard-production-validation-v1':raise ValueError('Complete validation receipt required')
    if (receipt['target_origin']!=doc['site_url'] or receipt['validation_origin']==doc['site_url']
        or receipt['validation_origin']!='https://'+_origin(receipt['validation_origin'])
        or receipt['environment'] not in ('local','development','staging')
        or type(receipt['validated_at']) is not int or not 0<=doc['approved_at']-receipt['validated_at']<=604800
        or type(receipt['checks']) is not dict or set(receipt['checks'])!=CHECKS or any(v is not True for v in receipt['checks'].values())
        or any(receipt[k]!=doc[k] for k in ('source_commit','wp_version','theme_sha256','companion_sha256','content_selector'))):
        raise PermissionError('Authorized matching nonproduction validation required')
    actual=sha256((Path(__file__).parent/'wordpress_companion/filip-guard-companion.php').read_bytes()).hexdigest()
    if actual!=doc['companion_sha256']:raise PermissionError('Companion source differs from reviewed release')
    return ProductionPolicy(raw,doc)
