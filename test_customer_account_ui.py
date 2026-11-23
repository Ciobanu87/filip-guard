from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from customer_auth import CustomerAuth, AuthenticationError


class CustomerAccountUITests(unittest.TestCase):
    def test_unconfigured_does_not_request_credentials(self):
        with patch.dict('os.environ',{},clear=True):
            app=AppTest.from_string('from customer_account_ui import render_customer_account\nrender_customer_account()').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.text_input),0)
        self.assertEqual(len(app.button),0)

    def test_login_logout_does_not_retain_password_or_customer_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'accounts.sqlite'
            auth=CustomerAuth(path); auth.register('alice','UI-test-password-123')
            code='from customer_account_ui import render_customer_account\nfrom customer_auth import CustomerAuth\nrender_customer_account(auth=CustomerAuth('+repr(str(path))+'), allow_registration=False)'
            app=AppTest.from_string(code).run()
            app.text_input[0].set_value('alice')
            app.text_input[1].set_value('UI-test-password-123')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            token=app.session_state['fg_customer_session']
            self.assertEqual(auth.resolve(token).username,'alice')
            self.assertEqual(len(app.text_input),0)
            app.session_state['fg_customer_plan']='synthetic-private-plan'
            app.button(key='fg_account_logout').click().run()
            self.assertFalse(app.exception)
            with self.assertRaises(KeyError): _=app.session_state['fg_customer_plan']
            with self.assertRaises(AuthenticationError): auth.resolve(token)
