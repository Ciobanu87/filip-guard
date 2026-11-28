"""A fresh authenticated observation can inform recovery, never clear its hold."""
import unittest
from unittest.mock import patch
import test_guard_application as fixture


class RecoveryReviewTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.UnifiedFlowTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.review=self.f.proposal();self.plan=self.review['plan_id']
        engine,identity,_=self.f.sites._context(self.f.a,self.f.site_a,require_external=True)
        approval=engine.approve(self.plan,confirmed=True,**identity)
        self.backend=self.f.backends[self.f.origins[0]];compare=self.backend.compare_and_swap
        def lost(*args,**kwargs):compare(*args,**kwargs);raise TimeoutError('Fixture reply lost')
        with patch.object(self.backend,'compare_and_swap',side_effect=lost):
            self.result=engine.apply(self.plan,approval,**identity)
        self.assertEqual(self.result['status'],'outcome_unknown')
    def test_proposed_content_does_not_prove_success_or_permit_repeat_even_after_new_login(self):
        self.f.auth.logout(self.f.a);self.f.a=self.f.auth.login('alice','Alice-unified-password')
        with patch.object(self.backend,'compare_and_swap') as write,patch.object(self.f.store,'get') as download:
            report=self.f.application.recovery_review(self.f.a,self.f.site_a,self.plan)
            write.assert_not_called();download.assert_not_called()
        self.assertEqual(report['observed_content'],'proposed');self.assertFalse(report['operation_outcome_proven'])
        self.assertFalse(report['mutations_authorized']);self.assertFalse(report['automatic_retry_allowed'])
        self.assertEqual(report['backup_id'],self.result['backup_id'])
        self.assertEqual(self.f.sites.repair_record(self.f.a,self.f.site_a,self.plan)['result'],self.result)
        with self.assertRaises(PermissionError):self.f.application.renew_review(self.f.a,self.f.site_a,self.plan)
    def test_later_original_bytes_are_not_mislabeled_as_verified_rollback(self):
        current=self.backend.read_authorized(self.f.origins[0],'post',1,7)
        self.backend.compare_and_swap(current,self.review['original']['content'],7,operation_id='independent-later-editor')
        report=self.f.application.recovery_review(self.f.a,self.f.site_a,self.plan)
        self.assertEqual(report['observed_content'],'original');self.assertFalse(report['original_version_matches'])
        self.assertFalse(report['operation_outcome_proven']);self.assertTrue(report['requires_intervention'])
    def test_other_customer_is_blocked_before_resource_read(self):
        with patch.object(self.backend,'read_authorized') as read:
            with self.assertRaises(PermissionError):self.f.application.recovery_review(self.f.b,self.f.site_a,self.plan)
            read.assert_not_called()
