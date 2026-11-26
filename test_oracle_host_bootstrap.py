import hashlib
import io
import json
from pathlib import Path
import tarfile
import unittest
from unittest.mock import patch

from deployment.oracle_host_bootstrap import archive_entries
from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command
import test_operations_oracle_ssh_probe as pinned_tests


class HostBootstrapSafetyTests(unittest.TestCase):
    def test_owner_confirmed_host_scope_cannot_activate_cloud_backup_ai_or_wrong_branch(self):
        data = json.loads(Path('deployment/oracle-host-setup-request.json').read_text())
        evidence = Path('deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
        env = {'FG_OCI_HOST': '92.5.89.125', 'FG_OCI_HOST_SETUP_AUTHORIZED': '1',
               'GITHUB_REF': 'refs/heads/filip-guard-development', 'GITHUB_REPOSITORY': 'Ciobanu87/filip-guard'}
        validate_authorization(data, evidence, env)
        for change in ({'external_backup_activation_authorized': True}, {'ai_calls_authorized': True},
                       {'new_cloud_resources_authorized': True}, {'ocpus': True}, {'boot_gb': 200},
                       {'owner_confirmed_only_these_resources': False}):
            with self.assertRaises(ValueError): validate_authorization({**data, **change}, evidence, env)
        with self.assertRaises(ValueError): validate_authorization(data, evidence + b'changed', env)
        with self.assertRaises(ValueError): validate_authorization(data, evidence, {**env, 'GITHUB_REF': 'refs/heads/main'})

    def archive(self, name, kind=tarfile.REGTYPE):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as output:
            for path in ('app.py', 'requirements.txt', 'operations_host_gate.py', name):
                member = tarfile.TarInfo(path); member.type = kind if path == name else tarfile.REGTYPE
                member.size = 1 if member.isreg() else 0
                if not member.isreg(): member.linkname = '/etc/ssh/sshd_config'
                output.addfile(member, io.BytesIO(b'x') if member.size else None)
        return stream.getvalue()

    def test_source_archive_rejects_traversal_absolute_paths_links_and_internal_environments(self):
        for name, kind in (('../escape.py', tarfile.REGTYPE), ('/etc/passwd', tarfile.REGTYPE),
                           ('safe/link', tarfile.SYMTYPE), ('safe/hard', tarfile.LNKTYPE),
                           ('.git/config', tarfile.REGTYPE), ('.venv/bin/python', tarfile.REGTYPE)):
            with self.subTest(name=name), self.assertRaises(ValueError): archive_entries(self.archive(name, kind))
        self.assertIn('app.py', archive_entries(self.archive('normal.py')))

    def test_read_only_authorization_cannot_send_a_write_payload(self):
        with patch('operations_oracle_ssh_probe.subprocess.run') as command:
            with self.assertRaises(ValueError):
                run_pinned_command('fixed-host-setup', {'FG_OCI_SSH_PROBE_AUTHORIZED': '1'},
                                   operation='host-setup', input_data=b'archive', timeout=900)
        command.assert_not_called()

    def test_mismatching_host_pin_blocks_setup_before_payload_or_key_use(self):
        fixture = pinned_tests.OracleSSHPreflightTests(); fixture.setUp()
        env = {**fixture.env, 'FG_OCI_HOST_SETUP_AUTHORIZED': '1', 'FG_OCI_HOST_ED25519_SHA256': 'SHA256:' + 'a' * 43}
        from types import SimpleNamespace
        calls = []
        def runner(args, **kwargs):
            calls.append((args, kwargs)); return SimpleNamespace(returncode=0, stdout=fixture.scan)
        with self.assertRaises(ValueError):
            run_pinned_command('fixed-host-setup', env, runner, operation='host-setup', input_data=b'archive', timeout=900)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('input', calls[0][1])


if __name__ == '__main__': unittest.main()
