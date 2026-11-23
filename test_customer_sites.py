from pathlib import Path
import secrets
import tempfile
import unittest

from customer_auth import CustomerAuth,AuthenticationError
from customer_sites import CustomerSites
from wordpress_local_fixture import LocalWordPressFixture
from wordpress_autofix_engine import LiveAutoFixDisabled
from wordpress_encrypted_backup import EncryptedBackupError
from test_verified_external_backups import MemoryStore


class CustomerSitesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.auth=CustomerAuth(self.root/'auth.sqlite',session_ttl=120,idle_ttl=60)
        self.alice=self.auth.register('alice','Alice-isolated-password-123')
        self.bob=self.auth.register('bob','Bob-isolated-password-456')
        self.a=self.auth.login('alice','Alice-isolated-password-123',now=100)
        self.b=self.auth.login('bob','Bob-isolated-password-456',now=100)
        self.master=secrets.token_bytes(32);self.store=MemoryStore();self.calls=0
        self.origins=['https://alice.example','https://bob.example']
        self.backends={}
        for index,site in enumerate(self.origins):
            backend=LocalWordPressFixture(self.root/('remote-'+str(index)+'.sqlite'))
            backend.seed(site,'post',1,'Private original '+str(index),user_id=7)
            self.backends[site]=backend
        self.service=CustomerSites(self.auth,self.root/'customers',lambda _:self.master,
            active_key_id='test-key',object_store=self.store,gateway_factory=self.factory)
        self.site_a=self.service.connect(self.a,self.origins[0],'admin','fictitious-wordpress-password',now=100)['site_id']
        self.site_b=self.service.connect(self.b,self.origins[1],'admin','fictitious-wordpress-password',now=100)['site_id']

    def factory(self,origin,provider):
        service=self;backend=self.backends[origin]
        class Gateway:
            def check(self):
                service.calls+=1
                if provider()!=('admin','fictitious-wordpress-password'):raise PermissionError('Fixture admin proof failed')
            def verify_site_owner(self):self.check();return 7
            def read_authorized(self,*args):self.check();return backend.read_authorized(*args)
            def compare_and_swap(self,*args,**kwargs):self.check();return backend.compare_and_swap(*args,**kwargs)
        return Gateway()

    def plan(self,session=None,site=None):
        session=session or self.a;site=site or self.site_a
        return self.service.propose(session,site,'post',1,'Reviewed replacement',now=101)['plan_id']

    def approved(self,session=None,site=None):
        session=session or self.a;site=site or self.site_a;plan=self.plan(session,site)
        return plan,self.service.approve(session,site,plan,confirmed=True,now=102)

    def test_owner_binding_and_site_lists_are_isolated(self):
        self.assertEqual([row['site_id'] for row in self.service.list_sites(self.a,now=101)],[self.site_a])
        self.assertEqual([row['site_id'] for row in self.service.list_sites(self.b,now=101)],[self.site_b])
        with self.assertRaises(PermissionError):
            self.service.connect(self.b,self.origins[0],'admin','fictitious-wordpress-password',now=101)

    def test_credentials_are_authenticated_encrypted_and_separated_by_customer(self):
        with self.service.db() as db:rows=db.execute('SELECT credentials FROM customer_sites').fetchall()
        self.assertNotEqual(bytes(rows[0][0]),bytes(rows[1][0]))
        for row in rows:self.assertNotIn(b'fictitious-wordpress-password',bytes(row[0]))
        self.assertEqual(self.service._credentials(self.a,self.site_a,now=101)[0],'admin')
        with self.assertRaises(PermissionError):self.service._credentials(self.b,self.site_a,now=101)

    def test_swapping_ciphertexts_between_sites_is_rejected(self):
        with self.service.db() as db:
            ciphertext=db.execute('SELECT credentials FROM customer_sites WHERE site_id=?',(self.site_b,)).fetchone()[0]
            db.execute('UPDATE customer_sites SET credentials=? WHERE site_id=?',(ciphertext,self.site_a))
        with self.assertRaises(PermissionError):self.plan()

    def test_two_customers_same_wordpress_ids_use_separate_backups_and_approvals(self):
        plan_a,token_a=self.approved();plan_b,token_b=self.approved(self.b,self.site_b)
        result_a=self.service.apply(self.a,self.site_a,plan_a,token_a,now=103)
        result_b=self.service.apply(self.b,self.site_b,plan_b,token_b,now=103)
        self.assertEqual(result_a['status'],'applied');self.assertEqual(result_b['status'],'applied')
        self.assertEqual(self.service.get_backup(self.a,self.site_a,result_a['backup_id'],now=104)['content'],'Private original 0')
        self.assertEqual(self.service.get_backup(self.b,self.site_b,result_b['backup_id'],now=104)['content'],'Private original 1')
        prefixes={key.split('/')[1] for key in self.store.objects}
        self.assertEqual(prefixes,{self.alice.customer_id,self.bob.customer_id})

    def test_cross_customer_and_cross_site_operations_are_blocked_before_remote_io(self):
        plan,token=self.approved();calls=self.calls
        for operation in (
            lambda:self.service.review(self.b,self.site_a,plan,now=103),
            lambda:self.service.approve(self.b,self.site_a,plan,confirmed=True,now=103),
            lambda:self.service.apply(self.b,self.site_a,plan,token,now=103),
            lambda:self.service.get_backup(self.b,self.site_a,'forged',now=103),
            lambda:self.service.review(self.b,self.site_b,plan,now=103),
            lambda:self.service.review(self.a,self.site_b,plan,now=103)):
            with self.assertRaises(PermissionError):operation()
        self.assertEqual(self.calls,calls)

    def test_approval_token_cannot_be_copied_into_another_customers_plan(self):
        _,alice_token=self.approved();bob_plan,_=self.approved(self.b,self.site_b)
        with self.assertRaises(PermissionError):self.service.apply(self.b,self.site_b,bob_plan,alice_token,now=103)
        self.assertEqual(self.backends[self.origins[1]].read_authorized(self.origins[1],'post',1,7).revision,'1')

    def test_expired_or_logged_out_session_blocks_saved_approval(self):
        plan,token=self.approved();calls=self.calls
        with self.assertRaises(AuthenticationError):self.service.apply(self.a,self.site_a,plan,token,now=220)
        self.auth.logout(self.a)
        with self.assertRaises(AuthenticationError):self.service.apply(self.a,self.site_a,plan,token,now=104)
        self.assertEqual(self.calls,calls)

    def test_new_login_does_not_inherit_previous_session_approval(self):
        plan,token=self.approved()
        second=self.auth.login('alice','Alice-isolated-password-123',now=103)
        with self.assertRaises(PermissionError):self.service.apply(second,self.site_a,plan,token,now=104)

    def test_missing_store_or_master_key_blocks_repair(self):
        plan,token=self.approved();calls=self.calls
        self.service.object_store=None
        with self.assertRaises(PermissionError):self.service.apply(self.a,self.site_a,plan,token,now=103)
        self.assertEqual(self.calls,calls)
        self.service.object_store=self.store;self.service.master_keys=None
        with self.assertRaises(PermissionError):self.service.apply(self.a,self.site_a,plan,token,now=103)

    def test_corrupt_external_backup_blocks_write_and_preserves_approval(self):
        plan,token=self.approved();self.store.fail='corrupt'
        with self.assertRaises(EncryptedBackupError):self.service.apply(self.a,self.site_a,plan,token,now=103)
        self.assertEqual(self.backends[self.origins[0]].read_authorized(self.origins[0],'post',1,7).revision,'1')
        self.store.fail=None
        self.assertEqual(self.service.apply(self.a,self.site_a,plan,token,now=104)['status'],'applied')

    def test_wrong_customer_backup_id_and_replay_do_not_cross_boundaries(self):
        plan,token=self.approved();result=self.service.apply(self.a,self.site_a,plan,token,now=103)
        with self.assertRaises(PermissionError):self.service.get_backup(self.b,self.site_b,result['backup_id'],now=104)
        self.assertEqual(self.service.apply(self.a,self.site_a,plan,token,now=104),result)
        self.assertEqual(self.backends[self.origins[0]].read_authorized(self.origins[0],'post',1,7).revision,'2')

    def test_restart_preserves_ownership_and_encrypted_credentials(self):
        reopened=CustomerSites(self.auth,self.root/'customers',lambda _:self.master,active_key_id='test-key',
            object_store=self.store,gateway_factory=self.factory)
        self.assertEqual(reopened.list_sites(self.a,now=101)[0]['site_id'],self.site_a)
        self.assertEqual(reopened._credentials(self.a,self.site_a,now=101)[0],'admin')

    def test_site_connection_requires_remote_proof_and_default_gateway_stays_disabled(self):
        isolated=CustomerSites(self.auth,self.root/'disabled',lambda _:self.master)
        with self.assertRaises(LiveAutoFixDisabled):isolated.connect(self.a,self.origins[0],'admin','fake-password',now=101)
        with self.assertRaises(PermissionError):self.service.connect(self.a,self.origins[0],'wrong','wrong',now=101)

    def test_traversal_and_missing_explicit_confirmation_are_rejected(self):
        with self.assertRaises(PermissionError):self.service.review(self.a,'../escape','forged',now=101)
        plan=self.plan()
        with self.assertRaises(PermissionError):self.service.approve(self.a,self.site_a,plan,now=102)
