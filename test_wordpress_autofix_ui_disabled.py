"""The disabled AutoFix UI must never solicit credentials or enable writes."""
import unittest
from unittest.mock import Mock, patch

from wordpress_autofix_ui import render_wordpress_autofix_ui


class DisabledAutoFixUITests(unittest.TestCase):
    def test_disabled_ui_never_requests_credentials(self):
        ui = Mock()
        result = render_wordpress_autofix_ui(st_module=ui)
        ui.text_input.assert_not_called()
        ui.form.assert_not_called()
        ui.form_submit_button.assert_not_called()
        self.assertFalse(result["remote_write_authorized"])
        self.assertFalse(result["changes_applied"])
        self.assertTrue(result["missing_requirements"])

    @patch("wordpress_autofix_ui.assess_remote_readiness")
    def test_unsafe_readiness_fails_closed(self, readiness):
        readiness.return_value = {
            "remote_write_authorized": True,
            "changes_applied": False,
        }
        with self.assertRaises(RuntimeError):
            render_wordpress_autofix_ui(st_module=Mock())


if __name__ == "__main__":
    unittest.main()
