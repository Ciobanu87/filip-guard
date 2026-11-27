from hashlib import sha256
import unittest
from wordpress_compatibility import require_content_profile,assess_compatibility
from wordpress_revision_guard import ResourceSnapshot


class CompatibilityProfileTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=ResourceSnapshot('https://example.test','post',1,'<p><a href="/old">Link</a></p>','a'*64)
        self.evidence=dict(site_url=self.snapshot.site_url,resource_type='post',resource_id=1,revision='a'*64,
            content_sha256=sha256(self.snapshot.content.encode()).hexdigest(),observed_at=100,
            environment='staging',wp_version='6.8',multisite=False,active_plugins=['filip-guard-companion/filip-guard-companion.php'],
            mu_plugins=[],dropins=[],metadata_keys=[],theme_sha256='b'*64)
    def test_classic_html_is_candidate_not_production_authority(self):
        result=assess_compatibility(self.snapshot,self.evidence,reviewed_theme_sha256='b'*64,now=101)
        self.assertTrue(result['eligible_for_isolated_validation']);self.assertFalse(result['production_write_authorized'])
        self.assertFalse(result['live_compatibility_proven'])
    def test_unknown_environment_never_passes(self):
        self.assertFalse(assess_compatibility(self.snapshot)['eligible_for_isolated_validation'])
    def test_unsupported_editors_shortcodes_and_builder_markup_fail_closed(self):
        for content in ('<!-- wp:paragraph --><p>x</p>','[gallery ids="1"]','<div data-elementor-id="1">x</div>'):
            with self.assertRaises(ValueError):require_content_profile(content)
    def test_cross_resource_or_stale_evidence_is_rejected(self):
        for change in ({'resource_id':2},{'revision':'c'*64},{'observed_at':-1000},{'site_url':'https://other.test'}):
            self.assertFalse(assess_compatibility(self.snapshot,{**self.evidence,**change},reviewed_theme_sha256='b'*64,now=101)['eligible_for_isolated_validation'])
    def test_plugins_builders_multisite_and_unreviewed_themes_remain_blockers(self):
        for change in ({'active_plugins':['builder/plugin.php']},{'multisite':True},{'metadata_keys':['_elementor_data']},{'mu_plugins':['unknown.php']},{'theme_sha256':'c'*64}):
            self.assertFalse(assess_compatibility(self.snapshot,{**self.evidence,**change},reviewed_theme_sha256='b'*64,now=101)['eligible_for_isolated_validation'])

    def test_gateway_collects_only_authenticated_bound_diagnostics_without_writes(self):
        from unittest.mock import patch
        from wordpress_rest_gateway import WordPressRESTGateway
        gateway=WordPressRESTGateway(self.snapshot.site_url,lambda:('fixture','synthetic'))
        payload={'protocol':'filip-guard-compatibility-v1','snapshot':{
            'protocol':'filip-guard-cas-v1','resource_id':1,'resource_type':'post','user_id':7,'can_edit':True,
            'content':self.snapshot.content,'version':self.snapshot.revision},'evidence':{**self.evidence,'site_url':'https://forged.test'}}
        with patch.object(gateway,'_identity') as identity,patch.object(gateway,'_request',return_value=(None,payload)) as request:
            result=gateway.assess_compatibility(self.snapshot.site_url,'post',1,7,reviewed_theme_sha256='b'*64,now=101)
        self.assertTrue(result['eligible_for_isolated_validation'])
        self.assertFalse(result['production_write_authorized'])
        identity.assert_called_once_with(7)
        request.assert_called_once_with('/wp-json/filip-guard/v1/resources/post/1/compatibility')
        payload['evidence']['revision']='c'*64
        with patch.object(gateway,'_identity'),patch.object(gateway,'_request',return_value=(None,payload)):
            result=gateway.assess_compatibility(self.snapshot.site_url,'post',1,7,reviewed_theme_sha256='b'*64,now=101)
        self.assertIn('resource-evidence-binding',result['blockers'])
