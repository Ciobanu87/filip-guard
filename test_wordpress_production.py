"""Production branch against disposable fixtures only; no external calls/activation."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch,Mock
from wordpress_production_policy import read_production_policy,CHECKS
from wordpress_production import (ProductionGuardApplication,ProductionCustomerSites,ProductionWordPressGateway,
    configured_production_application,verify_rendered_change)
from wordpress_revision_guard import ResourceSnapshot
import test_guard_application as fixture


def artifacts(root,origin='https://controlled.example'):
    now=int(time.time());commit='c'*40
    receipt=dict(protocol='filip-guard-production-validation-v1',target_origin=origin,validation_origin='https://disposable.test',
        environment='staging',source_commit=commit,wp_version='7.1.5',theme_sha256='b'*64,
        companion_sha256=sha256(Path('wordpress_companion/filip-guard-companion.php').read_bytes()).hexdigest(),
        content_selector='article#post-{resource_id}',validated_at=now-60,checks=dict.fromkeys(CHECKS,True))
    receipt_path=root/'validation.json';receipt_path.write_text(json.dumps(receipt));receipt_path.chmod(0o400)
    policy={k:receipt[k] for k in ('source_commit','wp_version','theme_sha256','companion_sha256','content_selector')}
    policy.update(protocol='filip-guard-production-v1',profile='classic-html-link-v1',site_url=origin,
        resources=[dict(kind='post',id=1)],approved_at=now-1,expires_at=now+600,validation_sha256=sha256(receipt_path.read_bytes()).hexdigest())
    policy_path=root/'policy.json'
    def write():
        if policy_path.exists():policy_path.chmod(0o600)
        policy_path.write_text(json.dumps(policy,sort_keys=True,separators=(',',':')));policy_path.chmod(0o400)
    write()
    return policy_path,receipt_path,policy,receipt,write,commit


class ProductionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.path,self.receipt_path,self.doc,self.receipt,self.write,self.commit=artifacts(self.root)
    def read(self,**kwargs):return read_production_policy(self.path,self.receipt_path,self.commit,**kwargs)
    def test_default_off_reads_no_policy_state_key_or_provider(self):
        with patch.dict(os.environ,{},clear=True),patch('wordpress_production.read_production_policy') as policy:
            self.assertIsNone(configured_production_application());policy.assert_not_called()
    def test_valid_artifacts_admit_only_exact_origin_release_and_resources(self):
        policy=self.read();self.assertEqual(policy.origin,'https://controlled.example')
        self.assertTrue(policy.permits('post',1));self.assertFalse(policy.permits('page',1))
        with self.assertRaises(ValueError):read_production_policy(self.path,self.receipt_path,'d'*40)
    def test_unvalidated_versions_do_not_inherit_production_support(self):
        for version in ('6.8','7.1.4','7.1.6','7.2'):
            self.doc['wp_version']=version;self.write()
            with self.assertRaises(ValueError):self.read()

    def test_expiry_can_preserve_history_scope_but_never_write_admission(self):
        future=self.doc['expires_at']+1
        with self.assertRaises(PermissionError):self.read(now=future)
        self.assertEqual(self.read(now=future,for_history=True).origin,self.doc['site_url'])
    def test_missing_false_or_mismatched_validation_cannot_admit(self):
        self.receipt['checks']['rollback']=False
        self.receipt_path.chmod(0o600);self.receipt_path.write_text(json.dumps(self.receipt));self.doc['validation_sha256']=sha256(self.receipt_path.read_bytes()).hexdigest();self.write()
        with self.assertRaises(PermissionError):self.read()
    def test_public_file_duplicate_noncanonical_and_expanded_scope_fail(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):self.read()
        self.write();self.path.chmod(0o600);self.path.write_text(self.path.read_text()+'\n')
        with self.assertRaises(ValueError):self.read()
        self.doc['resources']*=2;self.write()
        with self.assertRaises(ValueError):self.read()
    def test_same_origin_trial_wrong_source_or_companion_is_not_accepted(self):
        for field,value in (('validation_origin',self.doc['site_url']),('source_commit','d'*40),('companion_sha256','e'*64)):
            original=deepcopy(self.receipt);self.receipt[field]=value
            self.receipt_path.chmod(0o600);self.receipt_path.write_text(json.dumps(self.receipt));self.doc['validation_sha256']=sha256(self.receipt_path.read_bytes()).hexdigest();self.write()
            with self.assertRaises((PermissionError,ValueError)):self.read()
            self.receipt=original
    def test_production_scope_does_not_relax_the_existing_test_origin_gate(self):
        from guard_application import GuardApplication
        policy=self.read();sites=Mock();sites.auth=Mock()
        with self.assertRaises(ValueError):GuardApplication(sites,Mock(),authorized_test_origins=[policy.origin])
        app=ProductionGuardApplication(sites,Mock(),policy_provider=lambda:policy)
        self.assertEqual(app.origins,frozenset((policy.origin,)))

    def test_gateway_rechecks_revocation_before_network(self):
        policy=self.read();provider=Mock(return_value=policy)
        gateway=ProductionWordPressGateway(policy.origin,lambda:('fixture','synthetic'),provider)
        provider.side_effect=PermissionError('Revoked')
        with patch('wordpress_secure_https.create_verified_connection') as network:
            with self.assertRaises(PermissionError):gateway.read_authorized(policy.origin,'post',1,7)
            network.assert_not_called()
    def test_gateway_rejects_unadmitted_resource_before_network(self):
        policy=self.read();gateway=ProductionWordPressGateway(policy.origin,lambda:('fixture','synthetic'),lambda:policy)
        with patch('wordpress_secure_https.create_verified_connection') as network:
            with self.assertRaises(PermissionError):gateway.read_authorized(policy.origin,'page',1,7)
            network.assert_not_called()
    def test_profile_and_remote_policy_digest_must_match_fresh_snapshot(self):
        policy=self.read();snapshot=ResourceSnapshot(policy.origin,'post',1,'<a href="/old">x</a>','a'*64)
        evidence=dict(site_url=policy.origin,resource_type='post',resource_id=1,revision='a'*64,content_sha256=sha256(snapshot.content.encode()).hexdigest(),
            observed_at=time.time(),environment='production',wp_version='7.1.5',multisite=False,active_plugins=['filip-guard-companion/filip-guard-companion.php'],
            mu_plugins=[],dropins=[],metadata_keys=[],theme_sha256='b'*64,companion_sha256=self.doc['companion_sha256'],production_policy_sha256=policy.digest)
        policy.check_evidence(snapshot,evidence)
        policy.check_evidence(snapshot,{**evidence,'metadata_keys':['_pingme','_encloseme','_trackbackme','_wp_old_date','_wp_desired_post_slug']})
        for change in ({'wp_version':'6.9'},{'production_policy_sha256':'e'*64},{'active_plugins':['unknown/plugin.php']},{'observed_at':0}):
            with self.assertRaises(PermissionError):policy.check_evidence(snapshot,{**evidence,**change})


class ProductionFlowTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.UnifiedFlowTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.path,self.receipt,self.doc,_,self.write,self.commit=artifacts(self.f.root,self.f.origins[0])
        self.provider=lambda:read_production_policy(self.path,self.receipt,self.commit)
        self.sites=ProductionCustomerSites(self.f.auth,self.f.sites.root,lambda _:self.f.master,active_key_id='test-key',
            object_store=self.f.store,gateway_factory=self.f.factory,policy_provider=self.provider)
        self.app=ProductionGuardApplication(self.sites,self.f.monitor,policy_provider=self.provider,scanner=self.f.public_scan,probe=lambda *_:True)
        self.backend=self.f.backends[self.f.origins[0]]
    def proposal(self):
        scan=self.app.scan(self.f.a,self.f.site_a,start_url=self.f.origins[0]+'/source/',page_limit=1)
        option=self.app.proposals(self.f.a,self.f.site_a,scan['scan_id'])[0]
        return self.app.prepare_repair(self.f.a,self.f.site_a,scan['scan_id'],option['issue_key'],1,self.f.origins[0]+'/destination/')
    def rendered(self,*args):return '<article id="post-1">'+self.backend.read_authorized(self.f.origins[0],'post',1,7).content+'</article>'
    def test_complete_diagnosis_approval_backup_independent_verify_and_manual_restore(self):
        review=self.proposal()
        with patch('wordpress_production.public_page',side_effect=self.rendered),patch('wordpress_production.verify_public_replacement',return_value=True):
            applied=self.app.approve_and_apply(self.f.a,self.f.site_a,review['plan_id'],confirmed=True)
            self.assertEqual(applied['status'],'applied');self.assertTrue(self.f.store.objects)
            restore=self.app.prepare_restore(self.f.a,self.f.site_a,review['plan_id'])
            self.assertEqual(self.app.approve_and_apply(self.f.a,self.f.site_a,restore['plan_id'],confirmed=True)['status'],'applied')
        self.assertIn('missing-destination',self.backend.read_authorized(self.f.origins[0],'post',1,7).content)
    def test_stale_public_page_triggers_verified_conditional_rollback(self):
        review=self.proposal();old=review['original']['content']
        with patch('wordpress_production.public_page',return_value='<article id="post-1">'+old+'</article>'):
            result=self.app.approve_and_apply(self.f.a,self.f.site_a,review['plan_id'],confirmed=True)
        self.assertEqual(result['status'],'rolled_back');self.assertFalse(result['changes_applied'])
    def test_unverified_public_restore_stays_held(self):
        review=self.proposal()
        with patch('wordpress_production.public_page',return_value='<article id="post-1">Unavailable</article>'):
            result=self.app.approve_and_apply(self.f.a,self.f.site_a,review['plan_id'],confirmed=True)
        self.assertEqual(result['status'],'rollback_unverified');self.assertTrue(result['requires_intervention'])
    def test_direct_content_plan_without_registered_diagnosis_cannot_reach_backup(self):
        review=self.sites.propose(self.f.a,self.f.site_a,'post',1,'<p>Unrelated content</p>')
        token=self.sites.approve(self.f.a,self.f.site_a,review['plan_id'],confirmed=True)
        with self.assertRaises((ValueError,PermissionError)):self.sites.apply(self.f.a,self.f.site_a,review['plan_id'],token)
        self.assertEqual(self.f.store.objects,{})
    def test_admission_revoked_during_backup_stops_write_and_keeps_local_history(self):
        review=self.proposal();put=self.f.store.put
        def revoked(*args):
            put(*args);self.path.unlink()
        with patch.object(self.f.store,'put',side_effect=revoked):
            with self.assertRaises((ValueError,PermissionError)):self.app.approve_and_apply(self.f.a,self.f.site_a,review['plan_id'],confirmed=True)
        self.assertFalse(self.app.write_admission_active())
        history=self.app.history(self.f.a,self.f.site_a)
        self.assertEqual(history[0]['repair']['state'],'preparing_backup')
        self.assertIn('missing-destination',self.backend.read_authorized(self.f.origins[0],'post',1,7).content)
    def test_concurrent_edit_during_independent_check_wins_over_automatic_rollback(self):
        review=self.proposal();current=self.backend.read_authorized
        def later(*args):
            snapshot=current(self.f.origins[0],'post',1,7)
            self.backend.compare_and_swap(snapshot,'<p>Later independent edit</p>',7,operation_id='later-public-check-edit')
            return '<article id="post-1">Not verified</article>'
        with patch('wordpress_production.public_page',side_effect=later):
            result=self.app.approve_and_apply(self.f.a,self.f.site_a,review['plan_id'],confirmed=True)
        self.assertEqual(result['status'],'rollback_conflict')
        self.assertEqual(current(self.f.origins[0],'post',1,7).content,'<p>Later independent edit</p>')

    def test_other_customer_cannot_approve_or_read_recovery_history(self):
        review=self.proposal()
        with self.assertRaises(PermissionError):self.app.approve_and_apply(self.f.b,self.f.site_a,review['plan_id'],confirmed=True)
        with self.assertRaises(PermissionError):self.app.history(self.f.b,self.f.site_a)


class PublicVerificationTests(unittest.TestCase):
    def test_container_counts_are_independent_of_navigation_links(self):
        original=ResourceSnapshot('https://example.test','post',1,'<a href="/old">x</a>','1')
        written=replace(original,content='<a href="/new">x</a>',revision='2')
        self.assertTrue(verify_rendered_change(original,written,'https://example.test/source','article#post-{resource_id}',
            '<nav><a href="/old">old</a></nav><article id="post-1"><a href="/new">x</a></article>'))
        for html in ('<article id="post-1"><a href="/old">x</a></article>','<article id="post-1"></article><article id="post-1"></article>',
                     '<base href="https://other.test"><article id="post-1"><a href="/new">x</a></article>'):
            with self.assertRaises(ValueError):verify_rendered_change(original,written,'https://example.test/source','article#post-{resource_id}',html)
