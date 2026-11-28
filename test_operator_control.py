import unittest
from unittest.mock import patch
from deployment.oracle_operator_control import run

class OperatorControlTests(unittest.TestCase):
    def test_nonroot_cannot_control_units(self):
        with patch('deployment.oracle_operator_control.os.geteuid',return_value=99),patch('deployment.oracle_operator_control.app_states') as states:
            with self.assertRaises(ValueError):run({})
            states.assert_not_called()
    def test_unknown_action_cannot_activate_anything(self):
        with patch('deployment.oracle_operator_control.os.geteuid',return_value=0),patch('deployment.oracle_operator_control.app_states') as states:
            with self.assertRaises(ValueError):run(dict(action='start-production',hashes={},free_plan_confirmed=True,email_channel_confirmed=True,external_down_seen=False))
            states.assert_not_called()
    def test_active_application_holds_independent_control_phase(self):
        with patch('deployment.oracle_operator_control.os.geteuid',return_value=0),patch('deployment.oracle_operator_control.app_states',return_value=['active']):
            with self.assertRaises(ValueError):run(dict(action='inspect',hashes={},free_plan_confirmed=True,email_channel_confirmed=True,external_down_seen=False))

if __name__=='__main__':unittest.main()
