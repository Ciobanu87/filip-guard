import tempfile
from pathlib import Path
import unittest
from operations_guard_setup import initialize_read_only
from customer_auth import CustomerAuth


class ReadOnlySetupTests(unittest.TestCase):
    def env(self,root):return {'FG_CUSTOMER_AUTH_DB':str(root/'accounts.sqlite'),'FG_CUSTOMER_DATA_ROOT':str(root/'sites'),'FG_MONITOR_DB':str(root/'monitor.sqlite')}
    def test_read_only_bootstrap_needs_no_wordpress_storage_email_or_model_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);env=self.env(root)
            result=initialize_read_only(env);self.assertFalse(result['repairs_enabled']);self.assertEqual(result['network_requests'],0)
            auth=CustomerAuth(env['FG_CUSTOMER_AUTH_DB']);auth.register('owner','Owner-readonly-password')
            self.assertEqual(initialize_read_only(env)['accounts_created'],0)
            self.assertEqual(auth.resolve(auth.login('owner','Owner-readonly-password')).username,'owner')

    def test_missing_registry_in_nonempty_directory_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sites=root/'sites';sites.mkdir(mode=0o700);saved=sites/'important.bin';saved.write_bytes(b'existing')
            with self.assertRaises(ValueError):initialize_read_only(self.env(root))
            self.assertEqual(saved.read_bytes(),b'existing');self.assertFalse((sites/'sites.sqlite').exists())
