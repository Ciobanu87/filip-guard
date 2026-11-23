from pathlib import Path
import sqlite3
import tempfile
import unittest
from customer_auth import CustomerAuth, AuthenticationError


class CustomerAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'accounts.sqlite'
        self.auth = CustomerAuth(self.path, session_ttl=120, idle_ttl=30)
        self.alice = self.auth.register('alice', 'Alice-test-password-123')
        self.bob = self.auth.register('bob', 'Bob-test-password-456')

    def login(self, name='alice', password='Alice-test-password-123'):
        return self.auth.login(name, password, now=100)

    def test_distinct_customers_and_fresh_opaque_sessions(self):
        first, second = self.login(), self.login()
        self.assertNotEqual(first, second)
        self.assertNotEqual(self.alice.customer_id, self.bob.customer_id)
        self.assertEqual(self.auth.resolve(first, now=101), self.alice)

    def test_passwords_and_tokens_are_not_persisted_in_plaintext(self):
        token = self.login()
        with self.auth.db() as db:
            hashes = [bytes(row[0]) for row in db.execute('SELECT password_hash FROM customers')]
            stored = db.execute('SELECT token_digest FROM customer_sessions').fetchone()[0]
        self.assertNotIn(b'Alice-test-password-123', b''.join(hashes))
        self.assertNotEqual(stored, token)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_password_hashes_are_salted(self):
        self.auth.register('carol', 'Alice-test-password-123')
        with self.auth.db() as db:
            rows = db.execute("SELECT salt,password_hash FROM customers WHERE username IN ('alice','carol')").fetchall()
        self.assertNotEqual(rows[0][0], rows[1][0]); self.assertNotEqual(rows[0][1], rows[1][1])

    def test_wrong_password_and_unknown_account_rejected(self):
        for name, password in [('alice','wrong'), ('unknown','Alice-test-password-123')]:
            with self.assertRaises(AuthenticationError): self.auth.login(name,password,now=100)

    def test_login_throttling_and_recovery(self):
        for _ in range(5):
            with self.assertRaises(AuthenticationError): self.auth.login('alice','wrong',now=100)
        with self.assertRaises(AuthenticationError): self.login()
        token = self.auth.login('alice','Alice-test-password-123',now=161)
        self.assertEqual(self.auth.resolve(token,now=162),self.alice)

    def test_expired_idle_and_absolute_session(self):
        token = self.login()
        with self.assertRaises(AuthenticationError): self.auth.resolve(token,now=130)
        token = self.login()
        for timestamp in (120,140,160,180,200): self.auth.resolve(token,now=timestamp)
        with self.assertRaises(AuthenticationError): self.auth.resolve(token,now=220)

    def test_logout_and_password_change_revoke_existing_sessions(self):
        token = self.login(); self.auth.logout(token)
        with self.assertRaises(AuthenticationError): self.auth.resolve(token,now=101)
        first, second = self.login(), self.login()
        self.auth.change_password(first,'Alice-test-password-123','New-test-password-987',now=101)
        for token in (first,second):
            with self.assertRaises(AuthenticationError): self.auth.resolve(token,now=102)
        token = self.auth.login('alice','New-test-password-987',now=103)
        self.assertEqual(self.auth.resolve(token,now=104),self.alice)

    def test_session_survives_service_restart(self):
        token = self.login()
        self.assertEqual(CustomerAuth(self.path,session_ttl=120,idle_ttl=30).resolve(token,now=101),self.alice)

    def test_malformed_or_forged_tokens_rejected(self):
        for token in (None,True,'short','x'*43,'../'+'a'*40):
            with self.assertRaises(AuthenticationError): self.auth.resolve(token,now=101)

    def test_bad_registration_or_duplicate_rejected(self):
        for name,password in [('a','long-enough-password'),('bad/name','long-enough-password'),('dave','short')]:
            with self.assertRaises(AuthenticationError): self.auth.register(name,password)
        with self.assertRaises(AuthenticationError): self.auth.register('ALICE','long-enough-password')

    def test_invalid_timestamp_and_future_session_rejected(self):
        token = self.login()
        for now in (float('nan'), True, float('inf')):
            with self.assertRaises(ValueError): self.auth.resolve(token,now=now)
        with self.assertRaises(AuthenticationError): self.auth.resolve(token,now=99)

    def test_disabled_account_cannot_login_or_use_session(self):
        token = self.login()
        with self.auth.db() as db: db.execute('UPDATE customers SET active=0 WHERE username=?',('alice',))
        with self.assertRaises(AuthenticationError): self.auth.resolve(token,now=101)
        with self.assertRaises(AuthenticationError): self.login()
