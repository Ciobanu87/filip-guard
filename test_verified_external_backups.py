from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from wordpress_autofix_engine import AutoFixEngine
from wordpress_local_fixture import LocalWordPressFixture
from wordpress_encrypted_backup import EncryptedBackupError
from verified_external_backups import VerifiedExternalBackups
from external_backup_store import ScopedObjectStore


class MemoryStore:
    def __init__(self):self.objects={};self.fail=None
    def put(self,key,value):
        if self.fail=='put':raise OSError('isolated upload failure')
        self.objects[key]=value
    def get(self,key):
        if self.fail=='get':raise OSError('isolated download failure')
        value=self.objects[key]
        return value[:-8] if self.fail=='corrupt' else value


class VerifiedExternalBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.key=secrets.token_bytes(32);self.store=MemoryStore()
        self.scoped=ScopedObjectStore(self.store,'a'*32,'b'*32)
        self.backups=VerifiedExternalBackups(self.root/'backups.sqlite',self.root/'receipts.sqlite',
            'https://example.com',self.scoped,lambda key_id:self.key,key_id='test-key')
        self.gateway=LocalWordPressFixture(self.root/'fixture.sqlite')
        self.gateway.seed('https://example.com','post',1,'old',user_id=7)
        self.engine=AutoFixEngine(self.root/'engine.sqlite',self.backups,self.gateway)
        self.session=dict(user_id=7,session_id='s'*43,now=100)

    def approved(self):
        plan=self.engine.propose(site_url='https://example.com',resource_type='post',resource_id=1,
            proposed_content='new',**self.session)['plan_id']
        return plan,self.engine.approve(plan,confirmed=True,**self.session)

    def test_external_backup_is_required_and_verified_before_write(self):
        plan,token=self.approved()
        result=self.engine.apply(plan,token,**self.session)
        self.assertEqual(result['status'],'applied')
        self.assertEqual(self.backups.get_backup(result['backup_id'])['content'],'old')
        self.assertTrue(all(b'SQLite format 3' not in value for value in self.store.objects.values()))

    def test_missing_upload_download_and_corruption_block_write_without_burning_approval(self):
        for failure in ('put','get','corrupt','missing'):
            with self.subTest(failure=failure):
                self.setUp()
                plan,token=self.approved();self.store.fail=failure
                if failure=='missing':self.backups.store=None
                with self.assertRaises(EncryptedBackupError):self.engine.apply(plan,token,**self.session)
                self.assertEqual(self.gateway.read_authorized('https://example.com','post',1,7).content,'old')
                self.store.fail=None;self.backups.store=self.scoped
                self.assertEqual(self.engine.apply(plan,token,**self.session)['status'],'applied')

    def test_recovery_survives_loss_of_local_content_database(self):
        backup_id=self.backups.create_backup('https://example.com',1,'restore independently')
        (self.root/'backups.sqlite').unlink()
        reopened=VerifiedExternalBackups(self.root/'backups.sqlite',self.root/'receipts.sqlite',
            'https://example.com',self.scoped,lambda key_id:self.key,key_id='test-key')
        self.assertEqual(reopened.get_backup(backup_id)['content'],'restore independently')

    def test_wrong_key_corrupt_object_and_forged_backup_id_are_rejected(self):
        backup_id=self.backups.create_backup('https://example.com',1,'old')
        self.backups.keys=lambda _:secrets.token_bytes(32)
        with self.assertRaises(EncryptedBackupError):self.backups.get_backup(backup_id)
        self.backups.keys=lambda _:self.key;self.store.fail='corrupt'
        with self.assertRaises(EncryptedBackupError):self.backups.get_backup(backup_id)
        with self.assertRaises(PermissionError):self.backups.get_backup('forged')

    def test_wrong_site_cannot_create_backup(self):
        with self.assertRaises(PermissionError):self.backups.create_backup('https://other.example',1,'secret')
        self.assertEqual(self.store.objects,{})
