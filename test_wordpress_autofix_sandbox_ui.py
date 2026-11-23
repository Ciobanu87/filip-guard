import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class SandboxUITests(unittest.TestCase):
    def app(self):
        return AppTest.from_string('from wordpress_autofix_sandbox_ui import render_autofix_sandbox\nrender_autofix_sandbox()').run()

    def test_initial_state_does_not_request_credentials_or_create_fixture(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.text_input), 0)
        self.assertEqual(len(app.text_area), 0)
        self.assertEqual(len(app.button), 0)

    def test_full_preview_explicit_approval_backup_apply_verify_without_network(self):
        with patch('socket.create_connection') as network:
            app = self.app()
            app.checkbox(key='fg_autofix_open').check().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.text_input), 0)
            app.button(key='fg_autofix_prepare').click().run()
            self.assertFalse(app.exception)
            apply_button = next(button for button in app.button if button.label == 'Apply approved local repair')
            self.assertTrue(apply_button.disabled)
            self.assertTrue(any(code.language == 'diff' for code in app.code))
            approve = next(box for box in app.checkbox if box.label == 'I approve this exact local test change')
            approve.check().run()
            apply_button = next(button for button in app.button if button.label == 'Apply approved local repair')
            self.assertFalse(apply_button.disabled)
            apply_button.click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('applied and verified' in item.value for item in app.success))
            context = app.session_state['fg_autofix_local_context']
            result = context['result']
            self.assertEqual(result['status'], 'applied')
            self.assertEqual(context['engine'].backups.get_backup(result['backup_id'])['content'],
                             '<p>Original test content.</p>\n')
            # A new operation always requires a fresh approval checkbox.
            app.text_area(key='fg_autofix_proposed').set_value('<p>Another test.</p>\n').run()
            app.button(key='fg_autofix_prepare').click().run()
            apply_button = next(button for button in app.button if button.label == 'Apply approved local repair')
            self.assertTrue(apply_button.disabled)
            network.assert_not_called()
