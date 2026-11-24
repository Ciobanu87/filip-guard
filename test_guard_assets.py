import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from guard_assets import GuardAssetDirectory,OWNERSHIP_SECONDS
from monitoring_service import MonitoringService


class GuardAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.now=100
        self.auth=CustomerAuth(self.root/'auth.sqlite');self.auth.register('alice','Alice-asset-password');self.auth.register('bob','Bob-asset-password')
        self.a=self.auth.login('alice','Alice-asset-password',now=100);self.b=self.auth.login('bob','Bob-asset-password',now=100)
        self.base=CustomerSites(self.auth,self.root/'sites',None);self.reader=Mock()
        self.assets=GuardAssetDirectory(self.base,clock=lambda:self.now,reader=self.reader)

    def proof(self):
        proof=self.assets.begin_proof(self.a,'https://api.example.com','api',now=100)
        self.reader.return_value=(200,'text/plain',proof['token'].encode())
        return proof

    def test_proof_is_single_use_digest_only_and_does_not_require_wordpress_credentials(self):
        proof=self.proof();asset=self.assets.confirm_proof(self.a,proof['origin'],proof['token'],now=100)
        with self.assets.asset_db() as db:self.assertNotIn(proof['token'],str([tuple(row) for row in db.execute('SELECT * FROM guard_proofs')]))
        self.assertEqual(self.assets.list_sites(self.a,now=101)[0]['site_id'],asset['site_id'])
        with self.assertRaises(PermissionError):self.assets.confirm_proof(self.a,proof['origin'],proof['token'],now=101)
        self.reader.assert_called_once()

    def test_other_account_wrong_token_expiry_and_private_origin_are_denied_before_network(self):
        proof=self.proof()
        for session,token,now in [(self.b,proof['token'],100),(self.a,'x'*50,100),(self.a,proof['token'],1001)]:
            with self.assertRaises(PermissionError):self.assets.confirm_proof(session,proof['origin'],token,now=now)
        with self.assertRaises(ValueError):self.assets.begin_proof(self.a,'https://127.0.0.1','api',now=100)
        self.reader.assert_not_called()

    def test_two_accounts_cannot_take_over_same_origin_or_read_each_others_asset(self):
        proof=self.proof();asset=self.assets.confirm_proof(self.a,proof['origin'],proof['token'],now=100)
        with self.assertRaises(PermissionError):self.assets.begin_proof(self.b,proof['origin'],'api',now=101)
        with self.assertRaises(PermissionError):self.assets._owned(self.b,asset['site_id'],now=101)
        self.assertEqual(self.assets.list_sites(self.b,now=101),[])
        self.assertFalse(self.assets.monitoring_binding(self.auth.resolve(self.b,now=101).customer_id,asset['site_id'],asset['origin']))

    def test_bad_response_and_retry_are_rate_limited_without_refunding_attempt(self):
        proof=self.proof();self.reader.return_value=(302,'text/plain',proof['token'].encode())
        with self.assertRaises(PermissionError):self.assets.confirm_proof(self.a,proof['origin'],proof['token'],now=100)
        with self.assertRaises(ValueError):self.assets.confirm_proof(self.a,proof['origin'],proof['token'],now=101)
        self.reader.assert_called_once()

    def test_expired_domain_control_disables_background_schedule(self):
        proof=self.proof();asset=self.assets.confirm_proof(self.a,proof['origin'],proof['token'],now=100)
        service=MonitoringService(self.assets,self.root/'monitor.sqlite')
        service.configure(self.a,asset['site_id'],enabled=True,now=100)
        self.now=100+OWNERSHIP_SECONDS+1
        self.assertIsNone(service.claim(now=self.now))
        with service.db() as db:self.assertEqual(db.execute('SELECT enabled FROM monitor_schedules').fetchone()[0],0)
        renewed=self.auth.login('alice','Alice-asset-password',now=self.now)
        with self.assertRaises(PermissionError):self.assets._owned(renewed,asset['site_id'],now=self.now)

    def test_proof_expiry_is_enforced_even_with_a_fresh_valid_session(self):
        proof=self.proof();fresh=self.auth.login('alice','Alice-asset-password',now=1001)
        with self.assertRaises(PermissionError):self.assets.confirm_proof(fresh,proof['origin'],proof['token'],now=1001)
        self.reader.assert_not_called()

    def test_logout_during_verification_cannot_grant_an_asset(self):
        proof=self.proof()
        def reader(origin):
            self.auth.logout(self.a)
            return 200,'text/plain',proof['token'].encode()
        self.assets.reader=reader
        with self.assertRaises(PermissionError):self.assets.confirm_proof(self.a,proof['origin'],proof['token'],now=100)
        fresh=self.auth.login('alice','Alice-asset-password',now=101)
        self.assertEqual(self.assets.list_sites(fresh,now=101),[])

    def test_default_proof_transport_blocks_mixed_dns_before_tls(self):
        import socket
        assets=GuardAssetDirectory(self.base,clock=lambda:100)
        proof=assets.begin_proof(self.a,'https://public.example.com','api',now=100)
        answers=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443)),
                 (socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch('wordpress_dns_deadline.getaddrinfo_with_deadline',return_value=answers),patch('wordpress_https_deadline.connect_pinned_addresses') as connect:
            with self.assertRaises(PermissionError):assets.confirm_proof(self.a,proof['origin'],proof['token'],now=100)
        connect.assert_not_called()
