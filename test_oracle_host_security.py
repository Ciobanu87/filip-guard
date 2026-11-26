import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import deployment.oracle_host_security as security
import operations_oracle_security as driver


class HostSecurityTests(unittest.TestCase):
    def test_failed_effective_policy_restores_exact_original_and_cancels_rollback_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config = root / 'sshd_config'; config.write_bytes(b'# original\nPubkeyAuthentication yes\n')
            before = config.read_bytes(); recovery = root / 'recovery'
            with patch.object(security, 'CONFIG', config), patch.object(security, 'RECOVERY', recovery), \
                 patch.object(security, 'private_regular'), patch.object(security, 'call') as command, \
                 patch.object(security, 'verified', return_value=False):
                with self.assertRaises(ValueError): security.apply('203.0.113.2 50000 10.0.0.2 22')
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual((recovery / 'sshd_config.before').read_bytes(), before)
            self.assertEqual(json.loads((recovery / 'pending.json').read_text())['status'], 'rolled-back')
            self.assertTrue(any(call.args[0] == ['/usr/bin/systemctl', 'stop', security.TIMER] for call in command.call_args_list))

    def test_actual_connection_context_is_required_for_effective_root_and_opc_checks(self):
        with patch.object(security, 'call', return_value=SimpleNamespace(stdout='pubkeyauthentication yes\n')) as command:
            result = security.settings('203.0.113.2 50000 10.0.0.2 22', 'opc')
            self.assertEqual(result['pubkeyauthentication'], 'yes')
            self.assertIn('user=opc,host=203.0.113.2,addr=203.0.113.2,laddr=10.0.0.2,lport=22', command.call_args.args[0])
            for invalid in ('', 'not-an-ip 50000 10.0.0.2 22', '203.0.113.2 50000 10.0.0.2 nope'):
                with self.assertRaises(ValueError): security.settings(invalid, 'root')

    def test_failed_second_pinned_connection_prevents_reboot(self):
        with patch.object(driver, 'validate_authorization'), patch.object(driver, 'action') as action, \
             patch('sys.stdout'):
            action.side_effect = [{'status': 'ssh-hardened-pending-second-connection'}, ConnectionError('failed')]
            self.assertEqual(driver.main(), 1)
        self.assertEqual([call.args[0] for call in action.call_args_list], ['apply', 'confirm'])

    def test_reboot_validation_never_passes_without_actual_boot_change_and_saved_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / 'receipt.json'
            import hashlib
            current = hashlib.sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest()
            receipt.write_text(json.dumps({'boot_id_sha256': current}))
            with patch.object(security, 'confirm'), patch.object(security, 'private_regular'), \
                 patch.object(security, 'RECEIPT', receipt):
                with self.assertRaises(ValueError): security.validate('unused mocked connection')


if __name__ == '__main__': unittest.main()
