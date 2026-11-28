"""Quiesced fixture recovery includes account challenges and held repair journals."""
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch
import application_state_backup as state
from customer_auth import CustomerAuth
from customer_recovery import AccountRecovery
from test_customer_recovery import CapturedDelivery
import test_guard_application as fixture


class NewStateRecoveryTests(unittest.TestCase):
    def test_encrypted_recovery_preserves_pending_account_mail_and_held_autofix_without_resume(self):
        f=fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups)
        recovery=AccountRecovery(f.auth,lambda _:f.master,key_id='test-key',authorized=True)
        delivery=CapturedDelivery();recovery.request_verification(f.a,'Alice-unified-password','alice@example.test')
        recovery.dispatch_once(delivery);recovery.confirm_verification(delivery.messages[-1]['token'])
        recovery.request_recovery('alice')
        review=f.proposal();engine,identity,_=f.sites._context(f.a,f.site_a,require_external=True)
        approval=engine.approve(review['plan_id'],confirmed=True,**identity)
        with patch.object(engine.gateway,'compare_and_swap',side_effect=SystemExit):
            with self.assertRaises(SystemExit):engine.apply(review['plan_id'],approval,**identity)
        held=engine.status(review['plan_id'],**identity)
        self.assertEqual(held['status'],'applying');self.assertTrue(held['backup_id'])
        source=f.root/'quiesced';source.mkdir(mode=0o700)
        shutil.copyfile(f.auth.path,source/'auth.sqlite');(source/'auth.sqlite').chmod(0o600)
        shutil.copytree(f.sites.root,source/'sites')
        shutil.copyfile(f.monitor.path,source/'monitor.sqlite');(source/'monitor.sqlite').chmod(0o600)
        receipt=state.export_application_state(source,f.store,lambda _:f.master,deployment_id='a'*32,key_id='test-key',quiesced=True)
        ciphertext=f.store.get(receipt['object_id'])
        self.assertNotIn(b'alice@example.test',ciphertext);self.assertNotIn(b'SQLite format',ciphertext)
        destination=f.root/'independent-recovery'
        result=state.recover_application_state(f.store,lambda _:f.master,receipt,destination)
        self.assertTrue(result['verified']);self.assertTrue(result['resume_blocked'])
        with self.assertRaises(ValueError):CustomerAuth(destination/'auth.sqlite')
        with sqlite3.connect(destination/'auth.sqlite') as db:
            pending=db.execute("SELECT delivery_state,consumed,length(payload),length(token_hash) FROM account_challenges WHERE purpose='recover'").fetchone()
            self.assertEqual(pending[:2],('pending',0));self.assertGreater(pending[2],43);self.assertEqual(pending[3],64)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM customers').fetchone()[0],2)
        relative=Path(engine.database_path).relative_to(f.sites.root)
        with sqlite3.connect(destination/'sites'/relative) as db:
            stored=db.execute('SELECT state,result FROM repair_plans WHERE plan_id=?',(review['plan_id'],)).fetchone()
            self.assertEqual(stored[0],'applying');self.assertIn(held['backup_id'],stored[1])
        self.assertEqual(f.backends[f.origins[0]].read_authorized(f.origins[0],'post',1,7).revision,'1')

    def test_existing_public_or_symlinked_workspace_is_not_silently_repaired_or_followed(self):
        f=fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups)
        parent=f.sites.root/'customers';parent.mkdir(mode=0o755)
        principal=f.auth.resolve(f.a)
        with self.assertRaises(ValueError):f.sites._workspace(principal,f.site_a)
        self.assertEqual(parent.stat().st_mode & 0o777,0o755)
        parent.rmdir();outside=f.root/'outside';outside.mkdir(mode=0o700);parent.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):f.sites._workspace(principal,f.site_a)
        self.assertEqual(list(outside.iterdir()),[])
