"""UI recovery only against disposable state; no SMTP/provider access."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from customer_auth import CustomerAuth,AuthenticationError
from customer_recovery import AccountRecovery
from test_customer_recovery import CapturedDelivery


class RecoveryUITests(unittest.TestCase):
    def test_default_off_adds_no_recovery_widgets(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict('os.environ',{},clear=True):
            code='from customer_auth import CustomerAuth\nfrom customer_recovery_ui import render_account_recovery\nimport streamlit as st\nrender_account_recovery(st,CustomerAuth('+repr(str(Path(directory)/'auth.sqlite'))+'))'
            app=AppTest.from_string(code).run()
            self.assertFalse(app.exception);self.assertEqual(len(app.text_input),0);self.assertEqual(len(app.button),0)

    def test_verify_and_reset_forms_preserve_no_login_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'auth.sqlite';auth=CustomerAuth(path)
            auth.register('alice','Original-UI-password');session=auth.login('alice','Original-UI-password')
            recovery=AccountRecovery(auth,lambda _:b'k'*32,key_id='fixture',authorized=True);delivery=CapturedDelivery()
            recovery.request_verification(session,'Original-UI-password','alice@example.test');recovery.dispatch_once(delivery)
            code=('import streamlit as st\nfrom customer_auth import CustomerAuth\nfrom customer_recovery import AccountRecovery\n'
                'from customer_recovery_ui import render_account_recovery\n'
                'auth=CustomerAuth('+repr(str(path))+')\n'
                'service=AccountRecovery(auth,lambda _:b"k"*32,key_id="fixture",authorized=True)\n'
                'def clear():\n for key in list(st.session_state):\n  if str(key).startswith("fg_customer_"):del st.session_state[key]\n'
                'render_account_recovery(st,auth,service=service,clear_state=clear)')
            app=AppTest.from_string(code).run()
            def field(label):return next(item for item in app.text_input if item.label==label)
            def submit(label):next(item for item in app.button if item.label==label).click().run()
            field('Email verification code').set_value(delivery.messages[-1]['token']);submit('Verify recovery email')
            self.assertFalse(app.exception);self.assertEqual(len(app.success),1)
            field('Account username for recovery').set_value('alice');submit('Request password recovery code')
            recovery.dispatch_once(delivery)
            field('Password recovery code').set_value(delivery.messages[-1]['token'])
            field('New account password').set_value('Recovered-UI-password');field('Confirm new account password').set_value('Recovered-UI-password')
            app.session_state['fg_customer_plan']='old-private-plan'
            submit('Reset account password')
            self.assertFalse(app.exception);self.assertEqual(len(app.success),1)
            with self.assertRaises(KeyError):_=app.session_state['fg_customer_plan']
            with self.assertRaises(KeyError):_=app.session_state['fg_customer_session']
            with self.assertRaises(AuthenticationError):auth.resolve(session)
            self.assertEqual(auth.resolve(auth.login('alice','Recovered-UI-password')).username,'alice')
            from streamlit.proto.TextInput_pb2 import TextInput
            self.assertEqual(field('Password recovery code').proto.type,TextInput.PASSWORD)
