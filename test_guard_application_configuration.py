import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from guard_application_configuration import configured_guard_application,_private_file

class UnifiedConfigurationTests(unittest.TestCase):
    def test_disabled_and_incomplete_configuration_never_enable_repairs(self):
        with patch.dict(os.environ,{},clear=True):self.assertIsNone(configured_guard_application())
        with patch.dict(os.environ,{'FG_GUARD_TEST_UI':'1'},clear=True):self.assertIsNone(configured_guard_application())
    def test_public_origin_is_rejected_before_loading_secrets(self):
        names=('FG_CUSTOMER_AUTH_DB','FG_CUSTOMER_DATA_ROOT','FG_MONITOR_DB','FG_GUARD_MASTER_KEY_FILE','FG_GUARD_S3_CREDENTIALS_FILE','FG_GUARD_S3_ENDPOINT','FG_GUARD_S3_BUCKET')
        values={name:'unused' for name in names};values.update(FG_GUARD_TEST_UI='1',FG_GUARD_TEST_ORIGINS='["https://example.com"]')
        with patch.dict(os.environ,values,clear=True),self.assertRaises(ValueError):configured_guard_application()
    def test_private_key_permissions_size_and_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'key';p.write_bytes(b'k'*32);p.chmod(0o600)
            self.assertEqual(_private_file(p,32),b'k'*32)
            p.chmod(0o644)
            with self.assertRaises(ValueError):_private_file(p,32)
            p.chmod(0o600)
            with self.assertRaises(ValueError):_private_file(p,31)
            link=Path(root)/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):_private_file(link,32)
