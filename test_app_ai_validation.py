import json
from pathlib import Path
import tempfile
import unittest
from contextual_advisor import ContextualAdvisor
from test_contextual_advisor import SimulatedProvider
from validate_app_ai import validate_authenticated_ui,prior_success,CASE_ID,REQUIRED_UI_CHECKS


class AppAIProbeTests(unittest.TestCase):
    def test_actual_ui_login_scan_advice_language_switch_and_reload_use_one_simulated_call(self):
        with tempfile.TemporaryDirectory() as root:
            provider=SimulatedProvider();engine=ContextualAdvisor(Path(root)/'ledger.sqlite',provider)
            report=validate_authenticated_ui(engine)
        self.assertTrue(report['accepted'],report)
        self.assertEqual(provider.calls,1)
        self.assertFalse(report['real_inference_executed']);self.assertFalse(report['quality_validated'])
        self.assertTrue(report['checks']['no_repair_authority']);self.assertTrue(report['checks']['no_wordpress_change'])

    def test_live_mode_requires_real_reviewed_adapter_before_any_fixture_or_call(self):
        with tempfile.TemporaryDirectory() as root:
            provider=SimulatedProvider();engine=ContextualAdvisor(Path(root)/'ledger.sqlite',provider)
            with self.assertRaises(ValueError):validate_authenticated_ui(engine,live=True)
            self.assertEqual(provider.calls,0)

    def test_private_success_receipt_is_historical_and_cannot_claim_new_inference(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'receipt.json'
            self.assertIsNone(prior_success(path,model='test'))
            path.write_text(json.dumps({'case':CASE_ID,'model':'test','accepted':True,'real_inference_executed':True,'mode':'live-cloud','checks':{key:True for key in REQUIRED_UI_CHECKS},'new_provider_responses':1}));path.chmod(0o600)
            replay=prior_success(path,model='test')
            self.assertFalse(replay['real_inference_executed']);self.assertEqual(replay['new_provider_responses'],0)
            self.assertTrue(replay['prior_live_verified'])
            with self.assertRaises(ValueError):prior_success(path,model='different-model')
