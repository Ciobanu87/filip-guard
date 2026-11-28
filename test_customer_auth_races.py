"""A session revoked after initial validation must not change credentials."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from customer_auth import CustomerAuth,AuthenticationError


class PasswordChangeRaceTests(unittest.TestCase):
    def test_logout_between_session_resolution_and_password_transaction_blocks_change(self):
        with tempfile.TemporaryDirectory() as directory:
            auth=CustomerAuth(Path(directory)/'auth.sqlite');auth.register('alice','Original-account-password')
            token=auth.login('alice','Original-account-password',now=100);resolve=auth.resolve
            def revoked(*args,**kwargs):
                principal=resolve(*args,**kwargs);auth.logout(token);return principal
            with patch.object(auth,'resolve',side_effect=revoked):
                with self.assertRaises(AuthenticationError):auth.change_password(token,'Original-account-password','Unexpected-password-change',now=101)
            auth.login('alice','Original-account-password',now=102)
