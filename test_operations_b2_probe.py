from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import operations_b2_probe as probe
from test_application_state_backup import Store


class B2ProbeTests(unittest.TestCase):
    def test_encrypted_upload_and_recovery_without_source_database(self):
        raw=Store();store=probe.ProbeStore(raw)
        def recover(payload):
            with tempfile.TemporaryDirectory() as root:
                return probe.recover_probe(payload,probe.ProbeStore(raw),Path(root)/'independent')
        report=probe.run_probe(store,recover)
        self.assertTrue(report['external_roundtrip_verified']);self.assertFalse(report['production_backup_validated'])
        self.assertEqual(store.puts,1);self.assertEqual(report['groq_calls'],0)
        self.assertNotIn(b'SQLite format',next(iter(raw.objects.values())))
    def test_wrong_key_and_corrupt_backup_cannot_pass_recovery(self):
        for corrupt in (False,True):
            raw=Store()
            def recover(payload):
                if corrupt:
                    name=payload['manifest']['object_id'];raw.objects[name]=b'corrupt'
                else:payload['test_key']='eA=='
                with tempfile.TemporaryDirectory() as root:
                    return probe.recover_probe(payload,probe.ProbeStore(raw),Path(root)/'restored')
            with self.assertRaises(ValueError):probe.run_probe(probe.ProbeStore(raw),recover)
    def test_network_upload_failure_does_not_claim_verified(self):
        store=Store()
        with patch.object(store,'put',side_effect=ConnectionError('private-detail')):
            with self.assertRaises(ConnectionError):probe.run_probe(probe.ProbeStore(store),lambda x:{})
    def test_limits_prevent_multiple_or_oversized_uploads(self):
        store=probe.ProbeStore(Store())
        with self.assertRaises(ValueError):store.put('x',b'x'*65537)
        store.put('x',b'x')
        with self.assertRaises(ValueError):store.put('y',b'y')
    def test_missing_authorization_and_wrong_host_block_before_sdk(self):
        env={'FG_B2_VALIDATE_AUTHORIZED':'1','FG_B2_ENDPOINT':'https://s3.eu-central-003.backblazeb2.com',
             'FG_B2_BUCKET':'synthetic-test-bucket','FG_B2_KEY_ID':'synthetic','FG_B2_APPLICATION_KEY':'synthetic-secret'}
        for changed in ({'FG_B2_VALIDATE_AUTHORIZED':'0'},{'FG_B2_ENDPOINT':'https://attacker.test'}, {'FG_B2_KEY_ID':''}):
            with patch('operations_b2_probe.configured_s3_store') as sdk,self.assertRaises(ValueError):probe.configured_probe_store({**env,**changed})
            sdk.assert_not_called()
    def test_cli_errors_never_echo_credentials(self):
        out=StringIO()
        with patch('operations_b2_probe.configured_probe_store',side_effect=ValueError('SENSITIVE')),redirect_stdout(out):
            self.assertEqual(probe.main(['run']),1)
        self.assertNotIn('SENSITIVE',out.getvalue());self.assertNotIn('verified": true',out.getvalue())
