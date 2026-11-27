"""Offline pre-upload guards; no production credentials, storage or API traffic."""
import unittest
from deployment.oracle_b2_readonly_inspect import provider_notification_disabled,validate_existing_backup


class B2ManualValidationGuards(unittest.TestCase):
    def test_exact_provider_feature_disabled_response(self):
        self.assertTrue(provider_notification_disabled(400,'bad_request','API not enabled'))
        self.assertTrue(provider_notification_disabled(400,'bad_request','This API is not enabled.'))

    def test_permission_and_other_errors_never_prove_feature_disabled(self):
        for status,code,message in [(403,'unauthorized','API not enabled'),(400,'bad_request','API not enabled for this key only'),(400,'bad_request','Missing bucketId'),(400,'bad_request','prefix restriction')]:
            self.assertFalse(provider_notification_disabled(status,code,message))

    def attempt(self,*,report=None,prefix=None,versions=None,unfinished=None):
        calls=[]
        responses=[versions if versions is not None else {'files':[]},unfinished if unfinished is not None else {'files':[]}]
        def get(*args,**kwargs):calls.append(kwargs['body']);return responses.pop(0)
        with self.assertRaises(ValueError):
            validate_existing_backup({},None,None,get,{'authorizationToken':'synthetic'},
                {'apiUrl':'https://api001.backblazeb2.com','allowed':{'namePrefix':prefix}},
                {'id':'synthetic'},report if report is not None else {'notification_cost_guard_verified':True})
        return calls

    def test_missing_notification_guard_stops_before_inventory(self):
        self.assertEqual(self.attempt(report={}),[])

    def test_prefix_restriction_never_weakens_scope(self):
        self.assertEqual(self.attempt(prefix='restricted/'),[])

    def test_paginated_inventory_cannot_be_treated_as_complete(self):
        self.assertEqual(len(self.attempt(versions={'files':[],'nextFileName':'next'})),1)

    def test_unfinished_uploads_block_before_state_or_external_write(self):
        self.assertEqual(len(self.attempt(unfinished={'files':[{'fileId':'synthetic'}]})),2)

    def test_insufficient_free_headroom_blocks_before_state_or_write(self):
        self.assertEqual(len(self.attempt(versions={'files':[{'contentLength':10_000_000_000}]})),2)


if __name__=='__main__':unittest.main()
