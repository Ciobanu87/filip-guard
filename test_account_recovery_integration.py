"""Recovery boundaries with existing repair approvals and isolated customer state."""
import unittest
from customer_auth import CustomerAuth,AuthenticationError
from customer_recovery import AccountRecovery
from test_customer_recovery import CapturedDelivery
import test_guard_application as fixtures


class AccountRecoveryIntegrationTests(unittest.TestCase):
    def test_reset_revokes_old_repair_session_and_preserves_owned_state(self):
        fixture=fixtures.UnifiedFlowTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        review=fixture.proposal()
        recovery=AccountRecovery(fixture.auth,lambda _:fixture.master,key_id='test-key',authorized=True)
        delivery=CapturedDelivery()
        recovery.request_verification(fixture.a,'Alice-unified-password','alice@example.test')
        recovery.dispatch_once(delivery);recovery.confirm_verification(delivery.messages[-1]['token'])
        recovery.request_recovery('alice');recovery.dispatch_once(delivery)
        recovery.reset_password(delivery.messages[-1]['token'],'Recovered-account-password')
        with self.assertRaises(AuthenticationError):fixture.application.approve_and_apply(fixture.a,fixture.site_a,review['plan_id'],confirmed=True)
        fresh=fixture.auth.login('alice','Recovered-account-password')
        self.assertEqual(fixture.sites.list_sites(fresh)[0]['site_id'],fixture.site_a)
        with self.assertRaises(PermissionError):fixture.sites.approve(fresh,fixture.site_a,review['plan_id'],confirmed=True)
        with self.assertRaises(PermissionError):fixture.sites.read_resource(fixture.b,fixture.site_a,'post',1)
        self.assertEqual(fixture.store.objects,{})
        self.assertIn('missing-destination',fixture.backends[fixture.origins[0]].read_authorized(fixture.origins[0],'post',1,7).content)

    def test_unsupported_editor_cannot_reach_repair_approval_or_backup(self):
        fixture=fixtures.UnifiedFlowTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        origin=fixture.origins[0];backend=fixture.backends[origin]
        for unsupported in ('<!-- wp:paragraph --><p>Block</p>','[gallery ids="1"]','<div data-elementor-id="1">Builder</div>'):
            with self.assertRaises(ValueError):fixture.sites.propose(fixture.a,fixture.site_a,'post',1,unsupported)
        original=backend.read_authorized(origin,'post',1,7)
        backend.compare_and_swap(original,'<!-- wp:paragraph -->'+original.content,7,operation_id='fixture-unsupported-editor')
        with self.assertRaises(ValueError):fixture.sites.propose(fixture.a,fixture.site_a,'post',1,'<p>Classic replacement</p>')
        self.assertEqual(fixture.store.objects,{})

    def test_explicit_configuration_reuses_retained_master_and_existing_state_without_sending(self):
        from unittest.mock import patch
        import json
        from customer_recovery_configuration import configured_account_dispatcher,configured_account_recovery
        fixture=fixtures.UnifiedFlowTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        master=fixture.root/'retained.key';master.write_bytes(fixture.master);master.chmod(0o400)
        smtp=fixture.root/'smtp.json';smtp.write_text(json.dumps({'username':'fixture','password':'synthetic'}));smtp.chmod(0o400)
        env={'FG_ACCOUNT_RECOVERY_AUTHORIZED':'1','FG_EMAIL_AUTHORIZED':'1',
            'FG_CUSTOMER_AUTH_DB':fixture.auth.path,'FG_CUSTOMER_DATA_ROOT':str(fixture.sites.root),
            'FG_MONITOR_DB':fixture.monitor.path,'FG_GUARD_MASTER_KEY_FILE':str(master),'FG_GUARD_KEY_ID':'test-key',
            'FG_SMTP_CREDENTIALS_FILE':str(smtp),'FG_SMTP_SENDER':'fixture@example.test'}
        with patch.dict('os.environ',env,clear=True),patch('smtplib.SMTP') as network:
            dispatcher=configured_account_dispatcher(fixture.monitor)
            self.assertEqual(dispatcher.dispatch_once()['status'],'idle');network.assert_not_called()
            self.assertEqual(master.read_bytes(),fixture.master)
            other=CustomerAuth(fixture.root/'different.sqlite')
            with self.assertRaises(ValueError):configured_account_recovery(other)
