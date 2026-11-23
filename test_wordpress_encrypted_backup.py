import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from backup import BackupManager
from wordpress_encrypted_backup import (
    export_encrypted_copy, restore_encrypted_copy, EncryptedBackupError,
)


class MemoryObjectStore:
    """Fixture only: does not represent configured external storage."""
    def __init__(self):
        self.objects = {}
    def put(self, object_id, content):
        self.objects[object_id] = content
    def get(self, object_id):
        return self.objects[object_id]


class EncryptedBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'original.sqlite'
        self.backups = BackupManager(self.path)
        self.backup_id = self.backups.create_backup('https://example.com', 7, 'Private content ✓')
        self.key = os.urandom(32)  # Ephemeral test key only.
        self.store = MemoryObjectStore()

    def export(self):
        return export_encrypted_copy(self.backups, self.store, self.key, key_id='test-key')

    def test_external_readback_and_independent_recovery(self):
        receipt = self.export()
        ciphertext = self.store.get(receipt.object_id)
        self.assertNotIn(b'Private content', ciphertext)
        self.assertNotIn(self.key, ciphertext)
        self.path.unlink()
        target = Path(self.temp.name) / 'restored.sqlite'
        result = restore_encrypted_copy(ciphertext, self.key, target,
                                        expected_sha256=receipt.ciphertext_sha256)
        self.assertEqual(result['backup_count'], 1)
        self.assertEqual(BackupManager(target).get_backup(self.backup_id)['content'], 'Private content ✓')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.key.hex(), repr(receipt))

    def test_wrong_key_tampering_truncation_and_wrong_digest_fail(self):
        receipt = self.export()
        data = self.store.get(receipt.object_id)
        cases = [(data, os.urandom(32), None),
                 (data[:-1] + bytes([data[-1] ^ 1]), self.key, None),
                 (data[:40], self.key, None),
                 (data, self.key, '0' * 64)]
        for ciphertext, key, digest in cases:
            target = Path(self.temp.name) / 'must-not-exist.sqlite'
            with self.assertRaises(EncryptedBackupError):
                restore_encrypted_copy(ciphertext, key, target, expected_sha256=digest)
            self.assertFalse(target.exists())

    def test_upload_or_readback_failure_never_reports_success(self):
        for method in ('put', 'get'):
            store = Mock()
            getattr(store, method).side_effect = OSError('provider unavailable')
            with self.assertRaises(EncryptedBackupError):
                export_encrypted_copy(self.backups, store, self.key, key_id='test-key')

    def test_corrupted_external_object_is_rejected(self):
        class CorruptStore(MemoryObjectStore):
            def get(self, object_id):
                return super().get(object_id)[:-1]
        with self.assertRaises(EncryptedBackupError):
            export_encrypted_copy(self.backups, CorruptStore(), self.key, key_id='test-key')

    def test_nonce_is_fresh_and_existing_recovery_file_is_preserved(self):
        first, second = self.export(), self.export()
        self.assertNotEqual(self.store.get(first.object_id), self.store.get(second.object_id))
        target = Path(self.temp.name) / 'existing'
        target.write_text('keep')
        with self.assertRaises(FileExistsError):
            restore_encrypted_copy(self.store.get(first.object_id), self.key, target)
        self.assertEqual(target.read_text(), 'keep')

    def test_invalid_key_rejected_without_upload(self):
        for key in (None, b'short', 'a' * 32):
            store = Mock()
            with self.assertRaises(EncryptedBackupError):
                export_encrypted_copy(self.backups, store, key, key_id='test-key')
            store.put.assert_not_called()
