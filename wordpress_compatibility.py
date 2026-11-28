"""Conservative content profile and bound offline environment assessment.

Diagnostic evidence never authorizes a production write or replaces live tests.
"""
from hashlib import sha256
import re
import time
from wordpress_revision_guard import ResourceSnapshot

PROFILE='classic-html-link-v1'
PATTERN=r'<!--\s*wp:|\[/?[A-Za-z][A-Za-z0-9_-]*(?:\s[^\]]*)?/?\]|data-(?:elementor|vc|fl)-|et_pb_|fl-builder'


def require_content_profile(content):
    if type(content) is not str or len(content.encode('utf-8'))>1_000_000 or re.search(PATTERN,content,re.I):
        raise ValueError('Unsupported WordPress content profile; manual compatibility review required')
    return PROFILE


def assess_compatibility(snapshot,evidence=None,*,reviewed_theme_sha256=None,now=None,expected_environment=None):
    if type(snapshot) is not ResourceSnapshot:raise ValueError('Trusted resource snapshot required')
    blockers=[]
    try:require_content_profile(snapshot.content)
    except ValueError:blockers.append('unsupported-content-format')
    if type(evidence) is not dict:blockers.append('authenticated-environment-evidence-required')
    else:
        expected={'site_url':snapshot.site_url,'resource_type':snapshot.resource_type,'resource_id':snapshot.resource_id,
                  'revision':snapshot.revision,'content_sha256':sha256(snapshot.content.encode()).hexdigest()}
        if any(evidence.get(k)!=v for k,v in expected.items()):blockers.append('resource-evidence-binding')
        stamp=evidence.get('observed_at');timestamp=time.time() if now is None else now
        if type(stamp) not in (int,float) or not stamp<=timestamp<stamp+300:blockers.append('stale-environment-evidence')
        environments=('production',) if expected_environment=='production' else ('local','development','staging')
        if evidence.get('environment') not in environments:blockers.append('reviewed-validation-environment-required' if expected_environment else 'nonproduction-validation-environment-required')
        if type(evidence.get('wp_version')) is not str or not (re.fullmatch(r'6\.\d+(?:\.\d+)?',evidence['wp_version']) or evidence['wp_version']=='7.1.5'):blockers.append('wordpress-version-review')
        if evidence.get('multisite') is not False:blockers.append('multisite-unsupported-or-unknown')
        plugins=evidence.get('active_plugins')
        if type(plugins) is not list or any(p!='filip-guard-companion/filip-guard-companion.php' for p in plugins):blockers.append('plugin-profile-review')
        if evidence.get('mu_plugins')!=[] or evidence.get('dropins')!=[]:blockers.append('mu-or-dropin-profile-review')
        metadata=evidence.get('metadata_keys')
        if type(metadata) is not list or any(k not in ('_edit_lock','_edit_last','_wp_old_slug','_wp_page_template','_thumbnail_id') for k in metadata):blockers.append('resource-metadata-review')
        theme=evidence.get('theme_sha256')
        if type(reviewed_theme_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',reviewed_theme_sha256) or theme!=reviewed_theme_sha256:blockers.append('theme-profile-review')
    return {'profile':PROFILE,'eligible_for_isolated_validation':not blockers,'blockers':blockers,
            'production_write_authorized':False,'live_compatibility_proven':False}
