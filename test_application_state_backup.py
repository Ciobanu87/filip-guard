import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import application_state_backup as state
from customer_auth import CustomerAuth, private_database
from operations_state_backup import main


class Store:
    def __init__(self): self.objects = {}; self.puts = 0
    def put(self, name, data): self.puts += 1; self.objects[name] = data
    def get(self, name): return self.objects[name]


class ApplicationStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root / 'source'; self.source.mkdir(mode=0o700)
        self.store = Store(); self.master = b'x' * 32; self.keys = lambda version: self.master
        self.did = 'a' * 32
        self.auth = CustomerAuth(self.source / 'accounts.sqlite')
        self.auth.register('alice', 'Synthetic-password-123')
        self.nested = self.source / 'workspaces'; self.nested.mkdir(mode=0o700)
        db = sqlite3.connect(private_database(self.nested / 'repairs.sqlite'))
        db.execute('CREATE TABLE proof (value TEXT)'); db.execute('INSERT INTO proof VALUES (?)', ('uncertain-write',)); db.commit(); db.close()

    def export(self, **kwargs):
        return state.export_application_state(self.source, self.store, self.keys,
            deployment_id=self.did, key_id='v1', quiesced=True, **kwargs)

    def recover(self, receipt=None, destination=None, keys=None):
        return state.recover_application_state(self.store, keys or self.keys, receipt or self.export(), destination or self.root / 'recovered')

    def test_independent_recovery_preserves_accounts_journals_and_blocks_resume(self):
        receipt = self.export(); result = self.recover(receipt)
        restored = self.root / 'recovered'
        self.assertTrue(result['verified']); self.assertTrue(result['resume_blocked'])
        self.assertFalse(result['full_wordpress_backup'])
        self.assertEqual((restored / 'workspaces/repairs.sqlite').read_bytes(), (self.nested / 'repairs.sqlite').read_bytes())
        with self.assertRaises(ValueError): CustomerAuth(restored / 'accounts.sqlite')
        with self.assertRaises(ValueError): private_database(restored / 'workspaces/new.sqlite')
        # Test-only operator review acknowledgement; never done by live recovery.
        (restored / state.REVIEW_MARKER).unlink()
        fresh = CustomerAuth(restored / 'accounts.sqlite')
        self.assertEqual(fresh.resolve(fresh.login('alice', 'Synthetic-password-123')).username, 'alice')
        for file in restored.rglob('*'):
            self.assertEqual(file.stat().st_mode & 0o077, 0)

    def test_ciphertext_contains_no_plaintext_account_data(self):
        receipt = self.export(); data = self.store.get(receipt['object_id'])
        self.assertNotIn(b'alice', data); self.assertNotIn(b'SQLite format', data)
        self.assertNotIn(self.master, data)

    def test_writers_stopped_assertion_required_before_upload(self):
        with self.assertRaises(ValueError): state.export_application_state(self.source, self.store, self.keys, deployment_id=self.did, key_id='v1')
        self.assertEqual(self.store.puts, 0)

    def test_unknown_files_and_secret_mounts_are_rejected_without_upload(self):
        for name in ('master.key', 'credentials.json', 'accounts.sqlite-wal', 'accounts.sqlite-shm', 'accounts.sqlite-journal'):
            path = self.source / name; path.write_bytes(b'fixture'); path.chmod(0o600)
            with self.assertRaises(ValueError): self.export()
            path.unlink()
        self.assertEqual(self.store.puts, 0)

    def test_symlink_hardlink_and_public_files_are_rejected(self):
        link = self.source / 'link.sqlite'; link.symlink_to(self.source / 'accounts.sqlite')
        with self.assertRaises(ValueError): self.export()
        link.unlink(); os.link(self.source / 'accounts.sqlite', link)
        with self.assertRaises(ValueError): self.export()
        link.unlink(); (self.source / 'accounts.sqlite').chmod(0o644)
        with self.assertRaises(ValueError): self.export()
        self.assertEqual(self.store.puts, 0)

    def test_symlink_directory_and_root_are_rejected(self):
        (self.source / 'escape').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): self.export()
        (self.source / 'escape').unlink()
        alias = self.root / 'alias'; alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError): state.export_application_state(alias, self.store, self.keys, deployment_id=self.did, key_id='v1', quiesced=True)

    def test_corrupt_sqlite_is_rejected_before_upload(self):
        (self.nested / 'repairs.sqlite').write_bytes(b'SQLite format 3\0invalid')
        with self.assertRaises((ValueError, sqlite3.DatabaseError)): self.export()
        self.assertEqual(self.store.puts, 0)

    def test_concurrent_changes_are_rejected_before_upload(self):
        original = state._inventory; calls = []
        def inventory(root):
            result = original(root); calls.append(1)
            if len(calls) == 1: (self.source / 'accounts.sqlite').touch()
            return result
        with patch.object(state, '_inventory', side_effect=inventory), self.assertRaises(ValueError): self.export()
        self.assertEqual(self.store.puts, 0)

    def test_upload_or_readback_failure_never_returns_verified_receipt(self):
        with patch.object(self.store, 'put', side_effect=ConnectionError), self.assertRaises(ConnectionError): self.export()
        with patch.object(self.store, 'get', side_effect=ConnectionError), self.assertRaises(ConnectionError): self.export()

    def test_corruption_wrong_key_and_wrong_deployment_fail_without_destination(self):
        receipt = self.export(); name = receipt['object_id']; original = self.store.objects[name]
        self.store.objects[name] = original[:-1] + bytes([original[-1] ^ 1])
        with self.assertRaises(ValueError): self.recover(receipt)
        self.store.objects[name] = original
        with self.assertRaises(ValueError): self.recover(receipt, keys=lambda version: b'y' * 32)
        altered = dict(receipt, deployment_id='b' * 32)
        with self.assertRaises(ValueError): self.recover(altered)
        with self.assertRaises(ValueError): self.recover(dict(receipt, key_id='v2'))
        self.assertFalse((self.root / 'recovered').exists())

    def test_existing_destination_is_never_overwritten_or_downloaded(self):
        receipt = self.export(); destination = self.root / 'recovered'; destination.mkdir()
        with patch.object(self.store, 'get') as get, self.assertRaises(ValueError): self.recover(receipt)
        get.assert_not_called()

    def test_authenticated_path_traversal_duplicate_or_missing_parent_rejected(self):
        receipt = self.export()
        for entries in (
            {'version': 1, 'directories': [], 'files': [{'path': '../evil.sqlite', 'data': '', 'sha256': ''}]},
            {'version': 1, 'directories': ['x', 'x'], 'files': []},
            {'version': 1, 'directories': [], 'files': [{'path': 'missing/a.sqlite', 'data': base64.b64encode((self.source/'accounts.sqlite').read_bytes()).decode(), 'sha256': sha256((self.source/'accounts.sqlite').read_bytes()).hexdigest()}]},
        ):
            nonce = b'n' * 12
            ciphertext = state.MAGIC + nonce + AESGCM(state._key(self.keys, self.did, 'v1')).encrypt(nonce, json.dumps(entries).encode(), state._manifest(receipt))
            self.store.objects[receipt['object_id']] = ciphertext
            altered = dict(receipt, ciphertext_sha256=sha256(ciphertext).hexdigest())
            with self.assertRaises(ValueError): self.recover(altered)
            self.assertFalse((self.root / 'recovered').exists())

    def test_size_and_count_bounds_precede_upload(self):
        with patch.object(state, 'MAX_STATE', 1), self.assertRaises(ValueError): self.export()
        with patch.object(state, 'MAX_FILES', 1), self.assertRaises(ValueError): self.export()
        self.assertEqual(self.store.puts, 0)

    def test_cli_blocks_unapproved_access_and_does_not_configure_provider(self):
        with patch('operations_state_backup.configured_external_store') as configured:
            with patch('builtins.print'):
                self.assertEqual(main(['export', '--manifest', str(self.root/'receipt.json')]), 2)
                self.assertEqual(main(['export', '--authorized-external-access', '--manifest', str(self.root/'receipt.json')]), 2)
            configured.assert_not_called()

    def test_cli_roundtrip_with_separate_private_receipt(self):
        receipt = self.root / 'receipt.json'
        with patch('operations_state_backup.configured_external_store', return_value=self.store), patch('operations_state_backup.configured_master_keys', return_value=self.keys), patch.dict(os.environ, {'FG_GUARD_KEY_ID': 'v1'}), patch('builtins.print'):
            self.assertEqual(main(['export', '--authorized-external-access', '--writers-stopped', '--root', str(self.source), '--deployment-id', self.did, '--manifest', str(receipt)]), 0)
            self.assertEqual(main(['recover', '--authorized-external-access', '--manifest', str(receipt), '--destination', str(self.root/'recovered')]), 0)
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)

    def test_integrated_recovery_keeps_two_customers_monitoring_notifications_and_ai_reservations(self):
        import test_monitoring_service as monitoring_fixture
        import test_contextual_advisor as advisor_fixture
        from customer_sites import CustomerSites
        from contextual_advisor import ContextualAdvisor
        from monitoring_service import MonitoringService
        fixture = monitoring_fixture.MonitoringServiceTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = Path(fixture.auth.path).parent
        fixture.enable(); fixture.enable(fixture.b, fixture.site_b)
        fixture.monitor.run_once(now=100); fixture.monitor.run_once(now=100)
        provider = advisor_fixture.SimulatedProvider()
        engine = ContextualAdvisor(source/'advisor.sqlite', provider, daily_calls=1, clock=lambda:100)
        original = engine.analyze(advisor_fixture.ROWS, advisor_fixture.CONTEXT, scope=advisor_fixture.SCOPE)
        self.assertEqual(original['status'], 'model-assisted'); self.assertEqual(provider.calls, 1)
        receipt = state.export_application_state(source, self.store, self.keys,
            deployment_id=self.did, key_id='v1', quiesced=True)
        destination = self.root/'integrated-recovery'
        state.recover_application_state(self.store, self.keys, receipt, destination)
        with self.assertRaises(ValueError): CustomerAuth(destination/'auth.sqlite')
        # Only this synthetic drill acknowledges review; live recovery never resumes itself.
        (destination/state.REVIEW_MARKER).unlink()
        auth = CustomerAuth(destination/'auth.sqlite')
        alice = auth.login('alice', 'Alice-monitor-password', now=101)
        bob = auth.login('bob', 'Bob-monitor-password', now=101)
        sites = CustomerSites(auth, destination/'sites', None)
        scanner = monitoring_fixture.FixtureScanner()
        monitor = MonitoringService(sites, destination/'monitor.sqlite', scanner=scanner)
        self.assertEqual(len(monitor.history(alice, fixture.site_a, now=101)), 1)
        self.assertEqual(len(monitor.notifications(alice, now=101)), 1)
        self.assertEqual(len(monitor.history(bob, fixture.site_b, now=101)), 1)
        with self.assertRaises(PermissionError): monitor.history(bob, fixture.site_a, now=101)
        self.assertEqual(monitor.run_once(now=101)['status'], 'idle')
        self.assertEqual(scanner.calls, [])
        fresh_provider = advisor_fixture.SimulatedProvider()
        recovered = ContextualAdvisor(destination/'advisor.sqlite', fresh_provider, daily_calls=1, clock=lambda:101)
        self.assertEqual(recovered.analyze(advisor_fixture.ROWS, advisor_fixture.CONTEXT, scope=advisor_fixture.SCOPE), original)
        self.assertEqual(recovered.analyze(advisor_fixture.ROWS, advisor_fixture.CONTEXT, scope='c'*32+':'+'d'*32)['status'], 'daily-limit')
        self.assertEqual(fresh_provider.calls, 0)


if __name__ == '__main__': unittest.main()
