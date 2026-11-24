import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from advisor_credentials import SessionCredential
from test_advisor_groq import KEY
import colab_validate_app_ai as loader


class ColabAppProbeTests(unittest.TestCase):
    def test_existing_memory_key_is_reused_without_secret_rpc_or_key_change(self):
        previous=SessionCredential(KEY);reader=Mock()
        current=loader.session_credential({'credential':previous},reader)
        reader.assert_not_called();self.assertEqual(current(),KEY)
        current.close();self.assertEqual(previous(),KEY);self.assertNotIn(KEY,repr(current))

    def test_missing_history_blocks_before_clone_install_or_provider_access(self):
        with tempfile.TemporaryDirectory() as root,patch.object(loader.subprocess,'run') as command:
            missing=Path(root)/'absent.sqlite'
            with self.assertRaises(RuntimeError):loader.run({'ledger':missing})
            command.assert_not_called();self.assertFalse(missing.exists())

    def test_all_nine_prior_cases_are_required_without_running_any_quality_case(self):
        from advisor_quality_evaluation import quality_cases
        completed={case['name']:{} for case in quality_cases()}
        with patch('advisor_quality_evaluation._completed_fixtures',return_value=completed):
            self.assertEqual(loader.require_completed_quality(object()),9)
        completed.pop('heading-context-en')
        with patch('advisor_quality_evaluation._completed_fixtures',return_value=completed):
            with self.assertRaises(RuntimeError):loader.require_completed_quality(object())
