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

    def test_sign_out_and_second_login_do_not_show_previous_customer_sites(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'accounts.sqlite'
            auth=CustomerAuth(path)
            auth.register('alice','Alice-UI-test-password')
            auth.register('bob','Bob-UI-test-password')
            code=("from customer_account_ui import render_customer_account\n"
                  "from customer_auth import CustomerAuth\n"
                  "auth=CustomerAuth("+repr(str(path))+")\n"
                  "class OwnedSites:\n"
                  " def list_sites(self, token):\n"
                  "  return [{'origin':'https://'+auth.resolve(token).username+'.example'}]\n"
                  "render_customer_account(auth=auth,allow_registration=False,sites=OwnedSites())")
            app=AppTest.from_string(code).run()
            for username,password in [('alice','Alice-UI-test-password'),('bob','Bob-UI-test-password')]:
                app.text_input[0].set_value(username);app.text_input[1].set_value(password)
                app.button[0].click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.dataframe[0].value.iloc[0,0],'https://'+username+'.example')
                self.assertFalse(any('repair' in button.label.lower() for button in app.button))
                app.button(key='fg_account_logout').click().run()
                self.assertEqual(len(app.dataframe),0)
