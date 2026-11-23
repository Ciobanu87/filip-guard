import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from backup import BackupManager
from wordpress_autofix_engine import AutoFixEngine, LiveAutoFixDisabled
from wordpress_local_fixture import LocalWordPressFixture
from wordpress_revision_guard import RevisionMismatchError


class AutoFixEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, 'engine.sqlite')
        self.backups = BackupManager(os.path.join(self.temp.name, 'backups.sqlite'))
        self.gateway = LocalWordPressFixture(os.path.join(self.temp.name, 'fixture.sqlite'))
        self.site = 'https://example.com'
        self.gateway.seed(self.site, 'post', 10, '<p>Old</p>\n', user_id=7)
        self.engine = AutoFixEngine(self.path, self.backups, self.gateway)
        self.session = dict(user_id=7, session_id='a' * 43, now=100)
        self.target = dict(site_url=self.site, resource_type='post', resource_id=10)

    def plan(self):
        return self.engine.propose(**self.target, **self.session, proposed_content='<p>New</p>\n')['plan_id']

    def approved(self):
        plan = self.plan()
        token = self.engine.approve(plan, **self.session, confirmed=True)
        return plan, token

    def read(self):
        return self.gateway.read_authorized(self.site, 'post', 10, 7)

    def test_preview_then_explicit_approval_then_apply_and_backup(self):
        plan = self.plan()
        review = self.engine.review(plan, **self.session)
        self.assertIn('-<p>Old</p>', review['diff'])
        self.assertIn('+<p>New</p>', review['diff'])
        self.assertEqual(self.read().content, '<p>Old</p>\n')
        with self.assertRaises(PermissionError):
            self.engine.approve(plan, **self.session)
        token = self.engine.approve(plan, **self.session, confirmed=True)
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'applied')
        self.assertTrue(result['changes_applied'])
        self.assertEqual(self.read().content, '<p>New</p>\n')
        self.assertEqual(self.backups.get_backup(result['backup_id'])['content'], '<p>Old</p>\n')
        self.assertEqual(result['backup_scope'], 'resource_content_only')

    def test_restart_and_replay_return_saved_result_without_new_write(self):
        plan, token = self.approved()
        result = self.engine.apply(plan, token, **self.session)
        restarted = AutoFixEngine(self.path, self.backups, self.gateway)
        self.assertEqual(restarted.apply(plan, token, **self.session), result)
        self.assertEqual(self.read().revision, '2')

    def test_unapproved_or_wrong_token_cannot_write(self):
        plan = self.plan()
        with self.assertRaises(PermissionError):
            self.engine.apply(plan, 'forged', **self.session)
        self.assertEqual(self.read().revision, '1')

    def test_wrong_session_and_wrong_user_rejected(self):
        plan, token = self.approved()
        for session in (self.session | {'user_id': 8}, self.session | {'session_id': 'b' * 43}):
            for call in (lambda: self.engine.review(plan, **session),
                         lambda: self.engine.apply(plan, token, **session)):
                with self.assertRaises(PermissionError):
                    call()
        self.assertEqual(self.read().revision, '1')

    def test_token_cannot_cross_resource_types_with_same_id_and_content(self):
        self.gateway.seed(self.site, 'page', 10, '<p>Old</p>\n', user_id=7)
        post, post_token = self.approved()
        page = self.engine.propose(**(self.target | {'resource_type': 'page'}),
            **self.session, proposed_content='<p>New</p>\n')['plan_id']
        self.engine.approve(page, **self.session, confirmed=True)
        with self.assertRaises(PermissionError):
            self.engine.apply(page, post_token, **self.session)
        self.assertEqual(self.read().revision, '1')

    def test_expired_approval_or_proposal_rejected(self):
        plan, token = self.approved()
        with self.assertRaises(PermissionError):
            self.engine.apply(plan, token, **(self.session | {'now': 400}))
        with self.assertRaises(PermissionError):
            self.engine.review(plan, **(self.session | {'now': 1000}))
        self.assertEqual(self.read().revision, '1')

    def test_unsupported_repairs_and_resource_permissions_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.propose(**self.target, **self.session, proposed_content='new', repair_type='plugin_update')
        with self.assertRaises(PermissionError):
            self.engine.propose(**self.target, **(self.session | {'user_id': 8}), proposed_content='new')

    def test_permissions_rechecked_at_approval(self):
        plan = self.plan()
        with sqlite3.connect(self.gateway.database_path) as db:
            db.execute('DELETE FROM editors')
        with self.assertRaises(PermissionError):
            self.engine.approve(plan, **self.session, confirmed=True)

    def test_stale_snapshot_rejected_before_backup(self):
        plan, token = self.approved()
        self.gateway.compare_and_swap(self.read(), 'Other editor', 7, operation_id='other')
        with patch.object(self.backups, 'create_backup') as backup:
            with self.assertRaises(RevisionMismatchError):
                self.engine.apply(plan, token, **self.session)
            backup.assert_not_called()

    def test_race_after_read_is_blocked_by_atomic_condition(self):
        plan, token = self.approved()
        compare = self.gateway.compare_and_swap
        def concurrent(expected, content, user_id, *, operation_id):
            compare(expected, 'Concurrent edit', user_id, operation_id='racer')
            return compare(expected, content, user_id, operation_id=operation_id)
        with patch.object(self.gateway, 'compare_and_swap', side_effect=concurrent):
            result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(self.read().content, 'Concurrent edit')

    def test_failed_or_corrupt_backup_blocks_write_and_preserves_approval(self):
        for failure in (OSError('disk full'), None):
            plan, token = self.approved()
            with patch.object(self.backups, 'get_backup', **(
                    {'side_effect': failure} if failure else {'return_value': None})):
                with self.assertRaises((RuntimeError, OSError)):
                    self.engine.apply(plan, token, **self.session)
            result = self.engine.apply(plan, token, **self.session)
            self.assertEqual(result['status'], 'applied')
            self.gateway.compare_and_swap(self.read(), '<p>Old</p>\n', 7, operation_id='reset-' + plan)

    def test_verification_failure_rolls_back_conditionally(self):
        plan, token = self.approved()
        read = self.gateway.read_authorized
        count = 0
        def flaky(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise TimeoutError('verification unavailable')
            return read(*args)
        with patch.object(self.gateway, 'read_authorized', side_effect=flaky):
            result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'rolled_back')
        self.assertEqual(self.read().content, '<p>Old</p>\n')
        self.assertEqual(self.read().revision, '3')

    def test_rollback_cannot_overwrite_later_editor_change(self):
        plan, token = self.approved()
        read, compare = self.gateway.read_authorized, self.gateway.compare_and_swap
        count = 0
        def later_edit(*args):
            nonlocal count
            count += 1
            if count == 2:
                compare(read(*args), 'Later editor change', 7, operation_id='late')
            return read(*args)
        with patch.object(self.gateway, 'read_authorized', side_effect=later_edit):
            result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'rollback_conflict')
        self.assertTrue(result['requires_intervention'])
        self.assertEqual(self.read().content, 'Later editor change')

    def test_uncertain_write_is_not_repeated_or_blindly_rolled_back(self):
        plan, token = self.approved()
        compare = self.gateway.compare_and_swap
        def lost_receipt(*args, **kwargs):
            compare(*args, **kwargs)
            raise TimeoutError('reply lost after commit')
        with patch.object(self.gateway, 'compare_and_swap', side_effect=lost_receipt) as write:
            result = self.engine.apply(plan, token, **self.session)
            replay = self.engine.apply(plan, token, **self.session)
            self.assertEqual(write.call_count, 1)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(replay, result)
        self.assertIsNone(result['changes_applied'])
        self.assertTrue(result['requires_intervention'])
        self.assertEqual(self.read().revision, '2')

    def test_failed_rollback_is_explicit(self):
        plan, token = self.approved()
        read, compare = self.gateway.read_authorized, self.gateway.compare_and_swap
        count = 0
        def verification_error(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise TimeoutError()
            return read(*args)
        def rollback_error(*args, **kwargs):
            if kwargs['operation_id'].endswith(':rollback'):
                raise ConnectionError()
            return compare(*args, **kwargs)
        with patch.object(self.gateway, 'read_authorized', side_effect=verification_error), \
             patch.object(self.gateway, 'compare_and_swap', side_effect=rollback_error):
            result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'rollback_unverified')
        self.assertTrue(result['requires_intervention'])

    def test_concurrent_execution_has_at_most_one_writer(self):
        plan, token = self.approved()
        def run(_):
            try:
                return self.engine.apply(plan, token, **self.session)
            except (PermissionError, RevisionMismatchError):
                return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(run, range(6)))
        self.assertTrue(any(r and r.get('status') == 'applied' for r in results))
        self.assertEqual(self.read().revision, '2')

    def test_default_gateway_never_enables_wordpress(self):
        engine = AutoFixEngine(self.path, self.backups)
        with patch('socket.create_connection') as network:
            with self.assertRaises(LiveAutoFixDisabled):
                engine.propose(**self.target, **self.session, proposed_content='new')
            network.assert_not_called()

    def test_fixture_idempotency_and_permissions_are_atomic(self):
        original = self.read()
        result = self.gateway.compare_and_swap(original, 'New', 7, operation_id='once')
        self.assertEqual(self.gateway.compare_and_swap(original, 'New', 7, operation_id='once'), result)
        with self.assertRaises(PermissionError):
            self.gateway.compare_and_swap(original, 'Different', 7, operation_id='once')
        with self.assertRaises(PermissionError):
            self.gateway.compare_and_swap(result, 'Forbidden', 8, operation_id='forbidden')
        self.assertEqual(self.read().revision, '2')
