"""New crash boundaries and adversarial receipts, using disposable state only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
import unittest
from unittest.mock import patch
from wordpress_autofix_engine import AutoFixEngine
import test_wordpress_autofix_engine as fixture


class AutoFixFailureBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.AutoFixEngineTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.plan,self.token=self.f.approved()
    def restart(self):return AutoFixEngine(self.f.path,self.f.backups,self.f.gateway)
    def apply(self,engine=None,**session):
        return (engine or self.f.engine).apply(self.plan,self.token,**(self.f.session|session))
    def test_concurrent_call_cannot_duplicate_backup_while_first_upload_is_in_progress(self):
        entered=threading.Event();release=threading.Event();create=self.f.backups.create_backup
        def blocking(*args):
            entered.set()
            if not release.wait(5):raise RuntimeError('Fixture coordination timeout')
            return create(*args)
        with patch.object(self.f.backups,'create_backup',side_effect=blocking) as backup,ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.apply);self.assertTrue(entered.wait(5))
            try:
                second=self.apply(self.restart())
                self.assertEqual(second['status'],'preparing_backup');self.assertFalse(second['changes_applied'])
            finally:release.set()
            self.assertEqual(first.result(timeout=5)['status'],'applied');self.assertEqual(backup.call_count,1)
    def test_crash_during_backup_is_held_on_restart_without_repeat(self):
        with patch.object(self.f.backups,'create_backup',side_effect=SystemExit):
            with self.assertRaises(SystemExit):self.apply()
        with patch.object(self.f.backups,'create_backup') as backup,patch.object(self.f.gateway,'compare_and_swap') as write:
            result=self.apply(self.restart());backup.assert_not_called();write.assert_not_called()
        self.assertEqual(result['status'],'preparing_backup');self.assertTrue(result['requires_intervention'])
        self.assertEqual(self.f.read().revision,'1')
    def test_crash_after_consumption_retains_verified_backup_and_does_not_reconsume(self):
        consume=self.f.engine.approvals.consume_for_offline_review
        def crashed(*args,**kwargs):consume(*args,**kwargs);raise SystemExit()
        with patch.object(self.f.engine.approvals,'consume_for_offline_review',side_effect=crashed):
            with self.assertRaises(SystemExit):self.apply()
        result=self.apply(self.restart());self.assertEqual(result['status'],'preparing_backup')
        self.assertEqual(self.f.backups.get_backup(result['backup_id'])['content'],'<p>Old</p>\n')
        self.assertEqual(self.f.read().revision,'1')
    def test_expiry_during_backup_retains_hold_and_prevents_remote_write(self):
        clock=[100];read=self.f.backups.get_backup
        def late(*args):
            value=read(*args);clock[0]=400;return value
        with patch('wordpress_autofix_engine.time.time',side_effect=lambda:clock[0]),patch.object(self.f.backups,'get_backup',side_effect=late):
            with self.assertRaises(PermissionError):self.apply(now=None)
        result=self.apply(self.restart());self.assertEqual(result['status'],'preparing_backup')
        self.assertIsNotNone(result['backup_id']);self.assertEqual(self.f.read().revision,'1')
    def test_malformed_write_receipt_never_triggers_automatic_rollback(self):
        compare=self.f.gateway.compare_and_swap
        def invalid(*args,**kwargs):return replace(compare(*args,**kwargs),revision=' ')
        with patch.object(self.f.gateway,'compare_and_swap',side_effect=invalid) as write:
            result=self.apply();self.assertEqual(write.call_count,1)
        self.assertEqual(result['status'],'outcome_unknown');self.assertIsNone(result['changes_applied'])
    def test_foreign_rollback_receipt_cannot_be_reported_as_verified_restore(self):
        read=self.f.gateway.read_authorized;compare=self.f.gateway.compare_and_swap;count=0
        def interrupted(*args):
            nonlocal count
            count+=1
            if count==2:raise TimeoutError()
            return read(*args)
        def wrong_target(*args,**kwargs):
            result=compare(*args,**kwargs)
            return replace(result,resource_id=999) if kwargs['operation_id'].endswith(':rollback') else result
        with patch.object(self.f.gateway,'read_authorized',side_effect=interrupted),patch.object(self.f.gateway,'compare_and_swap',side_effect=wrong_target):result=self.apply()
        self.assertEqual(result['status'],'rollback_unverified');self.assertTrue(result['requires_intervention'])
    def test_crash_after_write_stays_applying_without_replaying_remote_operation(self):
        read=self.f.gateway.read_authorized;count=0
        def crashed(*args):
            nonlocal count
            count+=1
            if count==2:raise SystemExit()
            return read(*args)
        with patch.object(self.f.gateway,'read_authorized',side_effect=crashed):
            with self.assertRaises(SystemExit):self.apply()
        with patch.object(self.f.gateway,'compare_and_swap') as write:
            result=self.apply(self.restart());write.assert_not_called()
        self.assertEqual(result['status'],'applying');self.assertIsNone(result['changes_applied'])
        self.assertEqual(self.f.read().revision,'2')
