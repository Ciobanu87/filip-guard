"""Offline launch guards; never connect to Oracle or install dependencies."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import operations_oracle_autofix_wordpress as launcher
from deployment import oracle_autofix_wordpress_pilot as pilot


class PrivatePilotGuards(unittest.TestCase):
    def test_rejects_non_root_before_mutation(self):
        helper=Path('deployment/oracle_autofix_native_pilot.py').read_text()
        with patch.object(pilot.os,'geteuid',return_value=1000),patch.object(pilot.tempfile,'TemporaryDirectory') as temporary:
            with self.assertRaises(RuntimeError):pilot.run(b'',helper)
            temporary.assert_not_called()

    def test_all_selected_cases_exist_without_importing_live_runner(self):
        import ast
        tree=ast.parse(Path('tests/real_wordpress/run.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RealWordPressTests')
        methods={n.name for n in cls.body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(len(pilot.TESTS),9)
        self.assertTrue(set(pilot.TESTS)<=methods)

    def test_launcher_uses_pinned_source_and_requires_pass(self):
        archive=b'test archive'
        report={'status':'private-wordpress-pilot-passed','measured':{'tests':9}}
        with patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],0,archive)),patch.object(launcher,'run_pinned_command',return_value=json.dumps(report)) as ssh,patch('builtins.print'):
            self.assertEqual(launcher.main(),0)
        args=ssh.call_args
        self.assertEqual(args.kwargs['operation'],'host-setup')
        self.assertEqual(args.kwargs['input_data'],archive)
        self.assertEqual(args.kwargs['timeout'],900)
        self.assertTrue(args.args[0].startswith('sudo -n python3 -c '))

    def test_failed_or_unknown_report_cannot_be_success(self):
        for status in ('private-wordpress-pilot-held-or-failed','private-wordpress-pilot-failed','unexpected'):
            with self.subTest(status=status),patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'archive')),patch.object(launcher,'run_pinned_command',return_value=json.dumps({'status':status})),patch('builtins.print'):
                self.assertEqual(launcher.main(),1)

    def test_ssh_failure_is_redacted(self):
        with patch.object(launcher.subprocess,'run',side_effect=RuntimeError('sensitive-output')),patch('builtins.print') as output:
            self.assertEqual(launcher.main(),1)
            self.assertNotIn('sensitive-output',output.call_args.args[0])


if __name__=='__main__':unittest.main()
