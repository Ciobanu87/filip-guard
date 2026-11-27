from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from customer_auth import CustomerAuth,AuthenticationError
from customer_recovery import AccountRecovery


class CapturedDelivery:
    def __init__(self):self.messages=[];self.fail=False
    def send_account_challenge(self,message):
        self.messages.append(message)
        if self.fail:raise OSError('private SMTP detail')


class AccountRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.auth=CustomerAuth(Path(self.temp.name)/'auth.sqlite')
        self.alice=self.auth.register('alice','Alice-original-password');self.auth.register('bob','Bob-original-password')
        self.session=self.auth.login('alice','Alice-original-password',now=100)
        self.sender=CapturedDelivery();self.keys=lambda _:b'k'*32
        self.recovery=AccountRecovery(self.auth,self.keys,key_id='fixture-v1',authorized=True)
    def verify(self):
        self.recovery.request_verification(self.session,'Alice-original-password','alice@example.test',now=100)
        self.recovery.dispatch_once(self.sender,now=101)
        token=self.sender.messages[-1]['token']
        self.assertNotIn(token,Path(self.auth.path).read_bytes().decode('latin1'))
        self.assertEqual(self.recovery.confirm_verification(token,now=102)['status'],'email-verified')
    def reset_token(self):
        self.verify();self.recovery.request_recovery('alice',now=103)
        self.recovery.dispatch_once(self.sender,now=104)
        return self.sender.messages[-1]['token']
    def test_default_requires_explicit_authorization(self):
        with self.assertRaises(ValueError):AccountRecovery(self.auth,self.keys,key_id='fixture-v1')
        self.assertEqual(self.recovery.dispatch_once()['status'],'disabled')
    def test_verified_channel_is_single_use_and_not_a_login(self):
        self.verify();token=self.sender.messages[-1]['token']
        with self.assertRaises(AuthenticationError):self.recovery.confirm_verification(token,now=103)
        self.assertEqual(self.auth.resolve(self.session,now=103).customer_id,self.alice.customer_id)
    def test_unknown_and_unverified_recovery_requests_are_indistinguishable(self):
        self.assertEqual(self.recovery.request_recovery('alice',now=100),self.recovery.request_recovery('missing',now=100))
        self.assertEqual(self.recovery.dispatch_once(self.sender,now=101)['status'],'idle')
    def test_password_reset_revokes_sessions_preserves_customer_and_requires_new_login(self):
        token=self.reset_token();self.recovery.reset_password(token,'Alice-new-secure-password',now=105)
        with self.assertRaises(AuthenticationError):self.auth.resolve(self.session,now=106)
        with self.assertRaises(AuthenticationError):self.auth.login('alice','Alice-original-password',now=106)
        new=self.auth.login('alice','Alice-new-secure-password',now=107)
        self.assertEqual(self.auth.resolve(new,now=108).customer_id,self.alice.customer_id)
        with self.assertRaises(AuthenticationError):self.recovery.reset_password(token,'Another-new-password',now=109)
        self.auth.login('bob','Bob-original-password',now=109)
    def test_tokens_are_bound_to_purpose_and_expiry(self):
        token=self.reset_token()
        with self.assertRaises(AuthenticationError):self.recovery.confirm_verification(token,now=105)
        with self.assertRaises(AuthenticationError):self.recovery.reset_password(token,'Alice-new-secure-password',now=1003)
    def test_reauth_required_and_verified_address_cannot_be_silently_replaced(self):
        with self.assertRaises(AuthenticationError):self.recovery.request_verification(self.session,'wrong','bad@example.test',now=100)
        self.verify()
        with self.assertRaises(AuthenticationError):self.recovery.request_verification(self.session,'Alice-original-password','new@example.test',now=103)
    def test_uncertain_delivery_is_never_automatically_repeated(self):
        self.recovery.request_verification(self.session,'Alice-original-password','alice@example.test',now=100)
        self.sender.fail=True
        self.assertEqual(self.recovery.dispatch_once(self.sender,now=101)['status'],'unknown')
        self.assertEqual(self.recovery.dispatch_once(self.sender,now=102)['status'],'idle')
        self.assertEqual(len(self.sender.messages),1)
    def test_resend_invalidates_previous_code(self):
        self.recovery.request_verification(self.session,'Alice-original-password','alice@example.test',now=100)
        self.recovery.dispatch_once(self.sender,now=101);old=self.sender.messages[-1]['token']
        self.recovery.request_verification(self.session,'Alice-original-password','alice@example.test',now=102)
        with self.assertRaises(AuthenticationError):self.recovery.confirm_verification(old,now=103)
    def test_concurrent_reset_consumes_code_once(self):
        token=self.reset_token()
        def reset(_):
            try:self.recovery.reset_password(token,'Alice-new-secure-password',now=105);return True
            except AuthenticationError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(reset,range(2))),1)
    def test_recovery_limits_survive_service_recreation(self):
        self.verify()
        for _ in range(4):self.recovery.request_recovery('alice',now=103)
        reopened=AccountRecovery(self.auth,self.keys,key_id='fixture-v1',authorized=True)
        reopened.dispatch_once(self.sender,now=104)
        self.assertEqual(reopened.dispatch_once(self.sender,now=105)['status'],'idle')
        self.assertEqual(len(self.sender.messages),2)

    def test_pending_delivery_is_encrypted_and_authenticated(self):
        self.recovery.request_verification(self.session,'Alice-original-password','alice@example.test',now=100)
        before=Path(self.auth.path).read_bytes()
        self.recovery.dispatch_once(self.sender,now=101)
        self.assertNotIn(self.sender.messages[-1]['token'].encode(),before)
        self.recovery.request_verification(self.session,'Alice-original-password','alice@example.test',now=102)
        with self.auth.db() as db:db.execute("UPDATE account_challenges SET recipient='other@example.test' WHERE consumed=0")
        self.assertEqual(self.recovery.dispatch_once(self.sender,now=103)['status'],'unknown')
        self.assertEqual(len(self.sender.messages),1)

    def test_concurrent_delivery_claims_message_only_once(self):
        self.recovery.request_verification(self.session,'Alice-original-password','alice@example.test',now=100)
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.recovery.dispatch_once(self.sender,now=101)['status'],range(3)))
        self.assertEqual(results.count('sent'),1);self.assertEqual(len(self.sender.messages),1)

    def test_password_change_invalidates_pending_recovery_code(self):
        token=self.reset_token()
        self.auth.change_password(self.session,'Alice-original-password','Changed-through-account-password',now=105)
        with self.assertRaises(AuthenticationError):self.recovery.reset_password(token,'Unexpected-reset-password',now=106)

    def test_deactivation_prevents_recovery_and_dispatched_token_use(self):
        token=self.reset_token()
        with self.auth.db() as db:db.execute('UPDATE customers SET active=0 WHERE customer_id=?',(self.alice.customer_id,))
        with self.assertRaises(AuthenticationError):self.recovery.reset_password(token,'Unexpected-reset-password',now=105)
        self.recovery.request_recovery('alice',now=106)
        self.assertEqual(self.recovery.dispatch_once(self.sender,now=107)['status'],'idle')

    def test_unknown_request_flood_cannot_grow_unbounded_limiter_rows(self):
        for index in range(100):self.recovery.request_recovery('unknown'+str(index),now=100)
        with self.auth.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM account_action_limits').fetchone()[0],31)

    def test_disabled_configuration_does_not_read_state_keys_or_monitor(self):
        from unittest.mock import patch,Mock
        from customer_recovery_configuration import configured_account_recovery,configured_account_dispatcher
        with patch.dict('os.environ',{},clear=True),patch('customer_recovery_configuration.configured_master_keys') as keys,patch('customer_recovery_configuration.require_existing_guard_state') as state:
            self.assertIsNone(configured_account_recovery(self.auth))
            self.assertIsNone(configured_account_dispatcher(Mock()))
            keys.assert_not_called();state.assert_not_called()
