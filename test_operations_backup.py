from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_guard_application as fixture
from operations_backup import probe_external_backup,recover_customer_archive,main
from test_verified_external_backups import MemoryStore
from wordpress_encrypted_backup import EncryptedBackupError

class OperationsRecoveryTests(unittest.TestCase):
    def test_external_probe_uploads_only_ciphertext_and_recovers_without_original_database(self):
        store=MemoryStore();result=probe_external_backup(store)
        self.assertEqual(result['status'],'verified');self.assertTrue(result['independent_recovery'])
        self.assertNotIn(b'synthetic recovery probe',next(iter(store.objects.values())))
    def test_probe_rejects_corruption_and_provider_disconnects(self):
        for fault in ['corrupt','put','get']:
            store=MemoryStore();store.fail=fault
            with self.assertRaises(EncryptedBackupError):probe_external_backup(store)
    def test_customer_recovery_independent_of_auth_and_original_databases(self):
        f=fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups)
        review=f.proposal();result=f.application.approve_and_apply(f.a,f.site_a,review['plan_id'],confirmed=True)
        principal,row=f.sites._owned(f.a,f.site_a)
        engine,_,_=f.sites._context(f.a,f.site_a)
        with engine.backups.db() as db:receipt=dict(db.execute('SELECT * FROM external_backups WHERE backup_id=?',(result['backup_id'],)).fetchone())
        manifest={**receipt,'customer_id':principal.customer_id,'site_id':f.site_a,'scope':'resource_content_only'}
        f.auth.logout(f.a)
        destination=f.root/'independent-recovered.sqlite'
        answer=recover_customer_archive(f.store,lambda _:f.master,manifest,destination)
        self.assertTrue(answer['verified']);self.assertEqual(destination.stat().st_mode&0o777,0o600)
        with self.assertRaises(FileExistsError):recover_customer_archive(f.store,lambda _:f.master,manifest,destination)
        for change in [{'customer_id':'../escape'},{'site_id':'b'*32},{'ciphertext_sha256':'0'*64},{'scope':'full_site'}]:
            with self.assertRaises((ValueError,KeyError)):recover_customer_archive(f.store,lambda _:f.master,{**manifest,**change},f.root/'bad.sqlite')
    def test_cli_requires_explicit_external_authorization_and_redacts_errors(self):
        out=StringIO()
        with patch('operations_backup.configured_external_store') as config,redirect_stdout(out):
            self.assertEqual(main(['probe']),2);config.assert_not_called()
        with patch('operations_backup.configured_external_store',side_effect=RuntimeError('sensitive')),redirect_stdout(out):
            self.assertEqual(main(['probe','--authorized-external-access']),1)
        self.assertNotIn('sensitive',out.getvalue())
