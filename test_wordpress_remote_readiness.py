import unittest
from dataclasses import replace
from unittest.mock import patch

from wordpress_remote_readiness import (
    RemoteReadinessEvidence, assess_remote_readiness, _CHECKS,
)


class ReadinessTests(unittest.TestCase):
    def test_default_blocks_every_requirement(self):
        report = assess_remote_readiness()
        self.assertEqual(report['missing_requirements'], _CHECKS)
        self.assertFalse(report['remote_write_authorized'])

    def test_rejects_client_dictionary(self):
        with self.assertRaises(TypeError):
            assess_remote_readiness(dict.fromkeys(_CHECKS, True))

    def test_rejects_boolean(self):
        with self.assertRaises(TypeError):
            assess_remote_readiness(True)

    def test_all_diagnostics_still_do_not_enable_writes(self):
        evidence = RemoteReadinessEvidence(**dict.fromkeys(_CHECKS, True))
        report = assess_remote_readiness(evidence)
        self.assertTrue(report['diagnostic_checks_complete'])
        self.assertFalse(report['remote_write_authorized'])
        self.assertFalse(report['changes_applied'])

    def test_truthy_values_not_accepted(self):
        evidence = replace(RemoteReadinessEvidence(), rollback_tested=1)
        self.assertIn('rollback_tested', assess_remote_readiness(evidence)['missing_requirements'])

    def test_one_missing_blocks_completion(self):
        all_true = RemoteReadinessEvidence(**dict.fromkeys(_CHECKS, True))
        for field in _CHECKS:
            with self.subTest(field=field):
                report = assess_remote_readiness(replace(all_true, **{field: False}))
                self.assertEqual(report['missing_requirements'], (field,))

    def test_no_network(self):
        with patch('socket.create_connection') as connect:
            assess_remote_readiness()
            connect.assert_not_called()

    def test_result_is_not_mutable_evidence(self):
        report = assess_remote_readiness()
        report['remote_write_authorized'] = True
        self.assertFalse(assess_remote_readiness()['remote_write_authorized'])


if __name__ == '__main__':
    unittest.main()
