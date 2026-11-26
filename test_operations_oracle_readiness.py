"""Guard the fixed, inactive-only unit preparation transaction."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
from deployment import oracle_operations_readiness as readiness


class HeldUnitPreparationTests(unittest.TestCase):
    def request(self):
        units = {name: (Path('deployment/oracle-prepared') / (name + '.example')).read_text()
                 for name in readiness.UNITS}
        previous = {name: hashlib.sha256(b'installed-baseline').hexdigest() for name in units}
        return {'units': units, 'previous_sha256': previous}

    def test_unexpected_unit_cannot_be_written(self):
        data = self.request(); data['units']['unrelated.service'] = 'ignored'
        with patch.object(readiness, 'atomic') as write:
            with self.assertRaises(ValueError): readiness.prepare_units(data)
            write.assert_not_called()

    def test_modified_host_unit_is_not_overwritten(self):
        with patch.object(readiness, 'current_unit', return_value=b'local administrator change'), patch.object(readiness, 'atomic') as write:
            with self.assertRaises(ValueError): readiness.prepare_units(self.request())
            write.assert_not_called()

    def test_missing_activation_gate_cannot_be_installed(self):
        data = self.request(); name = sorted(data['units'])[0]
        data['units'][name] = data['units'][name].replace('ConditionPathExists=', 'RemovedCondition=')
        with patch.object(readiness, 'current_unit', return_value=b'installed-baseline'), patch.object(readiness, 'atomic') as write:
            with self.assertRaises(ValueError): readiness.prepare_units(data)
            write.assert_not_called()

    def test_valid_transaction_only_verifies_and_reloads(self):
        with patch.object(readiness, 'current_unit', return_value=b'installed-baseline'), patch.object(readiness, 'atomic') as write, patch.object(readiness, 'call') as run:
            readiness.prepare_units(self.request())
            self.assertEqual(write.call_count, 2)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[0][:2], ['/usr/bin/systemd-analyze', 'verify'])
            self.assertEqual(run.call_args_list[1].args[0], ['/usr/bin/systemctl', 'daemon-reload'])

    def test_failed_verification_rolls_back_both_units(self):
        with patch.object(readiness, 'current_unit', return_value=b'installed-baseline'), patch.object(readiness, 'atomic') as write, patch.object(readiness, 'call', side_effect=[RuntimeError('fixture'), None]) as run:
            with self.assertRaises(RuntimeError): readiness.prepare_units(self.request())
            self.assertEqual(write.call_count, 4)
            self.assertTrue(all(c.args[1] == b'installed-baseline' for c in write.call_args_list[2:]))
            self.assertEqual(run.call_args_list[-1].args[0], ['/usr/bin/systemctl', 'daemon-reload'])


if __name__ == '__main__': unittest.main()
